"""FlowBridge — direct Playwright/CDP bridge to Google Flow inside CloakBrowser.

Production port of the validated Phase-4 experiments (E7/E8/R2). Replaces the
browser-harness dependency with plain Playwright `connect_over_cdp`.

Validated recipe (see `docs/api_specs/flow_create_image.md` §7.5):
  1. Attach over CDP to the running CloakBrowser; find the flow.google.com tab.
  2. Install an idempotent fetch hook: block + capture the app's own ogiZ0b
     request (0 credit spent on the decoy) — the captured body carries the fresh
     reCAPTCHA token minted by the app.
  3. SPA-nav home -> project, type the prompt, click Generate (like a user).
  4. Build OUR OWN ogiZ0b body from the captured token (uppercase UUIDs,
     `_reqid` = app_reqid + 100000, int32 seed) and fire it in-page within ~100 ms.
  5. Long-poll the in-page promise, JSON-decode the two-layer envelope, extract
     the signed CDN URL, download the JPEG/PNG/WEBP with backoff.

Session context for the other RPCs (jHPbke / UpteDb) comes from
`window.WIZ_global_data.SNlM0e` (at) + `FdrFJe` (f.sid) + the latest batchexecute
performance entry (bl / hl / _reqid) — verified live read-only 2026-10-18.
"""

from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, quote, unquote_plus, urlsplit

from playwright.sync_api import CDPSession, Page, sync_playwright

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

FLOW_ORIGIN = "https://flow.google.com"
DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)

# int32 signed upper bound — seeds must stay < 2^31 (observed [3] INVALID_ARGUMENT otherwise)
SEED_MAX = 2147483647

EventFn = Callable[[str, str, Optional[dict]], None]


def enc(s: str) -> str:
    """encodeURIComponent-compatible percent-encoding (byte-identical, E8 forensics)."""
    return quote(s, safe="!'()*-._~")


def jitter(mean: float, sigma: float, lo: float = 0.0) -> float:
    """Gaussian-paced sleep duration (Humanized Pacing, AGENTS.md §4)."""
    return max(lo, random.gauss(mean, sigma))


def new_seed() -> int:
    """Random int32 seed (the app's own seeds are always < 2^31)."""
    return random.randint(1, SEED_MAX)


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #

class BridgeError(RuntimeError):
    """Base class for all bridge failures."""


class NoFlowTabError(BridgeError):
    pass


class PageInteractionError(BridgeError):
    pass


class CaptureTimeoutError(BridgeError):
    pass


class TokenParseError(BridgeError):
    pass


class FireTimeoutError(BridgeError):
    pass


