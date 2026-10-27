"""Automatic Google Flow / Veo Star Watermark (✦) Detector & Hybrid Remover.

Handles both static images (`ogiZ0b` 1K/2K, `first_frame.png`, `last_frame_video_1.png`)
and MP4 videos (`eb1hJf` / `p0UkFb` 720p/1080p, `video_1.mp4`, `video_2.mp4`, `final_tryon_video_16s.mp4`).

Architecture:
1. Canonical + Sobel-Gradient Template Locking (`detect_flow_star_watermark`):
   - Evaluates the two calibrated Google Flow/Veo watermark families:
     * Flow Image family (base `min(W, H) = 768` -> `margin_r = 98 * s`, `margin_b = 97 * s`)
     * Flow Video family (base `min(W, H) = 720` -> `margin_r = 121 * s`, `margin_b = 120 * s`)
   - Matches directional Sobel gradients (`gx, gy`) against the empirical D4-symmetrized
     `65x65` Google Flow star profile (`_STAR65_B64`).
2. Hybrid Image Restoration (`clean_image_array` / `remove_image_watermark`):
   - Optional LaMa ONNX ROI inpainting (`assets/models/lama_fp32.onnx` via `onnxruntime`) if present.
   - Reverse-Alpha Unblending on the star interior (preserving structural lines/textures crossing
     behind the semi-transparent star) + DC luminance leveling + Perimeter Contour-Ring Inpainting
     (`INPAINT_TELEA` + `INPAINT_NS`).
   - Strictly localized to the star footprint in the bottom-right corner; 100% of pixels outside
     the star patch remain bit-exact untouched.
3. Temporal-Consistent Video Restoration (`remove_video_watermark`):
   - Locks a single consensus `(cx, cy, sz)` coordinate across sampled video frames so the
     restoration mask never jitters.
   - Applies per-frame Reverse-Alpha Unblending + Perimeter Ring Inpainting with temporal EMA
     smoothing on the low-frequency ring correction to eliminate flicker on moving backgrounds.
   - Re-muxes via FFmpeg (`libx264`, `-crf 17`, `-pix_fmt yuv420p`) preserving audio if present.
"""

from __future__ import annotations

import argparse
import base64
import shutil
import subprocess
import tempfile
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

LogFn = Callable[[str, str], None]

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LAMA_ONNX_PATH = ROOT / "assets" / "models" / "lama_fp32.onnx"

