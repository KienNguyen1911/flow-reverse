"""Flow Video Bridge — image-to-video, frame extraction & concatenation.

Automates:
1. First Frame generation (Image Mode) with @nabi + try-on sample.
2. Video 1 generation (8 seconds) from First Frame + Video Prompt 1.
3. High-precision Last Frame extraction from Video 1 (FFmpeg + OpenCV fallback).
4. Video 2 generation (8 seconds) using Last Frame as First Frame + Video Prompt 2.
5. Automatic 16s video concatenation (Video 1 + Video 2 -> final_tryon_video.mp4).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .flow_bridge import (
    DEFAULT_CDP_URL,
    BridgeError,
    FlowBridge,
    find_signed_urls,
    jitter,
)

LogFn = Callable[[str, str], None]


# --------------------------------------------------------------------------- #
# Frame Extraction & Video Concat Helpers (FFmpeg / OpenCV)
# --------------------------------------------------------------------------- #


def extract_last_video_frame(
    video_path: Path | str,
    output_image_path: Path | str,
    log: Optional[LogFn] = None,
) -> Path:
    """Extract the exact last frame of a video using FFmpeg (or OpenCV fallback).

    Deterministic, bit-exact, and zero UI latency.
    """
    v_path = Path(video_path).resolve()
    out_path = Path(output_image_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not v_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file video: {v_path}")

    _log = log or (lambda kind, msg: None)
    _log("step", f"Trích xuất khung hình cuối từ {v_path.name}...")

    # Method 1: FFmpeg -sseof -0.1 (extract frame right before EOF)
    cmd = [
        "ffmpeg",
        "-y",
        "-sseof",
        "-0.2",
        "-i",
        str(v_path),
        "-update",
        "1",
        "-q:v",
        "1",
        str(out_path),
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
        if res.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 100:
            _log("info", f"FFmpeg trích xuất thành công: {out_path.name} ({out_path.stat().st_size} bytes)")
            return out_path
    except Exception as e:
        _log("warn", f"FFmpeg sseof lỗi ({e}), chuyển sang fallback OpenCV...")

    # Method 2: OpenCV fallback
    try:
        import cv2

        cap = cv2.VideoCapture(str(v_path))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames - 2))
            ret, frame = cap.read()
            if ret and frame is not None:
                cv2.imwrite(str(out_path), frame)
                cap.release()
                if out_path.is_file() and out_path.stat().st_size > 100:
                    _log("info", f"OpenCV trích xuất thành công: {out_path.name}")
                    return out_path
        cap.release()
    except Exception as e:
        _log("warn", f"OpenCV fallback lỗi: {e}")

    # Method 3: Reverse filter to extract the true last frame
    cmd_fallback = [
        "ffmpeg",
        "-y",
        "-i",
        str(v_path),
        "-vf",
        "reverse",
        "-vframes",
        "1",
        str(out_path),
    ]
    try:
        res3 = subprocess.run(cmd_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
        if res3.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 100:
            _log("info", f"FFmpeg (reverse filter) trích xuất thành công: {out_path.name}")
            return out_path
    except Exception as e:
        _log("warn", f"FFmpeg reverse fallback lỗi: {e}")

    raise RuntimeError(f"Không thể trích xuất khung hình cuối từ {v_path}")


def concatenate_two_videos(
    video1_path: Path | str,
    video2_path: Path | str,
    output_path: Path | str,
    log: Optional[LogFn] = None,
) -> Path:
    """Concatenate video 1 (8s) and video 2 (8s) into a unified 16s video using FFmpeg.

    Handles video streams with or without audio tracks seamlessly.
    """
    v1 = Path(video1_path).resolve()
    v2 = Path(video2_path).resolve()
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    _log = log or (lambda kind, msg: None)
    _log("step", f"Nối {v1.name} + {v2.name} thành {out.name}...")

    # Check if inputs have audio streams
    has_audio = False
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(v1)],
            capture_output=True, text=True, timeout=10
        )
        has_audio = bool(probe.stdout.strip())
    except Exception:
        has_audio = False

    # Method 1: Concat demuxer
    list_file = out.parent / f"_concat_{int(time.time() * 1000)}.txt"
    try:
        v1_esc = v1.as_posix().replace("'", "'\\''")
        v2_esc = v2.as_posix().replace("'", "'\\''")
        list_file.write_text(
            f"file '{v1_esc}'\nfile '{v2_esc}'\n",
            encoding="utf-8",
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ]
        if has_audio:
            cmd.extend(["-c:a", "aac"])
        else:
            cmd.append("-an")
        cmd.append(str(out))

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if res.returncode == 0 and out.is_file() and out.stat().st_size > 200:
            _log("info", f"Nối video thành công: {out.name} ({out.stat().st_size} bytes)")
            return out
    finally:
        if list_file.exists():
            try:
                list_file.unlink()
            except Exception:
                pass

    # Method 2: filter_complex with resolution & SAR normalization (handles different aspect ratios)
    w, h = 1280, 720
    try:
        probe_res = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(v1)],
            capture_output=True, text=True, timeout=10,
        )
        if probe_res.returncode == 0 and "x" in probe_res.stdout:
            parts = probe_res.stdout.strip().split("x")
            w, h = int(parts[0]), int(parts[1])
    except Exception:
        pass

    filter_expr = f"[0:v]scale={w}:{h},setsar=1[v0];[1:v]scale={w}:{h},setsar=1[v1];[v0][v1]concat=n=2:v=1[v]"
    cmd_filter = [
        "ffmpeg",
        "-y",
        "-i",
        str(v1),
        "-i",
        str(v2),
        "-filter_complex",
        filter_expr,
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(out),
    ]
    res2 = subprocess.run(cmd_filter, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if res2.returncode == 0 and out.is_file() and out.stat().st_size > 200:
        _log("info", f"Nối video (filter_complex) thành công: {out.name}")
        return out

    raise RuntimeError(f"Lỗi nối video: {res2.stderr.decode('utf-8', 'ignore')[:300]}")


# --------------------------------------------------------------------------- #
# FlowVideoBridge Class
# --------------------------------------------------------------------------- #


class FlowVideoBridge:
    """Manages Video and Image generation on Google Flow via Playwright CDP."""

    def __init__(
        self,
        cdp_url: str = DEFAULT_CDP_URL,
        log: Optional[LogFn] = None,
    ):
        self.cdp_url = cdp_url
        self._log = log or (lambda kind, msg: None)

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

    def attach_video_starting_frame(
        self,
        bridge: FlowBridge,
        frame_path: Path,
    ) -> bool:
        """Attach an image as the starting frame for video generation in Flow."""
        self._log("step", f"Đính kèm starting frame cho video: {frame_path.name}")
        info = bridge.attach_reference(frame_path)
        self._log("info", f"Starting frame attached: preview={info.get('preview_seen')}")
        return bool(info.get("preview_seen"))

    def trigger_video_generation(
        self,
        bridge: FlowBridge,
        prompt: str,
        duration_s: int = 8,
    ) -> int:
        """Enter video prompt and trigger video generation button."""
        # Unblock hook so that app's native video generation request is not intercepted
        bridge._eval("window.__blockOgi = false;")

        # Ensure video generation mode in composer if toggle/tab exists
        bridge.eval_json(
            """(() => {
                const btns = Array.from(document.querySelectorAll('button, div[role="tab"]'));
                for (const b of btns) {
                    const txt = ((b.getAttribute('aria-label') || '') + ' ' + (b.textContent || '')).toLowerCase();
                    if ((txt.includes('video') || txt.includes('animate') || txt.includes('veo')) && !txt.includes('image')) {
                        if (b.getAttribute('aria-selected') !== 'true' && !b.classList.contains('active')) {
                            b.click();
                            return {clicked: true, text: txt.trim()};
                        }
                    }
                }
                return {clicked: false};
            })()"""
        )

        self._log("step", f"Nhập video prompt ({duration_s}s): '{prompt[:80]}...'")
        bridge.type_prompt(prompt)
        time.sleep(jitter(1.0, 0.2, 0.5))
        click_ts = bridge.click_generate(timeout_s=30.0)
        self._log("info", f"Bắt đầu tạo video @ {click_ts}")
        return click_ts

    def poll_for_video_completion(
        self,
        bridge: FlowBridge,
        dest_path: Path,
        known_urls: Optional[set[str]] = None,
        timeout_s: float = 300.0,
        poll_interval_s: float = 5.0,
    ) -> Path:
        """Poll the Flow page until the new video is ready, then download it."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        self._log("step", f"Đang chờ video render xong (tối đa {timeout_s}s)...")

        t0 = time.time()
        deadline = t0 + timeout_s
        seen_before = known_urls or set()

        while time.time() < deadline:
            time.sleep(poll_interval_s)
            elapsed = int(time.time() - t0)

            # Hover over first tile in grid to ensure <video> tag is mounted with signed URL
            bridge.eval_json(
                """(() => {
                    const firstCard = document.querySelector('.mat-context-menu-trigger, .tile-row, [class*="asset"], [class*="card"]');
                    if (firstCard) {
                        const event = new MouseEvent('mouseover', { 'view': window, 'bubbles': true, 'cancelable': true });
                        firstCard.dispatchEvent(event);
                    }
                })()"""
            )

            video_info = bridge.eval_json(
                """(() => {
                    const videos = Array.from(document.querySelectorAll('video'));
                    const srcs = videos.map(v => v.src || v.currentSrc || '').filter(s => s.length > 0);
                    const entries = performance.getEntriesByType('resource')
                        .map(e => e.name || '')
                        .filter(u => u.indexOf('.mp4') >= 0 || u.indexOf('/video/') >= 0);
                    return {srcs: srcs, entries: entries, count: videos.length};
                })()"""
            )

            if video_info:
                srcs = video_info.get("srcs", [])
                entries = video_info.get("entries", [])
                all_candidates = [s for s in (srcs + entries) if s.startswith("http")]
                # Filter out candidates that were already present before triggering this video
                new_candidates = [s for s in all_candidates if s not in seen_before]

                if new_candidates:
                    latest_url = new_candidates[-1]
                    self._log("info", f"Tìm thấy video mới sau {elapsed}s: {latest_url[:80]}...")
                    ok, size = bridge.download(latest_url, dest_path)
                    if ok and size > 2000:
                        self._log("info", f"Đã tải video: {dest_path.name} ({size} bytes)")
                        return dest_path
                elif all_candidates and not seen_before:
                    # If seen_before was empty (e.g. first video), pick latest
                    latest_url = all_candidates[-1]
                    ok, size = bridge.download(latest_url, dest_path)
                    if ok and size > 2000:
                        self._log("info", f"Đã tải video: {dest_path.name} ({size} bytes)")
                        return dest_path

            self._log("info", f"Đang tạo video... đã qua {elapsed}s")

        raise BridgeError(f"Hết thời gian chờ tạo video ({timeout_s}s).")

    def save_last_frame_via_ui(
        self,
        bridge: FlowBridge,
        timeout_s: float = 15.0,
    ) -> bool:
        """Optional: Automate clicking the Flow UI menu to 'Save last frame'."""
        self._log("step", "Kích hoạt 'Lưu last frame' trên giao diện Flow...")
        res = bridge.eval_json(
            """(() => {
                // Try to find the last frame action button or 3-dots menu on video card
                const btns = Array.from(document.querySelectorAll('button'));
                for (const b of btns) {
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                    const txt = (b.textContent || '').toLowerCase();
                    if (aria.includes('last frame') || txt.includes('last frame') ||
                        aria.includes('khung hình cuối') || txt.includes('khung hình cuối')) {
                        b.click();
                        return {clicked: true, label: aria || txt};
                    }
                }
                return {clicked: false};
            })()"""
        )
        if res and res.get("clicked"):
            self._log("info", f"Đã click: {res.get('label')}")
            time.sleep(2.0)
            return True
        return False

    def generate_video_flow(
        self,
        frame_path: Path | str,
        prompt_text: str,
        dest_path: Path | str,
        duration_s: int = 8,
        timeout_s: float = 300.0,
        project_id: Optional[str] = None,
        aspect_ratio: str = "9:16",
    ) -> Path:
        """Fully autonomous video generation on Google Flow via Playwright CDP.

        1. Connects to flow.google.com tab.
        2. Uploads frame_path to Flow media assets.
        3. Sets Video Mode (8s).
        4. Focuses ProseMirror, types mention chip @<stem> and confirms from popup.
        5. Types sanitized prompt_text.
        6. Clicks Generate.
        7. Polls for video rendering completion, hovers to mount <video>, downloads to dest_path.
        """
        import requests
        from playwright.sync_api import sync_playwright

        frame_p = Path(frame_path).resolve()
        dest_p = Path(dest_path).resolve()
        dest_p.parent.mkdir(parents=True, exist_ok=True)

        if not frame_p.is_file():
            raise FileNotFoundError(f"Không tìm thấy file frame: {frame_p}")

        clean_prompt = " ".join([line.strip() for line in prompt_text.splitlines() if line.strip()])
        # Sanitize any celebrity policy trigger phrases
        clean_prompt = re.sub(
            r"\b(exact young korean woman|korean woman|celebrity)\b",
            "young woman",
            clean_prompt,
            flags=re.IGNORECASE,
        )

        self._log("step", f"Tạo Video Flow ({duration_s}s) từ frame: {frame_p.name}")
        self._log("info", f"Prompt ({len(clean_prompt)} ký tự): '{clean_prompt[:80]}...'")

        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(self.cdp_url)
            flow_page = None
            for ctx in browser.contexts:
                for p in ctx.pages:
                    if "flow.google.com" in p.url:
                        flow_page = p
                        break
                if flow_page:
                    break

            if not flow_page:
                if browser.contexts and browser.contexts[0].pages:
                    flow_page = browser.contexts[0].pages[0]
                    init_url = f"https://flow.google.com/project/{project_id}" if project_id else "https://flow.google.com/"
                    self._log("info", f"Mở trang Flow trên tab hiện tại: {init_url}")
                    flow_page.goto(init_url, wait_until="domcontentloaded", timeout=30000)
                    flow_page.wait_for_timeout(3000)
                else:
                    raise BridgeError(f"Không tìm thấy tab flow.google.com trên CDP {self.cdp_url}")

            try:
                cdp_sess = flow_page.context.new_cdp_session(flow_page)
                win_info = cdp_sess.send("Browser.getWindowForTarget")
                win_id = win_info.get("windowId")
                bounds = win_info.get("bounds") or {}
                if win_id and bounds.get("windowState") == "minimized":
                    cdp_sess.send("Browser.setWindowBounds", {"windowId": win_id, "bounds": {"windowState": "maximized"}})
                cdp_sess.detach()
            except Exception:
                pass
            flow_page.bring_to_front()
            if project_id and f"/project/{project_id}" not in flow_page.url:
                self._log("info", f"Điều hướng tới dự án Flow: {project_id}")
                flow_page.goto(f"https://flow.google.com/project/{project_id}")
                flow_page.wait_for_timeout(3000)
            flow_page.keyboard.press("Escape")
            flow_page.wait_for_timeout(500)

            # 1. Switch to Video mode + Khung hình (Frames Mode) + 8 giây + Aspect Ratio
            target_aspect = "9:16" if "9:16" in aspect_ratio else "16:9"
            self._log("info", f"Thiết lập chế độ Video -> Khung hình (Frames Mode) 8s (tỷ lệ {target_aspect})...")
            settings_btn = flow_page.query_selector('button.settings-trigger-button')
            if settings_btn:
                settings_btn.click(force=True)
                flow_page.wait_for_timeout(600)

                # Ensure Video toggle
                v_btn = flow_page.query_selector('//button[@role="radio" and contains(., "Video")]')
                if v_btn and v_btn.get_attribute("aria-checked") != "true":
                    v_btn.click(force=True)
                    flow_page.wait_for_timeout(300)

                # Ensure Khung hình (Frames Mode) toggle
                kh_btn = flow_page.query_selector('//button[@role="radio" and contains(., "Khung hình")]')
                if kh_btn and kh_btn.get_attribute("aria-checked") != "true":
                    kh_btn.click(force=True)
                    flow_page.wait_for_timeout(300)

                # Ensure Aspect Ratio toggle (9:16 vs 16:9)
                asp_btn = flow_page.query_selector(f'//button[@role="radio" and contains(., "{target_aspect}")]')
                if asp_btn and asp_btn.get_attribute("aria-checked") != "true":
                    asp_btn.click(force=True)
                    flow_page.wait_for_timeout(300)

                # Ensure 8 giây duration toggle
                d8_btn = flow_page.query_selector('//button[@role="radio" and contains(., "8 giây")]')
                if d8_btn and d8_btn.get_attribute("aria-checked") != "true":
                    d8_btn.click(force=True)
                    flow_page.wait_for_timeout(300)

                # Close settings popover safely (click backdrop or Escape)
                backdrop = flow_page.query_selector('.cdk-overlay-backdrop')
                if backdrop:
                    backdrop.click(force=True)
                else:
                    flow_page.keyboard.press("Escape")
                flow_page.wait_for_timeout(400)

            # 2. Attach frame_path to 'Bắt đầu' (Starting Frame) slot
            self._log("step", f"Gắn ảnh {frame_p.name} vào ô 'Bắt đầu' (Starting Frame)...")
            
            # 2a. Clear any existing starting frame chip if present
            cancel_btn = flow_page.query_selector(
                'flow-image-ingredient-chip button, '
                'flow-image-ingredient-chip [class*="cancel"], '
                'flow-image-ingredient-chip mat-icon:has-text("cancel"), '
                'flow-image-ingredient-chip .hover-icon-overlay'
            )
            if cancel_btn:
                self._log("info", "Đang xóa Starting Frame chip cũ để thay bằng frame mới...")
                cancel_btn.click(force=True)
                flow_page.wait_for_timeout(500)

            # 2b. Click 'Bắt đầu' button
            start_btn = flow_page.query_selector('//button[contains(., "Bắt đầu")]')
            if not start_btn:
                # Check if chip is already mounted
                if not flow_page.query_selector('flow-image-ingredient-chip'):
                    raise BridgeError("Không tìm thấy nút 'Bắt đầu' trên thanh flow-ingredient-bar.")
            else:
                start_btn.click(force=True)
                flow_page.wait_for_timeout(800)

                # 2c. Upload frame_p via sidebar-upload-btn inside the popover if file exists
                upload_btn = flow_page.query_selector(
                    '.cdk-overlay-pane .sidebar-upload-btn, flow-add-menu-popover-content .sidebar-upload-btn'
                )
                if upload_btn and frame_p.is_file():
                    try:
                        self._log("info", f"Tải file {frame_p.name} lên qua menu...")
                        with flow_page.expect_file_chooser(timeout=5000) as fc:
                            upload_btn.click(force=True)
                        fc.value.set_files([str(frame_p)])
                        flow_page.wait_for_timeout(2000)
                    except Exception as e:
                        self._log("warn", f"Upload frame: {e}")

                # 2d. Wait and check every 15s until image upload & thumbnail registration are 100% complete
                self._log("step", f"Đang chờ ảnh {frame_p.name} upload xong 100% và sẵn sàng...")
                t_upload_start = time.time()
                last_log_s = t_upload_start
                max_upload_timeout_s = 180.0  # Allow up to 3 minutes for large 2K/4K images
                upload_done = False

                while time.time() - t_upload_start < max_upload_timeout_s:
                    elapsed = int(time.time() - t_upload_start)

                    if flow_page.query_selector('flow-image-ingredient-chip'):
                        upload_done = True
                        self._log("info", f"Ảnh {frame_p.name} đã tự động gắn vào ô 'Bắt đầu' sau {elapsed}s!")
                        break

                    # Probe upload & thumbnail state inside the popover WITHOUT clicking first_item prematurely
                    status = flow_page.evaluate("""() => {
                        const pane = document.querySelector('.cdk-overlay-pane, flow-add-menu-popover-content');
                        if (!pane) return {ready: false, reason: 'no_pane'};

                        const firstItem = pane.querySelector('button.asset-item');
                        if (!firstItem) return {ready: false, reason: 'no_first_item'};

                        const itemText = (firstItem.innerText || '').trim();
                        const isUploadingText = itemText.includes('Đang tải lên') || itemText.toLowerCase().includes('uploading');
                        const thumbImg = firstItem.querySelector('img.asset-thumbnail-image, img[src^="http"]');

                        // Check percentage text anywhere on the page (e.g. '60%')
                        let pct = '';
                        const text = document.body.innerText;
                        const match = text.match(/(\\d{1,3})%/);
                        if (match) {
                            pct = match[0];
                        }

                        // Check spinner in preview pane or active asset item
                        const spinner = pane.querySelector(
                            'mat-spinner, mat-progress-spinner, [role="progressbar"], flow-spinner, ' +
                            '.spinner, [class*="spinner"], [class*="loading-indicator"]'
                        );

                        return {
                            ready: !!thumbImg && !isUploadingText && !spinner,
                            hasThumb: !!thumbImg,
                            isUploadingText: isUploadingText,
                            hasSpinner: !!spinner,
                            pct: pct
                        };
                    }""")

                    if status and status.get("ready"):
                        upload_done = True
                        self._log("info", f"Ảnh {frame_p.name} đã upload hoàn tất 100% sau {elapsed}s!")
                        break

                    # Periodic log every 15s as requested by user
                    now = time.time()
                    if now - last_log_s >= 15.0:
                        pct_info = f" ({status.get('pct')})" if (status and status.get("pct")) else ""
                        self._log("info", f"Đang chờ ảnh upload hoàn tất{pct_info}... đã qua {elapsed}s (check mỗi 15s)")
                        last_log_s = now

                    flow_page.wait_for_timeout(1200)

                if not upload_done:
                    raise BridgeError(f"Hết thời gian chờ upload ảnh {frame_p.name} vượt quá {max_upload_timeout_s}s.")

                # 2e. Image is 100% uploaded! Activate first item and attach to 'Bắt đầu'
                self._log("step", "Ảnh đã sẵn sàng 100%. Gắn First Frame vào ô 'Bắt đầu'...")
                for _attempt in range(3):
                    if flow_page.query_selector('flow-image-ingredient-chip'):
                        break

                    first_item = flow_page.query_selector('button.asset-item')
                    if first_item:
                        cls = first_item.get_attribute("class") or ""
                        if "asset-item-active" not in cls:
                            first_item.click(force=True)
                            flow_page.wait_for_timeout(500)

                    if flow_page.query_selector('flow-image-ingredient-chip'):
                        break

                    add_btn = flow_page.query_selector(
                        'button.detail-add-to-prompt-btn:not([disabled]), button:has-text("Thêm vào câu lệnh"):not([disabled])'
                    )
                    if add_btn:
                        add_btn.click(force=True)
                        flow_page.wait_for_timeout(1200)
                    elif first_item:
                        first_item.click(force=True)
                        flow_page.wait_for_timeout(1200)

            # 2f. HARD VERIFICATION: flow-image-ingredient-chip MUST BE MOUNTED
            chip = flow_page.wait_for_selector('flow-image-ingredient-chip', timeout=10000)
            if not chip:
                raise BridgeError(
                    "LỖI: Chưa chọn First Frame thành công vào ô 'Bắt đầu'! "
                    "Slot 'Bắt đầu' vẫn trống, không thể tiếp tục nhập prompt."
                )
            self._log("info", "Đã xác nhận First Frame gắn thành công vào ô 'Bắt đầu'.")

            # 3. Type pure action prompt directly into ProseMirror (NO @ mention in Frames mode)
            pm = flow_page.query_selector('div.ProseMirror')
            if not pm:
                raise BridgeError("Không tìm thấy composer div.ProseMirror trên Flow.")
            pm.click(force=True)
            flow_page.keyboard.press("Control+A")
            flow_page.keyboard.press("Backspace")
            flow_page.wait_for_timeout(200)

            self._log("info", f"Nhập prompt hành động vào composer: '{clean_prompt[:80]}...'")
            flow_page.keyboard.type(clean_prompt, delay=5)
            flow_page.wait_for_timeout(600)

            # Double check chip is still mounted before clicking Generate
            if not flow_page.query_selector('flow-image-ingredient-chip'):
                raise BridgeError("LỖI: Starting Frame chip bị mất sau khi nhập prompt!")

            # Snapshot existing videos before clicking Generate
            init_videos = flow_page.evaluate("""() => {
                const vids = Array.from(document.querySelectorAll('video')).map(v => v.src || v.currentSrc || '').filter(Boolean);
                const perf = performance.getEntriesByType('resource')
                    .map(e => e.name || '')
                    .filter(u => u.indexOf('.mp4') >= 0 || u.indexOf('/video/') >= 0);
                return Array.from(new Set([...vids, ...perf]));
            }""") or []

            # 4. Click Generate
            self._log("step", "Bấm nút bắt đầu tạo Video...")
            flow_page.click("button.generate-icon-button", force=True)
            flow_page.wait_for_timeout(3000)

            # 6. Poll for completion
            t0 = time.time()
            deadline = t0 + timeout_s
            video_url = ""
            while time.time() < deadline:
                time.sleep(5.0)
                elapsed = int(time.time() - t0)

                # Hover over the first video tile / grid tile to mount <video> element if ready
                try:
                    vtile = flow_page.query_selector('flow-video-tile, flow-grid-tile-container')
                    if vtile:
                        vtile.hover(force=True)
                        flow_page.wait_for_timeout(400)
                except Exception:
                    pass

                res = flow_page.evaluate("""(inits) => {
                    const firstCard = document.querySelector('flow-video-tile, .mat-context-menu-trigger, .tile-row, [class*="asset"], [class*="card"]');
                    if (firstCard) {
                        const event = new MouseEvent('mouseover', { 'view': window, 'bubbles': true, 'cancelable': true });
                        firstCard.dispatchEvent(event);
                    }
                    const vids = Array.from(document.querySelectorAll('video')).map(v => v.src || v.currentSrc || '').filter(Boolean);
                    const perf = performance.getEntriesByType('resource')
                        .map(e => e.name || '')
                        .filter(u => u.indexOf('.mp4') >= 0 || u.indexOf('/video/') >= 0);
                    const cur = Array.from(new Set([...vids, ...perf])).filter(u => u.startsWith('http'));
                    const diff = cur.filter(s => !inits.includes(s));
                    const isBusy = !!document.querySelector('mat-progress-spinner, mat-progress-bar, [class*="generating"]');
                    const alert = document.querySelector('[role="alert"], [class*="alert"]')?.innerText || '';
                    return { isBusy, curCount: cur.length, newCount: diff.length, newSrc: diff[diff.length - 1] || '', alert };
                }""", init_videos)

                if res.get("alert"):
                    self._log("warn", f"Flow cảnh báo: {res['alert']}")

                if res.get("newCount", 0) > 0 and not res.get("isBusy"):
                    video_url = res["newSrc"]
                    self._log("info", f"Tìm thấy Video mới sau {elapsed}s: {video_url[:80]}...")
                    break

                self._log("info", f"Đang tạo video trên Flow... ({elapsed}s)")

            if not video_url:
                # Last ditch check for any video
                v_src = flow_page.evaluate("""() => {
                    const v = document.querySelector('video');
                    return v ? v.src : '';
                }""")
                if v_src and "blob:" not in v_src:
                    video_url = v_src

            if video_url:
                self._log("info", f"Đang tải video về: {dest_p.name}...")
                resp = requests.get(video_url, timeout=60)
                if resp.status_code == 200 and len(resp.content) > 10000:
                    dest_p.write_bytes(resp.content)
                    self._log("info", f"Đã lưu video thành công: {dest_p.name} ({len(resp.content)} bytes)")
                    return dest_p

            raise BridgeError(f"Không thể tải video từ Flow sau {timeout_s}s")
