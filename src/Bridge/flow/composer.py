"""Composer / Generate-button driving for :class:`FlowBridge` (DOM selectors, typing, mode guards)."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Optional, Union

from .common import PageInteractionError, jitter


@dataclass
class TextSegment:
    text: str

    def __eq__(self, other: object) -> bool:
        return other.__class__.__name__ == "TextSegment" and getattr(other, "text", None) == self.text


@dataclass
class MentionSegment:
    alias_name: str
    media_id: str

    def __eq__(self, other: object) -> bool:
        return (
            other.__class__.__name__ == "MentionSegment"
            and getattr(other, "alias_name", None) == self.alias_name
            and getattr(other, "media_id", None) == self.media_id
        )


def parse_prompt_segments(
    prompt: str,
    refs: list[dict[str, Any]],
) -> list[Union[TextSegment, MentionSegment]]:
    """Parse prompt into interleaved TextSegment and MentionSegment items.

    Maps:
    - Index 0: `Image 1`, `{{@model}}`, `@model`, or direct `alias_name` -> refs[0]
    - Index 1: `Image 2`, `{{@garment}}`, `@garment`, or direct `alias_name` -> refs[1]
    - Index 2: `Image 3`, `{{@scene}}`, `@scene`, or direct `alias_name` -> refs[2]
    - Index >= 3: `Image {k}`, `{{@ref{k}}}`, `@ref{k}` -> refs[k-1]

    If any reference in `refs` is NOT mentioned anywhere in the prompt text,
    it is automatically prepended as a MentionSegment at the start of the list.
    """
    if not refs:
        return [TextSegment(prompt)] if prompt else []

    patterns: list[tuple[int, str]] = []
    for idx, ref in enumerate(refs):
        alias = ref.get("alias_name", "")
        sub_pats: list[str] = []
        k = idx + 1
        if idx == 0:
            sub_pats.extend([r"\{\{@model\}\}", r"@model\b", r"\bImage\s*1\b"])
        elif idx == 1:
            sub_pats.extend([r"\{\{@garment\}\}", r"@garment\b", r"\bImage\s*2\b"])
        elif idx == 2:
            sub_pats.extend([r"\{\{@scene\}\}", r"@scene\b", r"\bImage\s*3\b"])
        else:
            sub_pats.extend([rf"\{{\{{@ref{k}\}}\}}", rf"@ref{k}\b", rf"\bImage\s*{k}\b"])
        if alias:
            sub_pats.extend([rf"\{{\{{@{re.escape(alias)}\}}\}}", rf"@{re.escape(alias)}\b"])
        patterns.append((idx, "|".join(sub_pats)))

    combined = "|".join(f"(?P<REF_{idx}>{pat})" for idx, pat in patterns)

    segments: list[Union[TextSegment, MentionSegment]] = []
    used_indices: set[int] = set()
    last_end = 0

    if prompt:
        for m in re.finditer(combined, prompt, flags=re.IGNORECASE):
            start, end = m.span()
            if start > last_end:
                segments.append(TextSegment(prompt[last_end:start]))
            for idx in range(len(refs)):
                if m.group(f"REF_{idx}") is not None:
                    alias = refs[idx].get("alias_name", f"ref{idx+1}")
                    if idx not in used_indices:
                        # Only FIRST occurrence becomes a rich MentionSegment (chip in ProseMirror).
                        # This registers the asset into Google Flow's reference shelf (max 3 references).
                        segments.append(
                            MentionSegment(
                                alias_name=alias,
                                media_id=refs[idx].get("media_id", ""),
                            )
                        )
                        used_indices.add(idx)
                    else:
                        # Subsequent occurrences remain as clean plain text (@alias).
                        # This prevents duplicate mention chips which causes Google Flow
                        # backend to reject the request with [3] (INVALID_ARGUMENT).
                        segments.append(TextSegment(f"@{alias}"))
                    break
            last_end = end

        if last_end < len(prompt):
            segments.append(TextSegment(prompt[last_end:]))

    # Prepend any unused references
    prepends: list[Union[TextSegment, MentionSegment]] = []
    for idx in range(len(refs)):
        if idx not in used_indices:
            prepends.append(
                MentionSegment(
                    alias_name=refs[idx].get("alias_name", f"ref{idx+1}"),
                    media_id=refs[idx].get("media_id", ""),
                )
            )
            if prompt or segments or idx < len(refs) - 1:
                prepends.append(TextSegment(" "))

    final_raw = prepends + segments
    # Merge consecutive TextSegments and eliminate empties
    out: list[Union[TextSegment, MentionSegment]] = []
    for s in final_raw:
        if isinstance(s, TextSegment):
            if not s.text:
                continue
            if out and isinstance(out[-1], TextSegment):
                out[-1].text += s.text
            else:
                out.append(s)
        else:
            out.append(s)
    return out


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
                self._eval("(() => { try { "
            "const chips = document.querySelectorAll('flow-image-ingredient-chip, flow-ingredient-chip, .reference-ingredient-chip'); "
            "if (!chips.length) { document.execCommand('selectAll'); } "
            "} catch (e) {} return true; })()")
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

    def _paste_text_segment(self, text: str) -> None:
        """Paste a text chunk into ProseMirror using synthetic ClipboardEvent."""
        if not text:
            return
        js_paste = """([text]) => {
            const pm = document.querySelector('div.ProseMirror');
            if (!pm) return false;
            pm.focus();
            const dt = new DataTransfer();
            dt.setData('text/plain', text);
            const ev = new ClipboardEvent('paste', {
                bubbles: true,
                cancelable: true,
                clipboardData: dt
            });
            const dispatched = pm.dispatchEvent(ev);
            if (dispatched) {
                try {
                    document.execCommand('insertText', false, text);
                } catch (e) {}
            }
            return true;
        }"""
        try:
            self.page.evaluate(js_paste, [text])
        except Exception as exc:
            self._log(f"Paste text segment error: {exc}, fallback to Input.insertText")
            try:
                self._cdp.send("Input.insertText", {"text": text})
            except Exception:
                pass

    def type_prompt_with_mentions(
        self,
        prompt: str,
        refs: list[dict[str, Any]],
        project_id: Optional[str] = None,
        registry: Optional[Any] = None,
    ) -> None:
        """Type a prompt into ProseMirror with chunked paste for text and @mention chips for references.
        
        Paced with explicit 2.0s sleep after each pasted chunk and each @mention.
        """
        if not refs:
            self.type_prompt(prompt)
            return

        segments = parse_prompt_segments(prompt, refs)
        if not segments:
            return

        pos = self.wait_composer()
        self.page.mouse.click(pos["x"], pos["y"])
        time.sleep(0.5)
        # Clear existing content cleanly using Ctrl+A + Backspace
        try:
            self.page.keyboard.press("Control+A")
            time.sleep(0.2)
            self.page.keyboard.press("Backspace")
            time.sleep(0.3)
        except Exception:
            pass

        for idx, seg in enumerate(segments):
            if isinstance(seg, TextSegment):
                if seg.text:
                    self._log(f"[Composer] Paste đoạn #{idx+1}: {repr(seg.text[:35])}...")
                    self._paste_text_segment(seg.text)
                    # Thời gian nghỉ sau mỗi lần paste đoạn là 2.0s theo yêu cầu
                    time.sleep(2.0)
            elif isinstance(seg, MentionSegment):
                self._log(f"[Composer] Chèn @mention #{idx+1}: @{seg.alias_name}")
                self._insert_mention(
                    seg.alias_name,
                    seg.media_id,
                    project_id=project_id,
                    registry=registry,
                    refs=refs,
                )
                # Thời gian nghỉ sau mỗi lần @mention là 2.0s theo yêu cầu
                time.sleep(2.0)

    def _insert_mention(
        self,
        alias_name: str,
        media_id: str,
        project_id: Optional[str] = None,
        registry: Optional[Any] = None,
        refs: Optional[list[dict[str, Any]]] = None,
        retry_on_stale: bool = True,
    ) -> bool:
        """Insert a single @mention chip into ProseMirror by searching alias_name in the popover.
        
        Paced with explicit 1.0s wait intervals to eliminate race conditions.
        """
        page = self.page
        if not page:
            return False

        # 1. Type '@' to open the popover, then WAIT 1.0s for popover to render
        try:
            page.keyboard.type("@")
        except Exception:
            self._cdp.send("Input.insertText", {"text": "@"})
        time.sleep(1.0)

        # 2. Wait for flow-add-menu-popover-content and input.search-input
        search_input = page.locator("flow-add-menu-popover-content input.search-input")
        try:
            search_input.wait_for(state="visible", timeout=4000)
        except Exception:
            add_trigger = page.locator('button.add-menu-trigger, button[aria-label="Thêm thành phần vào ô nhập câu lệnh"]')
            if add_trigger.is_visible():
                add_trigger.click(force=True)
                time.sleep(1.0)
            try:
                search_input.wait_for(state="visible", timeout=3000)
            except Exception as exc:
                self._log(f"Không mở được popover mention: {exc}")
                self._paste_text_segment(f"{alias_name} ")
                return False

        # 3. Fill alias_name into search input and WAIT 1.0s for filtering
        search_input.fill(alias_name)
        time.sleep(1.0)

        # 4. Check if matching item appears in virtual scroll
        matched_option = None
        opts = page.locator('flow-add-menu-asset-list button[role="option"].asset-item')
        count = opts.count()
        for idx in range(min(count, 12)):
            opt = opts.nth(idx)
            txt = (opt.locator(".asset-title").inner_text() or "").strip()
            if alias_name.lower() in txt.lower():
                matched_option = opt
                break

        if not matched_option and count > 0:
            first_txt = (opts.first.locator(".asset-title").inner_text() or "").strip()
            if alias_name.split("_")[-1] in first_txt or alias_name.split("_")[0] in first_txt:
                matched_option = opts.first

        if matched_option:
            matched_option.click(force=True)
            time.sleep(1.0)

            # If a detail pane opened with "Thêm vào câu lệnh":
            add_btn = page.locator('button.detail-add-to-prompt-btn, flow-add-menu-detail-pane button:has-text("Thêm vào câu lệnh")').first
            if add_btn.is_visible():
                add_btn.click(force=True)
                time.sleep(1.0)

            # Position cursor after chip and add trailing space
            page.keyboard.press("End")
            time.sleep(0.2)
            self._paste_text_segment(" ")
            time.sleep(0.3)
            return True

        # 5. Item not found in search results: close popover safely with Escape
        self._log(f"Không tìm thấy item [{alias_name}] trong popover mention")
        page.keyboard.press("Escape")
        time.sleep(0.5)

        # Safe fallback: do NOT press Backspace
        self._paste_text_segment(f"{alias_name} ")
        return False

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
