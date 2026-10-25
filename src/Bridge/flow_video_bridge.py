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
