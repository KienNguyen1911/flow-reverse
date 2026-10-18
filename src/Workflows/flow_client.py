"""FlowClient — high-level Google Flow API client + CLI (production, Python).

Wraps the proven Bridge Mode (docs/phase4_report.md §3, api_specs §7.5):
  with FlowClient() as client:
      client.status()
      client.list_projects()                      # UpteDb   — 0 credit
      client.create_project("Batch 18/10")        # jHPbke   — 0 credit
      client.generate_image(project, prompt=...)  # ogiZ0b   — ~1 credit if accepted

Resilience layer (AGENTS.md §4):
  - Humanized pacing: Gaussian jitter between UI actions.
  - Exponential backoff on technical retries (download, poll).
  - Circuit breaker: 401/403 -> 30 min cooldown, 429 -> 10 min cooldown,
    3 consecutive anti-abuse rejections -> 30 min cooldown (persisted in
    out/bridge_state.json); anti-abuse rejections retried with backoff (max N).

CLI:
  python -m src.Workflows.flow_client status
  python -m src.Workflows.flow_client list-projects
  python -m src.Workflows.flow_client create-project --title "Batch 18/10"
  python -m src.Workflows.flow_client generate --project <uuid> --prompt "..." [--dry-run] [--yes]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import requests

from ..Bridge.flow_bridge import (
    DEFAULT_CDP_URL,
    BridgeError,
    FlowBridge,
    HttpStatusError,
    build_capture_fire_url,
    build_rpc_url_from_template,
    describe_reject,
    extract_app_reqid,
    find_signed_urls,
    jitter,
    parse_app_capture,
    parse_batchexecute_text,
    parse_captured_args,
)
from .flow_models import (
    ASPECT_DEFAULT,
    BridgeStatus,
    CapturedRequestInfo,
    GeneratedImage,
    GenerationResult,
    ProjectInfo,
    ReferenceTemplate,
    UUID_RE,
    build_args_from_template,
    build_create_project_args,
    build_image_args,
    build_uptedb_args,
    captured_args_has_reference,
    encode_batchexecute_form,
    find_uuid_candidates,
    generate_seed,
    mask_template_token,
    new_uuids,
    parse_project_ref,
    parse_uptedb_projects,
    validate_seed,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "out" / "playground"
DEFAULT_BREAKER = ROOT / "out" / "bridge_state.json"

EventFn = Callable[[str, str, Optional[dict]], None]


# --------------------------------------------------------------------------- #
# Circuit breaker (persisted)
# --------------------------------------------------------------------------- #

class CircuitOpenError(RuntimeError):
    def __init__(self, remaining_s: float, reason: str):
        super().__init__(f"Circuit breaker đang mở: {reason} (còn {remaining_s / 60:.1f} phút)")
        self.remaining_s = remaining_s
        self.reason = reason


class CircuitBreaker:
    """Profile cooldown guard persisted to disk (survives restarts)."""

    def __init__(self, path: Path = DEFAULT_BREAKER):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.state = {
            "cooldown_until_ms": 0,
            "cooldown_reason": "",
            "consecutive_anti_abuse": 0,
            "last_anti_abuse_ms": 0,
            "total_accepted": 0,
            "total_rejected": 0,
        }
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.state.update({k: data[k] for k in data if k in self.state})
        except Exception:  # noqa: BLE001
            pass

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    # -- API ---------------------------------------------------------------- #

    def snapshot(self) -> dict:
        with self._lock:
            s = dict(self.state)
        now = int(time.time() * 1000)
        s["cooldown_remaining_s"] = max(0.0, (s["cooldown_until_ms"] - now) / 1000.0)
        return s

    def check(self) -> None:
        s = self.snapshot()
        if s["cooldown_remaining_s"] > 0:
            raise CircuitOpenError(s["cooldown_remaining_s"], s["cooldown_reason"] or "cooldown")

    def trip(self, seconds: float, reason: str) -> None:
        with self._lock:
            self.state["cooldown_until_ms"] = int(time.time() * 1000 + seconds * 1000)
            self.state["cooldown_reason"] = reason
            self._save()

    def clear_cooldown(self) -> None:
        with self._lock:
            self.state["cooldown_until_ms"] = 0
            self.state["cooldown_reason"] = ""
            self._save()

    def record_anti_abuse(self) -> int:
        with self._lock:
            self.state["consecutive_anti_abuse"] = int(self.state.get("consecutive_anti_abuse", 0)) + 1
            self.state["last_anti_abuse_ms"] = int(time.time() * 1000)
            n = self.state["consecutive_anti_abuse"]
            if n >= 3:
                self.state["cooldown_until_ms"] = int(time.time() * 1000 + 1800 * 1000)
                self.state["cooldown_reason"] = f"{n} lần liên tiếp bị anti-abuse từ chối"
            self._save()
            return n

    def note_success(self) -> None:
        with self._lock:
            self.state["consecutive_anti_abuse"] = 0
            self.state["total_accepted"] = int(self.state.get("total_accepted", 0)) + 1
            self.state["cooldown_until_ms"] = 0
            self.state["cooldown_reason"] = ""
            self._save()

    def note_rejected(self) -> None:
        with self._lock:
            self.state["total_rejected"] = int(self.state.get("total_rejected", 0)) + 1
            self._save()


# --------------------------------------------------------------------------- #
# FlowClient
# --------------------------------------------------------------------------- #

def _slugify(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return (s[:max_len].strip("_") or "image")


def sha256_file(path: Path | str, chunk: int = 1 << 20) -> str:
    """Content hash used as the per-account reference cache key (plan §2)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