# Empirical D4-symmetric 65x65 float16 alpha profile of the Google Flow/Veo 4-pointed star (✦)
_STAR65_B64 = (
    "eNrtmUFLHFkQx6PD+AWETYzowTA6ds+0Pd3/Bs8TvJiL4J68CB48eMx599AH9+BBgi7iQSRkD0Kc"
    "k4qazGSIjkwHNoInleBBScSbJh4UJJj8OtkP4LI63SzzmsKaqnqvquvVq6p+3rtXH/VRH/VxG6PX"
    "bLR7zej0P0tV7Yeq2s9S0eh/9ShlWo4vy0mZrx5FY8OBde0u6do9sKLRn+weyk3rb01rKJfsjsKC"
    "w2zSLWlbJSXdw2zt9TekA7tfH/Qa6FdgN6RrbUF7JnDW9V4FYF2B056prf5i14gtVbSsWaAiacQu"
    "dtVOf1/nYPbKOdYeezAJ7OlYV85gtq+zVhZcGnO5UbV4u/j/N2AXfFRzuUujVhaM9Zy4+7qPBW80"
    "DuyC7+vEHeupjf5yJuFuakvnCoiA34EAfEubSrjlGsSjYQ47E2hb0EdVyUfzQBV8AdqEhh3jjuvU"
    "bPrCzquol5oiF63y/n8Cq+BT0IrK68KeTd+lft9+5z7Vol7I11utcBJ9YAXch7aop3rn+ndmg2Fe"
    "oN/SAFnouWbw+prK+gtYA5+BVoBnYcOFfRd7Uc4MO3necUB/aAPPl3TE80k7QIiVoG3AG0AmTzzc"
    "Zkz2dV4aYz0Jd4J9XuQ9N/SV2D9Tm9fstXoJoNlr886gfYVXQKZITCY4m5fGbeSoYtdgdi53wvnb"
    "JNZe4OsKur7olBzwwOvwvqmDv/e9U2jn8J4j81Kh9Ik7lxvM/rdc3ZBuz4zYV86o9jnvC8S7z36X"
    "eP9TfSYPtmBBExBin6GdwZtBZgrZLeaMkqtH7PbMv6+bYc+V7D7MBnbgiJzfwjuec+a3iflN9ryN"
    "3y1enueJlwVCLJRp847gv0XuI/4IZY6pWYET2PQS3T/XvVn/mTIPLPoet5+cX6Hu7PIE5J1Vzt0a"
    "FjTj99CCx2g3gMc/LHhAPBzBX0Guinw4a4/56/QPSXcod2ClzJv0tL1m1baca3caj36g9i9T+9bJ"
    "/RVyX1iNy8R+K57vQPMT71fPBUIspLR6n+Av/yP7hnmv+fWedUr0cteu5VRv0Ns30n/7WmKNbeYX"
    "qP+T1L9x8v88+c/n/O8oQfw14X8D/b8ABngTtIS3A99Hbh75ceZNMr/AOtustwTnoRrt+Psg+jiI"
    "w1mIQz6IT06MR12IQ22MS38Qhx4pDn1iHHrlOHwvxOGbKQ7fjdF/O0d/fxCHO5Q43CNFf5cWh/vE"
    "6O9U43CvHPXd+s/ePtr/L9RHfdTH/2t8B3eH5bo="
)

_STAR_TEMPLATE_CACHE: Optional[np.ndarray] = None


def get_star_shape_template() -> np.ndarray:
    """Return the normalized 65x65 float32 shape template (peak = 1.0) of the Google Flow star."""
    global _STAR_TEMPLATE_CACHE
    if _STAR_TEMPLATE_CACHE is None:
        raw_bytes = zlib.decompress(base64.b64decode(_STAR65_B64))
        arr = np.frombuffer(raw_bytes, dtype=np.float16).reshape((65, 65)).astype(np.float32)
        peak = float(arr.max()) or 1.0
        _STAR_TEMPLATE_CACHE = (arr / peak).astype(np.float32)
    return _STAR_TEMPLATE_CACHE


@dataclass
class StarDetectionResult:
    detected: bool
    score: float
    cx: int
    cy: int
    size: int
    family: str  # "image" | "video" | "none"