class HttpStatusError(BridgeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


# --------------------------------------------------------------------------- #
# Page hook (proven shape from the E-series experiments; idempotent)
# --------------------------------------------------------------------------- #

HOOK_JS = r"""
(() => {
  const isOgi = u => { const s = String(u || ''); return s.indexOf('/data/batchexecute?') >= 0 && s.indexOf('rpcids=ogiZ0b') >= 0; };
  const isOurs = h => { try { return !!(h && (h['x-harness-ours'] || (h.get && h.get('x-harness-ours')))); } catch (e) { return false; } };
  if (!window.__flowHook) {
    window.__flowHook = {v: 3, cap: null, blocked: false};
    const prevFetch = window.fetch;
    window.fetch = function(input, init) {
      let url = '';
      try { url = typeof input === 'string' ? input : (input && input.url) || ''; } catch (e) {}
      if (!isOgi(url) || !window.__blockOgi) return prevFetch(input, init);
      if (typeof input !== 'string' && input && typeof input.text === 'function') {
        const ours = isOurs(init && init.headers);
        if (!ours) {
          const cap = {url: String(url), body: '', bodyReady: false, ts: Date.now(), via: 'fetch-request'};
          window.__flowHook.cap = cap;
          input.text().then(t => { cap.body = t; cap.bodyReady = true; window.__flowHook.blocked = true; })
            .catch(e => { cap.readErr = String(e); cap.bodyReady = true; });
          return Promise.reject(new Error('bridge-blocked-ogiz0b'));
        }
        return prevFetch(input, init);
      }
      const body = String((init && init.body) || '');
      const ours2 = isOurs(init && init.headers);
      if (!ours2) {
        window.__flowHook.cap = {url: String(url), body: body, bodyReady: true, ts: Date.now(), via: 'fetch-init'};
        window.__flowHook.blocked = true;
        return Promise.reject(new Error('bridge-blocked-ogiz0b'));
      }
      return prevFetch(input, init);
    };
  }
  window.__flowHook.cap = null;
  window.__flowHook.blocked = false;
  window.__blockOgi = true;
  return {installed: true};
})()
"""


# --------------------------------------------------------------------------- #
# Small data carriers
# --------------------------------------------------------------------------- #

@dataclass
class AppCapture:
    url: str
    body: str
    ts_ms: int
    via: str


@dataclass
class FireResult:
    status: int
    text: str
    elapsed_ms: int
    fire_ts_ms: int


@dataclass
class SessionCtx:
    """Fresh page-session params for firing arbitrary batchexecute RPCs."""
    at: str
    f_sid: str
    bl: str
    hl: str
    reqid: int
    url_template: str  # a real batchexecute URL captured from the app (perf entry)


# --------------------------------------------------------------------------- #
# Envelope parsing / URL building (pure functions)
# --------------------------------------------------------------------------- #

def parse_app_capture(body: str) -> tuple[str, str]:
    """Extract (recaptcha_token, at_param) from the captured app ogiZ0b body."""
    token = ""
    at_param = ""
    try:
        qs = parse_qs(body, keep_blank_values=True)
        obj = json.loads(qs.get("f.req", [""])[0])
        app_args = json.loads(obj[0][0][1])
        token = app_args[1][0][7][10][0]
        at_param = qs.get("at", [""])[0]
    except Exception:
        pass
    if not token:
        m = re.search(r"0cAFcWeA[A-Za-z0-9_\-]{400,}", body)
        token = m.group(0) if m else ""
    if not at_param:
        m = re.search(r"(?:^|&)at=([^&]+)", body)
        at_param = unquote_plus(m.group(1)) if m else ""
    if not (len(token) > 2000 and token.startswith("0cAFcWeA")):
        raise TokenParseError(f"reCAPTCHA token sanity failed (len={len(token)})")
    if len(at_param) < 10:
        raise TokenParseError("at param missing in captured app body")
    return token, at_param


def extract_app_reqid(url: str) -> Optional[int]:
    m = re.search(r"([?&]_reqid=)(\d+)", url or "")
    return int(m.group(2)) if m else None


def parse_captured_args(body: str) -> list:
    """Extract the raw args JSON (``f.req[0][0][1]``) from a captured ogiZ0b body."""
    qs = parse_qs(body, keep_blank_values=True)
    obj = json.loads(qs.get("f.req", ["[]"])[0])
    return json.loads(obj[0][0][1])


def build_capture_fire_url(captured_url: str, new_reqid: int) -> str:
    """Replace _reqid in the app's own (captured) ogiZ0b URL — proven in R2."""
    if re.search(r"([?&]_reqid=)\d+", captured_url):
        return re.sub(r"([?&]_reqid=)\d+", lambda m: m.group(1) + str(new_reqid), captured_url)
    return captured_url + ("&" if "?" in captured_url else "?") + "_reqid=" + str(new_reqid)


def build_rpc_url_from_template(template_url: str, rpcid: str, new_reqid: int) -> str:
    """Reuse a real batchexecute URL (bl/f.sid/hl/source-path) for another RPC."""
    url = template_url or ""
    if re.search(r"([?&]rpcids=)[^&]*", url):
        url = re.sub(r"([?&]rpcids=)[^&]*", lambda m: m.group(1) + rpcid, url)
    else:
        url += ("&" if "?" in url else "?") + "rpcids=" + rpcid
    if re.search(r"([?&]_reqid=)\d+", url):
        url = re.sub(r"([?&]_reqid=)\d+", lambda m: m.group(1) + str(new_reqid), url)
    else:
        url += "&_reqid=" + str(new_reqid)
    return url


def parse_batchexecute_text(txt: str) -> dict:
    """Two-layer JSON decode of a batchexecute response body.

    Returns {ok, data, reason, detail, grpc_code}.
    Success: frame `[["wrb.fr", id, <payload-json>, ...]]` -> arr[0][2] -> json.
    Failure: payload null, frame col 5 carries the gRPC canonical status
             (`[3]` INVALID_ARGUMENT, `[7, ...ErrorInfo]` PERMISSION_DENIED, ...).
    """
    payload = None
    for line in (txt or "").splitlines():
        ls = line.strip()
        if ls.startswith('[["wrb.fr"'):
            payload = ls
            break
    if payload is None:
        return {"ok": False, "reason": "no_wrbfr_payload"}
    try:
        arr = json.loads(payload)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"payload_json_error: {e!r}"}
    if not arr or not isinstance(arr[0], list):
        return {"ok": False, "reason": "unexpected_payload_shape"}
    row = arr[0]
    if len(row) >= 3 and row[2]:
        try:
            return {"ok": True, "data": json.loads(row[2])}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "reason": f"inner_json_error: {e!r}"}
    detail = row[5] if len(row) > 5 else row
    grpc_code = None
    if isinstance(detail, list) and detail and isinstance(detail[0], int):
        grpc_code = detail[0]
    return {
        "ok": False,
        "reason": "rpc_error",
        "detail": json.dumps(detail, ensure_ascii=False)[:1200],
        "grpc_code": grpc_code,
    }


