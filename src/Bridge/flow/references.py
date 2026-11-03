"""Reference-image attach for :class:`FlowBridge` (synthetic paste / file input uploads)."""

from __future__ import annotations

import base64
import time
from pathlib import Path

from .common import PageInteractionError, jitter


class ReferenceMixin:
    """Attach local images to the composer and wait for the app's own upload to finish."""

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

    # Observed live (2026-10-28, scratch probe): Flow's project composer has NO
    # <input type=file>. A synthetic ClipboardEvent('paste') carrying the File on
    # div.ProseMirror makes the app mount a <flow-image-ingredient-chip>, show an
    # "N%" upload counter, call maseQ (upload) and finally swap the chip to a
    # signed flow-content.google image with aria-busy="false".
    _CHIP_STATE_JS = (
        "(() => { const chips = Array.from(document.querySelectorAll('flow-image-ingredient-chip')); "
        "const last = chips.length ? chips[chips.length - 1] : null; "
        "const btn = last ? last.querySelector('button') : null; "
        "const img = last ? last.querySelector('img') : null; "
        "const txt = last ? String(last.innerText || '') : ''; "
        "const m = txt.match(/(\\d{1,3})\\s?%/); "
        "return {chips: chips.length, busy: btn ? btn.getAttribute('aria-busy') === 'true' : null, "
        "src: img ? String(img.src || '').slice(0, 24) : '', pct: m ? parseInt(m[1], 10) : null}; })()"
    )

    _PASTE_JS = (
        "([b64, fname, mime]) => { const bin = atob(b64); const arr = new Uint8Array(bin.length); "
        "for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i); "
        "const file = new File([arr], fname, {type: mime}); const dt = new DataTransfer(); dt.items.add(file); "
        "const pm = document.querySelector('div.ProseMirror') || document.body; pm.focus(); "
        "pm.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true, clipboardData: dt})); }"
    )

    def clear_reference_chips(self) -> int:
        """Remove ingredient chips left from a previous attach (best effort). Returns chips remaining."""
        for _ in range(6):
            st = self.eval_json(self._CHIP_STATE_JS) or {}
            if not int(st.get("chips") or 0):
                return 0
            btn = self.page.query_selector(
                "flow-image-ingredient-chip .hover-icon-overlay, flow-image-ingredient-chip button"
            )
            if not btn:
                break
            try:
                btn.click(force=True)
            except Exception:  # noqa: BLE001
                break
            time.sleep(0.5)
        st = self.eval_json(self._CHIP_STATE_JS) or {}
        return int(st.get("chips") or 0)

    def attach_reference_paste(
        self,
        file_path: str | Path,
        timeout_s: float = 90.0,
        settle_s: float = 3.0,
        clear_existing: bool = True,
    ) -> dict:
        """Upload a reference image via synthetic paste, wait until upload is 100% done, then +settle_s.

        Completion = a new ingredient chip whose upload counter is gone (or hit 100%),
        ``aria-busy`` is not true and its <img> is a real URL. Only then does the caller type the prompt.
        """
        path = Path(file_path)
        if not path.is_file():
            raise PageInteractionError(f"Không thấy file ảnh tham chiếu: {path}")
        left = self.clear_reference_chips() if clear_existing else 0
        before = int((self.eval_json(self._CHIP_STATE_JS) or {}).get("chips") or 0)
        mime = {".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower(), "image/jpeg")
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        self.page.evaluate(self._PASTE_JS, [b64, path.name, mime])
        self._log(f"paste reference {path.name} -> composer (chips before={before}, left={left})")

        t0 = time.time()
        seen_pct = -1
        seen_chip = False
        done = False
        while time.time() - t0 < timeout_s:
            st = self.eval_json(self._CHIP_STATE_JS) or {}
            chips = int(st.get("chips") or 0)
            pct = st.get("pct")
            if chips > before:
                seen_chip = True
            if isinstance(pct, int):
                if pct != seen_pct and pct % 20 == 0:
                    self._log(f"upload ảnh tham chiếu: {pct}%")
                seen_pct = max(seen_pct, pct)
            if (
                seen_chip
                and chips > before
                and pct is None
                and st.get("busy") is not True
                and str(st.get("src") or "").startswith(("http", "blob:"))
            ):
                done = True
                break
            time.sleep(0.4)
        if not done:
            raise PageInteractionError(
                f"Upload ảnh tham chiếu chưa hoàn tất sau {timeout_s:.0f}s (chip={seen_chip}, max%={seen_pct})."
            )
        self._log(f"upload xong sau {time.time() - t0:.1f}s (max {seen_pct}%) — chờ thêm {settle_s:.0f}s rồi gửi prompt")
        if settle_s > 0:
            time.sleep(settle_s)
        return {"input_index": -1, "accept": "paste", "preview_seen": True, "inputs": [], "method": "paste",
                "upload_s": round(time.time() - t0, 1)}

    def attach_reference_pastes(
        self,
        file_paths: list[str | Path],
        timeout_per_file_s: float = 90.0,
        settle_s: float = 3.0,
    ) -> list[dict]:
        """Upload multiple reference images via paste sequentially and wait for all to settle."""
        valid_paths = [Path(p) for p in file_paths if Path(p).is_file()]
        if not valid_paths:
            return []
        self.clear_reference_chips()
        results = []
        for idx, p in enumerate(valid_paths):
            info = self.attach_reference_paste(
                p,
                timeout_s=timeout_per_file_s,
                settle_s=0.5,
                clear_existing=False,
            )
            results.append(info)
        if settle_s > 0:
            time.sleep(settle_s)
        return results

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
            # Flow's composer has no file input (observed): use the paste upload path.
            return self.attach_reference_paste(path)
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
