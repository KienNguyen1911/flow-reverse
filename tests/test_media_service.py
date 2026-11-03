"""Tests for the canvas node media service (image/video independence + options)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.Workflows.account_pool import ReferenceMediaRegistry, sha256_file
from src.Workflows.flow_models import GeneratedImage, GenerationResult, ReferenceTemplate
from src.Workflows.media_service import (
    AspectNotVerifiedError,
    MediaService,
    UnsupportedOptionError,
    cdp_lock,
    load_image_aspects,
    node_options,
    normalize_video_ratio,
    normalize_video_resolution,
    resolve_image_aspect,
    resolve_input_path,
    validate_video_duration,
)

PROJECT_ID = "11111111-1111-4111-8111-111111111111"


class FakeImageClient:
    """Stand-in for FlowClient.generate_image / upload_reference_image."""

    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.uploads: list[str] = []
        self.calls: list[dict] = []

    def status(self):
        return SimpleNamespace(flow_project_id=PROJECT_ID)

    def list_projects(self, on_event=None):
        return []

    def create_project(self, title, on_event=None):
        return SimpleNamespace(id=PROJECT_ID, title=title)

    def upload_reference_image(self, project_id, file_path, *, prompt_probe="reference", on_event=None):
        self.uploads.append(str(file_path))
        return ReferenceTemplate(
            sha256=sha256_file(file_path),
            project_id=project_id,
            prompt=prompt_probe,
            template_args=[],
            source_path=str(file_path),
        )

    def generate_image(
        self,
        project_id,
        prompt,
        *,
        aspect=3,
        aspect_ratio=None,
        seed=None,
        dry_run=False,
        remove_watermark=True,
        poll_timeout_s=150.0,
        anti_abuse_retries=1,
        reference=None,
        model_key=None,
        model_label=None,
        count=1,
        on_event=None,
    ):
        self.calls.append(
            {
                "project_id": project_id,
                "prompt": prompt,
                "aspect": aspect,
                "aspect_ratio": aspect_ratio,
                "seed": seed,
                "dry_run": dry_run,
                "reference": reference,
                "model_key": model_key,
                "model_label": model_label,
                "count": count,
            }
        )
        run_dir = self.out_dir / f"img_run_{len(self.calls)}"
        run_dir.mkdir(parents=True, exist_ok=True)
        f = run_dir / "out.jpg"
        f.write_bytes(b"jpeg-bytes")
        img = GeneratedImage(
            prompt=prompt,
            file_path=str(f) if not dry_run else None,
            file_bytes=None if dry_run else len(b"jpeg-bytes"),
            resolution=[1376, 768],
            width=1376,
            height=768,
            media_id="media_1",
        )
        return GenerationResult(
            status="dry_run" if dry_run else "ok",
            image=img,
            run_dir=str(run_dir),
            seed_used=seed or 4242,
            elapsed_s=0.01,
        )


class FakeVideoBridge:
    def __init__(self):
        self.calls: list[dict] = []
        self.text_calls: list[dict] = []

    def generate_video_flow(self, **kwargs):
        self.calls.append(kwargs)
        dest = Path(kwargs["dest_path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"ftyp-mp4")
        return dest

    def generate_text_video_flow(self, **kwargs):
        self.text_calls.append(kwargs)
        dest = Path(kwargs["dest_path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"ftyp-mp4")
        return dest


def _service(tmp_path: Path, *, registry=None, account_id="acc_1"):
    image = FakeImageClient(tmp_path / "nodes")
    video = FakeVideoBridge()
    svc = MediaService(
        cdp_url="http://127.0.0.1:4999",
        out_dir=tmp_path / "nodes",
        account_id=account_id,
        registry=registry,
        image_client=image,
        video_bridge=video,
    )
    return svc, image, video


# --------------------------------------------------------------------------- #
# Option resolution
# --------------------------------------------------------------------------- #


def test_resolve_image_aspect_verified_and_escape_hatch(tmp_path):
    assert resolve_image_aspect("16:9") == ("16:9", 3)
    assert resolve_image_aspect(" 16x9 ") == ("16:9", 3)
    assert resolve_image_aspect("landscape") == ("16:9", 3)
    assert resolve_image_aspect("3") == ("16:9", 3)
    # Raw enum is passed through untouched (values captured by hand).
    assert resolve_image_aspect(aspect=7) == ("aspect_7", 7)


def test_resolve_image_aspect_reads_capture_config(tmp_path):
    cfg = tmp_path / "image_aspect_enums.json"
    cfg.write_text('{"ratios": {"9:16": 1, "1:1": 2}}', encoding="utf-8")
    assert resolve_image_aspect("9:16", config_path=cfg) == ("9:16", 1)
    assert load_image_aspects(cfg)["1:1"] == 2
    assert load_image_aspects(cfg)["16:9"] == 3  # built-in stays available
    assert load_image_aspects(cfg)["4:3"] == 5  # captured 2026-11-03
    assert load_image_aspects(cfg)["3:4"] == 4
    # Without the capture config a ratio with no captured enum must fail loudly, never guess.
    with pytest.raises(AspectNotVerifiedError) as exc:
        resolve_image_aspect("21:9", config_path=tmp_path / "missing.json")
    assert "capture_image_aspects" in str(exc.value)


def test_video_option_validation():
    assert normalize_video_ratio("portrait") == "9:16"
    assert normalize_video_ratio("16:9") == "16:9"
    with pytest.raises(UnsupportedOptionError):
        normalize_video_ratio("1:1")
    assert normalize_video_resolution("1080") == "1080p"
    assert normalize_video_resolution("720") == "720p"
    assert normalize_video_resolution("360") == "360p"
    with pytest.raises(UnsupportedOptionError):
        normalize_video_resolution("4k")
    assert validate_video_duration(8) == 8
    assert validate_video_duration(4) == 4
    with pytest.raises(UnsupportedOptionError):
        validate_video_duration(16)


def test_video_option_validation_per_model():
    """Veo hides resolution + duration, so those choices must fail loudly per model."""
    assert normalize_video_resolution("360p", model="omni_1_1_flash") == "360p"
    assert normalize_video_resolution("1080p", model="omni_1_1_flash") == "1080p"
    with pytest.raises(UnsupportedOptionError) as exc:
        normalize_video_resolution("360p", model="veo_3_1_fast")
    assert "360p" in str(exc.value)
    assert validate_video_duration(4, model="omni_1_1_flash") == 4
    assert validate_video_duration(8, model="veo_3_1_quality") == 8
    with pytest.raises(UnsupportedOptionError):
        validate_video_duration(4, model="veo_3_1_quality")


def test_node_options_exposes_captured_catalog(tmp_path):
    opts = node_options(config_path=tmp_path / "none.json")
    assert opts["image"]["aspect_ratios"] == ["16:9", "4:3", "1:1", "3:4", "9:16"]
    assert opts["image"]["supports_reference_image"] is True
    assert opts["image"]["counts"] == [1, 2, 3, 4]
    assert [m["id"] for m in opts["image"]["models"]] == [
        "nano_banana_pro", "nano_banana_2_lite", "nano_banana_2_1"
    ]
    assert opts["video"]["aspect_ratios"] == ["16:9", "9:16"]
    assert opts["video"]["sub_modes"] == ["frames", "ingredients"]
    assert opts["video"]["supports_text_to_video"] is True
    assert opts["video"]["auto_image_chain"] is True
    assert opts["video"]["counts"] == [1, 2, 3, 4]
    assert opts["agent"]["locks_config"] is True


def test_cdp_lock_is_shared_per_endpoint():
    assert cdp_lock("http://127.0.0.1:4999/") is cdp_lock("http://127.0.0.1:4999")
    assert cdp_lock("http://127.0.0.1:4999") is not cdp_lock("http://127.0.0.1:4998")


def test_resolve_input_path_maps_api_prefixes(tmp_path):
    direct = tmp_path / "a.png"
    direct.write_bytes(b"x")
    assert resolve_input_path(direct) == direct.resolve()
    assert resolve_input_path(str(direct) + "?v=2") == direct.resolve()
    mapped = resolve_input_path("/api/uploads/2026_photo.png")
    assert mapped.as_posix().endswith("/out/uploads/2026_photo.png")


# --------------------------------------------------------------------------- #
# Image node
# --------------------------------------------------------------------------- #


def test_image_node_reuses_reference_cache(tmp_path):
    registry = ReferenceMediaRegistry(tmp_path / "ref_cache.json")
    svc, image, _video = _service(tmp_path, registry=registry)
    ref = tmp_path / "garment.png"
    ref.write_bytes(b"garment")

    first = svc.generate_image(prompt="a model wearing it", aspect_ratio="16:9", reference_image=ref)
    assert first.status == "ok"
    assert first.aspect_ratio == "16:9" and first.aspect_enum == 3
    assert first.project_id == PROJECT_ID
    assert first.file_path and Path(first.file_path).is_file()
    assert first.reference_sha256 == sha256_file(ref)
    assert image.calls[0]["reference"] is not None
    assert len(image.uploads) == 1

    second = svc.generate_image(prompt="another shot", reference_image=ref)
    assert second.status == "ok"
    assert len(image.uploads) == 1, "second call must hit the reference cache"
    assert image.calls[1]["reference"].sha256 == sha256_file(ref)


def test_image_node_dry_run_has_no_file(tmp_path):
    svc, image, _video = _service(tmp_path)
    res = svc.generate_image(prompt="plan only", dry_run=True)
    assert res.status == "dry_run"
    assert res.file_path is None
    assert res.dry_run is True
    assert image.calls[0]["dry_run"] is True


# --------------------------------------------------------------------------- #
# Video node
# --------------------------------------------------------------------------- #


def test_video_node_with_attached_frame(tmp_path):
    svc, _image, video = _service(tmp_path)
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"frame")

    res = svc.generate_video(
        prompt="camera pans slowly",
        frame_path=frame,
        aspect_ratio="9:16",
        resolution="720p",
        seed=99,
        remove_watermark=False,
    )
    assert res.status == "ok"
    assert res.frame_source == "provided"
    assert res.frame_path and Path(res.frame_path).is_file()
    assert res.video_path and Path(res.video_path).is_file()
    assert Path(res.run_dir, "manifest.json").is_file()
    call = video.calls[0]
    assert call["aspect_ratio"] == "9:16"
    assert call["resolution"] == "720p"
    assert call["seed"] == 99
    assert call["project_id"] == PROJECT_ID
    assert call["prompt_text"] == "camera pans slowly"


def test_video_node_without_frame_chains_image_generation(tmp_path):
    svc, image, video = _service(tmp_path)
    res = svc.generate_video(prompt="a dancer in a studio", aspect_ratio="16:9", remove_watermark=False)
    assert res.status == "ok"
    assert res.frame_source == "generated"
    assert res.image_prompt == "a dancer in a studio"
    assert image.calls[0]["aspect"] == 3, "auto image uses the verified 16:9 enum"
    assert Path(video.calls[0]["frame_path"]).is_file()


def test_video_node_without_frame_and_auto_image_off_fails(tmp_path):
    svc, image, video = _service(tmp_path)
    with pytest.raises(UnsupportedOptionError):
        svc.generate_video(prompt="no frame", auto_image=False)
    assert image.calls == [] and video.calls == []


def test_video_node_dry_run_does_not_call_bridge(tmp_path):
    svc, _image, video = _service(tmp_path)
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"frame")
    res = svc.generate_video(prompt="plan", frame_path=frame, dry_run=True)
    assert res.status == "dry_run"
    assert res.video_path is None
    assert video.calls == []


# --------------------------------------------------------------------------- #
# Composer parity: model / count / sub-mode / agent mode
# --------------------------------------------------------------------------- #


def test_image_node_forwards_model_and_count(tmp_path):
    """count N must reach the client as x N with the captured model key."""
    svc, image, _video = _service(tmp_path)
    res = svc.generate_image(
        prompt="three cats", aspect_ratio="1:1", model="nano_banana_pro", count=3, dry_run=True
    )
    assert res.status == "dry_run"
    assert (res.model, res.model_label, res.count) == ("nano_banana_pro", "Nano Banana Pro", 3)
    call = image.calls[0]
    assert call["model_key"] == "GEM_PIX_2"
    assert call["model_label"] == "Nano Banana Pro"
    assert call["count"] == 3
    assert call["aspect"] == 1
    assert call["aspect_ratio"] == "1:1"


def test_image_node_rejects_unknown_model_and_count(tmp_path):
    svc, image, _video = _service(tmp_path)
    with pytest.raises(Exception):
        svc.generate_image(prompt="x", model="nano_banana_9")
    with pytest.raises(Exception):
        svc.generate_image(prompt="x", count=7)
    assert image.calls == []


def test_image_agent_mode_uses_defaults(tmp_path):
    """Agent ON hides model/aspect/count in Flow ⇒ we must fall back to defaults."""
    svc, image, _video = _service(tmp_path)
    res = svc.generate_image(
        prompt="x", aspect_ratio="3:4", model="nano_banana_pro", count=4, agent_mode=True, dry_run=True
    )
    assert res.agent_mode is True
    assert res.aspect_ratio == "16:9" and res.aspect_enum == 3
    assert res.model == "nano_banana_2_1"
    assert res.count == 1
    call = image.calls[0]
    assert call["model_key"] == "BELUGA"
    assert call["count"] == 1


def test_video_node_forwards_model_key_frames(tmp_path):
    svc, _image, video = _service(tmp_path)
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"frame")
    res = svc.generate_video(
        prompt="pan",
        frame_path=frame,
        aspect_ratio="16:9",
        model="veo_3_1_fast",
        sub_mode="frames",
        count=2,
        remove_watermark=False,
    )
    assert res.status == "ok"
    assert (res.model, res.sub_mode, res.count) == ("veo_3_1_fast", "frames", 2)
    call = video.calls[0]
    assert call["model_key"] == "veo_3_1_i2v_s_fast"
    assert call["count"] == 2
    assert call["offer_resolution"] is False and call["offer_duration"] is False
    assert call["capture_resolution"] == "720p"


def test_video_node_ingredients_is_text_to_video(tmp_path):
    """'Thành phần' submits YhhmEf: no frame, no auto image, t2v model key."""
    svc, image, video = _service(tmp_path)
    res = svc.generate_video(
        prompt="ocean at sunrise",
        sub_mode="ingredients",
        aspect_ratio="9:16",
        model="veo_3_1_quality",
        auto_image=True,  # must be ignored in this sub-mode
        remove_watermark=False,
    )
    assert res.status == "ok"
    assert res.sub_mode == "ingredients"
    assert res.frame_source is None
    assert res.reference_image_paths is None
    assert res.model_key == "veo_3_1_t2v_portrait"
    assert image.calls == [], "ingredients must not generate a starting frame"
    assert video.calls == [], "ingredients must not use the image→video RPC"
    assert video.text_calls[0]["model_key"] == "veo_3_1_t2v_portrait"
    assert video.text_calls[0]["prompt_text"] == "ocean at sunrise"


def test_video_node_ingredients_with_reference_images(tmp_path):
    """'Thành phần' with reference images forwards reference_paths to generate_text_video_flow."""
    svc, image, video = _service(tmp_path)
    ref1 = tmp_path / "ref1.png"
    ref1.write_bytes(b"ref1")
    ref2 = tmp_path / "ref2.jpg"
    ref2.write_bytes(b"ref2")
    res = svc.generate_video(
        prompt="character walking in forest",
        reference_image_paths=[str(ref1), str(ref2)],
        sub_mode="ingredients",
        aspect_ratio="9:16",
        model="omni_1_1_flash",
        remove_watermark=False,
    )
    assert res.status == "ok"
    assert res.sub_mode == "ingredients"
    assert res.frame_source == "provided"
    assert res.reference_image_paths == [str(ref1.resolve()), str(ref2.resolve())]
    assert image.calls == []
    assert len(video.text_calls) == 1
    call = video.text_calls[0]
    assert call["reference_paths"] == [ref1.resolve(), ref2.resolve()]
    assert call["prompt_text"] == "character walking in forest"


def test_video_node_omni_360p_and_duration(tmp_path):
    svc, _image, video = _service(tmp_path)
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"frame")
    res = svc.generate_video(
        prompt="pan",
        frame_path=frame,
        aspect_ratio="9:16",
        model="omni_1_1_flash",
        sub_mode="frames",
        resolution="360p",
        duration_s=4,
        remove_watermark=False,
    )
    assert res.model_key == "abra_i2v_4s_360p"
    assert res.reference_image_paths is None
    call = video.calls[0]
    assert call["resolution"] == "360p"
    assert call["capture_resolution"] == "360p"
    assert call["duration_s"] == 4
    assert call["offer_resolution"] is True and call["offer_duration"] is True


def test_video_node_1080p_upsamples_from_720p(tmp_path):
    svc, _image, video = _service(tmp_path)
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"frame")
    res = svc.generate_video(
        prompt="pan", frame_path=frame, model="omni_1_1_flash", duration_s=8, remove_watermark=False
    )
    assert res.resolution == "1080p"
    call = video.calls[0]
    assert call["resolution"] == "1080p"
    assert call["capture_resolution"] == "720p"
    assert call["model_key"] == "abra_i2v_8s"


def test_video_node_rejects_veo_with_360p(tmp_path):
    svc, _image, video = _service(tmp_path)
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"frame")
    with pytest.raises(UnsupportedOptionError):
        svc.generate_video(
            prompt="pan", frame_path=frame, model="veo_3_1_lite", resolution="360p"
        )
    assert video.calls == []


def test_video_agent_mode_uses_defaults(tmp_path):
    svc, _image, video = _service(tmp_path)
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"frame")
    res = svc.generate_video(
        prompt="pan",
        frame_path=frame,
        aspect_ratio="16:9",
        model="veo_3_1_fast",
        resolution="360p",
        duration_s=4,
        count=3,
        agent_mode=True,
        remove_watermark=False,
    )
    assert res.agent_mode is True
    assert res.model == "omni_1_1_flash"
    assert res.aspect_ratio == "9:16"
    assert res.resolution == "1080p"
    assert res.duration_s == 8
    assert res.count == 1
    call = video.calls[0]
    assert call["model_key"] == "abra_i2v_8s"
    assert call["count"] == 1
