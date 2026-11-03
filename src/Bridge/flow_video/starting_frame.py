"""Starting-frame upload/attach for :class:`FlowVideoBridge` (synthetic paste -> `maseQ`, UI fallback)."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any, Optional

from ..flow_bridge import FlowBridge, parse_batchexecute_text
from .parsing import extract_media_records


class StartingFrameMixin:
    """Get an image into the video composer's "Bắt đầu" slot and learn its media id."""

    def upload_starting_frame_via_paste(
        self,
        bridge: FlowBridge,
        frame_path: Path,
        project_id: Optional[str] = None,
        timeout_s: float = 45.0,
    ) -> Optional[str]:
        """Upload & attach starting frame via synthetic ClipboardEvent('paste') (`maseQ` RPC).

        Returns `starting_frame_media_id` (UUIDv4) directly from `maseQ`'s JSON response
        once upload completes, or None if synthetic paste did not trigger `maseQ`.
        """
        page = bridge.page
        assert page is not None

        # Clear any existing starting frame chip first
        cancel_btn = page.query_selector(
            'flow-image-ingredient-chip button, '
            'flow-image-ingredient-chip [class*="cancel"], '
            'flow-image-ingredient-chip mat-icon:has-text("cancel"), '
            'flow-image-ingredient-chip .hover-icon-overlay'
        )
        if cancel_btn:
            cancel_btn.click(force=True)
            page.wait_for_timeout(400)

        bridge._eval("if (window.__videoHook) window.__videoHook.lastUpload = null;")

        mime = "image/png" if frame_path.suffix.lower() == ".png" else "image/jpeg"
        b64_data = base64.b64encode(frame_path.read_bytes()).decode("ascii")

        self._log("step", f"Đẩy starting frame {frame_path.name} qua sự kiện Paste (RPC maseQ)...")
        page.evaluate(
            """([b64, fname, mimeType]) => {
                const bin = atob(b64);
                const arr = new Uint8Array(bin.length);
                for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
                const file = new File([arr], fname, {type: mimeType});
                const dt = new DataTransfer();
                dt.items.add(file);
                const pm = document.querySelector('div.ProseMirror') || document.body;
                pm.focus();
                pm.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true, clipboardData: dt}));
            }""",
            [b64_data, frame_path.name, mime],
        )

        t0 = time.time()
        while time.time() - t0 < timeout_s:
            up = bridge.eval_json(
                """(() => {
                    const u = window.__videoHook && window.__videoHook.lastUpload;
                    return (u && u.ready) ? {status: u.status, resp: u.resp} : null;
                })()"""
            )
            if up and up.get("resp"):
                parsed = parse_batchexecute_text(up["resp"])
                if parsed.get("ok"):
                    records = extract_media_records(parsed.get("data"), project_id=project_id)
                    if not records:
                        records = extract_media_records(parsed.get("data"), project_id=None)
                    if records:
                        media_id = str(records[0][0]).lower()
                        self._log("info", f"maseQ upload hoàn tất sau {time.time() - t0:.1f}s -> media_id={media_id}")
                        # Give Angular 600ms to mount the chip in composer state
                        page.wait_for_timeout(600)
                        return media_id
                break
            time.sleep(0.25)

        return None

    def attach_video_starting_frame(
        self,
        bridge: FlowBridge,
        frame_path: Path,
    ) -> bool:
        """Attach an image as the starting frame for video generation in Flow."""
        self._log("step", f"Đính kèm starting frame cho video: {frame_path.name}")
        media_id = self.upload_starting_frame_via_paste(bridge, frame_path)
        if media_id:
            return True
        info = bridge.attach_reference(frame_path)
        return bool(info.get("preview_seen"))

    def attach_video_ingredient_via_paste(
        self,
        bridge: FlowBridge,
        file_path: Path,
        settle_s: float = 0.5,
    ) -> dict:
        """Attach a reference image as an ingredient chip via synthetic paste."""
        return bridge.attach_reference_paste(
            file_path,
            timeout_s=90.0,
            settle_s=settle_s,
            clear_existing=False,
        )

    def attach_video_ingredients(
        self,
        bridge: FlowBridge,
        file_paths: list[Path],
        settle_s: float = 3.0,
    ) -> list[dict]:
        """Attach multiple reference images as ingredients sequentially."""
        bridge.clear_reference_chips()
        results = []
        n = len(file_paths)
        if n == 1:
            self._log("step", f"Đính ảnh tham chiếu thành phần: {file_paths[0].name} (chờ upload 100% + {settle_s:.0f}s)...")
            res = self.attach_video_ingredient_via_paste(bridge, file_paths[0], settle_s=settle_s)
            self._log("info", f"Upload ảnh tham chiếu thành phần hoàn tất ({res.get('upload_s', 0)}s) + {settle_s:.0f}s chờ ổn định")
            return [res]

        self._log("step", f"Đính {n} ảnh tham chiếu thành phần lần lượt...")
        for idx, p in enumerate(file_paths, 1):
            self._log("step", f"Đính ảnh tham chiếu thành phần #{idx}/{n}: {p.name}...")
            res = self.attach_video_ingredient_via_paste(bridge, p, settle_s=0.5)
            self._log("info", f"Upload ảnh #{idx} ({p.name}) hoàn tất ({res.get('upload_s', 0)}s)")
            results.append(res)
        if settle_s > 0:
            self._log("info", f"Chờ tất cả ảnh tham chiếu thành phần ổn định ({settle_s:.0f}s)...")
            time.sleep(settle_s)
        return results

    def _attach_starting_frame_ui_fallback(self, page: Any, frame_p: Path) -> None:
        """Fallback UI attachment when synthetic paste does not mount flow-image-ingredient-chip (bilingual VI/EN)."""
        start_btn = page.query_selector('//button[contains(., "Bắt đầu") or contains(., "Start")]')
        if start_btn:
            start_btn.click(force=True)
            page.wait_for_timeout(700)
            upload_btn = page.query_selector(
                ".cdk-overlay-pane .sidebar-upload-btn, flow-add-menu-popover-content .sidebar-upload-btn"
            )
            if upload_btn and frame_p.is_file():
                try:
                    with page.expect_file_chooser(timeout=5000) as fc:
                        upload_btn.click(force=True)
                    fc.value.set_files([str(frame_p)])
                    page.wait_for_timeout(2000)
                except Exception as e:
                    self._log("warn", f"Upload frame UI fallback: {e}")

            t_up = time.time()
            while time.time() - t_up < 90.0:
                if page.query_selector("flow-image-ingredient-chip"):
                    break
                ready = page.evaluate("""() => {
                    const pane = document.querySelector('.cdk-overlay-pane, flow-add-menu-popover-content');
                    if (!pane) return false;
                    const firstItem = pane.querySelector('button.asset-item');
                    if (!firstItem) return false;
                    const txt = (firstItem.innerText || '').trim();
                    const uploading = txt.includes('Đang tải lên') || txt.toLowerCase().includes('uploading');
                    const thumb = firstItem.querySelector('img.asset-thumbnail-image, img[src^="http"]');
                    const spinner = pane.querySelector('mat-spinner, mat-progress-spinner, [role="progressbar"]');
                    return !!thumb && !uploading && !spinner;
                }""")
                if ready:
                    first_item = page.query_selector("button.asset-item")
                    if first_item:
                        first_item.click(force=True)
                        page.wait_for_timeout(700)
                    add_btn = page.query_selector(
                        'button.detail-add-to-prompt-btn:not([disabled]), '
                        'button:has-text("Thêm vào câu lệnh"):not([disabled]), '
                        'button:has-text("Add to prompt"):not([disabled])'
                    )
                    if add_btn and not page.query_selector("flow-image-ingredient-chip"):
                        add_btn.click(force=True)
                        page.wait_for_timeout(800)
                    break
                page.wait_for_timeout(1000)