def find_signed_urls(obj: Any) -> list[str]:
    """Recursively collect signed CDN URLs (prefix walk — never regex: `\\u003d` trap)."""
    acc: list[str] = []

    def walk(o: Any) -> None:
        if isinstance(o, str):
            if o.startswith("https://flow-content.google/image/"):
                acc.append(o)
        elif isinstance(o, list):
            for x in o:
                walk(x)
        elif isinstance(o, dict):
            for x in o.values():
                walk(x)

    walk(obj)
    out = list(dict.fromkeys(acc))
    return out


def describe_reject(grpc_code: Optional[int], detail: str) -> tuple[str, str]:
    """Map a gRPC rejection to (short kind, human hint, VI)."""
    if grpc_code == 3:
        return (
            "INVALID_ARGUMENT",
            "Tham số không hợp lệ (seed ngoài int32, prompt/aspect sai?). Không mất credit.",
        )
    if grpc_code == 7:
        return (
            "PERMISSION_DENIED",
            "Bị hệ thống chống lạm dụng từ chối (PUBLIC_ERROR_UNUSUAL_ACTIVITY). "
            "Không mất credit; nên chờ vài phút rồi thử lại.",
        )
    if grpc_code == 16:
        return ("UNAUTHENTICATED", "Phiên đăng nhập có vấn đề. Kiểm tra lại tab Flow trong browser.")
    return (f"RPC_ERROR[{grpc_code}]", detail[:280] if detail else "Lỗi RPC không rõ nguyên nhân.")


# --------------------------------------------------------------------------- #
# FlowBridge — the Playwright side
# --------------------------------------------------------------------------- #

