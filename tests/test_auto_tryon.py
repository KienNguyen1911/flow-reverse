"""Unit and integration tests for the Auto Try-On Pipeline.

Tests:
1. Shopee URL parsing & primary garment selection.
2. Gemini response parsing (Image prompt and dual 8s video prompts).
3. Real FFmpeg / OpenCV last-frame extraction & 16s video concatenation.
4. Full AutoTryOnPipeline execution in dry-run mode.
5. WebUI API endpoints for auto try-on.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.Bridge.flow_video_bridge import concatenate_two_videos, extract_last_video_frame
from src.Bridge.gemini_bridge import (
    parse_gemini_image_prompt,
    parse_gemini_video_prompts,
)
from src.Workflows.auto_tryon_pipeline import AutoTryOnPipeline
from src.Workflows.shopee_downloader import (
    parse_shopee_ids,
    pick_primary_garment_image,
)


# --------------------------------------------------------------------------- #
# 1. Shopee Downloader Tests
# --------------------------------------------------------------------------- #


def test_parse_shopee_ids():
    # Affiliate offer URL
    aff_url = "https://affiliate.shopee.vn/offer/product_offer?offer_id=123&item_id=23456789012&shop_id=98765432"
    shop_id, item_id = parse_shopee_ids(aff_url)
    assert item_id == 23456789012
    assert shop_id == 98765432

    # Standard product slug URL
    slug_url = "https://shopee.vn/Ao-Thun-Cotton-Oversize-Unisex-i.112233.44556677"
    shop_id2, item_id2 = parse_shopee_ids(slug_url)
    assert shop_id2 == 112233
    assert item_id2 == 44556677

    # Path /product/{shop}/{item}
    path_url = "https://shopee.vn/product/998877/66554433"
    shop_id3, item_id3 = parse_shopee_ids(path_url)
    assert shop_id3 == 998877
    assert item_id3 == 66554433

    # Invalid URL
    shop_id4, item_id4 = parse_shopee_ids("https://google.com")
    assert item_id4 is None


def test_pick_primary_garment_image(tmp_path):
    img1 = tmp_path / "img1_badge.jpg"
    img2 = tmp_path / "img2_clean_garment.jpg"
    img3 = tmp_path / "img3_detail.jpg"
    for img in (img1, img2, img3):
        img.write_bytes(b"dummy")

    # With multiple images, picks index 1 (clean clothing shot without front badge)
    picked = pick_primary_garment_image([img1, img2, img3])
    assert picked == img2

    # Single image
    assert pick_primary_garment_image([img1]) == img1
    assert pick_primary_garment_image([]) is None


# --------------------------------------------------------------------------- #
# 2. Gemini Response Parsing Tests
# --------------------------------------------------------------------------- #


def test_parse_gemini_image_prompt_codeblock():
    raw = """
Sure! Here is the prompt for Google Flow to create the first frame try-on image:

```
Full-length portrait of female model Nabi wearing a loose-knit beige cardigan, paired with wide-leg white trousers, natural indoor daylight studio, highly realistic fabric texture, 8k.
```

Let me know if you want adjustments!
"""
    prompt = parse_gemini_image_prompt(raw)
    assert "Full-length portrait of female model Nabi" in prompt
    assert "Sure!" not in prompt
    assert "Let me know" not in prompt


def test_parse_gemini_image_prompt_labeled():
    raw = """
Chào bạn, đây là prompt tạo ảnh:
Prompt: A chic fashionable Asian model Nabi wearing the pastel blue pleated midi skirt from product offer, minimalist beige studio background, commercial fashion photography.
"""
    prompt = parse_gemini_image_prompt(raw)
    assert prompt.startswith("A chic fashionable Asian model Nabi")
def test_parse_gemini_image_prompt_dual_options():
    raw = """
Dưới đây là 2 phiên bản prompt được thiết kế riêng:

Bản 1: Direct Flow Transfer Prompt (Ngắn gọn, trực diện)
Markdown
Model swap task: Keep outfit from Image 2, replace face with Image 1.

Bản 2: Detailed Realism Try-On Prompt (Chuyên sâu, khử da nhựa AI & chi tiết chân thực)
Markdown
A photorealistic, candid lifestyle fashion portrait of the exact young Korean woman from Image 1 wearing the outfit from Image 2. Visible skin micro-pores, authentic fabric texture.

