"""Composer / Generate-button driving for :class:`FlowBridge` (DOM selectors, typing, mode guards)."""

from __future__ import annotations

import re
import time
from typing import Optional

from .common import PageInteractionError, jitter


class ComposerMixin:
    """Prompt typing, image-mode/aspect/model/count selection and the guarded Generate click."""

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

    def prompt_value(self) -> str:
        """Read current text inside the ProseMirror composer ('' if empty or missing)."""
        txt = self._eval(
            "(() => { try { const ed = document.querySelector('div.ProseMirror'); return ed ? String(ed.innerText || '').trim() : ''; } catch (e) { return ''; } })()",
            retries=2,
        )
        return str(txt or "").strip()

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
            clean_prompt = re.sub(r"\s+", " ", prompt[:60]).strip().lower()
            clean_txt = re.sub(r"\s+", " ", str(txt or "")).strip().lower()
            prefix = clean_prompt[:20]
            if (prefix and prefix in clean_txt) or (
                len(clean_txt) >= 20
                and any(w in clean_txt for w in re.findall(r"\b[a-zA-Z]{4,}\b", clean_prompt))
            ):
                self._log("prompt typed & verified in composer")
                return
            self._eval(
                "(() => { try { const ev = new KeyboardEvent('keydown', {key: 'Escape', keyCode: 27, bubbles: true}); document.dispatchEvent(ev); } catch (x) {} return true; })()"
            )
            time.sleep(1.0)
        raise PageInteractionError("Không nhập được prompt vào composer sau nhiều lần thử.")

    def ensure_ui_image_mode(
        self,
        target_aspect: Optional[str] = None,
        *,
        model_label: Optional[str] = None,
        count: int = 1,
    ) -> bool:
        """Ensure composer UI is in Image Mode ('Hình ảnh' / 'Image') with target_aspect, model and count.

        Prevents the critical issue where a previous video run leaves composer in Video mode,
        causing subsequent image nodes to trigger video generation instead of image generation.

        Also selects the composer model (the app closes the popover after a model pick, so
        every option group needs its own popover open) and the batch count, because the
        captured request carries whichever options the UI is showing.
        """
        if self.page is None:
            return False
        page = self.page
        want_count = max(1, int(count or 1))
        try:
            settings_btn = page.query_selector("button.settings-trigger-button")
            if not settings_btn:
                settings_btn = page.query_selector(
                    '//button[contains(@class, "settings-trigger") or contains(@class, "settings-btn")]'
                )
            if not settings_btn:
                self._log("Không tìm thấy button.settings-trigger-button trên composer (bỏ qua điều chỉnh chế độ)")
                return False

            btn_txt = (settings_btn.inner_text() or "").strip()
            btn_html = settings_btn.inner_html() or ""
            is_video = "Video" in btn_txt or "videocam" in btn_html

            aspect_ok = True
            if target_aspect:
                norm_aspect = target_aspect.replace(":", "_")
                aspect_ok = (target_aspect in btn_txt) or (f"crop_{norm_aspect}" in btn_html)

            model_ok = True
            if model_label:
                model_ok = model_label.replace("🍌 ", "") in btn_txt or "🍌" in btn_txt
            count_ok = f"x{want_count}" in btn_txt

            if not is_video and aspect_ok and count_ok and model_ok:
                self._log(f"UI đã ở chế độ Hình ảnh ({btn_txt})")
                return True

            self._log(f"Chuyển UI composer sang chế độ Hình ảnh (trước đó: {btn_txt!r})...")
            settings_btn.click(force=True)
            page.wait_for_timeout(500)

            # 1. Switch to Image Mode Tab ("Hình ảnh" / "Image")
            img_tabs = [
                '//button[@role="radio" and (contains(., "Hình ảnh") or contains(., "Image") or contains(., "image"))]',
                '//button[contains(@class, "tab") and (contains(., "Hình ảnh") or contains(., "Image"))]',
                '//button[contains(., "Hình ảnh") or contains(., "Image")]',
            ]
            for xp in img_tabs:
                r_btn = page.query_selector(xp)
                if r_btn:
                    if r_btn.get_attribute("aria-checked") != "true":
                        r_btn.click(force=True)
                        page.wait_for_timeout(350)
                    break

            # 2. Select Target Aspect Ratio (e.g. "16:9", "9:16", "1:1", "4:3", "3:4")
            if target_aspect:
                aspect_selectors = [
                    f'//button[@role="radio" and (contains(., "{target_aspect}") or contains(@aria-label, "{target_aspect}"))]',
                    f'//button[contains(., "{target_aspect}")]',
                ]
                for axp in aspect_selectors:
                    asp_btn = page.query_selector(axp)
                    if asp_btn:
                        if asp_btn.get_attribute("aria-checked") != "true":
                            asp_btn.click(force=True)
                            page.wait_for_timeout(250)
                        break

            # 3. Batch Count ("x1".."x4") — the app's own batch length decides how many
            #    specs our payload carries, so the UI must agree with `count`.
            x_count_selectors = [
                f'//button[@role="radio" and normalize-space(.)="x{want_count}"]',
                f'//button[normalize-space(.)="x{want_count}"]',
            ]
            for x_xp in x_count_selectors:
                x_btn = page.query_selector(x_xp)
                if x_btn:
                    if x_btn.get_attribute("aria-checked") != "true":
                        x_btn.click(force=True)
                        page.wait_for_timeout(250)
                    break

            # 4. Close backdrop popup
            backdrop = page.query_selector(".cdk-overlay-backdrop")
            if backdrop:
                backdrop.click(force=True)
            else:
                page.keyboard.press("Escape")
            page.wait_for_timeout(400)

            # 5. Model — Angular closes the popover after a pick, so this needs its own open.
            if model_label:
                self._select_image_model(model_label)

            # Verification
            new_txt = (settings_btn.inner_text() or "").strip()
            self._log(f"UI composer đã chuyển sang: {new_txt}")
            return True
        except Exception as e:
            self._log(f"Lỗi khi điều chỉnh UI sang chế độ Hình ảnh: {e}")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False

    def _select_image_model(self, model_label: str) -> bool:
        """Pick an image model in the composer's model dropdown (label like 'Nano Banana Pro')."""
        page = self.page
        if page is None:
            return False
        target = model_label.replace("🍌 ", "").strip()
        try:
            btn = page.query_selector("button.settings-trigger-button")
            if not btn:
                return False
            btn.click(force=True)
            page.wait_for_timeout(500)
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
                page.keyboard.press("Escape")
                return False
            page.wait_for_timeout(450)
            picked = page.evaluate(
                r"""(label) => {
                const n = s => (s || '').replace(/🍌/g, '').replace(/\s+/g, ' ').trim();
                const ps = [...document.querySelectorAll('.cdk-overlay-pane')].filter(p => p.offsetWidth || p.offsetHeight);
                const p = ps[ps.length - 1];
                if (!p) return false;
                const el = [...p.querySelectorAll('[role="menuitem"], button.mat-mdc-menu-item, button')]
                  .find(e => n(e.innerText) === label);
                if (!el) return false;
                el.click();
                return true;
              }""",
                target,
            )
            page.wait_for_timeout(450)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            if not picked:
                self._log(f"Không chọn được model ảnh {target!r} trên composer")
            return bool(picked)
        except Exception as e:  # noqa: BLE001
            self._log(f"Lỗi chọn model ảnh ({target}): {e}")
            return False

    _GEN_BTN_JS = (
        "(() => { const b = document.querySelector('button.generate-icon-button'); if (!b) return null; "
        "const r = b.getBoundingClientRect(); "
        "return {disabled: !!b.disabled, x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)}; })()"
    )

    def composer_mode(self) -> Optional[str]:
        """Return the composer's current generation mode: "video", "image" or None (unknown).

        Detection is based on `button.settings-trigger-button`:
          - Video mode: 'Video · 720p · 8s ...' / `videocam` icon.
          - Image mode: '<model name> crop_9_16 x1' (e.g. 'Nano Banana 2.1').
        """
        if self.page is None:
            return None
        try:
            s_btn = self.page.query_selector("button.settings-trigger-button")
            if not s_btn:
                return None
            txt = (s_btn.inner_text() or "").strip()
            html = s_btn.inner_html() or ""
            if "Video" in txt or "videocam" in html:
                return "video"
            return "image"
        except Exception as e:  # noqa: BLE001
            self._log(f"composer_mode probe error: {e}")
            return None

    def click_generate(
        self,
        timeout_s: float = 8.0,
        target_aspect: Optional[str] = None,
        expected_mode: str = "image",
    ) -> int:
        """Click the composer's Generate button, guarded by the expected generation mode.

        expected_mode="image": if the composer is left in Video mode, auto-switch to Image mode
            (and refuse to click if the switch did not take effect).
        expected_mode="video": NEVER switch modes; refuse to click unless the composer is
            verifiably in Video mode. (A decoy click in Image mode mints a reCAPTCHA token for the
            image action -> eb1hJf rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY, and may start an
            unwanted image generation.)
        """
        if expected_mode not in ("image", "video"):
            raise ValueError(f"expected_mode phải là 'image' hoặc 'video', nhận: {expected_mode!r}")

        mode = self.composer_mode()
        if expected_mode == "video":
            if mode != "video":
                raise PageInteractionError(
                    f"Composer đang ở chế độ {mode or 'không xác định'} thay vì Video — "
                    "từ chối click Generate (tránh tạo nhầm ảnh)."
                )
        elif mode == "video":
            self._log("Phát hiện UI vẫn ở chế độ Video trước khi Generate ảnh -> Tự động chuyển về Hình ảnh")
            self.ensure_ui_image_mode(target_aspect)
            if self.composer_mode() == "video":
                raise PageInteractionError(
                    "Không chuyển được composer sang chế độ Hình ảnh — từ chối click Generate (tránh tạo nhầm video)."
                )

        deadline = time.time() + timeout_s
        btn = None
        while time.time() < deadline:
            btn = self.eval_json(self._GEN_BTN_JS)
            if btn and not btn.get("disabled"):
                break
            time.sleep(0.5)
        if not (btn and not btn.get("disabled")):
            raise PageInteractionError("Nút Generate không tìm thấy hoặc bị disabled.")
        # Last-moment re-check: the mode must not have drifted while waiting for the button.
        final_mode = self.composer_mode()
        if final_mode is not None and final_mode != expected_mode:
            raise PageInteractionError(
                f"Composer đổi sang chế độ {final_mode} ngay trước khi Generate (mong đợi {expected_mode}) — hủy click."
            )
        self.page.mouse.click(btn["x"], btn["y"])
        ts = int(time.time() * 1000)
        self._log(f"generate clicked @ {ts} (mode={final_mode or expected_mode})")
        return ts