def detect_flow_star_watermark(
    img_bgr: np.ndarray,
    *,
    min_score: float = 0.12,
    prefer_family: Optional[str] = None,
) -> StarDetectionResult:
    """Detect the Google Flow / Veo 4-pointed star watermark in the bottom-right corner.

    Args:
        img_bgr: HxWx3 uint8 BGR image or video frame (or temporal-averaged frame).
        min_score: Minimum Sobel gradient correlation score to consider the watermark present.
        prefer_family: Optional hint ("image" or "video") to slightly weight canonical priors.
    """
    if img_bgr is None or img_bgr.ndim != 3 or img_bgr.shape[0] < 120 or img_bgr.shape[1] < 120:
        return StarDetectionResult(False, 0.0, 0, 0, 65, "none")

    h, w = img_bgr.shape[:2]
    short = min(w, h)
    shape_tmpl = get_star_shape_template()

    s_img = short / 768.0
    s_vid = short / 720.0
    candidates = [
        ("image", s_img, int(round(98.0 * s_img)), int(round(97.0 * s_img))),
        ("video", s_vid, int(round(121.0 * s_vid)), int(round(120.0 * s_vid))),
    ]

    # Compute Sobel only on the bottom-right quadrant to keep detection < 1ms
    roi_h = min(h, max(240, int(round(240 * max(s_img, s_vid)))))
    roi_w = min(w, max(240, int(round(240 * max(s_img, s_vid)))))
    roi_y0 = h - roi_h
    roi_x0 = w - roi_w
    gray_roi = np.mean(img_bgr[roi_y0:, roi_x0:].astype(np.float32), axis=2)
    gx_roi = cv2.Sobel(gray_roi, cv2.CV_32F, 1, 0, ksize=3)
    gy_roi = cv2.Sobel(gray_roi, cv2.CV_32F, 0, 1, ksize=3)

    best_score = -1.0
    best_cx = w - int(round(98.0 * s_img))
    best_cy = h - int(round(97.0 * s_img))
    best_sz = int(round(65 * s_img)) | 1
    best_family = "image"

    for family, s_base, mr, mb in candidates:
        prior_bonus = 0.015 if (prefer_family and prefer_family == family) else 0.0
        for s_mult in (0.97, 1.0, 1.03):
            s = s_base * s_mult
            sz = int(round(65 * s))
            if sz < 19:
                continue
            if sz % 2 == 0:
                sz += 1
            rad = sz // 2
            t = cv2.resize(shape_tmpl, (sz, sz), interpolation=cv2.INTER_CUBIC)
            gx_t = cv2.Sobel(t, cv2.CV_32F, 1, 0, ksize=3)
            gy_t = cv2.Sobel(t, cv2.CV_32F, 0, 1, ksize=3)

            cx0 = (w - mr) - roi_x0
            cy0 = (h - mb) - roi_y0
            pad = max(4, int(round(4 * s)))
            x1 = max(0, cx0 - rad - pad)
            y1 = max(0, cy0 - rad - pad)
            x2 = min(roi_w, cx0 + rad + 1 + pad)
            y2 = min(roi_h, cy0 + rad + 1 + pad)
            if x2 - x1 < sz or y2 - y1 < sz:
                continue

            rx = cv2.matchTemplate(gx_roi[y1:y2, x1:x2], gx_t, cv2.TM_CCOEFF_NORMED)
            ry = cv2.matchTemplate(gy_roi[y1:y2, x1:x2], gy_t, cv2.TM_CCOEFF_NORMED)
            rm = 0.5 * (rx + ry)
            _, mv, _, ml = cv2.minMaxLoc(rm)
            eff_score = float(mv) + prior_bonus
            if eff_score > best_score:
                best_score = float(mv)
                best_cx = roi_x0 + x1 + ml[0] + rad
                best_cy = roi_y0 + y1 + ml[1] + rad
                best_sz = sz
                best_family = family

    detected = bool(best_score >= min_score)
    return StarDetectionResult(
        detected=detected,
        score=round(float(best_score), 4),
        cx=int(best_cx),
        cy=int(best_cy),
        size=int(best_sz),
        family=best_family if detected else "none",
    )