💡 Hướng dẫn thao tác trên flow.google.com:
Dán prompt vào ô câu lệnh.
"""
    prompt = parse_gemini_image_prompt(raw)
    assert prompt.startswith("A photorealistic, candid lifestyle fashion portrait")
    assert "Visible skin micro-pores" in prompt
    assert "Hướng dẫn" not in prompt
    assert "Markdown" not in prompt


def test_parse_gemini_video_prompts_labeled():

    raw = """
Here are your 2 video prompts (8 seconds each):

**Video 1 (0-8s):**
Nabi stands facing forward, smiling softly at the camera as the camera gently zooms in, showing the flow of the silk blouse.

**Video 2 (8-16s):**
Nabi gracefully turns 90 degrees to her right, lifting one arm slightly to display the sleeve drape and tailoring, ending in a dynamic pose.

Hope this helps!
"""
    p1, p2 = parse_gemini_video_prompts(raw)
    assert "Nabi stands facing forward" in p1
    assert "Nabi gracefully turns 90 degrees" in p2
    assert "Video 1" not in p1
    assert "0-8s" not in p1


def test_parse_gemini_video_prompts_numbered():
    raw = """
1. Camera tracks forward in 4k, Nabi models the green oversized hoodie with hands in pocket, subtle wind effect, 8 seconds.
2. Nabi spins around playfully, displaying the back print typography of the hoodie, ending with a confident over-the-shoulder look, 8 seconds.
"""
    p1, p2 = parse_gemini_video_prompts(raw)
    assert "Camera tracks forward" in p1
    assert "Nabi spins around playfully" in p2


# --------------------------------------------------------------------------- #
# 3. FFmpeg Video Tools Tests (Last Frame Extraction & Concat)
# --------------------------------------------------------------------------- #


def _create_synthetic_video(
    path: Path, color: str = "green", duration_s: int = 1, size: str = "320x240"
) -> None:
    """Helper to create small synthetic test video using FFmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s={size}:d={duration_s}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def test_extract_last_video_frame(tmp_path):
    video = tmp_path / "test_clip.mp4"
    _create_synthetic_video(video, color="blue", duration_s=1)

    frame_out = tmp_path / "last_frame.png"
    result = extract_last_video_frame(video, frame_out)
    assert result.is_file()
    assert result.stat().st_size > 500
    # Check PNG magic bytes
    data = result.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_concatenate_two_videos(tmp_path):
    v1 = tmp_path / "clip1.mp4"
    v2 = tmp_path / "clip2.mp4"
    out = tmp_path / "concat.mp4"

    _create_synthetic_video(v1, color="red", duration_s=1)
    _create_synthetic_video(v2, color="blue", duration_s=1)

    result = concatenate_two_videos(v1, v2, out)
    assert result.is_file()
    assert result.stat().st_size > 2000

    # Probe duration with ffprobe if available
    try:
        probe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(result),
        ]
        duration_str = subprocess.check_output(probe_cmd, text=True).strip()
        duration = float(duration_str)
        # 1s + 1s = ~2s
        assert 1.8 <= duration <= 2.2
    except Exception:
        pass


def test_concatenate_two_videos_different_resolutions(tmp_path):
    v1 = tmp_path / "clip1_landscape.mp4"
    v2 = tmp_path / "clip2_portrait.mp4"
    out = tmp_path / "concat_mismatch.mp4"

    _create_synthetic_video(v1, color="red", duration_s=1, size="640x360")
    _create_synthetic_video(v2, color="blue", duration_s=1, size="320x240")

    result = concatenate_two_videos(v1, v2, out)
    assert result.is_file()
    assert result.stat().st_size > 2000


def test_concatenate_two_videos_filename_with_quote(tmp_path):
    v1 = tmp_path / "clip's_1.mp4"
    v2 = tmp_path / "clip's 2.mp4"
    out = tmp_path / "concat's output.mp4"

    _create_synthetic_video(v1, color="red", duration_s=1)
    _create_synthetic_video(v2, color="blue", duration_s=1)

    result = concatenate_two_videos(v1, v2, out)
    assert result.is_file()
    assert result.stat().st_size > 2000


# --------------------------------------------------------------------------- #
# 4. Full AutoTryOnPipeline Dry-Run Test
# --------------------------------------------------------------------------- #


