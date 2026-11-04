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


def test_starting_frame_attach_video_ingredients_single(tmp_path):
    from src.Bridge.flow_video.starting_frame import StartingFrameMixin

    class FakeBridge:
        def __init__(self):
            self.cleared = False
            self.attached = []

        def clear_reference_chips(self):
            self.cleared = True

        def attach_reference_paste(self, p, timeout_s=90.0, settle_s=0.5, clear_existing=False):
            self.attached.append((p, settle_s, clear_existing))
            return {"status": "ok", "path": str(p), "upload_s": 0.4}

    f1 = tmp_path / "img1.png"
    f1.write_bytes(b"data1")

    mixin = StartingFrameMixin()
    mixin._log = lambda lvl, msg: None
    br = FakeBridge()
    res = mixin.attach_video_ingredients(br, [f1], settle_s=2.0)
    assert br.cleared is True
    assert len(br.attached) == 1
    assert br.attached[0] == (f1, 2.0, False)
    assert len(res) == 1


def test_flow_client_account_id_default_and_custom():
    from src.Workflows.flow_client import FlowClient

    fc1 = FlowClient()
    assert fc1.account_id == "default"

    fc2 = FlowClient(account_id="acc_user1")
    assert fc2.account_id == "acc_user1"




def test_video_ingredients_submit_rpc_constant():
    from src.Bridge.flow_video.constants import VIDEO_INGREDIENTS_SUBMIT_RPC
    assert VIDEO_INGREDIENTS_SUBMIT_RPC == "MZZa6b"


def test_video_generation_mzza6b_spec_preserves_ingredients():
    import copy
    import uuid
    from src.Bridge.flow_video.constants import VIDEO_INGREDIENTS_SUBMIT_RPC

    # Simulated MZZa6b captured base_spec
    captured_base_spec = [
        [None, None, [[["A cinematic runway scene"]]]],
        [[None, "media-id-1"], [None, "media-id-2"]],
        "abra_r2v_8s",
        1,
        None,
        [None, None, None, None, "OLD-U1", "OLD-U2"],
    ]

    cap_rpcid = VIDEO_INGREDIENTS_SUBMIT_RPC
    base_spec = copy.deepcopy(captured_base_spec)
    is_ingredients_spec = (
        cap_rpcid == VIDEO_INGREDIENTS_SUBMIT_RPC
        or (len(base_spec) > 1 and isinstance(base_spec[1], list))
    )
    assert is_ingredients_spec is True

    clean_prompt = "Refined runway prompt"
    eff_model_key = "abra_r2v_8s"
    aspect_val = 1
    seed_to_use = 12345
    u1 = str(uuid.uuid4()).upper()
    u2 = str(uuid.uuid4()).upper()

    s = copy.deepcopy(base_spec)
    if len(s) > 0 and isinstance(s[0], list):
        s[0] = [None, None, [[[clean_prompt]]]]
    if is_ingredients_spec:
        r2v_model_key = eff_model_key.replace("abra_t2v", "abra_r2v") if "abra_t2v" in eff_model_key else eff_model_key
        if len(s) > 2:
            s[2] = r2v_model_key
        if len(s) > 3:
            s[3] = int(aspect_val)
        if len(s) > 4 and s[4] is not None:
            s[4] = int(seed_to_use)
    
    uuid_idx = None
    for idx in range(len(s) - 1, 3, -1):
        slot = s[idx]
        if isinstance(slot, list) and len(slot) >= 6:
            if slot[0] is None and slot[1] is None and slot[2] is None and slot[3] is None:
                uuid_idx = idx
                break
    if uuid_idx is None:
        uuid_idx = 5 if is_ingredients_spec else 4
    if uuid_idx < len(s) and isinstance(s[uuid_idx], list) and len(s[uuid_idx]) >= 6:
        s[uuid_idx][4] = u1
        s[uuid_idx][5] = u2

    # Verification:
    # 1. Prompt was updated
    assert s[0][2][0][0][0] == "Refined runway prompt"
    # 2. Ingredients list was PRESERVED at s[1]
    assert s[1] == [[None, "media-id-1"], [None, "media-id-2"]]
    # 3. Model key is abra_r2v_8s at s[2]
    assert s[2] == "abra_r2v_8s"
    # 4. Aspect ratio is 1 at s[3]
    assert s[3] == 1
    # 5. UUID slot was correctly placed at index 5 with new UUIDs
    assert uuid_idx == 5
    assert s[5][4] == u1
    assert s[5][5] == u2
