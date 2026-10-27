"""Unit and integration tests for `src.Workflows.watermark_remover`."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.Bridge.flow_video_bridge import concatenate_two_videos, strip_video_audio
from src.WebUI.app import AutoTryOnBody, BatchBody, GenerateBody
from src.Workflows.watermark_remover import (
    clean_image_array,
    detect_flow_star_watermark,
    get_star_shape_template,
    remove_image_watermark,
    remove_video_watermark,
)


def _synthesize_watermarked_frame(
    w: int = 1376,
    h: int = 768,
    family: str = "image",
    peak_alpha: float = 0.31,
) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int]]:
    """Create a synthetic textured BGR image and apply the exact Google Flow/Veo star watermark."""
    rng = np.random.default_rng(12345)
    yy, xx = np.mgrid[:h, :w]
    # Textured gradient + vertical/horizontal structural bars crossing the bottom-right corner
    base_b = np.clip(60 + (xx * 90) // w + ((yy // 18) % 2) * 14, 0, 220).astype(np.float32)
    base_g = np.clip(80 + (yy * 80) // h + ((xx // 22) % 2) * 18, 0, 220).astype(np.float32)
    base_r = np.clip(70 + ((xx + yy) * 60) // (w + h), 0, 220).astype(np.float32)
    clean = np.stack([base_b, base_g, base_r], axis=2)
    clean += rng.normal(0.0, 1.5, size=clean.shape).astype(np.float32)
    clean_u8 = np.clip(np.round(clean), 0, 255).astype(np.uint8)

    short = min(w, h)
    if family == "image":
        s = short / 768.0
        mr, mb = int(round(98.0 * s)), int(round(97.0 * s))
    else:
        s = short / 720.0
        mr, mb = int(round(121.0 * s)), int(round(120.0 * s))

    sz = int(round(65 * s)) | 1
    rad = sz // 2
    cx, cy = w - mr, h - mb
    tmpl = cv2.resize(get_star_shape_template(), (sz, sz), interpolation=cv2.INTER_CUBIC)
    alpha = (peak_alpha * tmpl)[:, :, None]

    watermarked = clean_u8.astype(np.float32)
    roi = watermarked[cy - rad : cy + rad + 1, cx - rad : cx + rad + 1]
    watermarked[cy - rad : cy + rad + 1, cx - rad : cx + rad + 1] = (1.0 - alpha) * roi + alpha * 255.0
    wm_u8 = np.clip(np.round(watermarked), 0, 255).astype(np.uint8)
    return clean_u8, wm_u8, (cx, cy, sz)


def test_detect_and_clean_image_16_9_and_9_16(tmp_path: Path) -> None:
    for w, h, fam in [(1376, 768, "image"), (768, 1376, "image"), (1280, 720, "video"), (720, 1280, "video")]:
        clean_gt, wm_img, (cx, cy, sz) = _synthesize_watermarked_frame(w, h, family=fam)

        # 1. Clean image without watermark should not trigger false detection
        det_clean = detect_flow_star_watermark(clean_gt)
        assert det_clean.score < 0.20

        # 2. Watermarked image must be detected accurately within 2px of true center
        det_wm = detect_flow_star_watermark(wm_img, prefer_family=fam)
        assert det_wm.detected is True
        assert det_wm.score > 0.35
        assert abs(det_wm.cx - cx) <= 2
        assert abs(det_wm.cy - cy) <= 2

        # 3. Clean watermark and verify bit-exact preservation outside bottom-right ROI
        restored, _ = clean_image_array(wm_img, prefer_family=fam)
        assert np.array_equal(restored[:-220, :], wm_img[:-220, :])
        assert np.array_equal(restored[:, :-220], wm_img[:, :-220])

        # 4. Verify MSE inside the star patch is dramatically reduced compared to watermarked image
        rad = sz // 2
        gt_patch = clean_gt[cy - rad : cy + rad + 1, cx - rad : cx + rad + 1].astype(np.float32)
        wm_patch = wm_img[cy - rad : cy + rad + 1, cx - rad : cx + rad + 1].astype(np.float32)
        res_patch = restored[cy - rad : cy + rad + 1, cx - rad : cx + rad + 1].astype(np.float32)

        mae_before = float(np.mean(np.abs(wm_patch - gt_patch)))
        mae_after = float(np.mean(np.abs(res_patch - gt_patch)))
        assert mae_after < mae_before * 0.35

    # Test file-based remove_image_watermark
    _, wm_file_img, _ = _synthesize_watermarked_frame(1376, 768, family="image")
    img_path = tmp_path / "sample_wm.png"
    cv2.imwrite(str(img_path), wm_file_img)
    out_path = remove_image_watermark(img_path)
    assert out_path == img_path
    reloaded = cv2.imread(str(img_path))
    assert reloaded is not None
    assert reloaded.shape == (768, 1376, 3)


def test_remove_video_watermark(tmp_path: Path) -> None:
    w, h = 720, 1280
    _, wm_frame, (cx, cy, sz) = _synthesize_watermarked_frame(w, h, family="video")
    vid_path = tmp_path / "test_video_wm.mp4"

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(vid_path), fourcc, 12.0, (w, h))
    for i in range(12):
        # Slightly shift brightness each frame to simulate motion
        f = np.clip(wm_frame.astype(np.int16) + (i % 3) - 1, 0, 255).astype(np.uint8)
        writer.write(f)
    writer.release()

    cleaned_vid = remove_video_watermark(vid_path)
    assert cleaned_vid.is_file()
    assert cleaned_vid.stat().st_size > 500

    cap = cv2.VideoCapture(str(cleaned_vid))
    ret, first_f = cap.read()
    cap.release()
    assert ret and first_f is not None
    assert first_f.shape == (h, w, 3)

    rad = sz // 2
    before_center_val = float(np.mean(wm_frame[cy - 5 : cy + 6, cx - 5 : cx + 6]))
    after_center_val = float(np.mean(first_f[cy - 5 : cy + 6, cx - 5 : cx + 6]))
    assert after_center_val < before_center_val - 15.0


def test_api_models_default_remove_watermark() -> None:
    g = GenerateBody(project_id="12345678-1234-1234-1234-123456789abc", prompt="test")
    assert g.remove_watermark is True

    b = BatchBody(items=[])
    assert b.remove_watermark is True

    t = AutoTryOnBody(first_frame_path="assets/sample_first_frame.png")
    assert t.remove_watermark is True


def test_concatenate_two_videos_stream_copy_and_no_audio(tmp_path: Path) -> None:
    import subprocess

    v1 = tmp_path / "video_1.mp4"
    v2 = tmp_path / "video_2.mp4"
    merged = tmp_path / "final_16s.mp4"

    # Generate 2 test MP4s WITH audio tracks (sine wave)
    for out_v, color in [(v1, "red"), (v2, "blue")]:
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=320x240:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(out_v),
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=15)

    res_path = concatenate_two_videos(v1, v2, merged)
    assert res_path == merged
    assert merged.is_file() and merged.stat().st_size > 500

    # Verify v1, v2, and merged have 0 audio streams
    for vp in (v1, v2, merged):
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(vp)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert probe.stdout.strip() == "", f"Expected no audio stream in {vp.name}, got: {probe.stdout!r}"

