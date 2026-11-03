"""Browser session side of :class:`FlowBridge`: CDP attach/lifecycle, in-page eval, hook, SPA navigation."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, Optional

from playwright.sync_api import Page, sync_playwright

from .common import (
    FLOW_ORIGIN,
    BridgeError,
    NoFlowTabError,
    PageInteractionError,
    jitter,
)
from .hook_js import HOOK_JS

if TYPE_CHECKING:
    from ..flow_bridge import FlowBridge


class SessionMixin:
    """Lifecycle + low-level page access. Expects ``__init__`` to set the connection attributes."""

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
        try:
            win_info = self._cdp.send("Browser.getWindowForTarget")
            win_id = win_info.get("windowId")
            bounds = win_info.get("bounds") or {}
            if win_id and bounds.get("windowState") == "minimized":
                self._cdp.send("Browser.setWindowBounds", {"windowId": win_id, "bounds": {"windowState": "maximized"}})
        except Exception:  # noqa: BLE001
            pass
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
        if "404" in self.page.url:
            raise PageInteractionError(f"Dự án {project_id} không tồn tại trên tài khoản này (Flow trả về 404).")

    def reload(self, settle_s: float = 6.0) -> None:
        """Full reload of the current Flow page (clears hooks + shows new images)."""
        try:
            self.page.reload(wait_until="domcontentloaded", timeout=self.page_timeout_ms)
            time.sleep(settle_s)
            self._log(f"page reloaded -> {self.page.url}")
        except Exception as e:  # noqa: BLE001
            self._log(f"reload skipped: {e}")