def test_auto_tryon_pipeline_dry_run(tmp_path):
    # Setup dummy model image
    model_img = tmp_path / "nabi.png"
    model_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 300)

    # Setup dummy product directory
    prod_dir = tmp_path / "product_files"
    prod_dir.mkdir()
    garment_img = prod_dir / "product_01.jpg"
    garment_img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 300)

    out_root = tmp_path / "runs"
    pipeline = AutoTryOnPipeline(out_root=out_root)

    res = pipeline.run(
        model_path=model_img,
        product_dir=prod_dir,
        dry_run=True,
        auto_stitch=True,
    )

    assert res.status == "succeeded"
    assert res.dry_run is True
    assert Path(res.first_frame_path).is_file()
    assert Path(res.video_1_path).is_file()
    assert Path(res.last_frame_path).is_file()
    assert Path(res.video_2_path).is_file()
    assert Path(res.final_video_path).is_file()

    # Manifest file written
    manifest_p = Path(res.dest_dir) / "manifest.json"
    assert manifest_p.is_file()
    data = json.loads(manifest_p.read_text(encoding="utf-8"))
    assert data["status"] == "succeeded"
    assert "video_prompt_1" in data
    assert "video_prompt_2" in data


# --------------------------------------------------------------------------- #
# 5. Edge Cases & Error Handling Tests
# --------------------------------------------------------------------------- #


def test_gemini_parsers_edge_cases():
    # Empty inputs
    assert parse_gemini_image_prompt("") == ""
    assert parse_gemini_image_prompt("   ") == ""
    p1, p2 = parse_gemini_video_prompts("")
    assert p1 == "" and p2 == ""

    # Complex markdown with emojis, timestamps, bold, brackets
    raw_video = """
Dưới đây là 2 prompt video chuẩn 8 giây:
🎬 **Đoạn 1 (0-8 giây)**:
Người mẫu Nabi bước đi nhẹ nhàng về phía ống kính, ánh mắt tự tin, chiếc áo len oversize bay nhẹ theo chuyển động.
✨ **Đoạn 2 (8-16 giây)**:
Nabi xoay người 180 độ, tạo dáng nhìn qua vai để tôn dáng phần lưng của trang phục, máy quay quay chậm cinematic.
Chúc bạn thành công!
"""
    v1, v2 = parse_gemini_video_prompts(raw_video)
    assert "Người mẫu Nabi bước đi nhẹ nhàng" in v1
    assert "Nabi xoay người 180 độ" in v2
    assert "🎬" not in v1
    assert "Đoạn 1" not in v1
    assert "0-8" not in v1


def test_pipeline_validation_errors(tmp_path):
    pipeline = AutoTryOnPipeline(out_root=tmp_path)

    # Missing all inputs
    with pytest.raises(ValueError, match="Phải cung cấp"):
        pipeline.run(model_path="dummy.png", dry_run=True)

    # Missing model path in real run
    with pytest.raises(FileNotFoundError):
        pipeline.run(
            model_path="non_existent_nabi.png",
            product_dir=tmp_path,
            dry_run=False,
        )

    # Missing garment path in real run
    with pytest.raises(FileNotFoundError):
        dummy_model = tmp_path / "model.png"
        dummy_model.write_bytes(b"dummy")
        pipeline.run(
            model_path=dummy_model,
            garment_path=tmp_path / "non_existent_garment.png",
            dry_run=False,
        )

    # Missing extra image in real run raises FileNotFoundError
    with pytest.raises(FileNotFoundError, match="Không tìm thấy ảnh bổ sung"):
        dummy_model = tmp_path / "model.png"
        dummy_garment = tmp_path / "garment.png"
        dummy_garment.write_bytes(b"dummy")
        pipeline.run(
            model_path=dummy_model,
            garment_path=dummy_garment,
            extra_images=["non_existent_extra.png"],
            dry_run=False,
        )

    # Dry-run with extra images populates them correctly
    res_dry_extra = pipeline.run(
        model_path=dummy_model,
        garment_path=dummy_garment,
        extra_images=["mock_extra_1.png", "mock_extra_2.png"],
        dry_run=True,
    )
    assert len(res_dry_extra.shopee_images) == 3


