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
        seed=None,
        dry_run=False,
        remove_watermark=True,
        poll_timeout_s=150.0,
        anti_abuse_retries=1,
        reference=None,
        on_event=None,
    ):
        self.calls.append(
            {
                "project_id": project_id,
                "prompt": prompt,
                "aspect": aspect,
                "seed": seed,
                "dry_run": dry_run,
                "reference": reference,
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

    def generate_video_flow(self, **kwargs):
        self.calls.append(kwargs)
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
    # Without the capture config the ratio must fail loudly, never guess.
    with pytest.raises(AspectNotVerifiedError) as exc:
        resolve_image_aspect("9:16", config_path=tmp_path / "missing.json")
    assert "capture_image_aspects" in str(exc.value)


def test_video_option_validation():
    assert normalize_video_ratio("portrait") == "9:16"
    assert normalize_video_ratio("16:9") == "16:9"
    with pytest.raises(UnsupportedOptionError):
        normalize_video_ratio("1:1")
    assert normalize_video_resolution("1080") == "1080p"
    assert normalize_video_resolution("720") == "720p"
    with pytest.raises(UnsupportedOptionError):
        normalize_video_resolution("4k")
    assert validate_video_duration(8) == 8
    with pytest.raises(UnsupportedOptionError):
        validate_video_duration(16)


def test_node_options_exposes_capabilities(tmp_path):
    opts = node_options(config_path=tmp_path / "none.json")
    assert opts["image"]["aspect_ratios"] == {"16:9": 3}
    assert opts["image"]["supports_reference_image"] is True
    assert opts["video"]["aspect_ratios"] == ["9:16", "16:9"]
    assert opts["video"]["durations_s"] == [8]
    assert opts["video"]["supports_text_to_video"] is False
    assert opts["video"]["auto_image_chain"] is True


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
