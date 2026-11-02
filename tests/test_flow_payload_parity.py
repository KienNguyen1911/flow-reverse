"""Payload-shape tests for the composer parity work (image + video builders).

Every layout asserted here was captured 0-credit from the real Flow composer by
blocking ``/data/batchexecute`` right before clicking Generate. See
``.turbo/node-config-parity/matrix.md`` and ``traces/submit_bodies/*_summary.json``.

The point of these tests is to pin the *shape*, because a wrong shape spends
credits or gets rejected with an opaque status code:

* image  (``ogiZ0b``): one spec per image in ``args[1]``, ``args[2]`` stays 1
* i2v    (``eb1hJf``): 720p spec len 6, 360p spec len 10 with ``spec[9] == [4]``
* t2v    (``YhhmEf``): 720p spec len 5, 360p spec len 8 with ``spec[7] == [4]``
"""

from __future__ import annotations

import pytest

from src.Bridge.flow_video_bridge import build_text_video_args, build_video_args
from src.Workflows.flow_catalog import (
    CatalogError,
    capture_resolution,
    image_model_key,
    normalize_count,
    resolve_image_model,
    resolve_video_model,
    video_model_key,
)
from src.Workflows.flow_models import build_image_args

PROJECT_ID = "11111111-1111-4111-8111-111111111111"
SF_MEDIA_ID = "0f0e0d0c-1111-4222-8333-444455556666"


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "model_id,key",
    [
        ("nano_banana_pro", "GEM_PIX_2"),
        ("nano_banana_2_lite", "HARBOR_SEAL"),
        ("nano_banana_2_1", "BELUGA"),
    ],
)
def test_image_model_keys_are_captured(model_id, key):
    assert image_model_key(model_id) == key
    # The composer label must resolve to the same model.
    assert image_model_key(resolve_image_model(model_id).label) == key


def test_image_model_rejects_unknown_value():
    with pytest.raises(CatalogError) as exc:
        resolve_image_model("nano_banana_9")
    assert "nano_banana_9" in str(exc.value)


def test_count_is_clamped_to_composer_values():
    for v, expected in ((1, 1), (2, 2), (3, 3), (4, 4), ("4", 4)):
        assert normalize_count(v) == expected
    with pytest.raises(CatalogError):
        normalize_count(5)


@pytest.mark.parametrize(
    "model,sub,aspect,expected",
    [
        ("omni_1_1_flash", "frames", "9:16", "abra_i2v_8s"),
        ("omni_1_1_flash", "frames", "16:9", "abra_i2v_8s"),
        ("omni_1_1_flash", "ingredients", "9:16", "abra_t2v_8s"),
        ("veo_3_1_lite", "frames", "9:16", "veo_3_1_i2v_lite"),
        ("veo_3_1_lite", "ingredients", "16:9", "veo_3_1_t2v_lite"),
        ("veo_3_1_fast", "frames", "9:16", "veo_3_1_i2v_s_fast_portrait"),
        ("veo_3_1_fast", "frames", "16:9", "veo_3_1_i2v_s_fast"),
        ("veo_3_1_fast", "ingredients", "9:16", "veo_3_1_t2v_fast_portrait"),
        ("veo_3_1_fast", "ingredients", "16:9", "veo_3_1_t2v_fast"),
        ("veo_3_1_quality", "frames", "9:16", "veo_3_1_i2v_s_portrait"),
        ("veo_3_1_quality", "frames", "16:9", "veo_3_1_i2v_s"),
        ("veo_3_1_quality", "ingredients", "9:16", "veo_3_1_t2v_portrait"),
        ("veo_3_1_quality", "ingredients", "16:9", "veo_3_1_t2v"),
    ],
)
def test_video_model_key_matrix(model, sub, aspect, expected):
    assert (
        video_model_key(model, sub_mode=sub, aspect_ratio=aspect, duration_s=8)
        == expected
    )


@pytest.mark.parametrize("duration", [4, 6, 8, 10])
def test_omni_model_key_tracks_duration(duration):
    assert (
        video_model_key("omni_1_1_flash", sub_mode="frames", duration_s=duration)
        == f"abra_i2v_{duration}s"
    )
    assert (
        video_model_key("omni_1_1_flash", sub_mode="ingredients", duration_s=duration)
        == f"abra_t2v_{duration}s"
    )


def test_omni_360p_suffix_and_veo_rejection():
    assert (
        video_model_key("omni_1_1_flash", sub_mode="frames", duration_s=4, resolution="360p")
        == "abra_i2v_4s_360p"
    )
    assert (
        video_model_key("omni_1_1_flash", sub_mode="ingredients", duration_s=8, resolution="360p")
        == "abra_t2v_8s_360p"
    )
    for model in ("veo_3_1_lite", "veo_3_1_fast", "veo_3_1_quality"):
        with pytest.raises(CatalogError):
            video_model_key(model, duration_s=8, resolution="360p")


def test_veo_duration_and_bad_aspect_rejected():
    with pytest.raises(CatalogError):
        video_model_key("veo_3_1_fast", duration_s=4)
    with pytest.raises(CatalogError):
        video_model_key("omni_1_1_flash", aspect_ratio="1:1")