def test_auto_tryon_manual_transfer_model_dry_run(tmp_path):
    # Setup dummy model image
    model_img = tmp_path / "nabi.png"
    model_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 300)

    # Setup user-chosen garment / transfer model image
    chosen_transfer = tmp_path / "user_chosen_garment.png"
    chosen_transfer.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 300)

    out_root = tmp_path / "manual_runs"
    pipeline = AutoTryOnPipeline(out_root=out_root)

    # 1. Run with garment_path directly without Shopee or product_dir
    res = pipeline.run(
        model_path=model_img,
        garment_path=chosen_transfer,
        dry_run=True,
        auto_stitch=True,
    )

    assert res.status == "succeeded"
    assert res.dry_run is True
    assert res.garment_image_path == str(chosen_transfer)
    assert res.model_image_path == str(model_img)
    assert Path(res.first_frame_path).is_file()
    assert Path(res.video_1_path).is_file()
    assert Path(res.last_frame_path).is_file()
    assert Path(res.video_2_path).is_file()
    assert Path(res.final_video_path).is_file()

    # 2. Run with transfer_image alias
    res_alias = pipeline.run(
        model_path=model_img,
        transfer_image=chosen_transfer,
        dry_run=True,
        auto_stitch=False,
    )
    assert res_alias.status == "succeeded"
    assert res_alias.garment_image_path == str(chosen_transfer)
    assert res_alias.final_video_path is None  # no stitch

    # 3. Run with garment_path + product_dir (extra images)
    prod_dir = tmp_path / "extra_prod"
    prod_dir.mkdir()
    extra1 = prod_dir / "extra1.jpg"
    extra1.write_bytes(b"\xff\xd8\xff")
    extra2 = prod_dir / "extra2.jpg"
    extra2.write_bytes(b"\xff\xd8\xff")

    res_extra = pipeline.run(
        model_path=model_img,
        garment_path=chosen_transfer,
        product_dir=prod_dir,
        dry_run=True,
    )
    assert res_extra.status == "succeeded"
    assert len(res_extra.shopee_images) == 3  # garment + 2 extras


def test_auto_tryon_cli_parsing(tmp_path):
    from src.Workflows.auto_tryon_pipeline import main

    model_img = tmp_path / "model.png"
    model_img.write_bytes(b"\x89PNG\r\n\x1a\n")
    transfer_img = tmp_path / "transfer.png"
    transfer_img.write_bytes(b"\x89PNG\r\n\x1a\n")

    # 1. Successful CLI invocation with --garment-path
    code1 = main([
        "--model-path", str(model_img),
        "--garment-path", str(transfer_img),
        "--dry-run",
    ])
    assert code1 == 0

    # 2. Successful CLI invocation with --transfer-image alias
    code2 = main([
        "--model-path", str(model_img),
        "--transfer-image", str(transfer_img),
        "--dry-run",
    ])
    assert code2 == 0

    # 3. Missing inputs raises SystemExit
    with pytest.raises(SystemExit):
        main(["--dry-run"])


# --------------------------------------------------------------------------- #
# 6. WebUI API Integration Tests
# --------------------------------------------------------------------------- #


def test_webui_tryon_api(tmp_path):
    from fastapi.testclient import TestClient
    from src.WebUI.app import create_app

    # Create dummy app instance
    out_dir = tmp_path / "playground"
    app = create_app(cdp_url="http://127.0.0.1:4022", out_dir=out_dir)
    client = TestClient(app)

    # 1. Missing inputs -> 400
    res = client.post("/api/tryon/start", json={})
    assert res.status_code == 400

    # 2. Dry run with product_dir
    prod_dir = tmp_path / "mock_prod"
    prod_dir.mkdir()
    res2 = client.post(
        "/api/tryon/start",
        json={
            "product_dir": str(prod_dir),
            "model_path": "assets/nabi_model.png",
            "dry_run": True,
            "confirm": False,
        },
    )
    assert res2.status_code == 200
    data = res2.json()
    assert "job_id" in data
    assert data["job_id"].startswith("j_")

    # 3. Dry run with direct garment_path
    mock_garment = tmp_path / "custom_garment.png"
    mock_garment.write_bytes(b"\x89PNG\r\n\x1a\n")
    res_garment = client.post(
        "/api/tryon/start",
        json={
            "garment_path": str(mock_garment),
            "model_path": "assets/nabi_model.png",
            "dry_run": True,
            "confirm": False,
        },
    )
    assert res_garment.status_code == 200
    assert "job_id" in res_garment.json()

    # 4. Dry run with transfer_image alias
    res_transfer = client.post(
        "/api/tryon/start",
        json={
            "transfer_image": str(mock_garment),
            "model_path": "assets/nabi_model.png",
            "dry_run": True,
            "confirm": False,
        },
    )
    assert res_transfer.status_code == 200
    assert "job_id" in res_transfer.json()

    # 5. GET /api/tryon/runs returns list
    res_runs = client.get("/api/tryon/runs")
    assert res_runs.status_code == 200
    assert "runs" in res_runs.json()
    assert isinstance(res_runs.json()["runs"], list)

    # 6. Verify background worker completes dry-run job cleanly
    import time
    job_id = res2.json()["job_id"]
    completed_job = None
    for _ in range(40):
        time.sleep(0.1)
        j = client.get(f"/api/jobs/{job_id}").json()
        if j.get("state") in ("succeeded", "failed"):
            completed_job = j
            break
    assert completed_job is not None
    assert completed_job["state"] == "succeeded"
    assert completed_job["result"]["status"] == "succeeded"
    assert completed_job["result"]["dry_run"] is True


