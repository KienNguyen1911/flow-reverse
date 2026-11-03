"""Local FFmpeg / OpenCV helpers: last-frame extraction, audio stripping, clip concatenation."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

from .constants import LogFn

def condition_frame_for_policy_retry(
    frame_path: Path | str,
    output_path: Optional[Path | str] = None,
    log: Optional[LogFn] = None,
    level: int = 1,
) -> Path:
    """Return the original starting frame untouched to preserve 100% character and facial consistency."""
    return Path(frame_path).resolve()


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

    # Method 1: FFmpeg -sseof -0.2 (extract frame right before EOF)
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


def strip_video_audio(
    video_path: Path | str,
    log: Optional[LogFn] = None,
) -> Path:
    """Strip audio tracks from an MP4 file in-place using lossless stream copy (`-c:v copy -an`)."""
    vp = Path(video_path).resolve()
    if not vp.is_file():
        return vp
    _log = log or (lambda kind, msg: None)
    tmp_out = vp.parent / f"._noaudio_{int(time.time() * 1000)}_{vp.name}"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(vp),
        "-c:v",
        "copy",
        "-an",
        "-movflags",
        "+faststart",
        str(tmp_out),
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if res.returncode == 0 and tmp_out.is_file() and tmp_out.stat().st_size > 200:
            tmp_out.replace(vp)
            _log("info", f"Đã loại bỏ luồng âm thanh trên {vp.name} (stream copy -c:v copy -an).")
    except Exception as e:
        _log("warn", f"strip_video_audio ({vp.name}) gặp lỗi nhẹ: {e}")
    finally:
        if tmp_out.exists():
            tmp_out.unlink(missing_ok=True)
    return vp


def concatenate_two_videos(
    video1_path: Path | str,
    video2_path: Path | str,
    output_path: Path | str,
    log: Optional[LogFn] = None,
) -> Path:
    """Concatenate video 1 (8s) and video 2 (8s) into a unified 16s silent video using FFmpeg.

    Uses lossless stream copy (`-c:v copy -an`) first so no re-rendering occurs;
    falls back to normalized H.264 encoding only if stream parameters differ.
    """
    v1 = Path(video1_path).resolve()
    v2 = Path(video2_path).resolve()
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    _log = log or (lambda kind, msg: None)
    _log("step", f"Nối trực tiếp {v1.name} + {v2.name} thành {out.name} (stream copy, không âm thanh)...")

    # Ensure both input videos have no audio tracks
    strip_video_audio(v1, log=_log)
    strip_video_audio(v2, log=_log)

    # Method 1: Concat demuxer with direct stream copy (-c:v copy -an, 0 re-encoding)
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
            "copy",
            "-an",
            "-movflags",
            "+faststart",
            str(out),
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if res.returncode == 0 and out.is_file() and out.stat().st_size > 200:
            _log("info", f"Nối video trực tiếp (-c:v copy -an) thành công: {out.name} ({out.stat().st_size} bytes)")
            return out
    finally:
        if list_file.exists():
            try:
                list_file.unlink()
            except Exception:
                pass

    # Method 2: filter_complex fallback (if stream resolutions/codecs differ) with audio stripped (-an)
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
        "-crf",
        "17",
        "-preset",
        "fast",
        "-pix_fmt",
        "yuv420p",
        "-an",
        "-movflags",
        "+faststart",
        str(out),
    ]
    res2 = subprocess.run(cmd_filter, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if res2.returncode == 0 and out.is_file() and out.stat().st_size > 200:
        _log("info", f"Nối video (filter_complex fallback, -an) thành công: {out.name}")
        return out

    raise RuntimeError(f"Lỗi nối video: {res2.stderr.decode('utf-8', 'ignore')[:300]}")
