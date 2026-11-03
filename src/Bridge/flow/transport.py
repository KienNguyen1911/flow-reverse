"""Network side of :class:`FlowBridge`: session context, decoy capture, in-page fire + long-poll, CDN download."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlsplit

from .common import (
    DEFAULT_UA,
    BridgeError,
    CaptureTimeoutError,
    EventFn,
    FireTimeoutError,
    HttpStatusError,
    jitter,
)
from .protocol import AppCapture, FireResult, SessionCtx, extract_app_reqid


class TransportMixin:
    """batchexecute session params, request capture/fire and signed-URL downloads."""

    # -- session context (WIZ + performance entries) --------------------------- #

    def session_ctx(self, timeout_s: float = 10.0) -> SessionCtx:
        deadline = time.time() + timeout_s
        last = None
        while time.time() < deadline:
            info = self.eval_json(
                """(() => {
                  const g = window.WIZ_global_data || {};
                  const es = performance.getEntriesByType('resource')
                    .filter(e => (e.name || '').indexOf('/data/batchexecute?') >= 0);
                  const last = es.length ? es[es.length - 1].name : '';
                  return {at: g.SNlM0e || '', sid: g.FdrFJe || '', lastUrl: last};
                })()"""
            )
            if info and info.get("lastUrl"):
                qs = parse_qs(urlsplit(info["lastUrl"]).query)
                reqid = extract_app_reqid(info["lastUrl"])
                if reqid is not None:
                    last = SessionCtx(
                        at=info.get("at") or "",
                        f_sid=info.get("sid") or (qs.get("f.sid", [""])[0]),
                        bl=qs.get("bl", [""])[0],
                        hl=qs.get("hl", ["vi"])[0],
                        reqid=reqid,
                        url_template=info["lastUrl"],
                    )
                    if last.at:
                        return last
            time.sleep(0.5)
        if last is not None:
            return last
        raise BridgeError("Không lấy được session ctx (at/bl/f.sid/_reqid) từ page.")

    # -- capture / fire / poll --------------------------------------------------- #

    _CAP_JS = (
        "(() => { const c = window.__flowHook && window.__flowHook.cap; "
        "return c && c.bodyReady ? JSON.stringify({url: c.url, ts: c.ts, via: c.via, len: (c.body || '').length}) : ''; })()"
    )

    def wait_capture(self, timeout_s: float = 20.0, min_len: int = 100) -> AppCapture:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            raw = self._eval(self._CAP_JS, retries=2)
            if raw:
                try:
                    info = json.loads(raw)
                except Exception:  # noqa: BLE001
                    info = None
                if info and int(info.get("len") or 0) > min_len:
                    body = self._eval("(window.__flowHook && window.__flowHook.cap && window.__flowHook.cap.body) || ''", retries=2)
                    if body and len(body) > min_len:
                        return AppCapture(url=info.get("url") or "", body=body, ts_ms=int(info.get("ts") or 0), via=info.get("via") or "")
            time.sleep(0.12)
        raise CaptureTimeoutError("Không bắt được request ogiZ0b của app (hook không thấy trong ~20s).")

    def fire(self, url: str, body: str, timeout_s: float = 150.0, poll_s: float = 3.0) -> FireResult:
        """Fire OUR batchexecute request in-page (fire-and-forget) and long-poll."""
        start_js = (
            "(() => {"
            "  window.__fireTs = Date.now();"
            "  window.__bridgeState = {state: 'pending', startedTs: window.__fireTs};"
            "  fetch(" + json.dumps(url) + ", {method: 'POST', credentials: 'include',"
            "    headers: {'content-type': 'application/x-www-form-urlencoded;charset=utf-8', 'x-same-domain': '1', 'x-harness-ours': '1'},"
            "    body: " + json.dumps(body) + "})"
            "  .then(function(r) { return r.text().then(function(t) {"
            "    window.__bridgeState = {state: 'done', status: r.status, len: t.length, text: t, doneTs: Date.now()};"
            "  }); })"
            "  .catch(function(e) { window.__bridgeState = {state: 'error', error: String(e), doneTs: Date.now()}; });"
            "  return 'started';"
            "})()"
        )
        res = self._eval(start_js)
        if res != "started":
            raise BridgeError(f"fire failed to start: {res!r}")
        fire_ts = int(self._eval("window.__fireTs || 0") or 0)
        t0 = time.time()
        deadline = t0 + timeout_s
        while time.time() < deadline:
            time.sleep(poll_s)
            st = self.eval_json(
                "(() => { const s = window.__bridgeState; if (!s) return null; "
                "return {state: s.state, status: s.status, len: s.len, error: s.error, doneTs: s.doneTs}; })()"
            )
            if st and st.get("state") in ("done", "error"):
                if st.get("state") == "error":
                    raise BridgeError(f"in-page fetch failed: {st.get('error')}")
                status = int(st.get("status") or 0)
                text = self._eval("(window.__bridgeState && window.__bridgeState.text) || ''") or ""
                elapsed = int((time.time() - t0) * 1000)
                if status != 200:
                    raise HttpStatusError(status, (text or "")[:200])
                return FireResult(status=status, text=text, elapsed_ms=elapsed, fire_ts_ms=fire_ts)
        raise FireTimeoutError(f"Không có phản hồi sau {timeout_s:.0f}s (long-poll).")

    # -- download ---------------------------------------------------------------- #

    def download(self, url: str, dest: Path, attempts: int = 5, base_delay_s: float = 4.0,
                 on_event: Optional[EventFn] = None) -> tuple[bool, int]:
        """Download the signed URL to dest (magic-byte validated for image/video, exponential backoff)."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        for a in range(attempts):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
                with urllib.request.urlopen(req, timeout=45) as resp:
                    data = resp.read()
                is_img = (
                    data[:3] == b"\xff\xd8\xff"
                    or data[:8] == b"\x89PNG\r\n\x1a\n"
                    or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
                )
                is_video = (
                    b"ftyp" in data[:32]
                    or data[:4] == b"\x1a\x45\xdf\xa3"
                    or "video" in str(resp.headers.get("Content-Type", "")).lower()
                )
                if is_img or is_video or len(data) > 8192:
                    dest.write_bytes(data)
                    return True, len(data)
                if on_event:
                    on_event("warn", f"download attempt {a + 1}: unexpected content ({resp.headers.get('Content-Type')}, {len(data)}B)", None)
            except urllib.error.HTTPError as e:
                if on_event:
                    on_event("warn", f"download attempt {a + 1}: HTTP {e.code}", None)
            except Exception as e:  # noqa: BLE001
                if on_event:
                    on_event("warn", f"download attempt {a + 1}: {e!r}", None)
            if a < attempts - 1:
                delay = base_delay_s * (2 ** a) + jitter(1.0, 0.5)
                time.sleep(delay)
        return False, 0