def test_parse_shopee_ids_camel_case_and_hash():
    # CamelCase affiliate query params
    aff_camel = "https://affiliate.shopee.vn/offer/product_offer?offerId=123&itemId=456789&shopId=987654"
    shop_id, item_id = parse_shopee_ids(aff_camel)
    assert item_id == 456789
    assert shop_id == 987654

    # SPA hash query params
    spa_url = "https://affiliate.shopee.vn/#/offer/product_offer?productId=112233&sellerId=445566"
    shop_id2, item_id2 = parse_shopee_ids(spa_url)
    assert item_id2 == 112233
    assert shop_id2 == 445566


def test_gemini_multiparagraph_prompt_preserved():
    # Multi-paragraph video prompt
    raw = """
**Video 1 (0-8s):**
Nabi stands in an elegant posture facing the camera.
The camera moves slowly closer in 4k HDR cinematic lighting.

She pauses and smiles softly with natural fabric drape.

**Video 2 (8-16s):**
Nabi rotates smoothly to show the back of the garment.
Soft wind catches the lightweight cotton fabric.

Hope this helps!
"""
    p1, p2 = parse_gemini_video_prompts(raw)
    # Paragraph 2 of prompt 1 must NOT be chopped off
    assert "Nabi stands in an elegant posture" in p1
    assert "She pauses and smiles softly" in p1
    assert "Nabi rotates smoothly" in p2
    assert "Soft wind catches" in p2
    assert "Hope this helps" not in p2


def test_flow_bridge_download_video_and_image(tmp_path, monkeypatch):
    import io
    import urllib.request
    from src.Bridge.flow_bridge import FlowBridge

    br = FlowBridge(cdp_url="http://127.0.0.1:4022")

    # Mock urllib.request.urlopen to return MP4 video bytes
    dummy_mp4 = b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2mp41" + b"\x00" * 3000

    class MockResp:
        def __init__(self, data, ct):
            self.data = data
            self.headers = {"Content-Type": ct}
        def read(self):
            return self.data
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: MockResp(dummy_mp4, "video/mp4"))

    video_dest = tmp_path / "downloaded.mp4"
    ok, size = br.download("http://example.com/video.mp4", video_dest)
    assert ok is True
    assert size == len(dummy_mp4)
    assert video_dest.is_file()


