"""HfStudioClient — HTTP client for the hf-studio render service.

hf-studio is a separate service (its own repo, its own process, its own port).
This module is only a transport: it never imports HyperFrames, never touches
bases or deltas, and owns no rendering logic. Keeping the boundary this hard is
what lets the two codebases evolve independently.

What it does own is the awkward part of talking to it: hf-studio renders one job
at a time and answers 429 while busy, so a caller has to poll rather than block,
and a render that outlives the job that started it must still be collectable.

    with HfStudioClient() as hf:
        project = hf.create_project(base_id="quote-card", name="SS26 teaser")
        hf.set_delta(project["projectId"], {"var.accent": "#0044ff"})
        out = hf.render_and_wait(project["projectId"])

CLI:
    python -m src.Workflows.hf_client health
    python -m src.Workflows.hf_client bases
    python -m src.Workflows.hf_client render --base quote-card --set accent=#0044ff
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:4600/api/v1"
ROOT = Path(__file__).resolve().parents[2]

EventFn = Callable[[str, str, Optional[dict]], None]

#: Render jobs are polled rather than blocked on. A quote card takes ~30 s, a
#: longer composition a few minutes; the cap is a runaway guard, not a target.
DEFAULT_RENDER_TIMEOUT_S = 600.0


class HfStudioError(RuntimeError):
    """An error the service reported in its standard envelope."""

    def __init__(self, status: int, code: str, message: str, hint: Optional[str] = None):
        super().__init__(f"[{code}] {message}" + (f" — {hint}" if hint else ""))
        self.status = status
        self.code = code
        self.message = message
        self.hint = hint

    @property
    def retryable(self) -> bool:
        """429 means the single render slot is busy; the caller should wait and retry."""
        return self.status == 429


class HfStudioClient:
    def __init__(self, base_url: Optional[str] = None, timeout_s: float = 30.0):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout_s = timeout_s
        self._session = requests.Session()

    # -- plumbing ------------------------------------------------------------ #

    def __enter__(self) -> "HfStudioClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()

    def _request(self, method: str, path: str, *, json_body: Optional[dict] = None) -> dict:
        url = f"{self.base_url}{path}"
        try:
            res = self._session.request(method, url, json=json_body, timeout=self.timeout_s)
        except requests.RequestException as exc:
            raise HfStudioError(
                0,
                "hf_unreachable",
                f"không kết nối được hf-studio tại {self.base_url}",
                hint=f"khởi động service: cd services/hf-studio && npm start ({exc.__class__.__name__})",
            ) from exc

        payload = _parse_json(res)
        if res.status_code >= 400 or payload.get("ok") is False:
            err = payload.get("error") or {}
            raise HfStudioError(
                res.status_code,
                str(err.get("code") or "http_error"),
                str(err.get("message") or f"HTTP {res.status_code}"),
                err.get("hint"),
            )
        return payload

    # -- reads --------------------------------------------------------------- #

    def health(self) -> dict:
        return self._request("GET", "/health")

    def list_bases(self) -> list[dict]:
        return self._request("GET", "/bases").get("bases", [])

    def base_schema(self, base_id: str) -> dict:
        """Variables plus the element index — everything an editor needs."""
        return self._request("GET", f"/bases/{base_id}/schema")

    def get_project(self, project_id: str) -> dict:
        return self._request("GET", f"/projects/{project_id}")

    # -- writes -------------------------------------------------------------- #

    def create_project(self, base_id: str, name: str) -> dict:
        body = self._request("POST", "/projects", json_body={"baseId": base_id, "name": name})
        return body["project"]

    def set_delta(self, project_id: str, delta: dict) -> dict:
        """Replace the project's delta. Variable keys are `var.<id>`, not bare ids."""
        return self._request("PUT", f"/projects/{project_id}/delta", json_body={"delta": delta})

    def delete_project(self, project_id: str) -> bool:
        return bool(self._request("DELETE", f"/projects/{project_id}").get("ok"))

    # -- render -------------------------------------------------------------- #

    def start_render(self, project_id: str, variables: Optional[dict] = None) -> str:
        """Kick off a render and return the job id.

        Raises `HfStudioError` with `retryable=True` when the single render slot
        is busy — the service deliberately does not queue, so the caller decides
        how long to wait rather than the request hanging.
        """
        body: dict = {}
        if variables:
            body["variables"] = variables
        payload = self._request("POST", f"/projects/{project_id}/render", json_body=body)
        return str(payload["jobId"])

    def get_job(self, job_id: str) -> dict:
        return self._request("GET", f"/jobs/{job_id}").get("job", {})

    def wait_for_job(
        self,
        job_id: str,
        *,
        poll_s: float = 2.0,
        timeout_s: float = DEFAULT_RENDER_TIMEOUT_S,
        on_event: Optional[EventFn] = None,
        abort: Optional[object] = None,
    ) -> dict:
        """Poll until the job leaves `running`/`queued`.

        `abort` is anything with `.is_set()` (a `threading.Event`), which lets a
        job manager stop the wait without killing the render — hf-studio keeps
        working and the output stays collectable.
        """
        started = time.monotonic()
        last_progress = -1.0
        last_message = ""

        while True:
            if abort is not None and getattr(abort, "is_set", lambda: False)():
                raise HfStudioError(0, "cancelled", "đã dừng chờ render theo yêu cầu")

            job = self.get_job(job_id)
            status = job.get("status")
            progress = float(job.get("progress") or 0)
            message = str(job.get("message") or "")

            if on_event and (abs(progress - last_progress) >= 5 or message != last_message):
                on_event("progress", f"{progress:.0f}% {message}".strip(), {"jobId": job_id})
                last_progress, last_message = progress, message

            if status == "succeeded":
                return job
            if status in ("failed", "cancelled"):
                error = job.get("error") or {}
                raise HfStudioError(
                    0,
                    str(error.get("code") or status),
                    str(error.get("message") or f"render {status}"),
                    error.get("hint"),
                )

            if time.monotonic() - started > timeout_s:
                raise HfStudioError(
                    0,
                    "render_timeout",
                    f"render {job_id} chưa xong sau {timeout_s:.0f}s",
                    hint="kiểm tra lại thủ công: GET /api/v1/jobs/" + job_id,
                )

            time.sleep(poll_s)

    def download(self, url_or_path: str, dest: Path) -> Path:
        """Fetch a finished render to `dest`.

        Accepts the absolute public URL the service reports as well as a bare
        path, so a caller never has to know how the service names its outputs.
        """
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            url = url_or_path
        else:
            url = f"{self.base_url.rsplit('/api/v1', 1)[0]}{url_or_path}"

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)

        with self._session.get(url, stream=True, timeout=self.timeout_s) as res:
            if res.status_code >= 400:
                raise HfStudioError(res.status_code, "download_failed", f"tải render thất bại: {url}")
            tmp = dest.with_suffix(dest.suffix + ".part")
            with tmp.open("wb") as fh:
                for chunk in res.iter_content(chunk_size=1 << 20):
                    if chunk:
                        fh.write(chunk)
            tmp.replace(dest)
        return dest

    def render_and_wait(
        self,
        project_id: str,
        dest: Optional[Path] = None,
        *,
        variables: Optional[dict] = None,
        on_event: Optional[EventFn] = None,
        abort: Optional[object] = None,
        busy_retry_s: float = 5.0,
        busy_timeout_s: float = 120.0,
    ) -> Path:
        """Start a render, wait for it, and download the output.

        Only a 429 is retried: it means another render holds the slot. A genuine
        failure is raised immediately, because retrying it would just waste
        another minute on the same broken composition.
        """
        deadline = time.monotonic() + busy_timeout_s
        while True:
            try:
                job_id = self.start_render(project_id, variables=variables)
                break
            except HfStudioError as exc:
                if not exc.retryable or time.monotonic() >= deadline:
                    raise
                if on_event:
                    on_event("wait", "hf-studio đang render job khác, chờ…", {"retryIn": busy_retry_s})
                time.sleep(busy_retry_s)

        job = self.wait_for_job(job_id, on_event=on_event, abort=abort)

        outputs = job.get("outputs") or []
        if not outputs:
            raise HfStudioError(0, "no_output", f"job {job_id} kết thúc nhưng không có output")
        first = outputs[0]

        if dest is None:
            return Path(str(first.get("path") or ""))
        return self.download(str(first.get("url") or first.get("path")), Path(dest))


