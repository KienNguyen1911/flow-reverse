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


def test_node_video_body_multiple_references():
    from src.WebUI.routes.node import NodeVideoBody

    body = NodeVideoBody(
        prompt="Dynamic scene",
        reference_image_paths=["out/uploads/ref1.png", "out/uploads/ref2.png"],
        sub_mode="ingredients",
    )
    assert body.reference_image_paths == ["out/uploads/ref1.png", "out/uploads/ref2.png"]
    assert body.reference_image_path is None


def test_starting_frame_attach_video_ingredients(tmp_path):
    from src.Bridge.flow_video.starting_frame import StartingFrameMixin

    class FakeBridge:
        def __init__(self):
            self.cleared = False
            self.attached = []

        def clear_reference_chips(self):
            self.cleared = True

        def attach_reference_paste(self, p, timeout_s=90.0, settle_s=0.5, clear_existing=False):
            self.attached.append((p, settle_s, clear_existing))
            return {"status": "ok", "path": str(p)}

    f1 = tmp_path / "img1.png"
    f1.write_bytes(b"data1")
    f2 = tmp_path / "img2.png"
    f2.write_bytes(b"data2")

    mixin = StartingFrameMixin()
    mixin._log = lambda lvl, msg: None
    br = FakeBridge()
    res = mixin.attach_video_ingredients(br, [f1, f2], settle_s=0.0)
    assert br.cleared is True
    assert len(br.attached) == 2
    assert br.attached[0] == (f1, 0.5, False)
    assert br.attached[1] == (f2, 0.5, False)
    assert len(res) == 2