def test_api_upload_and_serve(tmp_path):
    from fastapi.testclient import TestClient
    from src.WebUI.app import create_app

    out_dir = tmp_path / "out" / "playground"
    out_dir.mkdir(parents=True)
    app = create_app(cdp_url="http://127.0.0.1:4022", out_dir=out_dir)
    client = TestClient(app)

    # 1. Upload an image
    file_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    res = client.post(
        "/api/upload",
        files={"file": ("test_model.png", file_bytes, "image/png")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "filename" in data
    assert "url" in data
    assert "path" in data

    # 2. Retrieve the uploaded image
    get_res = client.get(data["url"])
    assert get_res.status_code == 200
    assert get_res.content == file_bytes


def test_api_tryon_files_serving(tmp_path):
    from fastapi.testclient import TestClient
    from src.WebUI.app import create_app

    out_dir = tmp_path / "out" / "playground"
    aff_dir = tmp_path / "out" / "affiliate_runs"
    run_dir = aff_dir / "tryon_test_123"
    run_dir.mkdir(parents=True)

    dummy_mp4 = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 50
    (run_dir / "final_tryon_video_16s.mp4").write_bytes(dummy_mp4)
    (run_dir / "first_frame.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    manifest = {
        "run_id": "tryon_test_123",
        "status": "succeeded",
        "product_title": "Test Dress",
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    app = create_app(cdp_url="http://127.0.0.1:4022", out_dir=out_dir)
    client = TestClient(app)

    # Check files endpoint
    res_v = client.get("/api/tryon/files/tryon_test_123/final_tryon_video_16s.mp4")
    assert res_v.status_code == 200
    assert res_v.content == dummy_mp4

    res_img = client.get("/api/tryon/files/tryon_test_123/first_frame.png")
    assert res_img.status_code == 200
    assert res_img.content == b"\x89PNG\r\n\x1a\n"

    # Check runs listing has enriched URLs
    res_runs = client.get("/api/tryon/runs")
    assert res_runs.status_code == 200
    runs = res_runs.json()["runs"]
    assert len(runs) >= 1
    found = next((r for r in runs if r.get("run_id") == "tryon_test_123"), None)
    assert found is not None
    assert found.get("final_video_url") == "/api/tryon/files/tryon_test_123/final_tryon_video_16s.mp4"
    assert found.get("first_frame_url") == "/api/tryon/files/tryon_test_123/first_frame.png"


def test_api_upload_sanitization_and_validation(tmp_path):
    from fastapi.testclient import TestClient
    from src.WebUI.app import create_app

    out_dir = tmp_path / "out" / "playground"
    out_dir.mkdir(parents=True)
    app = create_app(cdp_url="http://127.0.0.1:4022", out_dir=out_dir)
    client = TestClient(app)

    # 1. Filename with special URL characters (#, spaces, quotes)
    file_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    res = client.post(
        "/api/upload",
        files={"file": ("my photo #1 (sample).png", file_bytes, "image/png")},
    )
    assert res.status_code == 200
    data = res.json()
    assert "#" not in data["filename"]
    # Can fetch successfully without 404 URL fragmentation
    get_res = client.get(data["url"])
    assert get_res.status_code == 200
    assert get_res.content == file_bytes

    # 2. Reject non-image extension
    res_bad = client.post(
        "/api/upload",
        files={"file": ("exploit.exe", b"binary", "application/octet-stream")},
    )
    assert res_bad.status_code == 400

    # 3. Reject empty file
    res_empty = client.post(
        "/api/upload",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert res_empty.status_code == 400


def test_auto_tryon_pipeline_direct_first_frame_dry_run(tmp_path):
    """Test the streamlined 3-step video pipeline directly starting from first frame."""
    out_root = tmp_path / "affiliate_runs"
    pipeline = AutoTryOnPipeline(out_root=out_root)

    first_frame = tmp_path / "custom_first_frame.png"
    first_frame.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 300)

    res = pipeline.run(
        first_frame_path=first_frame,
        override_video_prompt_1="Cinematic woman walking in bakery, 8 seconds",
        override_video_prompt_2="Cinematic woman turning towards camera with smile, 8 seconds",
        dry_run=True,
        auto_stitch=True,
    )

    assert res.status == "succeeded"
    assert res.first_frame_path is not None
    assert Path(res.first_frame_path).exists()
    assert res.video_prompt_1 == "Cinematic woman walking in bakery, 8 seconds"
    assert res.video_prompt_2 == "Cinematic woman turning towards camera with smile, 8 seconds"
    assert res.video_1_path is not None
    assert res.last_frame_path is not None
    assert res.video_2_path is not None
    assert res.final_video_path is not None


def test_api_tryon_start_with_first_frame(tmp_path):
    """Test API accepts direct first_frame_path without requiring garment_path or shopee_url."""
    from fastapi.testclient import TestClient
    from src.WebUI.app import create_app

    out_dir = tmp_path / "out" / "playground"
    out_dir.mkdir(parents=True)
    app = create_app(cdp_url="http://127.0.0.1:4022", out_dir=out_dir)
    client = TestClient(app)

    res = client.post(
        "/api/tryon/start",
        json={
            "first_frame_path": "out/first_frame_perfect.png",
            "video_prompt_1": "Video 1 prompt",
            "video_prompt_2": "Video 2 prompt",
            "dry_run": True,
            "confirm": True,
        },
    )
    assert res.status_code == 200
    assert "job_id" in res.json()




