"""Playwright network sniffer for the Google Flow reverse-engineering workflow.

Attaches to an ALREADY-RUNNING browser (CloakBrowser launched by
``src/BrowserHost/launch_profile.py``, CDP port 9222 by default) and writes one
JSON event per line (JSONL) into ``traces/raw_trace_<UTC>.jsonl``. Run it as a
standalone process while another agent drives the UI (browser-harness); it is
read-only: it only listens to Playwright events and never navigates or mutates
pages.

Event schema (one JSON object per line):

    ts_ms            float  - event time (time.time() * 1000)
    kind             str    - request | response | ws_open | ws_frame | ws_close
    method           str?   - HTTP method (request/response events)
    url              str    - request URL (ws_* events: WebSocket URL)
    status           int?   - HTTP status (response events)
    resource_type    str?   - Playwright resource type of the request
    frame_direction  str?   - ws_frame only: "sent" | "received"
    headers          obj?   - HTTP headers, clipped to ~50 entries
    req_body         str?   - request body; ws_frame "sent" payload lands here too
    resp_body        str?   - response body; ws_frame "received" payload here too
    encoding         str?   - "base64" when the body is not valid UTF-8
                              (protobuf/binary); absent for plain text
    truncated        bool?  - true when the body was cut at --max-body
    body_error       str?   - why the response body could not be read

Deliberate behaviour choices:

    * Response bodies of streaming (``text/event-stream``) responses and of
      redirects are NOT fetched: ``response.body()`` blocks until a stream
      ends, which would freeze live sniffing. Malformed/failed reads are
      reported through ``body_error`` instead of killing the callback.
    * Every listener body is wrapped in try/except, so a single bad event can
      never kill the sniffer.
    * The sync Playwright API only dispatches events while the caller yields
      to the driver loop (greenlet-based since Playwright 1.30), so the idle
      loop "pumps" via ``page.wait_for_timeout`` instead of ``time.sleep``.

Usage:
    python discovery/sniffer.py
    python discovery/sniffer.py --cdp-url http://127.0.0.1:9222 \
        --out-dir traces --types xhr,fetch,websocket --max-body 262144

Stop with Ctrl+C: the trace file is flushed/closed and a per-kind summary is
printed. Windows-compatible (plain SIGINT handler, no POSIX-only APIs).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from playwright.sync_api import sync_playwright

# Keep the JSONL lean: cookies/auth headers matter, but 50 entries is plenty.
MAX_HEADERS = 50

# Streaming responses are skipped on purpose (response.body() would block
# until the stream finishes and freeze the sniffer).
SKIP_BODY_CONTENT_TYPES = ("text/event-stream",)

_WS_TAG = {"request": "REQ ", "response": "RESP", "ws_open": "WS+ ", "ws_frame": "WSF ", "ws_close": "WS- "}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def short_url(url: str, limit: int = 160) -> str:
    return url if len(url) <= limit else url[: limit - 3] + "..."


class Sniffer:
    """Listen to fetch/XHR/WebSocket traffic of an already-running browser."""

    def __init__(self, cdp_url: str, out_dir: str, types: str, max_body: int) -> None:
        self.cdp_url = cdp_url
        self.types = {t.strip().lower() for t in types.split(",") if t.strip()}
        self.log_all = "all" in self.types
        self.max_body = max_body
        self.out_dir = Path(out_dir)
        self.out_path = self.out_dir / f"raw_trace_{utc_stamp()}.jsonl"

        self._fh: Optional[Any] = None
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}
        self._attached_pages: set[int] = set()
        self._attached_contexts: set[int] = set()
        self._pages: list[Any] = []
        self._context: Optional[Any] = None
        self._browser: Optional[Any] = None
        self._pw: Optional[Any] = None
        self._start = time.time()

    # ------------------------------------------------------------------ setup
    def open(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        # One file per run; the UTC timestamp keeps concurrent runs apart.
        self._fh = open(self.out_path, "w", encoding="utf-8", newline="\n")
        print(f"[sniffer] CDP endpoint : {self.cdp_url}")
        print(f"[sniffer] trace file   : {self.out_path}")
        print(f"[sniffer] resource types: {','.join(sorted(self.types)) or '(none)'}")
        print(f"[sniffer] max body     : {self.max_body} bytes")
        print("[sniffer] attached - waiting for traffic (Ctrl+C to stop)", flush=True)

    def connect(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
        self._browser.on("context", lambda ctx: self._guard("context", lambda: self._attach_context(ctx)))
        for ctx in self._browser.contexts:
            self._attach_context(ctx)
        n_pages = sum(len(ctx.pages) for ctx in self._browser.contexts)
        print(
            f"[sniffer] connected: {len(self._browser.contexts)} context(s), "
            f"{n_pages} open page(s)",
            flush=True,
        )

    def _attach_context(self, ctx: Any) -> None:
        if id(ctx) in self._attached_contexts:
            return
        self._attached_contexts.add(id(ctx))
        self._context = ctx
        # New tabs/popups keep coming through the external browser; attach live.
        ctx.on("page", lambda page: self._guard("page-open", lambda: self._attach_page(page)))
        for page in ctx.pages:
            self._attach_page(page)

    def _attach_page(self, page: Any) -> None:
        if id(page) in self._attached_pages:
            return
        self._attached_pages.add(id(page))
        self._pages.append(page)
        print(f"[sniffer] + page {short_url(page.url or 'about:blank')}", flush=True)
        # Navigations reuse the same Page object, so these listeners survive
        # them; only "close" removes the page.
        page.on("request", lambda req: self._guard("request", lambda: self._on_request(page, req)))
        page.on("response", lambda res: self._guard("response", lambda: self._on_response(page, res)))
        page.on("websocket", lambda ws: self._guard("websocket", lambda: self._on_websocket(page, ws)))
        page.on("close", lambda _p: self._guard("page-close", lambda: self._forget_page(page)))

    def _forget_page(self, page: Any) -> None:
        self._attached_pages.discard(id(page))
        self._pages = [p for p in self._pages if p is not page]

    # --------------------------------------------------------------- plumbing
    def _guard(self, name: str, fn: Callable[[], None]) -> None:
        """Run one listener body; a failing callback must never kill the sniffer."""
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - deliberately broad, sniffer must survive
            print(f"[sniffer] !! {name} handler error: {exc!r}", file=sys.stderr, flush=True)

    def _emit(self, event: dict[str, Any]) -> None:
        event.setdefault("ts_ms", time.time() * 1000.0)
        kind = str(event.get("kind", "?"))
        with self._lock:
            self._counts[kind] = self._counts.get(kind, 0) + 1
            if self._fh is not None:
                self._fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
                self._fh.flush()  # live tailing: readers see events immediately
        self._print_event(event)

    def _print_event(self, event: dict[str, Any]) -> None:
        kind = str(event.get("kind", "?"))
        parts = [_WS_TAG.get(kind, f"{kind.upper():<5}")]
        if event.get("status") is not None:
            parts.append(str(event["status"]))
        if event.get("method"):
            parts.append(str(event["method"]))
        if event.get("frame_direction") == "received":
            parts.append("<-")
        elif event.get("frame_direction") == "sent":
            parts.append("->")
        line = " ".join(parts) + " " + short_url(str(event.get("url") or ""))
        if event.get("encoding") == "base64":
            line += " [base64]"
        if event.get("truncated"):
            line += " [truncated]"
        print(line, flush=True)

    def _logs(self, resource_type: str) -> bool:
        return self.log_all or resource_type.lower() in self.types

    @staticmethod
    def _clip_headers(headers: Any) -> Optional[dict[str, str]]:
        if not headers:
            return None
        try:
            items = list(headers.items())[:MAX_HEADERS]
        except Exception:  # noqa: BLE001 - never let header clipping raise
            return None
        return {str(k): str(v) for k, v in items}

    def _body_fields(self, field: str, raw: Any) -> dict[str, Any]:
        """Encode a body payload into JSON-safe fields.

        UTF-8 bodies stay as text; anything else (protobuf/binary) is
        base64-encoded and flagged with ``"encoding": "base64"``. Bodies over
        ``--max-body`` are cut and flagged with ``"truncated": true``. A cut
        that lands mid-codepoint therefore falls back to base64 - acceptable,
        the truncation flag still tells the reader why.
        """
        if raw is None or raw == b"" or raw == "":
            return {field: None}
        if isinstance(raw, str):
            data = raw.encode("utf-8", errors="surrogatepass")
        else:
            data = bytes(raw)
        truncated = len(data) > self.max_body
        if truncated:
            data = data[: self.max_body]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            fields: dict[str, Any] = {field: base64.b64encode(data).decode("ascii"), "encoding": "base64"}
        else:
            fields = {field: text}
        if truncated:
            fields["truncated"] = True
        return fields

    def _request_body_fields(self, request: Any) -> dict[str, Any]:
        raw: Any = None
        try:
            raw = request.post_data
        except Exception:  # noqa: BLE001
            raw = None
        if raw is None:
            try:
                raw = request.post_data_buffer  # bytes; covers binary bodies
            except Exception:  # noqa: BLE001
                raw = None
        return self._body_fields("req_body", raw)

    def _response_body_fields(self, response: Any) -> dict[str, Any]:
        status = response.status
        content_type = ""
        try:
            content_type = str(response.headers.get("content-type", ""))
        except Exception:  # noqa: BLE001
            content_type = ""
        if status is not None and 300 <= status < 400:
            return {"resp_body": None, "body_error": "redirect response without body"}
        if any(skip in content_type.lower() for skip in SKIP_BODY_CONTENT_TYPES):
            return {"resp_body": None, "body_error": f"streaming content-type skipped ({content_type})"}
        try:
            data = response.body()  # bytes; raises for many Google binary responses
        except Exception as exc:  # noqa: BLE001
            return {"resp_body": None, "body_error": str(exc)[:300]}
        return self._body_fields("resp_body", data)

    # --------------------------------------------------------------- handlers
    def _on_request(self, _page: Any, request: Any) -> None:
        resource_type = (request.resource_type or "").lower()
        if not self._logs(resource_type):
            return
        event: dict[str, Any] = {
            "kind": "request",
            "method": request.method,
            "url": request.url,
            "status": None,
            "resource_type": resource_type or None,
            "frame_direction": None,
            "headers": self._clip_headers(request.headers),
        }
        event.update(self._request_body_fields(request))
        self._emit(event)

    def _on_response(self, _page: Any, response: Any) -> None:
        try:
            request = response.request
            resource_type = (request.resource_type or "").lower()
            method = request.method
        except Exception:  # noqa: BLE001
            return
        if not self._logs(resource_type):
            return
        event: dict[str, Any] = {
            "kind": "response",
            "method": method,
            "url": response.url,
            "status": response.status,
            "resource_type": resource_type or None,
            "frame_direction": None,
            "headers": self._clip_headers(response.headers),
        }
        event.update(self._response_body_fields(response))
        self._emit(event)

    def _on_websocket(self, _page: Any, ws: Any) -> None:
        if not self._logs("websocket"):
            return
        try:
            url = ws.url
        except Exception:  # noqa: BLE001
            return
        self._emit(
            {
                "kind": "ws_open",
                "method": None,
                "url": url,
                "status": None,
                "resource_type": "websocket",
                "frame_direction": None,
                "headers": None,
                "req_body": None,
                "resp_body": None,
            }
        )
        ws.on("framereceived", lambda payload: self._guard("ws-frame", lambda: self._on_ws_frame(ws, "received", payload)))
        ws.on("framesent", lambda payload: self._guard("ws-frame", lambda: self._on_ws_frame(ws, "sent", payload)))
        ws.on(
            "close",
            lambda _ws: self._guard(
                "ws-close",
                lambda: self._emit(
                    {
                        "kind": "ws_close",
                        "method": None,
                        "url": url,
                        "status": None,
                        "resource_type": "websocket",
                        "frame_direction": None,
                        "headers": None,
                        "req_body": None,
                        "resp_body": None,
                    }
                ),
            ),
        )

    def _on_ws_frame(self, ws: Any, direction: str, payload: Any) -> None:
        # Convention: "sent" frames ride in req_body, "received" in resp_body.
        field = "req_body" if direction == "sent" else "resp_body"
        event: dict[str, Any] = {
            "kind": "ws_frame",
            "method": None,
            "url": ws.url,
            "status": None,
            "resource_type": "websocket",
            "frame_direction": direction,
            "headers": None,
        }
        event.update(self._body_fields(field, payload))
        self._emit(event)

    # ------------------------------------------------------------- idle loop
    def pump(self, seconds: float) -> None:
        """Let the driver loop dispatch queued events for ``seconds``.

        The sync API is greenlet-based: events are only delivered while the
        main greenlet switches out to the driver loop, so the idle loop must
        call into Playwright - ``time.sleep`` alone would stall the sniffer.
        """
        for page in list(self._pages):
            try:
                page.wait_for_timeout(max(1, int(seconds * 1000)))
                return
            except Exception:  # noqa: BLE001 - page closed between checks
                self._forget_page(page)
        ctx = self._context
        if ctx is not None:
            # No live page to pump through: run one asyncio sleep on the
            # driver loop via a private-but-stable hook (Playwright >= 1.30).
            coro = asyncio.sleep(seconds)
            try:
                ctx._sync(coro)  # type: ignore[attr-defined]
                return
            except Exception:  # noqa: BLE001
                try:
                    coro.close()
                except Exception:  # noqa: BLE001
                    pass
        time.sleep(seconds)

    # --------------------------------------------------------------- teardown
    def summary(self) -> None:
        elapsed = time.time() - self._start
        total = sum(self._counts.values())
        by_kind = ", ".join(f"{k}={v}" for k, v in sorted(self._counts.items())) or "no events"
        print(f"[sniffer] summary: total={total} ({by_kind}) in {elapsed:.1f}s", flush=True)

    def close(self) -> None:
        with self._lock:
            fh, self._fh = self._fh, None
        if fh is not None:
            try:
                fh.flush()
                fh.close()
                print(f"[sniffer] trace file: {self.out_path}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[sniffer] !! error closing trace file: {exc!r}", file=sys.stderr)
        try:
            if self._browser is not None:
                # connect_over_cdp: close() only disconnects this client;
                # the real browser window keeps running.
                self._browser.close()
        except Exception as exc:  # noqa: BLE001
            print(f"[sniffer] !! error while disconnecting: {exc!r}", file=sys.stderr)
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attach to a running Chromium over CDP and dump network traffic to JSONL.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--cdp-url",
        default="http://127.0.0.1:9222",
        help="CDP endpoint of the running browser (launch_profile.py opens port 9222)",
    )
    parser.add_argument("--out-dir", default="traces", help="Directory for raw_trace_<UTC>.jsonl")
    parser.add_argument(
        "--types",
        default="xhr,fetch,websocket",
        help="Comma-separated Playwright resource types to log; 'all' logs everything",
    )
    parser.add_argument(
        "--max-body",
        type=int,
        default=262144,
        help="Max bytes kept per body; larger bodies are truncated (truncated=true)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 - not all streams support reconfigure
            pass

    args = parse_args(argv)
    sniffer = Sniffer(args.cdp_url, args.out_dir, args.types, args.max_body)

    stop = threading.Event()

    def _on_sigint(_signum: int, _frame: Any) -> None:
        # signal.signal(SIGINT) works on Windows (Ctrl+C); keep it tiny - the
        # flush/close/summary work happens in the finally block below.
        print("\n[sniffer] SIGINT received - stopping (flush + summary)...", flush=True)
        stop.set()

    previous = signal.signal(signal.SIGINT, _on_sigint)
    sniffer.open()
    try:
        sniffer.connect()
    except Exception as exc:  # noqa: BLE001
        print(f"[sniffer] !! cannot attach to {args.cdp_url}: {exc}", file=sys.stderr)
        print(
            "[sniffer]    is the browser running with --remote-debugging-port? "
            "(see src/BrowserHost/launch_profile.py)",
            file=sys.stderr,
        )
        sniffer.close()
        return 2

    try:
        while not stop.is_set():
            sniffer.pump(0.2)
    except KeyboardInterrupt:  # pragma: no cover - safety net if SIGINT races the loop
        pass
    finally:
        sniffer.summary()
        sniffer.close()
        try:
            signal.signal(signal.SIGINT, previous)
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