def _parse_json(res: requests.Response) -> dict:
    try:
        parsed = res.json()
    except ValueError:
        return {"ok": False, "error": {"code": "invalid_response", "message": res.text[:300]}}
    return parsed if isinstance(parsed, dict) else {"ok": True, "data": parsed}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="hf_client", description="hf-studio client")
    ap.add_argument("--url", default=None, help=f"service base URL (default {DEFAULT_BASE_URL})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="is the service up?")
    sub.add_parser("bases", help="list bases with their declared variables")

    p_schema = sub.add_parser("schema", help="variables + element index for one base")
    p_schema.add_argument("base")

    p_render = sub.add_parser("render", help="render a base into out/hf/<base>.mp4")
    p_render.add_argument("--base", required=True)
    p_render.add_argument("--name", default=None, help="project name (default: base id)")
    p_render.add_argument("--set", action="append", default=[], metavar="ID=VALUE",
                          help="variable override, repeatable (e.g. --set accent=#0044ff)")
    p_render.add_argument("--project", default=None, help="reuse an existing project id")
    p_render.add_argument("--keep", action="store_true", help="keep the project after rendering")
    p_render.add_argument("--out", default=None, help="output file path")

    args = ap.parse_args(argv)

    with HfStudioClient(args.url) as hf:
        try:
            if args.cmd == "health":
                print(hf.health())
                return 0
            if args.cmd == "bases":
                for b in hf.list_bases():
                    ids = ", ".join(v["id"] for v in b.get("variables", []))
                    print(f"{b['baseId']:<24} {b['width']}x{b['height']}  vars: {ids}")
                return 0
            if args.cmd == "schema":
                s = hf.base_schema(args.base)
                for v in s.get("variables", []):
                    print(f"  var  {v['id']:<20} {v['type']:<8} default={v.get('default')!r}")
                for e in s.get("elements", []):
                    print(f"  el   {e['hfId']:<10} {e['tag']:<6} id={e.get('id')!r}")
                return 0
            if args.cmd == "render":
                upgraded = _parse_variables(args.set)

                project_id = args.project
                created = False
                if project_id is None:
                    project = hf.create_project(args.base, args.name or args.base)
                    project_id = project["projectId"]
                    created = True

                if upgraded:
                    hf.set_delta(project_id, upgraded)

                dest = Path(args.out) if args.out else ROOT / "out" / "hf" / f"{args.base}.mp4"
                print(f"project {project_id} -> {dest}")
                hf.render_and_wait(
                    project_id,
                    dest,
                    on_event=lambda kind, msg, _data: print(f"  {kind}: {msg}"),
                )
                print(f"done: {dest}")

                if created and not args.keep:
                    hf.delete_project(project_id)
                return 0
        except HfStudioError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    return 1


def _parse_variables(pairs: list[str]) -> dict:
    """`["accent=#0044ff", "scale=1.2"]` -> `{"var.accent": ..., "var.scale": 1.2}`.

    Values are parsed as JSON when they can be (`1.2`, `true`, `"x"`) so a number
    stays a number; anything else is taken as a string, which is what a colour or
    a headline wants.
    """
    out: dict = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--set expects ID=VALUE, got {pair!r}")
        key, _, raw = pair.partition("=")
        key = key.strip()
        raw = raw.strip()
        try:
            value = json.loads(raw)
        except ValueError:
            value = raw
        out[f"var.{key}"] = value
    return out


if __name__ == "__main__":
    raise SystemExit(_main())