class FlowBridge:
    """Attach to the running CloakBrowser over CDP and drive the Flow tab.

    Usage:
        with FlowBridge(cdp_url) as br:
            br.install_hook()
            br.nav_project(pid)
            ...
    """

    def __init__(
        self,
        cdp_url: str = DEFAULT_CDP_URL,
        log: Optional[Callable[[str], None]] = None,
        allow_new_tab: bool = True,
        page_timeout_ms: int = 30000,
    ):
        self.cdp_url = cdp_url
        self._log = log or (lambda *_: None)
        self.allow_new_tab = allow_new_tab
        self.page_timeout_ms = page_timeout_ms
        self._pw = None
        self.browser = None
        self.context = None
        self.page: Optional[Page] = None
        self._cdp: Optional[CDPSession] = None

    # -- lifecycle --------------------------------------------------------- #

    def open(self) -> "FlowBridge":
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
        except Exception as e:  # noqa: BLE001
            self._stop_pw()
            raise BridgeError(
                f"Không kết nối được CDP tại {self.cdp_url}. CloakBrowser đã chạy chưa? ({e})"
            ) from e
        self._attach_page()
        return self

    def _attach_page(self) -> Page:
        ctx, pg = None, None
        for c in self.browser.contexts:
            for p in c.pages:
                try:
                    if p.url.startswith(FLOW_ORIGIN):
                        ctx, pg = c, p
                        break
                except Exception:  # noqa: BLE001
                    continue
            if pg is not None:
                break
        if pg is None:
            if not self.allow_new_tab:
                raise NoFlowTabError(
                    "Không tìm thấy tab flow.google.com. Hãy mở flow.google.com trong CloakBrowser."
                )
            if not self.browser.contexts:
                raise NoFlowTabError("Browser không có context nào.")
            ctx = self.browser.contexts[0]
            pg = ctx.new_page()
            pg.goto(FLOW_ORIGIN, wait_until="domcontentloaded", timeout=self.page_timeout_ms)
        self.context = ctx
        self.page = pg
        try:
            self.page.set_default_timeout(self.page_timeout_ms)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.page.bring_to_front()
        except Exception:  # noqa: BLE001
            pass
        if self._cdp is not None:
            try:
                self._cdp.detach()
            except Exception:  # noqa: BLE001
                pass
        self._cdp = self.context.new_cdp_session(self.page)
        return self.page

    def close(self) -> None:
        """Disarm the block (best effort), then disconnect WITHOUT closing the browser."""
        try:
            if self.page is not None:
                self.disarm()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._cdp is not None:
                self._cdp.detach()
        except Exception:  # noqa: BLE001
            pass
        self._stop_pw()

    def _stop_pw(self) -> None:
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass
        self._pw = None

    def __enter__(self) -> "FlowBridge":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    # -- low-level helpers -------------------------------------------------- #

    def _eval(self, expr: str, retries: int = 3, delay_s: float = 0.4) -> Any:
        last: Optional[Exception] = None
        for _ in range(max(1, retries)):
            try:
                return self.page.evaluate(expr)
            except Exception as e:  # noqa: BLE001
                last = e
                msg = str(e).lower()
                if "destroyed" in msg or "execution context" in msg or "navigation" in msg:
                    time.sleep(delay_s)
                    continue
                raise
        raise PageInteractionError(f"evaluate failed after retries: {last}")

    def eval_json(self, expr: str, retries: int = 3) -> Any:
        raw = self._eval(f"(() => {{ const v = ({expr}); return v === undefined ? '' : JSON.stringify(v); }})()", retries=retries)
        if raw in (None, ""):
            return None
        try:
            return json.loads(raw)
        except Exception:  # noqa: BLE001
            return None

    # -- hook ---------------------------------------------------------------- #

    def install_hook(self) -> None:
        res = self._eval(HOOK_JS)
        if not (isinstance(res, dict) and res.get("installed")):
            raise BridgeError(f"hook install failed: {res!r}")
        self._log("hook installed (ogiZ0b block+capture armed)")

    def disarm(self) -> None:
        try:
            self._eval("window.__blockOgi = false; true", retries=2)
            self._log("hook disarmed (block off; app usable)")
        except Exception:  # noqa: BLE001
            pass

    # -- navigation ----------------------------------------------------------- #

    @staticmethod
    def _spa_nav_js(path: str) -> str:
        p = json.dumps(path)
        return (
            "(() => { try { history.pushState({}, '', " + p + "); "
            "window.dispatchEvent(new PopStateEvent('popstate')); } catch (e) {} return true; })()"
        )

    def nav_home(self, settle_s: Optional[float] = None) -> None:
        self._eval(self._spa_nav_js("/"))
        time.sleep(settle_s if settle_s is not None else jitter(3.0, 0.45))
        self._log(f"nav home -> {self.page.url}")

    def nav_project(self, project_id: str, settle_s: Optional[float] = None) -> None:
        self._eval(self._spa_nav_js("/project/" + project_id))
        time.sleep(settle_s if settle_s is not None else jitter(4.0, 0.55))
        self._log(f"nav project -> {self.page.url}")

    def reload(self, settle_s: float = 6.0) -> None:
        """Full reload of the current Flow page (clears hooks + shows new images)."""
        try:
            self.page.reload(wait_until="domcontentloaded", timeout=self.page_timeout_ms)
            time.sleep(settle_s)
            self._log(f"page reloaded -> {self.page.url}")
        except Exception as e:  # noqa: BLE001
            self._log(f"reload skipped: {e}")

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

    # -- composer & generate button -------------------------------------------- #

    _COMPOSER_POS_JS = (
        "(() => { const ed = document.querySelector('div.ProseMirror'); if (!ed) return null; "
        "const r = ed.getBoundingClientRect(); "
        "return {x: Math.round(r.x + 24), y: Math.round(r.y + r.height / 2)}; })()"
    )

    def wait_composer(self, timeout_s: float = 8.0) -> dict:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            pos = self.eval_json(self._COMPOSER_POS_JS)
            if pos and pos.get("x") is not None:
                return pos
            time.sleep(0.5)
        raise PageInteractionError("Không tìm thấy ô prompt (div.ProseMirror).")

    def type_prompt(self, prompt: str, attempts: int = 4) -> None:
        for attempt in range(attempts):
            pos = self.eval_json(self._COMPOSER_POS_JS)
            if not pos:
                time.sleep(1.0)
                continue
            self.page.mouse.click(pos["x"], pos["y"])
            time.sleep(jitter(0.5, 0.1, 0.3))
            try:
                self._eval("(() => { try { document.execCommand('selectAll'); } catch (e) {} return true; })()")
                self._cdp.send("Input.insertText", {"text": prompt})
            except Exception as e:  # noqa: BLE001
                self._log(f"type attempt {attempt}: insertText error {e}")
            time.sleep(jitter(0.9, 0.15, 0.6))
            txt = self._eval(
                "(() => { try { return (document.querySelector('div.ProseMirror').innerText || '').slice(0, 140); } catch (e) { return ''; } })()"
            )
            if prompt[:20].lower() in str(txt or "").lower():
                self._log("prompt typed & verified in composer")
                return
            self._eval(
                "(() => { try { const ev = new KeyboardEvent('keydown', {key: 'Escape', keyCode: 27, bubbles: true}); document.dispatchEvent(ev); } catch (x) {} return true; })()"
            )
            time.sleep(1.0)
        raise PageInteractionError("Không nhập được prompt vào composer sau nhiều lần thử.")

    _GEN_BTN_JS = (
        "(() => { const b = document.querySelector('button.generate-icon-button'); if (!b) return null; "
        "const r = b.getBoundingClientRect(); "
        "return {disabled: !!b.disabled, x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)}; })()"
    )

    def click_generate(self, timeout_s: float = 8.0) -> int:
        deadline = time.time() + timeout_s
        btn = None
        while time.time() < deadline:
            btn = self.eval_json(self._GEN_BTN_JS)
            if btn and not btn.get("disabled"):
                break
            time.sleep(0.5)
        if not (btn and not btn.get("disabled")):
            raise PageInteractionError("Nút Generate không tìm thấy hoặc bị disabled.")
        self.page.mouse.click(btn["x"], btn["y"])
        ts = int(time.time() * 1000)
        self._log(f"generate clicked @ {ts}")
        return ts

    # -- reference image attach (i2i template capture) --------------------------- #
    #
    # The image2image upload RPC is intentionally NOT guessed here: the app
    # performs its own upload when we attach the file via its <input type=file>
    # (Playwright set_input_files works on hidden inputs and fires `change`).
    # The app's next ogiZ0b request (blocked, 0 credit) is captured as the i2i
    # template — see FlowClient.upload_reference_image.

    _FILE_INPUTS_JS = (
        "(() => { const out = []; const nodes = Array.from(document.querySelectorAll('input[type=file]')); "
        "for (let i = 0; i < nodes.length; i++) { const el = nodes[i]; const r = el.getBoundingClientRect(); "
        "out.push({i: i, accept: String(el.accept || ''), multiple: !!el.multiple, "
        "visible: (r.width > 0 && r.height > 0), cls: String(el.className || '').slice(0, 60)}); } "
        "return out; })()"
    )

    _ATTACH_STATE_JS = (
        "(() => { let blob = 0, files = 0; "
        "for (const im of Array.from(document.querySelectorAll('img'))) { "
        "  const s = String(im.src || im.currentSrc || ''); if (s.indexOf('blob:') === 0) blob++; } "
        "for (const el of Array.from(document.querySelectorAll('input[type=file]'))) "
        "  files += (el.files ? el.files.length : 0); "
        "return {blobImgs: blob, fileInputsWithFiles: files}; })()"
    )

    def list_file_inputs(self) -> list[dict]:
        res = self.eval_json(self._FILE_INPUTS_JS)
        return res if isinstance(res, list) else []

    def composer_probe(self) -> dict:
        """Read-only DOM probe (discovery/QA, 0 side effects)."""
        return {
            "url": self.page.url if self.page is not None else None,
            "prosemirror": bool(self.eval_json("(() => !!document.querySelector('div.ProseMirror'))()")),
            "generate_button": bool(self.eval_json("(() => !!document.querySelector('button.generate-icon-button'))()")),
            "file_inputs": self.list_file_inputs(),
        }

    def attach_reference(self, file_path: str | Path, timeout_s: float = 20.0) -> dict:
        """Attach a local image to the composer via the app's own file input.

        Returns probe info; raises PageInteractionError when no file input
        exists (UI changed / image mode without attach support).
        """
        path = Path(file_path)
        if not path.is_file():
            raise PageInteractionError(f"Không thấy file ảnh tham chiếu: {path}")
        infos = self.list_file_inputs()
        if not infos:
            raise PageInteractionError(
                "Composer không có <input type=file> — chạy discovery để cập nhật selector "
                "(xem docs/api_specs/flow_image2image.md)."
            )
        pick = next((x for x in infos if "image" in str(x.get("accept") or "").lower()), infos[0])
        handles = self.page.query_selector_all("input[type=file]")
        idx = int(pick.get("i") or 0)
        if idx >= len(handles):
            raise PageInteractionError("Danh sách file input lệch — thử lại sau khi reload trang.")

        before = self.eval_json(self._ATTACH_STATE_JS) or {}
        handles[idx].set_input_files(str(path.resolve()))
        self._log(f"attached reference {path.name} -> input #{idx} (accept={pick.get('accept')!r})")

        deadline = time.time() + timeout_s
        preview = False
        while time.time() < deadline:
            st = self.eval_json(self._ATTACH_STATE_JS) or {}
            if int(st.get("blobImgs") or 0) > int(before.get("blobImgs") or 0) or int(st.get("fileInputsWithFiles") or 0) > 0:
                preview = True
                break
            time.sleep(0.5)
        time.sleep(jitter(1.5, 0.4, 0.6))  # let the app's own upload settle
        return {"input_index": idx, "accept": pick.get("accept"), "preview_seen": preview, "inputs": infos}

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
        """Download the signed URL to dest (magic-byte validated, exponential backoff)."""
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
                if is_img:
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