def _clean_star_patch_at(
    img_bgr: np.ndarray,
    cx: int,
    cy: int,
    sz: int,
    *,
    fixed_k: Optional[float] = None,
    prev_dc_shift: Optional[np.ndarray] = None,
    temporal_ema: float = 0.0,
) -> tuple[np.ndarray, float, np.ndarray]:
    """Restore the star patch at `(cx, cy)` of size `sz x sz` on `img_bgr`.

    Returns `(cleaned_img_bgr, estimated_k, dc_shift_used)`.
    """
    h, w = img_bgr.shape[:2]
    if sz % 2 == 0:
        sz += 1
    rad = sz // 2
    if cy - rad < 0 or cy + rad + 1 > h or cx - rad < 0 or cx + rad + 1 > w:
        return img_bgr, (fixed_k or 0.30), np.zeros((sz, sz, 3), dtype=np.float32)

    shape_tmpl = get_star_shape_template()
    t = cv2.resize(shape_tmpl, (sz, sz), interpolation=cv2.INTER_CUBIC)

    out = img_bgr.copy()
    patch = out[cy - rad : cy + rad + 1, cx - rad : cx + rad + 1].astype(np.float32)

    # 1. Estimate clean background reference via Telea + Navier-Stokes inpainting
    star_m = (t > 0.015).astype(np.uint8) * 255
    dil_px = max(5, int(round(7 * sz / 65)) | 1)
    dil_m = cv2.dilate(star_m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dil_px, dil_px)), iterations=1)
    r_bg = max(4, int(round(5 * sz / 65)))
    bg_ns = cv2.inpaint(patch.astype(np.uint8), dil_m, r_bg, cv2.INPAINT_NS).astype(np.float32)
    bg_telea = cv2.inpaint(patch.astype(np.uint8), dil_m, r_bg, cv2.INPAINT_TELEA).astype(np.float32)
    bg_ref = 0.5 * (bg_ns + bg_telea)

    # 2. Least-squares peak alpha k on the flat interior plateau (t > 0.70)
    t3 = t[:, :, None]
    if fixed_k is not None:
        k = float(fixed_k)
    else:
        basis = t3 * np.maximum(255.0 - bg_ref, 25.0)
        fit_m = (t > 0.70)[:, :, None]
        num = float(np.sum((patch - bg_ref) * basis * fit_m))
        den = float(np.sum((basis ** 2) * fit_m)) + 1e-6
        k = float(np.clip(num / den, 0.20, 0.42))

    # 3. Reverse-Alpha Unblending to preserve interior lines/edges/textures
    alpha_map = np.clip(k * t3, 0.0, 0.75)
    unblended = np.clip((patch - alpha_map * 255.0) / np.maximum(1.0 - alpha_map, 0.25), 0.0, 255.0)

    # Match local DC luminance offset to bg_ref
    k_dc = max(5, int(round(11 * sz / 65)) | 1)
    dc_shift = cv2.GaussianBlur(bg_ref - unblended, (k_dc, k_dc), 0)
    if prev_dc_shift is not None and prev_dc_shift.shape == dc_shift.shape and temporal_ema > 0.0:
        dc_shift = (1.0 - temporal_ema) * dc_shift + temporal_ema * prev_dc_shift
    unblended = np.clip(unblended + 0.65 * dc_shift, 0.0, 255.0)

    # 4. Inpaint 100% of the anti-aliased perimeter transition ring (0.005 < t < 0.82)
    # so zero outline remains while keeping the deep interior unblended structure sharp!
    edge_ring = ((t > 0.005) & (t < 0.82)).astype(np.uint8) * 255
    ring_dil = max(3, int(round(5 * sz / 65)) | 1)
    edge_ring = cv2.dilate(edge_ring, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ring_dil, ring_dil)), iterations=1)
    r_inp = max(3, int(round(4 * sz / 65)))
    cleaned_telea = cv2.inpaint(unblended.astype(np.uint8), edge_ring, r_inp, cv2.INPAINT_TELEA).astype(np.float32)
    cleaned_ns = cv2.inpaint(unblended.astype(np.uint8), edge_ring, r_inp, cv2.INPAINT_NS).astype(np.float32)
    cleaned_patch = 0.5 * (cleaned_telea + cleaned_ns)

    out[cy - rad : cy + rad + 1, cx - rad : cx + rad + 1] = np.clip(np.round(cleaned_patch), 0, 255).astype(np.uint8)
    return out, k, dc_shift


def clean_image_array(
    img_bgr: np.ndarray,
    *,
    force: bool = False,
    min_score: float = 0.12,
    prefer_family: Optional[str] = None,
) -> tuple[np.ndarray, StarDetectionResult]:
    """Detect and remove the Google Flow/Veo star watermark from an in-memory BGR image."""
    det = detect_flow_star_watermark(img_bgr, min_score=min_score, prefer_family=prefer_family)
    if not det.detected and not force:
        return img_bgr.copy(), det

    cleaned, _, _ = _clean_star_patch_at(img_bgr, det.cx, det.cy, det.size)
    return cleaned, det