class FlowClient:
    """High-level client: attach to the running CloakBrowser (CDP :9222)."""

    def __init__(
        self,
        cdp_url: str = DEFAULT_CDP_URL,
        out_dir: Optional[Path] = None,
        breaker_path: Optional[Path] = None,
        log: Optional[Callable[[str], None]] = None,
    ):
        self.cdp_url = cdp_url
        self.out_root = Path(out_dir) if out_dir else DEFAULT_OUT
        self.debug_dir = self.out_root / "_debug"
        self.breaker = CircuitBreaker(breaker_path or DEFAULT_BREAKER)
        self._log = log or (lambda *_: None)

    # -- helpers -------------------------------------------------------------- #

    @staticmethod
    def _mk_events(on_event: Optional[EventFn]) -> EventFn:
        def ev(kind: str, message: str, data: Optional[dict] = None) -> None:
            if on_event is None:
                return
            try:
                on_event(kind, message, data or {})
            except Exception:  # noqa: BLE001
                pass
        return ev

    def _new_run_dir(self, prompt: str) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        d = self.out_root / f"{ts}_{_slugify(prompt)}"
        n = 2
        while d.exists():
            d = self.out_root / f"{ts}_{_slugify(prompt)}_{n}"
            n += 1
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _save_debug(self, name: str, text: str) -> None:
        try:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            (self.debug_dir / name).write_text(text, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _write_meta(run_dir: Path, meta: dict) -> None:
        try:
            (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    # -- status (no browser automation) ---------------------------------------- #

    def status(self) -> BridgeStatus:
        st = BridgeStatus(cdp_url=self.cdp_url)
        base = self.cdp_url.rstrip("/")
        try:
            v = requests.get(base + "/json/version", timeout=2.5).json()
            st.cdp_ok = True
            st.browser = v.get("Browser")
        except Exception as e:  # noqa: BLE001
            st.error = f"CDP không phản hồi tại {self.cdp_url}: {e}"
        if st.cdp_ok:
            try:
                lst = requests.get(base + "/json/list", timeout=2.5).json()
                pages = [t for t in lst if t.get("type") == "page"]
                st.page_targets = len(pages)
                for t in pages:
                    u = t.get("url") or ""
                    if u.startswith("https://flow.google.com"):
                        st.flow_tab_url = u
                        m = re.search(r"/project/([0-9a-fA-F-]{36})", u)
                        st.flow_project_id = m.group(1).lower() if m else None
                        break
            except Exception as e:  # noqa: BLE001
                st.error = f"/json/list lỗi: {e}"
        snap = self.breaker.snapshot()
        st.cooldown_until_ms = int(snap.get("cooldown_until_ms") or 0)
        st.cooldown_reason = snap.get("cooldown_reason") or None
        return st

    # -- project ops (0 credit) ------------------------------------------------- #

    def list_projects(self, on_event: Optional[EventFn] = None) -> list[ProjectInfo]:
        ev = self._mk_events(on_event)
        with FlowBridge(self.cdp_url) as br:
            br.install_hook()
            ev("step", "mở trang chủ Flow (điều hướng SPA)...")
            br.nav_home()
            ctx = br.session_ctx(timeout_s=12.0)
            url = build_rpc_url_from_template(ctx.url_template, "UpteDb", ctx.reqid + 100000)
            body = encode_batchexecute_form("UpteDb", build_uptedb_args(), ctx.at)
            ev("step", "gọi UpteDb: đọc danh sách dự án (0 credit)")
            fr = br.fire(url, body, timeout_s=60.0)
            self._save_debug("list_projects_response.txt", fr.text)
            parsed = parse_batchexecute_text(fr.text)
            if not parsed.get("ok"):
                raise BridgeError(f"UpteDb lỗi: {parsed.get('reason')} {str(parsed.get('detail'))[:200]}")
            projects = parse_uptedb_projects(parsed["data"])
            self._save_debug("list_projects_parsed.json", json.dumps([p.model_dump() for p in projects], ensure_ascii=False, indent=1))
            ev("info", f"UpteDb OK: {len(projects)} dự án")
            return projects

    def create_project(self, title: str, on_event: Optional[EventFn] = None) -> ProjectInfo:
        ev = self._mk_events(on_event)
        title = (title or "").strip() or datetime.now().strftime("Batch %d/%m %H:%M")
        with FlowBridge(self.cdp_url) as br:
            br.install_hook()
            ev("step", "mở trang chủ Flow (điều hướng SPA)...")
            br.nav_home()
            ctx = br.session_ctx(timeout_s=12.0)
            url = build_rpc_url_from_template(ctx.url_template, "jHPbke", ctx.reqid + 100000)
            body = encode_batchexecute_form("jHPbke", build_create_project_args(title), ctx.at)
            ev("step", "gọi jHPbke: tạo dự án (0 credit)")
            fr = br.fire(url, body, timeout_s=60.0)
            self._save_debug("create_project_response.txt", fr.text)
            parsed = parse_batchexecute_text(fr.text)
            if not parsed.get("ok"):
                raise BridgeError(f"jHPbke lỗi: {parsed.get('reason')} {str(parsed.get('detail'))[:200]}")
            data = parsed["data"]
            pid = data[0] if isinstance(data, list) and data and isinstance(data[0], str) else None
            if not (pid and UUID_RE.match(pid)):
                raise BridgeError(f"jHPbke: không thấy project id trong payload: {str(data)[:200]}")
            title_echo = title
            if len(data) > 1 and isinstance(data[1], list) and data[1] and isinstance(data[1][0], str):
                title_echo = data[1][0]
            ev("info", f"đã tạo dự án {pid} ({title_echo})")
            br.nav_project(pid.lower())
            return ProjectInfo(id=pid.lower(), title=title_echo, source="created")

    # -- reference image (i2i) --------------------------------------------------- #

    def upload_reference_image(
        self,
        project_id: str,
        file_path: str | Path,
        *,
        prompt_probe: str = "reference",
        on_event: Optional[EventFn] = None,
    ) -> ReferenceTemplate:
        """Attach a local image and capture the app's own i2i request (0 credit).

        Google Flow's upload RPC is NOT reverse-engineered: the app uploads the
        file itself when we attach it via its ``<input type=file>`` (Playwright
        ``set_input_files``). We then let the app build its generate request and
        capture it blocked — that request IS the i2i template (arg layout + the
        per-account media reference). Callers cache the result in
        ``AccountPoolManager.registry`` keyed by account + file sha256, so each
        account uploads a given reference at most once (plan §2).

        ``prompt_probe`` is typed into the composer only to trigger the request;
        the stored template's prompt is textually substituted at fire time.
        """
        ev = self._mk_events(on_event)
        project = parse_project_ref(project_id)
        path = Path(file_path)
        if not path.is_file():
            raise BridgeError(f"Không thấy file ảnh tham chiếu: {path}")
        prompt_probe = (prompt_probe or "").strip() or "reference"
        sha = sha256_file(path)
        run_dir = self._new_run_dir(f"ref_{path.stem}")
        with FlowBridge(self.cdp_url) as br:
            try:
                ev("step", f"attach tab Flow: {br.page.url}")
                br.install_hook()
                ev("step", "hook armed: ogiZ0b của app sẽ bị chặn khi capture (0 credit)")
                br.nav_home()
                ev("step", f"mở dự án {project_id[:8]}...")
                br.nav_project(project)
                ev("step", f"đính ảnh tham chiếu vào composer: {path.name} (app tự upload)")
                info = br.attach_reference(path)
                ev("info", f"attach OK: input #{info['input_index']} accept={info['accept']!r} preview={info['preview_seen']}", info)
                ev("step", "nhập prompt thăm dò + bấm Generate (chặn) để app dựng request i2i…")
                br.type_prompt(prompt_probe)
                br.click_generate(timeout_s=30.0)
                cap = br.wait_capture(30.0)
                token, _at = parse_app_capture(cap.body)
                (run_dir / "app_request_body.txt").write_text(cap.body, encoding="utf-8")
                app_args = parse_captured_args(cap.body)
                has_ref = captured_args_has_reference(app_args)
                if has_ref is False:
                    raise BridgeError(
                        "Capture giống hệt request t2i — ảnh tham chiếu chưa kịp đính/upload. "
                        "Thử lại (chậm hơn) hoặc kiểm tra UI Flow."
                    )
                candidates = find_uuid_candidates(app_args, exclude=[project])
                masked = mask_template_token(app_args)
                (run_dir / "reference_template.pretty.json").write_text(
                    json.dumps(masked, ensure_ascii=False, indent=1), encoding="utf-8"
                )
                tpl = ReferenceTemplate(
                    sha256=sha,
                    project_id=project,
                    prompt=prompt_probe,
                    media_id=(candidates[0] if candidates else None),
                    candidates=candidates,
                    template_args=masked,
                    source_path=str(path),
                    captured_ts=int(cap.ts_ms or time.time() * 1000),
                )
                ev("info", f"template i2i OK: {len(candidates)} uuid tham chiếu (media≈{tpl.media_id}), token {len(token)} ký tự, sha {sha[:8]}…")
                self._reload_safe(br, ev)
                return tpl
            except Exception:
                try:
                    br.reload(settle_s=4.0)
                except Exception:  # noqa: BLE001
                    pass
                raise

    # -- generation ------------------------------------------------------------ #

    def generate_image(
        self,
        project_id: str,
        prompt: str,
        *,
        aspect: int = ASPECT_DEFAULT,
        seed: Optional[int] = None,
        dry_run: bool = False,
        poll_timeout_s: float = 150.0,
        anti_abuse_retries: int = 1,
        reference: Optional[ReferenceTemplate] = None,
        on_event: Optional[EventFn] = None,
    ) -> GenerationResult:
        """Generate one image via Bridge Mode. ~1 credit if accepted, 0 if rejected.

        ``reference`` (i2i): pass a :class:`ReferenceTemplate` captured (once
        per account) by :meth:`upload_reference_image`; the request is then a
        replay of the app's own i2i args with a fresh token/seed/prompt.
        """
        ev = self._mk_events(on_event)
        project = parse_project_ref(project_id)
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("prompt rỗng")
        if len(prompt) > 2000:
            raise ValueError("prompt quá dài (tối đa 2000 ký tự)")
        seed_v = validate_seed(seed if seed is not None else generate_seed())
        if not dry_run:
            self.breaker.check()

        attempt = 0
        while True:
            res = self._generate_once(
                project_id=project,
                prompt=prompt,
                aspect=int(aspect),
                seed=seed_v,
                dry_run=dry_run,
                poll_timeout_s=poll_timeout_s,
                reference=reference,
                ev=ev,
            )
            if dry_run or res.status == "dry_run":
                return res
            if res.status == "rejected" and res.anti_abuse:
                n = self.breaker.record_anti_abuse()
                if attempt < anti_abuse_retries:
                    attempt += 1
                    backoff = 120.0 * attempt + jitter(10.0, 5.0)
                    ev("retry", f"anti-abuse từ chối, chờ ~{backoff:.0f}s rồi thử lại (lần {attempt}/{anti_abuse_retries}, liên tiếp {n})",
                       {"backoff_s": round(backoff), "attempt": attempt})
                    end = time.time() + backoff
                    while time.time() < end:
                        time.sleep(min(15.0, max(0.5, end - time.time())))
                        ev("retry", f"còn {max(0.0, end - time.time()):.0f}s trước khi thử lại...")
                    continue
                return res
            if res.status == "rejected":
                self.breaker.note_rejected()
                return res
            # ok / ok_no_download
            self.breaker.note_success()
            return res

    def _generate_once(
        self,
        *,
        project_id: str,
        prompt: str,
        aspect: int,
        seed: int,
        dry_run: bool,
        poll_timeout_s: float,
        ev: EventFn,
        reference: Optional[ReferenceTemplate] = None,
    ) -> GenerationResult:
        run_dir = self._new_run_dir(prompt)
        t0 = time.time()
        with FlowBridge(self.cdp_url) as br:
            ui_started = False
            try:
                ev("step", f"attach tab Flow: {br.page.url}")
                br.install_hook()
                ev("step", "hook armed: request ogiZ0b của app sẽ bị chặn (0 credit)")
                ev("step", "mở trang chủ Flow (điều hướng SPA)...")
                br.nav_home()
                ev("step", f"mở dự án {project_id[:8]}...")
                br.nav_project(project_id)
                ui_started = True
                ev("step", "nhập prompt vào composer...")
                br.type_prompt(prompt)
                br.click_generate()
                cap = br.wait_capture(20.0)
                app_reqid = extract_app_reqid(cap.url)
                token, at_param = parse_app_capture(cap.body)
                (run_dir / "app_request_body.txt").write_text(cap.body, encoding="utf-8")

                u1, u2, gen_id = new_uuids()
                if reference is not None:
                    args, replaced = build_args_from_template(
                        reference.template_args,
                        token=token, seed=seed, prompt=prompt,
                        old_prompt=reference.prompt, u1=u1, u2=u2, gen_id=gen_id,
                    )
                    ev("info",
                       f"i2i template replay: ref sha {reference.sha256[:8]}… (media≈{reference.media_id or '?'}), "
                       f"thay {replaced}")
                else:
                    args = build_image_args(project_id, prompt, token, seed, aspect, u1, u2, gen_id)
                body = encode_batchexecute_form("ogiZ0b", args, at_param)
                (run_dir / "our_request_body.txt").write_text(body, encoding="utf-8")
                (run_dir / "our_args.pretty.json").write_text(json.dumps(args, ensure_ascii=False, indent=1), encoding="utf-8")

                cap_info = CapturedRequestInfo(
                    url=cap.url, ts_ms=cap.ts_ms, via=cap.via, body_len=len(cap.body),
                    token_len=len(token), at_len=len(at_param), app_reqid=app_reqid,
                )
                ev("capture", f"bắt request app: token {len(token)} ký tự, _reqid app {app_reqid}, via {cap.via}",
                   cap_info.model_dump())

                base_meta = {
                    "kind": "dry_run" if dry_run else "generate",
                    "mode": "i2i" if reference is not None else "t2i",
                    "prompt": prompt, "project_id": project_id, "seed": seed, "aspect": aspect,
                    "generation_id": gen_id, "uuid1": u1, "uuid2": u2,
                    "token_len": len(token), "app_reqid": app_reqid,
                    "created_ts": datetime.now().isoformat(timespec="seconds"),
                    "run_dir": str(run_dir),
                }
                if reference is not None:
                    base_meta["reference_sha256"] = reference.sha256
                    base_meta["reference_media_id"] = reference.media_id
                    base_meta["reference_source"] = reference.source_path

                if dry_run:
                    base_meta["status"] = "dry_run"
                    self._write_meta(run_dir, base_meta)
                    ev("info", "DRY-RUN: capture + build OK, KHÔNG bắn request (0 credit)")
                    self._reload_safe(br, ev)
                    return GenerationResult(status="dry_run", elapsed_s=round(time.time() - t0, 1),
                                            run_dir=str(run_dir), seed_used=seed)

                new_reqid = (app_reqid + 100000) if app_reqid is not None else 990001
                fire_url = build_capture_fire_url(cap.url, new_reqid)
                gap_ms = int(time.time() * 1000) - int(cap.ts_ms or 0)
                base_meta["our_reqid"] = new_reqid
                ev("step", f"fire ogiZ0b của ta (seed {seed}, _reqid {new_reqid}, gap {gap_ms}ms)")

                try:
                    fr = br.fire(fire_url, body, timeout_s=poll_timeout_s)
                except HttpStatusError as e:
                    if e.status in (401, 403):
                        self.breaker.trip(1800, f"HTTP {e.status} từ batchexecute: phiên/anti-bot có vấn đề, kiểm tra browser")
                    elif e.status == 429:
                        self.breaker.trip(600, "HTTP 429: vượt ngưỡng tần suất")
                    raise

                ev("response", f"server trả lời sau {fr.elapsed_ms / 1000:.1f}s (HTTP {fr.status}, {len(fr.text)} ký tự)")
                (run_dir / "response.txt").write_text(fr.text, encoding="utf-8")
                parsed = parse_batchexecute_text(fr.text)

                if not parsed.get("ok"):
                    kind, hint = describe_reject(parsed.get("grpc_code"), parsed.get("detail") or "")
                    anti = parsed.get("grpc_code") == 7
                    base_meta.update({
                        "status": "rejected", "reason": kind,
                        "detail": parsed.get("detail"), "grpc_code": parsed.get("grpc_code"),
                        "elapsed_s": round(time.time() - t0, 1),
                    })
                    self._write_meta(run_dir, base_meta)
                    ev("error", f"bị từ chối: {kind} (0 credit). {hint}")
                    self._reload_safe(br, ev)
                    return GenerationResult(
                        status="rejected", reason=kind, hint=hint,
                        detail=parsed.get("detail"), grpc_code=parsed.get("grpc_code"),
                        anti_abuse=anti, elapsed_s=round(time.time() - t0, 1),
                        run_dir=str(run_dir), seed_used=seed,
                    )

                data = parsed["data"]
                img = self._extract_image(data, project_id=project_id, prompt=prompt, seed=seed, gen_id=gen_id)
                urls = find_signed_urls(data)
                img.signed_url = urls[0] if urls else None

                if img.signed_url:
                    dest = run_dir / (_slugify(prompt) + ".jpg")
                    ok, nbytes = br.download(img.signed_url, dest, on_event=ev)
                    if ok:
                        img.file_path = str(dest)
                        img.file_bytes = nbytes
                        ev("download", f"đã tải ảnh ({nbytes / 1024:.1f} KB) → {dest.name}")

                ev("info", "reload trang project để ảnh mới hiện trên UI...")
                self._reload_safe(br, ev)
                status = "ok" if img.file_path else "ok_no_download"
                base_meta.update({
                    "status": status,
                    "media_id": img.media_id, "item_id": img.item_id,
                    "generation_id_echo": img.generation_id_echo, "seed_echo": img.seed_echo,
                    "title": img.title, "resolution": img.resolution,
                    "signed_url": img.signed_url, "file": img.file_path, "file_bytes": img.file_bytes,
                    "elapsed_s": round(time.time() - t0, 1),
                })
                self._write_meta(run_dir, base_meta)
                ev("done", f"HOÀN TẤT: ảnh {img.resolution or '?'} ({img.file_bytes or 0} bytes), seed echo {img.seed_echo}")
                return GenerationResult(status=status, image=img, elapsed_s=round(time.time() - t0, 1),
                                        run_dir=str(run_dir), seed_used=seed)
            except Exception:
                if ui_started:
                    self._reload_safe(br, ev)
                raise

    @staticmethod
    def _reload_safe(br: FlowBridge, ev: EventFn) -> None:
        try:
            time.sleep(jitter(1.5, 0.3, 0.5))
            br.reload(settle_s=6.0)
        except Exception as e:  # noqa: BLE001
            ev("warn", f"reload bỏ qua: {e}")

    @staticmethod
    def _extract_image(data, *, project_id: str, prompt: str, seed: int, gen_id: str) -> GeneratedImage:
        img = GeneratedImage(project_id=project_id, prompt=prompt, seed=seed, generation_id=gen_id)
        try:
            rec = data[0][0]
            img.media_id = rec[0]
            img.item_id = rec[2] if len(rec) > 2 else None
            gs = rec[6]
            if isinstance(gs, list) and gs and isinstance(gs[0], list):
                img.seed_echo = gs[0][1]
            if isinstance(gs, list) and len(gs) > 2 and isinstance(gs[2], list):
                res = [x for x in gs[2] if isinstance(x, int)]
                if res:
                    img.resolution = res
                    if len(res) >= 2:
                        img.width, img.height = res[0], res[1]
        except Exception:  # noqa: BLE001
            pass
        try:
            pi = data[1][0]
            if isinstance(pi[3], list):
                img.title = pi[3][0] if pi[3] else None
                if len(pi[3]) > 5:
                    img.generation_id_echo = pi[3][5]
                if len(pi[3]) > 4:
                    img.media_id_echo = pi[3][4]
        except Exception:  # noqa: BLE001
            pass
        return img


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _print_ev(kind: str, message: str, data: Optional[dict]) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {kind:9s} {message}")


def _confirm_or_die(n_images: int, yes: bool) -> None:
    if yes:
        return
    if not sys.stdin.isatty():
        print("!! Chạy thật cần --yes khi không có TTY (mỗi ảnh ~1 credit nếu được nhận).")
        raise SystemExit(3)
    ans = input(f"Chạy thật {n_images} ảnh? (~{n_images} credit nếu tất cả được nhận; reject = 0) [y/N] ")
    if ans.strip().lower() not in ("y", "yes"):
        print("Đã huỷ.")
        raise SystemExit(1)


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    ap = argparse.ArgumentParser(prog="flow_client", description="Google Flow client (bridge mode).")
    ap.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    ap.add_argument("--out", default=None, help="output base dir (default out/playground)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="trạng thái browser/CDP/tab Flow (0 credit)")

    p_list = sub.add_parser("list-projects", help="đọc danh sách dự án qua UpteDb (0 credit)")
    p_list.add_argument("--json", action="store_true")

    p_cr = sub.add_parser("create-project", help="tạo dự án qua jHPbke (0 credit)")
    p_cr.add_argument("--title", required=True)

    p_gen = sub.add_parser("generate", help="tạo 1 ảnh qua ogiZ0b (bridge mode)")
    p_gen.add_argument("--project", required=True, help="UUID project (hoặc URL)")
    p_gen.add_argument("--prompt", required=True)
    p_gen.add_argument("--aspect", type=int, default=ASPECT_DEFAULT)
    p_gen.add_argument("--seed", type=int, default=None, help="int32; bỏ trống = random")
    p_gen.add_argument("--dry-run", action="store_true", help="chỉ capture+build, KHÔNG fire (0 credit)")
    p_gen.add_argument("--yes", action="store_true", help="bỏ xác nhận credit")
    p_gen.add_argument("--anti-abuse-retries", type=int, default=1)

    args = ap.parse_args(argv)
    client = FlowClient(cdp_url=args.cdp_url, out_dir=Path(args.out) if args.out else None, log=lambda m: _print_ev("debug", m, None))

    if args.cmd == "status":
        st = client.status()
        print(json.dumps(st.model_dump(), ensure_ascii=False, indent=1))
        return 0 if st.cdp_ok else 2

    if args.cmd == "list-projects":
        try:
            projects = client.list_projects(on_event=_print_ev)
        except BridgeError as e:
            print(f"LỖI: {e}")
            return 2
        if args.json:
            print(json.dumps([p.model_dump() for p in projects], ensure_ascii=False, indent=1))
        else:
            print(f"{len(projects)} dự án:")
            for p in projects:
                print(f"  {p.id}  {(p.title or '(không tiêu đề)')[:60]}")
        return 0

    if args.cmd == "create-project":
        try:
            p = client.create_project(args.title, on_event=_print_ev)
        except BridgeError as e:
            print(f"LỖI: {e}")
            return 3
        print(json.dumps(p.model_dump(), ensure_ascii=False))
        return 0

    if args.cmd == "generate":
        if not args.dry_run:
            _confirm_or_die(1, args.yes)
        try:
            res = client.generate_image(
                args.project, args.prompt,
                aspect=args.aspect, seed=args.seed, dry_run=args.dry_run,
                anti_abuse_retries=args.anti_abuse_retries,
                on_event=_print_ev,
            )
        except CircuitOpenError as e:
            print(f"CIRCUIT: {e}")
            return 4
        except BridgeError as e:
            print(f"LỖI: {e}")
            return 3
        print("KẾT QUẢ:", json.dumps(res.model_dump(exclude_none=True), ensure_ascii=False, indent=1)[:1600])
        if res.status in ("ok", "ok_no_download", "dry_run"):
            return 0
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
