"""API-level tests for the canvas node endpoints (validation only, no browser)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.WebUI.app import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory) -> TestClient:
    base = tmp_path_factory.mktemp("node_api")
    app = create_app(
        out_dir=base / "playground",
        projects_file=base / "projects.json",
        pool_config=base / "pool.json",
        pool_state=base / "pool_state.json",
        web_dist=base / "dist",
    )
    return TestClient(app)


def test_node_options_matches_captured_flow_composer(client: TestClient):
    """Options come from flow_catalog (0-credit captures), never from FE guesses."""
    r = client.get("/api/node/options")
    assert r.status_code == 200
    body = r.json()

    image = body["image"]
    assert image["aspect_ratios"] == ["16:9", "4:3", "1:1", "3:4", "9:16"]
    assert image["aspect_enums"] == {"16:9": 3, "9:16": 2, "4:3": 5, "1:1": 1, "3:4": 4}
    assert image["counts"] == [1, 2, 3, 4]
    assert [(m["id"], m["model_key"]) for m in image["models"]] == [
        ("nano_banana_pro", "GEM_PIX_2"),
        ("nano_banana_2_lite", "HARBOR_SEAL"),
        ("nano_banana_2_1", "BELUGA"),
    ]

    video = body["video"]
    assert video["sub_modes"] == ["frames", "ingredients"]
    assert video["aspect_ratios"] == ["16:9", "9:16"]
    assert video["counts"] == [1, 2, 3, 4]
    assert video["supports_text_to_video"] is True
    assert video["supports_last_frame"] is True
    assert video["supports_video_reference"] is True
    models = {m["id"]: m for m in video["models"]}
    # Omni 1.1 / Veo Fast / Veo Quality are retired by Flow on 5 Dec, so the catalog no
    # longer offers them; only Omni 1.2 and Veo Lite remain selectable.
    assert set(models) == {"omni_1_2_flash", "veo_3_1_lite"}
    assert video["default_model"] == "omni_1_2_flash"
    # Omni 1.2 replaced the 4/6/8/10 radios with a 3..15s slider, capped at 10s when a
    # last frame is attached (observed 2026-11-09).
    assert models["omni_1_2_flash"]["has_resolution"] is True
    assert models["omni_1_2_flash"]["durations_s"] == list(range(3, 16))
    assert models["omni_1_2_flash"]["durations_with_last_frame_s"] == list(range(3, 11))
    assert models["omni_1_2_flash"]["has_last_frame"] is True
    assert models["veo_3_1_lite"]["has_resolution"] is False
    assert models["veo_3_1_lite"]["has_duration"] is False
    assert models["veo_3_1_lite"]["durations_s"] == [8]
    assert "360p" not in models["veo_3_1_lite"]["resolutions"]

    # Agent mode locks the whole config block.
    assert body["agent"]["locks_config"] is True
    assert "model" in body["agent"]["locked_fields"]
    assert "count" in body["agent"]["locked_fields"]


def test_node_image_accepts_every_captured_ratio(client: TestClient):
    """All five ratios now have a captured enum ⇒ none may be rejected as unverified."""
    for ratio in ("16:9", "4:3", "1:1", "3:4", "9:16"):
        r = client.post("/api/node/image", json={"prompt": "x", "aspect_ratio": ratio, "dry_run": True})
        assert r.status_code == 200, f"{ratio}: {r.text}"


def test_node_image_rejects_unknown_ratio(client: TestClient):
    r = client.post("/api/node/image", json={"prompt": "x", "aspect_ratio": "21:9", "dry_run": True})
    assert r.status_code == 400
    assert "21:9" in r.json()["detail"]


def test_node_image_rejects_unknown_model_and_bad_count(client: TestClient):
    r = client.post(
        "/api/node/image",
        json={"prompt": "x", "aspect_ratio": "16:9", "model": "nano_banana_9", "dry_run": True},
    )
    assert r.status_code == 400
    assert "nano_banana_9" in r.json()["detail"]

    r = client.post(
        "/api/node/image",
        json={"prompt": "x", "aspect_ratio": "16:9", "count": 9, "dry_run": True},
    )
    assert r.status_code == 400
    assert "Số lượng" in r.json()["detail"]


def test_node_image_echoes_model_and_count(client: TestClient):
    r = client.post(
        "/api/node/image",
        json={
            "prompt": "x",
            "aspect_ratio": "1:1",
            "model": "nano_banana_pro",
            "count": 3,
            "dry_run": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"] == "nano_banana_pro"
    assert body["model_key"] == "GEM_PIX_2"
    assert body["count"] == 3
    assert body["aspect"] == 1


def test_node_image_requires_confirm(client: TestClient):
    r = client.post("/api/node/image", json={"prompt": "x", "aspect_ratio": "16:9"})
    assert r.status_code == 400
    assert "confirm" in r.json()["detail"]


def test_node_image_rejects_bad_seed(client: TestClient):
    r = client.post("/api/node/image", json={"prompt": "x", "aspect": 3, "seed": 0, "dry_run": True})
    assert r.status_code == 400
    assert "int32" in r.json()["detail"]


def test_node_video_requires_frame_or_auto_image(client: TestClient):
    r = client.post(
        "/api/node/video",
        json={"prompt": "x", "auto_image": False, "aspect_ratio": "9:16", "dry_run": True},
    )
    assert r.status_code == 400
    assert "Khung hình" in r.json()["detail"]


def test_node_video_ingredients_needs_no_frame(client: TestClient):
    """"Thành phần" is a real text→video path (`YhhmEf`): no frame, no auto image."""
    r = client.post(
        "/api/node/video",
        json={
            "prompt": "x",
            "sub_mode": "ingredients",
            "auto_image": False,
            "aspect_ratio": "9:16",
            "dry_run": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sub_mode"] == "ingredients"
    assert body["frame_source"] == "none"
    # Default model is Omni 1.2, whose reference-free ingredients key is `macaron_cookie_t2v_*`.
    assert body["model_key"] == "macaron_cookie_t2v_8s"


def test_node_video_ingredients_accepts_reference_images(client: TestClient, tmp_path: Path):
    """'Thành phần' with reference images returns frame_source='provided' and accepts valid files."""
    ref1 = tmp_path / "ref1.png"
    ref1.write_bytes(b"png1")
    ref2 = tmp_path / "ref2.jpg"
    ref2.write_bytes(b"jpg2")
    r = client.post(
        "/api/node/video",
        json={
            "prompt": "x",
            "sub_mode": "ingredients",
            "reference_image_paths": [str(ref1), str(ref2)],
            "aspect_ratio": "9:16",
            "dry_run": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sub_mode"] == "ingredients"
    assert body["frame_source"] == "provided"


def test_node_video_ingredients_validates_reference_images(client: TestClient):
    """'Thành phần' validates that attached reference images actually exist on disk."""
    r = client.post(
        "/api/node/video",
        json={
            "prompt": "x",
            "sub_mode": "ingredients",
            "reference_image_paths": ["nonexistent_ref_image_12345.png"],
            "aspect_ratio": "9:16",
            "dry_run": True,
        },
    )
    assert r.status_code == 400
    assert "Không tìm thấy ảnh đính kèm" in r.json()["detail"]


def test_node_video_ingredients_accepts_single_reference_path(client: TestClient, tmp_path: Path):
    """'Thành phần' also accepts reference_image_path as a single string."""
    ref = tmp_path / "single_ref.png"
    ref.write_bytes(b"png")
    r = client.post(
        "/api/node/video",
        json={
            "prompt": "x",
            "sub_mode": "ingredients",
            "reference_image_path": str(ref),
            "aspect_ratio": "9:16",
            "dry_run": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sub_mode"] == "ingredients"
    assert body["frame_source"] == "provided"


def test_node_video_rejects_bad_ratio_and_duration(client: TestClient):
    r = client.post("/api/node/video", json={"prompt": "x", "aspect_ratio": "1:1", "dry_run": True})
    assert r.status_code == 400
    r = client.post("/api/node/video", json={"prompt": "x", "duration_s": 16, "dry_run": True})
    assert r.status_code == 400
    assert "16s" in r.json()["detail"] or "không hỗ trợ" in r.json()["detail"].lower()


def test_node_video_veo_fixes_resolution_and_duration(client: TestClient):
    """Veo hides the resolution + duration groups, so those values must be rejected."""
    r = client.post(
        "/api/node/video",
        json={
            "prompt": "x",
            "model": "veo_3_1_lite",
            "sub_mode": "ingredients",
            "resolution": "360p",
            "auto_image": False,
            "dry_run": True,
        },
    )
    assert r.status_code == 400
    assert "360p" in r.json()["detail"]

    r = client.post(
        "/api/node/video",
        json={
            "prompt": "x",
            "model": "veo_3_1_lite",
            "sub_mode": "ingredients",
            "duration_s": 4,
            "auto_image": False,
            "dry_run": True,
        },
    )
    assert r.status_code == 400

    ok = client.post(
        "/api/node/video",
        json={
            "prompt": "x",
            "model": "veo_3_1_lite",
            "sub_mode": "ingredients",
            "aspect_ratio": "16:9",
            "duration_s": 8,
            "resolution": "1080p",
            "auto_image": False,
            "dry_run": True,
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["model_key"] == "veo_3_1_t2v_lite"

    portrait = client.post(
        "/api/node/video",
        json={
            "prompt": "x",
            "model": "veo_3_1_lite",
            "sub_mode": "ingredients",
            "aspect_ratio": "9:16",
            "auto_image": False,
            "dry_run": True,
        },
    )
    assert portrait.status_code == 200, portrait.text
    assert portrait.json()["model_key"] == "veo_3_1_t2v_lite"


def test_node_video_retired_model_falls_back_to_the_live_default(client: TestClient):
    """A canvas that still names a retired model must keep submitting, on Omni 1.2.

    The three models Flow retires on 5 Dec are gone from the catalog, but stored node configs
    still carry their ids; resolving them to the default is what keeps those nodes runnable.
    """
    r = client.post(
        "/api/node/video",
        json={
            "prompt": "x",
            "model": "veo_3_1_fast",
            "sub_mode": "ingredients",
            "duration_s": 8,
            "auto_image": False,
            "dry_run": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["model"] == "omni_1_2_flash"
    assert r.json()["model_key"] == "macaron_cookie_t2v_8s"


def test_node_video_omni_360p_and_durations(client: TestClient):
    r = client.post(
        "/api/node/video",
        json={
            "prompt": "x",
            "model": "omni_1_2_flash",
            "sub_mode": "ingredients",
            "resolution": "360p",
            "duration_s": 4,
            "auto_image": False,
            "dry_run": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["model_key"] == "macaron_cookie_t2v_4s_360p"

    r = client.post(
        "/api/node/video",
        json={
            "prompt": "x",
            "model": "omni_1_2_flash",
            "sub_mode": "frames",
            "resolution": "720p",
            "duration_s": 10,
            "auto_image": True,
            "dry_run": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["model_key"] == "macaron_cookie_i2v_10s"


def test_node_video_requires_confirm(client: TestClient):
    r = client.post("/api/node/video", json={"prompt": "x", "aspect_ratio": "9:16"})
    assert r.status_code == 400
    assert "confirm" in r.json()["detail"]


def test_node_video_last_frame_switches_key_and_caps_duration(client: TestClient, tmp_path: Path):
    """A last frame is not an option: it changes the RPC, the key and the duration ceiling.

    Flow caps the clip at 10s once both frame slots are filled (slider max 12 → 7), so a
    15s request must be rejected rather than silently submitted at the wrong length.
    """
    first = tmp_path / "first.png"
    last = tmp_path / "last.png"
    for p in (first, last):
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    base = {
        "prompt": "x",
        "model": "omni_1_2_flash",
        "sub_mode": "frames",
        "resolution": "720p",
        "auto_image": False,
        "dry_run": True,
        "frame_path": str(first),
        "last_frame_path": str(last),
    }

    r = client.post("/api/node/video", json={**base, "duration_s": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_last_frame"] is True
    assert body["model_key"] == "macaron_cookie_i2v_fl_5s"

    # 10s is the last frame's ceiling; 11s and 15s are out of range for that shape.
    assert client.post("/api/node/video", json={**base, "duration_s": 10}).status_code == 200
    for too_long in (11, 15):
        r = client.post("/api/node/video", json={**base, "duration_s": too_long})
        assert r.status_code == 400, f"{too_long}s must be rejected with a last frame"
        assert "Kết thúc" in r.json()["detail"]

    # Without the last frame the same 15s is valid again, and the key loses `_fl`.
    r = client.post("/api/node/video", json={**base, "duration_s": 15, "last_frame_path": None})
    assert r.status_code == 200, r.text
    assert r.json()["model_key"] == "macaron_cookie_i2v_15s"
    assert r.json()["has_last_frame"] is False


def test_node_video_video_reference_takes_the_edit_path(client: TestClient):
    """A clip reference leaves the Omni family entirely: `jIps6` / `abra_edit`.

    It also implies the ingredients sub-mode and makes image references irrelevant, because
    Flow fires exactly one submit RPC.
    """
    r = client.post(
        "/api/node/video",
        json={
            "prompt": "x",
            "model": "omni_1_2_flash",
            "duration_s": 5,
            "resolution": "720p",
            "auto_image": False,
            "dry_run": True,
            "video_reference_title": "Fashion model",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model_key"] == "abra_edit"
    # Requested `frames` was overridden: a video reference only exists in "Thành phần".
    assert body["sub_mode"] == "ingredients"


def test_node_prompt_limit_is_7200(client: TestClient):
    """Prompt dài (>5.000 ký tự) phải qua được validate; chỉ chặn khi vượt 7.200."""
    ok = client.post(
        "/api/node/image",
        json={"prompt": "a" * 7200, "aspect_ratio": "16:9", "dry_run": True},
    )
    assert ok.status_code == 200, ok.text

    too_long = client.post(
        "/api/node/image",
        json={"prompt": "a" * 7201, "aspect_ratio": "16:9", "dry_run": True},
    )
    assert too_long.status_code == 422
    assert "7200" in too_long.json()["detail"]


def test_node_files_blocks_traversal(client: TestClient, tmp_path: Path):
    r = client.get("/api/node/files/..%2F..%2Fconfigs%2Faccounts_pool.json")
    assert r.status_code == 404


def test_node_image_and_video_accept_preferred_account_and_workspace(client: TestClient):
    r_img = client.post(
        "/api/node/image",
        json={
            "prompt": "test prompt",
            "aspect_ratio": "16:9",
            "workspace_project_id": "prj_workspace_123",
            "preferred_account_id": "flow_account_a",
            "dry_run": True,
        },
    )
    assert r_img.status_code == 200
    job_id_img = r_img.json()["job_id"]
    job_img = client.app.state.manager.get(job_id_img)
    assert job_img.params["workspace_project_id"] == "prj_workspace_123"
    assert job_img.params["preferred_account_id"] == "flow_account_a"

    r_vid = client.post(
        "/api/node/video",
        json={
            "prompt": "test video",
            "aspect_ratio": "9:16",
            "sub_mode": "ingredients",
            "workspace_project_id": "prj_workspace_456",
            "preferred_account_id": "flow_account_b",
            "dry_run": True,
        },
    )
    assert r_vid.status_code == 200
    job_id_vid = r_vid.json()["job_id"]
    job_vid = client.app.state.manager.get(job_id_vid)
    assert job_vid.params["workspace_project_id"] == "prj_workspace_456"
    assert job_vid.params["preferred_account_id"] == "flow_account_b"
