from pathlib import Path
import pytest
from src.WebUI.app import NodeImageBody
from src.Workflows.media_service import MediaService, NodeImageResult
from tests.test_media_service import FakeImageClient, PROJECT_ID


def test_node_image_body_multiple_references():
    body = NodeImageBody(
        prompt="A photo with multiple styles",
        reference_image_paths=["out/uploads/ref1.png", "out/uploads/ref2.png"],
    )
    assert body.reference_image_paths == ["out/uploads/ref1.png", "out/uploads/ref2.png"]
    assert body.reference_image_path is None


def test_media_service_multiple_references(tmp_path):
    img1 = tmp_path / "ref1.png"
    img1.write_bytes(b"\x89PNG\r\n\x1a\nfakeimage1")
    img2 = tmp_path / "ref2.png"
    img2.write_bytes(b"\x89PNG\r\n\x1a\nfakeimage2")

    fake = FakeImageClient(tmp_path)
    svc = MediaService("http://127.0.0.1:4022", tmp_path, account_id="acc_01")
    svc.image = fake

    # Call with multiple references
    res: NodeImageResult = svc.generate_image(
        prompt="Combine both images",
        reference_images=[img1, img2],
        dry_run=True,
    )
    assert res.status == "dry_run"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["prompt"] == "Combine both images"
