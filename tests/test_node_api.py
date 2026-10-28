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


def test_node_options(client: TestClient):
    r = client.get("/api/node/options")
    assert r.status_code == 200
    body = r.json()
    assert body["image"]["aspect_ratios"] == {"16:9": 3}
    assert body["video"]["aspect_ratios"] == ["9:16", "16:9"]
    assert body["video"]["supports_text_to_video"] is False


def test_node_image_rejects_unverified_ratio(client: TestClient):
    r = client.post("/api/node/image", json={"prompt": "x", "aspect_ratio": "9:16", "dry_run": True})
    assert r.status_code == 400
    assert "capture_image_aspects" in r.json()["detail"]


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
    assert "image-to-video" in r.json()["detail"]


def test_node_video_rejects_bad_ratio_and_duration(client: TestClient):
    r = client.post("/api/node/video", json={"prompt": "x", "aspect_ratio": "1:1", "dry_run": True})
    assert r.status_code == 400
    r = client.post("/api/node/video", json={"prompt": "x", "duration_s": 16, "dry_run": True})
    assert r.status_code == 400
    assert "8s" in r.json()["detail"]


def test_node_video_requires_confirm(client: TestClient):
    r = client.post("/api/node/video", json={"prompt": "x", "aspect_ratio": "9:16"})
    assert r.status_code == 400
    assert "confirm" in r.json()["detail"]


def test_node_files_blocks_traversal(client: TestClient, tmp_path: Path):
    r = client.get("/api/node/files/..%2F..%2Fconfigs%2Faccounts_pool.json")
    assert r.status_code == 404