def test_1080p_is_an_upsample_of_720p():
    """1080p is our own p0UkFb step, not a Flow option: the submit still asks 720p."""
    for model in ("omni_1_1_flash", "veo_3_1_fast"):
        assert capture_resolution(model, "1080p") == "720p"
    assert capture_resolution("omni_1_1_flash", "360p") == "360p"
    assert capture_resolution("omni_1_1_flash", "720p") == "720p"


# --------------------------------------------------------------------------- #
# Image payload (ogiZ0b)
# --------------------------------------------------------------------------- #


def test_build_image_args_default_is_unchanged():
    args = build_image_args(PROJECT_ID, "a cat", "token", 123, 3)
    assert len(args) == 5
    assert args[0] is None
    assert args[2] == 1
    spec = args[1][0]
    assert len(spec) == 14
    assert spec[3] == 123
    assert spec[4] == 3
    assert spec[5] == "BELUGA"
    # ref is shared between the spec and args[3] (the app does the same).
    assert spec[7] is args[3]


def test_build_image_args_count_produces_one_spec_per_image():
    args = build_image_args(
        PROJECT_ID, "a cat", "token", 123, 2, model_key="GEM_PIX_2", count=4
    )
    batch = args[1]
    assert len(batch) == 4
    assert args[2] == 1, "args[2] stays 1 regardless of the batch size"
    for spec in batch:
        assert len(spec) == 14
        assert spec[4] == 2
        assert spec[5] == "GEM_PIX_2"
    # First spec keeps the caller's seed; the rest get their own, plus own UUIDs.
    assert batch[0][3] == 123
    assert len({s[3] for s in batch}) == 4
    assert len({s[12] for s in batch}) == 4
    assert len({s[13] for s in batch}) == 4
    # All specs must point at the same ref object (the app shares it).
    assert all(s[7] is args[3] for s in batch)


# --------------------------------------------------------------------------- #
# Image→video payload (eb1hJf)
# --------------------------------------------------------------------------- #


def test_build_video_args_720p_shape():
    args = build_video_args(
        PROJECT_ID, "pan", "token", SF_MEDIA_ID,
        aspect_ratio="9:16", seed=42, model_key="abra_i2v_4s",
    )
    assert len(args) == 3
    specs = args[0]
    assert len(specs) == 1
    spec = specs[0]
    assert len(spec) == 6
    assert spec[1] == "abra_i2v_4s"
    assert spec[2] == 1  # 9:16
    assert spec[3] == 42
    assert spec[4][1] == SF_MEDIA_ID.lower()
    assert args[2][1] == 2


def test_build_video_args_360p_grows_the_spec():
    args = build_video_args(
        PROJECT_ID, "pan", "token", SF_MEDIA_ID,
        aspect_ratio="9:16", model_key="abra_i2v_4s", resolution="360p",
    )
    spec = args[0][0]
    assert len(spec) == 10
    assert spec[1] == "abra_i2v_4s_360p"
    assert spec[9] == [4]


def test_build_video_args_count_gives_one_spec_per_render():
    args = build_video_args(
        PROJECT_ID, "pan", "token", SF_MEDIA_ID,
        aspect_ratio="16:9", seed=7, model_key="abra_i2v_8s", count=2,
    )
    specs = args[0]
    assert len(specs) == 2
    assert [s[2] for s in specs] == [2, 2]
    assert [s[3] for s in specs][0] == 7
    assert len({s[5][4] for s in specs}) == 2, "each render needs its own u1"
    assert len({s[5][5] for s in specs}) == 2, "each render needs its own u2"
    assert len({s[5][4] for s in specs} | {s[5][5] for s in specs}) == 4
    # Count does not change the trailing gen id marker.
    assert args[2][1] == 2


# --------------------------------------------------------------------------- #
# Text→video payload (YhhmEf)
# --------------------------------------------------------------------------- #


def test_build_text_video_args_has_no_starting_frame():
    args = build_text_video_args(
        PROJECT_ID, "wave", "token",
        aspect_ratio="9:16", seed=7, model_key="abra_t2v_8s",
    )
    assert len(args) == 3
    spec = args[0][0]
    assert len(spec) == 5
    assert spec[1] == "abra_t2v_8s"
    assert spec[2] == 1
    assert spec[3] == 7
    # spec[4] is the UUID slot — no media id anywhere.
    assert spec[4][:4] == [None, None, None, None]
    assert isinstance(spec[4][4], str) and len(spec[4][4]) == 36
    assert args[2][1] == 2


def test_build_text_video_args_360p_grows_the_spec():
    args = build_text_video_args(
        PROJECT_ID, "wave", "token", model_key="abra_t2v_4s", resolution="360p",
    )
    spec = args[0][0]
    assert len(spec) == 8
    assert spec[1] == "abra_t2v_4s_360p"
    assert spec[7] == [4]


def test_build_text_video_args_count_gives_one_spec_per_render():
    args = build_text_video_args(
        PROJECT_ID, "wave", "token", model_key="veo_3_1_t2v_fast", aspect_ratio="16:9", count=3,
    )
    specs = args[0]
    assert len(specs) == 3
    assert all(s[1] == "veo_3_1_t2v_fast" for s in specs)
    assert all(s[2] == 2 for s in specs)
    assert len({s[4][4] for s in specs}) == 3