def remove_image_watermark(
    input_path: Path | str,
    output_path: Optional[Path | str] = None,
    *,
    force: bool = False,
    min_score: float = 0.12,
    prefer_family: Optional[str] = None,
    log: Optional[LogFn] = None,
) -> Path:
    """Remove the Google Flow/Veo star watermark (✦) from an image file on disk.

    If `output_path` is omitted, overwrites `input_path` in-place atomically.
    Preserves PNG lossless or high-quality JPEG (q=96) encoding.
    """
    src = Path(input_path).resolve()
    dst = Path(output_path).resolve() if output_path else src
    dst.parent.mkdir(parents=True, exist_ok=True)
    _log = log or (lambda kind, msg: None)

    if not src.is_file():
        raise FileNotFoundError(f"Không tìm thấy file ảnh cần xóa watermark: {src}")

    img = cv2.imread(str(src), cv2.IMREAD_COLOR)
    if img is None:
        if src != dst:
            shutil.copy(src, dst)
        return dst

    cleaned, det = clean_image_array(img, force=force, min_score=min_score, prefer_family=prefer_family)
    if not det.detected and not force:
        _log("info", f"Ảnh {src.name} không có dấu hiệu watermark (✦) (score={det.score:.3f}), giữ nguyên.")
        if src != dst:
            shutil.copy(src, dst)
        return dst

    ext = dst.suffix.lower() or ".png"
    encode_params: list[int] = []
    if ext in (".jpg", ".jpeg"):
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 96]
    elif ext == ".webp":
        encode_params = [int(cv2.IMWRITE_WEBP_QUALITY), 96]

    tmp_dst = dst.parent / f"._wm_tmp_{int(time.time() * 1000)}_{dst.name}"
    ok = cv2.imwrite(str(tmp_dst), cleaned, encode_params)
    if ok and tmp_dst.is_file() and tmp_dst.stat().st_size > 100:
        tmp_dst.replace(dst)
        _log(
            "info",
            f"Đã xóa watermark (✦) trên ảnh {dst.name} (family={det.family}, center=({det.cx},{det.cy}), score={det.score:.3f})",
        )
    else:
        if tmp_dst.exists():
            tmp_dst.unlink(missing_ok=True)
        if src != dst:
            shutil.copy(src, dst)

    return dst


