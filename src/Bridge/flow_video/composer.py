"""Video composer driving for :class:`FlowVideoBridge` (settings popover, sub-mode, reCAPTCHA readiness).

Two composer facts drive most of this module and were captured 0-credit (2026-11-09):

* **Duration is a slider.** ``flow-duration-slider`` wraps an ``input[type=range]`` whose
  value is ``seconds - 3`` (0..12 → 3..15 giây). With both frame slots filled the max drops
  to 7 (3..10s). The retired Omni 1.1 / Veo Fast / Veo Quality models used a
  ``Thời lượng video`` radio group instead; Flow no longer offers them, so this module only
  drives the slider.
* **"Khung hình" has two slots: "Bắt đầu" and "Kết thúc".** Both are always rendered;
  the last one becomes optional input. Filling it changes the submit RPC to ``nprQif``.
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional

from ..flow_bridge import FlowBridge, PageInteractionError
from .constants import OMNI12_SLIDER_OFFSET_S

#: ``flow-toggles`` groups whose label differs from the visible text, keyed by the label
#: we address them with.
GROUP_MODE = "Chế độ"
GROUP_SUB_MODE = "Loại video"
GROUP_ASPECT = "Tỷ lệ khung hình"
GROUP_MODEL = None  # the model lives in its own button + nested menu, not a toggle group
GROUP_RESOLUTION = "Độ phân giải video"
GROUP_COUNT = "Số lượng kết quả đầu ra"


def _count_needs_change(chip_text: str, want: int) -> bool:
    """Does the composer chip show a different batch count than ``want``?"""
    txt = str(chip_text or "")
    return f"x{want}" not in txt


def parse_chip_duration(chip_text: str) -> Optional[int]:
    """Read ``N giây`` (or ``Ns``) out of the composer chip, if present."""
    match = re.search(r"(\d+)\s*(?:giây|giay|s)\b", str(chip_text or ""))
    return int(match.group(1)) if match else None


class VideoComposerMixin:
    """DOM-level state of the Flow video composer and project grid."""

    def snapshot_videos(self, bridge: FlowBridge) -> dict[str, Any]:
        """Capture existing video URLs and count in the current project DOM."""
        info = bridge.eval_json(
            """(() => {
                const videos = Array.from(document.querySelectorAll('video'));
                const srcs = videos.map(v => v.src || v.currentSrc || '').filter(s => s.length > 0);
                const entries = performance.getEntriesByType('resource')
                    .map(e => e.name || '')
                    .filter(u => u.indexOf('.mp4') >= 0 || u.indexOf('/video/') >= 0);
                return {srcs: srcs, entries: entries, count: videos.length};
            })()"""
        ) or {}
        urls = set(info.get("srcs", []) + info.get("entries", []))
        return {"urls": urls, "count": int(info.get("count", 0))}

    def _settings_popover_open(self, page: Any) -> bool:
        try:
            return bool(
                page.evaluate(
                    "() => [...document.querySelectorAll('.cdk-overlay-pane')]"
                    ".filter(p => p.offsetWidth || p.offsetHeight).length > 0"
                )
            )
        except Exception:  # noqa: BLE001
            return False

    def _open_settings_popover(self, page: Any) -> bool:
        if self._settings_popover_open(page):
            return True
        return bool(
            page.evaluate(
                "() => { const b = document.querySelector('button.settings-trigger-button');"
                " if (!b || !(b.offsetWidth || b.offsetHeight)) return false; b.click(); return true; }"
            )
        )

    def _pick_in_popover(self, page: Any, label: str) -> bool:
        """Click a radio/menu item in the open settings popover by its visible label."""
        return bool(
            page.evaluate(
                r"""(label) => {
                const n = s => (s || '').replace(/\s+/g, ' ').trim();
                const ps = [...document.querySelectorAll('.cdk-overlay-pane')].filter(p => p.offsetWidth || p.offsetHeight);
                const p = ps[ps.length - 1];
                if (!p) return false;
                const els = [...p.querySelectorAll('[role="radio"], [role="menuitem"], button')];
                const el = els.find(e => n(e.innerText) === label)
                  || els.find(e => n(e.innerText).endsWith(' ' + label))
                  || els.find(e => n(e.innerText).startsWith(label + ' '));
                if (!el) return false;
                if (el.disabled === true || el.getAttribute('aria-disabled') === 'true') return false;
                if (el.getAttribute('aria-checked') === 'true') return true;
                el.click();
                return true;
            }""",
                label,
            )
        )

    def _pick_video_model(self, page: Any, model_label: str) -> bool:
        """Pick a model in the video composer (the model menu lives in a nested overlay)."""
        if not self._open_settings_popover(page):
            return False
        page.wait_for_timeout(450)
        opened = page.evaluate(
            r"""() => {
            const ps = [...document.querySelectorAll('.cdk-overlay-pane')].filter(p => p.offsetWidth || p.offsetHeight);
            const p = ps[ps.length - 1];
            if (!p) return false;
            const b = [...p.querySelectorAll('button')].find(x => (x.getAttribute('aria-label') || '') === 'Chọn nhóm mô hình');
            if (!b) return false;
            b.click();
            return true;
          }"""
        )
        if not opened:
            return False
        page.wait_for_timeout(450)
        ok = self._pick_in_popover(page, model_label)
        page.wait_for_timeout(400)
        return bool(ok)

    def _close_settings_popover(self, page: Any) -> None:
        backdrop = page.query_selector(".cdk-overlay-backdrop")
        if backdrop:
            backdrop.click(force=True)
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(320)

    def _ensure_ui_video_mode(
        self,
        page: Any,
        *,
        sub_mode: str = "frames",
        target_aspect: str = "9:16",
        model_label: Optional[str] = None,
        duration_s: int = 8,
        resolution: str = "720p",
        count: int = 1,
        offer_resolution: bool = True,
        offer_duration: bool = True,
    ) -> str:
        """Drive the composer to Video + the requested sub-mode/config; returns the chip text.

        Observed contract (``discovery/probe_video_model_matrix.py``):

        * Angular closes the settings popover after a model pick, so every option group
          needs its own open.
        * Picking a Veo model removes the resolution + duration groups entirely.
        * Omni 1.2 replaces the duration radio group with a slider, so duration is handled
          by :meth:`_set_duration_slider` instead of :meth:`_pick_in_popover`.
        * The sub-mode group's accessible label is ``Loại video`` (its item texts are
          ``Khung hình`` / ``Thành phần``), not a label named after the sub-mode.
        """
        sub_label = "Khung hình" if sub_mode == "frames" else "Thành phần"
        aspect = "9:16" if "9:16" in str(target_aspect) else "16:9"
        want_count = max(1, int(count or 1))

        def _chip() -> str:
            btn = page.query_selector("button.settings-trigger-button")
            return ((btn.inner_text() if btn else "") or "").replace("\n", " ").strip()

        # Already there?
        txt = _chip()
        expected_bits = [
            "Video" in txt,
            aspect.replace(":", "_").replace("_", "_") in txt.replace(":", "_"),
            f"x{want_count}" in txt,
        ]
        if model_label:
            expected_bits.append(model_label.replace("🍌 ", "") in txt)
        if offer_duration:
            expected_bits.append(f"{duration_s} giây" in txt or f"{duration_s}s" in txt)
        if offer_resolution:
            expected_bits.append(str(resolution).lower() in txt.lower())
        # Sub-mode is not part of the chip; always ensure it once.
        if all(expected_bits):
            self._ensure_video_sub_mode(page, sub_label)
            return _chip()

        for step in (("Video", None), (sub_label, None), (aspect, None)):
            if not self._open_settings_popover(page):
                break
            page.wait_for_timeout(450)
            if not self._pick_in_popover(page, step[0]):
                self._log("warn", f"Không chọn được {step[0]!r} trên popover Video")
            page.wait_for_timeout(320)
            self._close_settings_popover(page)

        if model_label and not self._pick_video_model(page, model_label):
            self._log("warn", f"Không chọn được model video {model_label!r}")
        self._close_settings_popover(page)

        if offer_resolution:
            if self._open_settings_popover(page):
                page.wait_for_timeout(420)
                self._pick_in_popover(page, str(resolution))
                page.wait_for_timeout(300)
                self._close_settings_popover(page)

        if offer_duration:
            self._apply_duration(page, duration_s)

        if _count_needs_change(_chip(), want_count):
            if self._open_settings_popover(page):
                page.wait_for_timeout(420)
                self._pick_in_popover(page, f"x{want_count}")
                page.wait_for_timeout(300)
                self._close_settings_popover(page)

        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
        return _chip()

    def _apply_duration(self, page: Any, duration_s: int) -> None:
        """Set the clip length on Omni 1.2's ``Độ dài`` slider.

        Every model the catalog still offers expresses duration the same way now: Omni 1.2
        has the slider, and Veo 3.1 Lite hides the duration group entirely (fixed 8s, so
        callers pass ``offer_duration=False``). The ``Thời lượng video`` radio group the
        retired Omni 1.1 / Veo Fast / Veo Quality used is gone from Flow, so a missing
        slider is a real failure worth logging rather than a cue to try another control.
        """
        if not self._set_duration_slider(page, duration_s):
            self._log("warn", f"Không đặt được thời lượng {duration_s}s trên composer")

    def _set_duration_slider(self, page: Any, duration_s: int) -> bool:
        """Drive Omni 1.2's ``Độ dài`` range input; returns False when there is none."""
        if not self._open_settings_popover(page):
            return False
        page.wait_for_timeout(400)
        state = page.evaluate(
            """() => {
            const sc = document.querySelector('.cdk-overlay-pane .settings-content');
            const inp = sc && sc.querySelector('input[type=range].mdc-slider__input');
            if (!inp) return null;
            const host = sc.querySelector('flow-duration-slider');
            const shown = host ? (host.innerText || '').replace(/\\s+/g, ' ').trim() : '';
            return {min: inp.getAttribute('min'), max: inp.getAttribute('max'),
                    value: inp.value, shown};
          }"""
        )
        if not state:
            self._close_settings_popover(page)
            return False
        try:
            vmin = int(state.get("min") or 0)
            vmax = int(state.get("max") or 0)
        except (TypeError, ValueError):
            self._close_settings_popover(page)
            return False

        # The slider's own value is the displayed seconds minus an offset that is read off
        # the DOM (a slider showing "8 giây" at value 5 has offset 3), so a change in Flow's
        # numbering does not silently set the wrong length.
        current_value = int(state.get("value") or 0)
        current_shown = parse_chip_duration(state.get("shown") or "")
        offset = OMNI12_SLIDER_OFFSET_S
        if current_shown is not None:
            offset = current_shown - current_value
        target = max(vmin, min(vmax, int(duration_s) - offset))

        page.evaluate(
            """(target) => {
            const inp = document.querySelector('.cdk-overlay-pane .settings-content input[type=range]');
            if (!inp) return false;
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(inp, String(target));
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            inp.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
          }""",
            target,
        )
        page.wait_for_timeout(350)
        self._close_settings_popover(page)
        if int(duration_s) - offset > vmax:
            self._log(
                "warn",
                f"Composer chỉ cho tối đa {vmax + offset}s ở trạng thái hiện tại "
                f"(yêu cầu {duration_s}s)",
            )
        return True

    def _ensure_video_sub_mode(self, page: Any, sub_label: str) -> None:
        """Make sure the composer is on the wanted sub-mode (Khung hình / Thành phần).

        The sub-mode group's accessible label is ``Loại video``; its items read
        ``crop_free Khung hình`` / ``chrome_extension Thành phần``. Matching on the group
        (instead of hoping the item text is unique in the popover) is what makes the
        wrong-sub-mode failure go away rather than move around.
        """
        try:
            if not self._open_settings_popover(page):
                return
            page.wait_for_timeout(420)
            # The group only exists while the popover is open, so the check has to happen here.
            if self._video_sub_mode_is(page, sub_label):
                self._close_settings_popover(page)
                return
            self._pick_in_popover(page, sub_label)
            page.wait_for_timeout(320)
            self._close_settings_popover(page)
        except Exception as exc:  # noqa: BLE001
            self._log("warn", f"Không đổi được sub-mode video sang {sub_label!r}: {exc}")

    def _video_sub_mode_is(self, page: Any, sub_label: str) -> bool:
        """Is the ``Loại video`` group currently showing ``sub_label`` as checked?"""
        return bool(
            page.evaluate(
                """(label) => {
                const n = s => (s || '').replace(/\\s+/g, ' ').trim();
                const sc = document.querySelector('.cdk-overlay-pane .settings-content');
                if (!sc) return false;
                const group = [...sc.querySelectorAll('flow-toggles')]
                  .find(g => (g.getAttribute('aria-label') || '') === 'Loại video');
                if (!group) return false;
                const items = [...group.querySelectorAll('mat-button-toggle')];
                const hit = items.find(t => n(t.innerText).includes(label));
                return !!(hit && hit.classList.contains('mat-button-toggle-checked'));
              }""",
                sub_label,
            )
        )

    def _ensure_ui_video_frames_mode(self, page: Any, target_aspect: str) -> None:
        """Backwards-compatible wrapper: Video → Khung hình → 8s → target_aspect → x1."""
        chip = self._ensure_ui_video_mode(page, sub_mode="frames", target_aspect=target_aspect)
        btn = page.query_selector("button.settings-trigger-button")
        html = (btn.inner_html() if btn else "") or ""
        if "Video" not in chip and "videocam" not in html:
            raise PageInteractionError(
                f"Không chuyển được composer sang chế độ Video (hiện tại: {chip!r})."
            )
        self._log("info", f"Composer ở chế độ Video: {chip!r}")

    def _ensure_recaptcha_ready(self, bridge: FlowBridge, active_pid: str, timeout_s: float = 12.0) -> None:
        """Ensure Flow's reCAPTCHA Enterprise service (`_.NK` / `xZbWve` / `grecaptcha.enterprise.execute`) is ready
        and that the page is not left in a dirty post-blocked state before capturing `eb1hJf`.
        """
        check_js = """(() => {
            const w = window;
            const siteKey = (w.WIZ_global_data && w.WIZ_global_data.xZbWve) ? String(w.WIZ_global_data.xZbWve) : '';
            const hasExec = !!(w.grecaptcha && w.grecaptcha.enterprise && typeof w.grecaptcha.enterprise.execute === 'function');
            const dirtyHook = !!(w.__videoHook && w.__videoHook.blocked);
            const hasComposer = !!document.querySelector('div.ProseMirror');
            return {siteKey: siteKey, hasExec: hasExec, dirtyHook: dirtyHook, hasComposer: hasComposer};
        })()"""

        st = bridge.eval_json(check_js) or {}
        if st.get("dirtyHook") or not st.get("siteKey"):
            self._log("info", "Làm mới trang dự án Flow để khởi tạo sạch phiên reCAPTCHA Enterprise...")
            if active_pid and f"/project/{active_pid}" not in (bridge.page.url or ""):
                try:
                    bridge.page.goto(
                        f"https://flow.google.com/project/{active_pid}",
                        wait_until="domcontentloaded",
                        timeout=bridge.page_timeout_ms,
                    )
                    time.sleep(4.5)
                except Exception:
                    bridge.reload(settle_s=4.5)
            else:
                bridge.reload(settle_s=4.5)

        t0 = time.time()
        reloaded = False
        while time.time() - t0 < timeout_s:
            st = bridge.eval_json(check_js) or {}
            if st.get("siteKey") and st.get("hasExec") and st.get("hasComposer") and not st.get("dirtyHook"):
                return
            if not reloaded and (time.time() - t0 > 5.0):
                reloaded = True
                self._log("info", "reCAPTCHA Enterprise chưa sẵn sàng sau 5s, đang reload lại trang dự án...")
                bridge.reload(settle_s=4.5)
            time.sleep(0.5)

    def _cleanup_failed_tiles_in_dom(self, page: Any) -> None:
        """Remove any stale 'Không thành công' error tiles from the project grid."""
        try:
            page.evaluate("""() => {
                const tiles = Array.from(document.querySelectorAll('flow-grid-tile-container, flow-tile-container, [class*="tile"], [class*="card"]'))
                    .filter(el => el.innerText && (
                        el.innerText.includes('Không thành công') ||
                        el.innerText.includes('Unsuccessful') ||
                        el.innerText.includes('vi phạm chính sách')
                    ));
                for (const t of tiles) {
                    const delBtn = Array.from(t.querySelectorAll('button')).find(b => {
                        const txt = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase();
                        return txt.includes('delete') || txt.includes('xoá') || txt.includes('xóa');
                    });
                    if (delBtn) delBtn.click();
                }
            }""")
        except Exception:
            pass