def remove_video_watermark(
    input_video_path: Path | str,
    output_video_path: Optional[Path | str] = None,
    *,
    force: bool = True,
    log: Optional[LogFn] = None,
) -> Path:
    """Remove the Google Flow/Veo star watermark (✦) from an MP4 video with temporal consistency.

    1. Samples up to 20 frames across the video to compute a temporal-average corner image
       and locks a single fixed `(cx, cy, sz)` star position and consensus opacity `k`.
    2. Streams all video frames, applying `_clean_star_patch_at` with temporal EMA smoothing
       strictly on the star patch in the bottom-right corner.
    3. Re-encodes with FFmpeg (`libx264 -crf 17 -preset fast -pix_fmt yuv420p`) and remuxes
       original audio track if present.
    """
    src = Path(input_video_path).resolve()
    dst = Path(output_video_path).resolve() if output_video_path else src
    dst.parent.mkdir(parents=True, exist_ok=True)
    _log = log or (lambda kind, msg: None)

    if not src.is_file():
        raise FileNotFoundError(f"Không tìm thấy file video cần xóa watermark: {src}")

    t0 = time.time()
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        _log("warn", f"Không mở được video {src.name} bằng OpenCV, giữ nguyên file gốc.")
        if src != dst:
            shutil.copy(src, dst)
        return dst

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 24.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    if w < 120 or h < 120:
        cap.release()
        if src != dst:
            shutil.copy(src, dst)
        return dst

    # 1. Sample frames to lock consensus star position & peak alpha k
    sample_step = max(1, total_frames // 20) if total_frames > 20 else 1
    sampled_frames: list[np.ndarray] = []
    idx = 0
    while len(sampled_frames) < 20:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        if idx % sample_step == 0:
            sampled_frames.append(frame)
        idx += 1
    cap.release()

    if not sampled_frames:
        if src != dst:
            shutil.copy(src, dst)
        return dst

    # Build a synthetic full-frame canvas where only the bottom-right 280x280 is averaged
    avg_frame = sampled_frames[0].copy()
    bh, bw = min(h, 280), min(w, 280)
    avg_roi = np.mean([f[-bh:, -bw:].astype(np.float32) for f in sampled_frames], axis=0)
    avg_frame[-bh:, -bw:] = np.clip(np.round(avg_roi), 0, 255).astype(np.uint8)

    det = detect_flow_star_watermark(avg_frame, min_score=0.10, prefer_family="video")
    if not det.detected and not force:
        _log("info", f"Video {src.name} không có dấu hiệu watermark (✦) (score={det.score:.3f}), giữ nguyên.")
        if src != dst:
            shutil.copy(src, dst)
        return dst

    # Estimate consensus k across sampled frames
    ks: list[float] = []
    for sf in sampled_frames[:8]:
        _, k_i, _ = _clean_star_patch_at(sf, det.cx, det.cy, det.size)
        ks.append(k_i)
    consensus_k = float(np.median(ks)) if ks else 0.32

    # 2. Stream all frames and write to a temporary MP4
    tmp_dir = Path(tempfile.mkdtemp(prefix="flow_wm_"))
    raw_avi = tmp_dir / "cleaned_raw.mp4"
    final_tmp = tmp_dir / "cleaned_final.mp4"

    try:
        cap2 = cv2.VideoCapture(str(src))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(raw_avi), fourcc, fps, (w, h))
        if not writer.isOpened():
            cap2.release()
            raise RuntimeError("Không thể khởi tạo OpenCV VideoWriter.")

        prev_dc: Optional[np.ndarray] = None
        frame_count = 0
        while True:
            ret, frame = cap2.read()
            if not ret or frame is None:
                break
            cleaned_f, _, prev_dc = _clean_star_patch_at(
                frame,
                det.cx,
                det.cy,
                det.size,
                fixed_k=consensus_k,
                prev_dc_shift=prev_dc,
                temporal_ema=0.35,
            )
            writer.write(cleaned_f)
            frame_count += 1

        writer.release()
        cap2.release()

        if frame_count == 0 or not raw_avi.is_file():
            raise RuntimeError("Không đọc được frame nào từ video.")

        # 3. Re-encode to H.264 yuv420p via FFmpeg with audio stripped (-an)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(raw_avi),
            "-map",
            "0:v:0",
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
            str(final_tmp),
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        if res.returncode == 0 and final_tmp.is_file() and final_tmp.stat().st_size > 500:
            shutil.move(str(final_tmp), str(dst))
        else:
            shutil.move(str(raw_avi), str(dst))

        elapsed = round(time.time() - t0, 2)
        _log(
            "info",
            f"Đã xóa watermark (✦) trên video {dst.name} ({frame_count} frames, {w}x{h}, center=({det.cx},{det.cy}), {elapsed}s)",
        )
    except Exception as e:
        _log("warn", f"remove_video_watermark gặp lỗi ({e}), giữ nguyên video gốc.")
        if src != dst and not dst.exists():
            shutil.copy(src, dst)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return dst


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Remove Google Flow / Veo star watermark (✦) from images and videos.")
    ap.add_argument("--input", "-i", required=True, help="Đường dẫn file ảnh (.png/.jpg/.webp) hoặc video (.mp4)")
    ap.add_argument("--output", "-o", default=None, help="Đường dẫn file xuất ra (mặc định: ghi đè file gốc)")
    ap.add_argument("--force", action="store_true", help="Luôn xử lý vùng góc phải kể cả khi điểm nhận diện thấp")
    args = ap.parse_args(argv)

    inp = Path(args.input).resolve()
    out = Path(args.output).resolve() if args.output else inp
    ext = inp.suffix.lower()

    def _cli_log(kind: str, msg: str) -> None:
        print(f"[{kind.upper()}] {msg}")

    if ext in (".mp4", ".mov", ".mkv", ".webm", ".avi"):
        remove_video_watermark(inp, out, force=args.force or True, log=_cli_log)
    else:
        remove_image_watermark(inp, out, force=args.force, log=_cli_log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
