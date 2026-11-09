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

from src.Bridge.flow_video_bridge import (
    SHAPE_FIRST_AND_LAST_FRAME,
    SHAPE_FIRST_FRAME,
    SHAPE_IMAGE_REFS,
    SHAPE_RPC,
    SHAPE_TEXT,
    SHAPE_VIDEO_REF,
    VIDEO_EDIT_MODEL_KEY,
    VIDEO_EDIT_RPC,
    build_text_video_args,
    build_video_args,
    build_video_edit_args,
    build_video_submit_args,
    omni12_duration,
    omni12_model_key,
    resolve_shape,
    submit_rpc_for,
)
from src.Bridge.flow_video.composer import VideoComposerMixin, parse_chip_duration
from src.Workflows.flow_catalog import (
    CatalogError,
    capture_resolution,
    image_model_key,
    normalize_count,
    resolve_image_model,
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


def test_build_video_args_360p_with_last_frame_is_not_padded():
    """`nprQif` carried the `_360p` suffix with a 7-slot spec and no `[4]` marker."""
    args = build_video_args(
        PROJECT_ID, "pan", "token", SF_MEDIA_ID,
        aspect_ratio="9:16", model_key="macaron_cookie_i2v_fl_5s", resolution="360p",
        last_frame_media_id="0f0e0d0c-1111-4222-8333-444455556666",
    )
    spec = args[0][0]
    assert len(spec) == 7
    assert spec[1] == "macaron_cookie_i2v_fl_5s_360p"
    assert spec[5][1] == "0f0e0d0c-1111-4222-8333-444455556666"


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


def test_build_text_video_args_with_references_uses_the_ingredients_layout():
    """`MZZa6b` moves the reference list to [1] and the key to [2]; 360p pads to 12."""
    ref = "11111111-1111-4111-8111-111111111111"
    args = build_text_video_args(
        PROJECT_ID, "wave", "token", model_key="macaron_cookie_r2v_5s",
        resolution="360p", reference_image_media_ids=[ref],
    )
    spec = args[0][0]
    assert len(spec) == 12
    assert spec[1] == [[None, ref]]
    assert spec[2] == "macaron_cookie_r2v_5s_360p"
    assert spec[11] == [4]


def test_build_text_video_args_count_gives_one_spec_per_render():
    args = build_text_video_args(
        PROJECT_ID, "wave", "token", model_key="veo_3_1_t2v_fast", aspect_ratio="16:9", count=3,
    )
    specs = args[0]
    assert len(specs) == 3
    assert all(s[1] == "veo_3_1_t2v_fast" for s in specs)
    assert all(s[2] == 2 for s in specs)
    assert len({s[4][4] for s in specs}) == 3


# --------------------------------------------------------------------------- #
# First + last frame (nprQif) and video reference (jIps6)
# --------------------------------------------------------------------------- #


LAST_MEDIA_ID = "0f0e0d0c-1111-4222-8333-444455556666"
CROP = [0.3123957754307949, None, 0.6876042245692051, 1]


def test_two_frames_switch_rpc_and_add_one_slot():
    """Filling "Kết thúc" is what changes the RPC — not the sub-mode.

    Captured 2026-11-09: same composer state, one extra frame slot between the frames
    and the UUID block, and `nprQif` instead of `eb1hJf`.
    """
    one = build_video_args(
        PROJECT_ID, "pan", "token", SF_MEDIA_ID,
        aspect_ratio="9:16", model_key=omni12_model_key(shape=SHAPE_FIRST_FRAME, duration_s=6),
    )
    two = build_video_args(
        PROJECT_ID, "pan", "token", SF_MEDIA_ID,
        aspect_ratio="9:16", model_key=omni12_model_key(shape=SHAPE_FIRST_AND_LAST_FRAME, duration_s=6),
        last_frame_media_id=LAST_MEDIA_ID, last_frame_crop=CROP,
    )
    assert submit_rpc_for(SHAPE_FIRST_FRAME) == "eb1hJf"
    assert submit_rpc_for(SHAPE_FIRST_AND_LAST_FRAME) == "nprQif"
    assert len(one[0][0]) == 6
    assert len(two[0][0]) == 7
    # Only the key, the extra frame slot and the shifted UUID block differ.
    assert two[0][0][1] == "macaron_cookie_i2v_fl_6s"
    assert two[0][0][4] == [None, SF_MEDIA_ID.lower()]
    assert two[0][0][5] == [None, LAST_MEDIA_ID.lower(), None, None, None, CROP]
    assert two[0][0][6][:4] == [None, None, None, None]


def test_two_frames_require_both_ids():
    """A last frame without a first frame is never a valid Flow request."""
    with pytest.raises(ValueError):
        build_video_submit_args(
            PROJECT_ID, "pan", "token", shape=SHAPE_FIRST_AND_LAST_FRAME,
            model_key="macaron_cookie_i2v_fl_6s", last_frame_media_id=LAST_MEDIA_ID,
        )
    with pytest.raises(ValueError):
        build_video_submit_args(
            PROJECT_ID, "pan", "token", shape=SHAPE_FIRST_AND_LAST_FRAME,
            model_key="macaron_cookie_i2v_fl_6s", starting_frame_media_id=SF_MEDIA_ID,
        )


def test_video_reference_uses_the_edit_layout_and_ignores_duration():
    """`jIps6` is a different family: `abra_edit`, clip in slot 0, no seed, no key duration."""
    args = build_video_edit_args(
        PROJECT_ID, "motion", "token",
        reference_video_media_id=SF_MEDIA_ID, reference_video_frame_count=192,
    )
    spec = args[0][0]
    assert len(spec) == 5
    assert spec[0] == [None, SF_MEDIA_ID.lower(), 0, 192]
    assert spec[1] == [None, None, [[["motion"]]]]
    assert spec[2] == VIDEO_EDIT_MODEL_KEY == "abra_edit"
    assert spec[4][:4] == [None, None, None, None]
    # The edit path has no duration slot at all, so a duration cannot leak into the key.
    assert omni12_model_key(shape=SHAPE_VIDEO_REF, duration_s=8) == "abra_edit"
    assert submit_rpc_for(SHAPE_VIDEO_REF) == VIDEO_EDIT_RPC == "jIps6"


# --------------------------------------------------------------------------- #
# Omni 1.2 model keys / duration window (models.py)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seconds", [3, 5, 8, 12, 15])
@pytest.mark.parametrize(
    "shape,kind,ceiling",
    [
        (SHAPE_FIRST_FRAME, "i2v", 15),
        (SHAPE_FIRST_AND_LAST_FRAME, "i2v_fl", 10),
        (SHAPE_TEXT, "t2v", 15),
        (SHAPE_IMAGE_REFS, "r2v", 15),
    ],
)
def test_omni12_key_embeds_the_duration(shape, kind, ceiling, seconds):
    """The duration is in the key for every integer second; the last-frame shape caps at 10s."""
    expected_s = min(seconds, ceiling)
    key = omni12_model_key(shape=shape, duration_s=seconds)
    assert key == f"macaron_cookie_{kind}_{expected_s}s"
    # 360p is the same key with a suffix, never a different duration.
    assert omni12_model_key(shape=shape, duration_s=seconds, resolution="360p") == f"{key}_360p"


def test_duration_window_shrinks_when_both_frames_are_attached():
    """Slider max is composer state: 12 (3..15s) alone, 7 (3..10s) with a last frame."""
    alone = omni12_duration()
    both = omni12_duration(has_last_frame=True)
    assert (alone.min_s, alone.max_s) == (3, 15)
    assert (both.min_s, both.max_s) == (3, 10)
    # The offset is read off the DOM (aria-valuetext - label), not invented here.
    assert alone.slider_value(3) == 0 and alone.seconds_from_slider(0) == 3
    assert alone.slider_value(15) == 12
    # Out-of-window requests clamp instead of producing an uncaptured key.
    assert both.clamp(15) == 10
    assert alone.clamp(2) == 3
    assert omni12_model_key(shape=SHAPE_FIRST_AND_LAST_FRAME, duration_s=15) == "macaron_cookie_i2v_fl_10s"


def test_shape_resolution_is_decided_by_slots_not_sub_mode_names():
    # Imported here, not at module scope: `runners_workflow` reloads the bridge (and its
    # submodules) per job, which rebinds exception classes. A module-level import would
    # compare against a stale class object.
    from src.Bridge.flow_video.models import VideoModelKeyError

    assert resolve_shape(sub_mode="frames", has_first_frame=True) == SHAPE_FIRST_FRAME
    assert (
        resolve_shape(sub_mode="frames", has_first_frame=True, has_last_frame=True)
        == SHAPE_FIRST_AND_LAST_FRAME
    )
    assert resolve_shape(sub_mode="ingredients", has_first_frame=False) == SHAPE_TEXT
    assert (
        resolve_shape(sub_mode="ingredients", has_first_frame=False, reference_count=2)
        == SHAPE_IMAGE_REFS
    )
    assert (
        resolve_shape(
            sub_mode="ingredients", has_first_frame=False,
            reference_count=1, has_video_reference=True,
        )
        == SHAPE_VIDEO_REF
    )
    with pytest.raises(VideoModelKeyError):
        resolve_shape(sub_mode="frames", has_first_frame=False)
    with pytest.raises(VideoModelKeyError):
        resolve_shape(sub_mode="frames", has_first_frame=False, has_last_frame=True)
    with pytest.raises(VideoModelKeyError):
        submit_rpc_for("not_a_shape")


# --------------------------------------------------------------------------- #
# Decoy parsers: read the composer's own choices back out of the blocked request
# --------------------------------------------------------------------------- #
#
# These run on the exact spec literals from the 2026-11-09 captures (inlined because
# `traces/` is gitignored). They matter because the decoy is the only ground truth at
# submit time: whatever it reports (frame ids, crops, references) is what we forward.


CAP_FIRST_ONLY = [[None, None, [[["p"]]]], "macaron_cookie_i2v_3s", 1, None, [None, SF_MEDIA_ID], [None, None, None, None, "U1", "U2"]]
CAP_FIRST_AND_LAST = [
    [None, None, [[["p"]]]], "macaron_cookie_i2v_fl_6s", 2, None,
    [None, SF_MEDIA_ID],
    [None, LAST_MEDIA_ID, None, None, None, CROP],
    [None, None, None, None, "U1", "U2"],
]
CAP_INGREDIENT = [
    [None, None, [[["p"]]]],
    [[None, SF_MEDIA_ID], [None, "11111111-1111-4111-8111-111111111111"]],
    "macaron_cookie_r2v_5s", 1, None, [None, None, None, None, "U1", "U2"],
]
CAP_VIDEO_REF = [
    [[None, SF_MEDIA_ID, 0, 192], [None, None, [[["p"]]]], "abra_edit", 1,
     [None, None, None, None, "U1", "U2"]],
]


def _as_args(spec):
    return [spec, [None, 22, None, None, None, PROJECT_ID, None, None, None, None, ["t", 1]], ["G", 2]]


def test_parsers_read_the_decoy_the_builder_wrote():
    """Round-trip: build a payload, parse it as if it were the decoy.

    This is the property the pipeline relies on — at submit time every id and crop comes
    from the blocked request, so a parser that misreads a slot submits the wrong frame.
    """
    from src.Bridge.flow_video.parsing import (
        extract_last_frame_from_args,
        extract_reference_media_ids,
        extract_reference_video_from_args,
        extract_starting_frame_from_eb1hjf_args,
    )

    # Only a first frame: no crop tail in, no crop out.
    args = build_video_args(PROJECT_ID, "p", "t", SF_MEDIA_ID, model_key="macaron_cookie_i2v_3s")
    assert extract_starting_frame_from_eb1hjf_args(args) == (SF_MEDIA_ID.lower(), None)
    # The UUID block sits where the last frame would be — it must not read as a frame.
    assert extract_last_frame_from_args(args) == (None, None)

    # Both frames: each slot reads its own id, and the crop survives.
    args = build_video_args(
        PROJECT_ID, "p", "t", SF_MEDIA_ID, model_key="macaron_cookie_i2v_fl_6s",
        last_frame_media_id=LAST_MEDIA_ID, last_frame_crop=CROP,
    )
    assert extract_starting_frame_from_eb1hjf_args(args) == (SF_MEDIA_ID.lower(), None)
    assert extract_last_frame_from_args(args) == (LAST_MEDIA_ID.lower(), CROP)

    # Ingredient chips: every reference id, none of the UUIDs.
    ref1 = SF_MEDIA_ID
    ref2 = "11111111-1111-4111-8111-111111111111"
    args = build_text_video_args(
        PROJECT_ID, "p", "t", model_key="macaron_cookie_r2v_5s",
        reference_image_media_ids=[ref1, ref2],
    )
    assert extract_reference_media_ids(args) == [ref1, ref2]

    # Video reference: clip id + frame count.
    args = build_video_edit_args(
        PROJECT_ID, "p", "t", reference_video_media_id=SF_MEDIA_ID, reference_video_frame_count=192,
    )
    assert extract_reference_video_from_args(args) == (SF_MEDIA_ID, 192)


def test_parsers_tolerate_a_shape_they_do_not_own():
    """A `YhhmEf` decoy has a model key where `MZZa6b` has references — read it as empty."""
    from src.Bridge.flow_video.parsing import (
        extract_last_frame_from_args,
        extract_reference_media_ids,
        extract_reference_video_from_args,
        extract_starting_frame_from_eb1hjf_args,
    )

    t2v = _as_args([None, None, [[["p"]]], "macaron_cookie_t2v_5s", 1, None,
                    [None, None, None, None, "U1", "U2"]])
    assert extract_reference_media_ids(t2v) == []
    assert extract_starting_frame_from_eb1hjf_args(t2v) == (None, None)
    assert extract_last_frame_from_args(t2v) == (None, None)
    assert extract_reference_video_from_args(t2v) == (None, None)

    # Garbage must not raise: these run inside retry loops.
    for junk in (None, [], [[[[1, 2, 3]]]], {"a": 1}):
        assert extract_reference_media_ids(junk) == []
        assert extract_reference_video_from_args(junk) == (None, None)
        assert extract_starting_frame_from_eb1hjf_args(junk) == (None, None)


# --------------------------------------------------------------------------- #
# Duration: slider (Omni 1.2) vs radio group (Omni 1.1 / Veo)
# --------------------------------------------------------------------------- #


class _FakePage:
    """Records ``evaluate`` calls and replays canned DOM answers.

    Enough to exercise ``_set_duration_slider`` without a browser: the method's only
    contact with the page is one state read and one write.
    """

    def __init__(self, state):
        self.state = state
        self.writes: list = []
        self.waits = 0

    def wait_for_timeout(self, _ms):
        self.waits += 1

    def query_selector(self, _sel):
        return None  # no backdrop: `_close_settings_popover` falls through to Escape

    class keyboard:
        @staticmethod
        def press(_key):
            pass

    def evaluate(self, script, arg=None):
        if "button.settings-trigger-button" in script:
            return True
        if "input[type=range].mdc-slider__input" in script:
            return None if self.state is None else {**self.state}
        if "getOwnPropertyDescriptor" in script:
            self.writes.append(arg)
            return True
        if "".join(script.split()).startswith("()=>[...document.querySelectorAll('.cdk-overlay-pane')]"):
            return False
        return None


class _Bridge:
    def __init__(self):
        self.logs: list[str] = []

    def _log(self, level, msg):
        self.logs.append(f"{level}:{msg}")


def _apply(state, seconds):
    """Run `_set_duration_slider` against `state`; returns (result, what was written)."""
    mixin = VideoComposerMixin()
    mixin._log = _Bridge()._log
    page = _FakePage(state)
    return mixin._set_duration_slider(page, seconds), page.writes


@pytest.mark.parametrize(
    "seconds,written",
    # max=12 → 3..15s, and value == seconds - 3 (the offset is read off `shown`).
    [(3, 0), (4, 1), (8, 5), (15, 12), (16, 12), (2, 0)],
)
def test_slider_writes_seconds_minus_three(seconds, written):
    result, writes = _apply(
        {"min": "0", "max": "12", "value": "5", "shown": "Độ dài 8 giây"}, seconds
    )
    assert result is True
    assert writes == [written]


def test_slider_respects_the_last_frame_ceiling():
    """With both frames attached Flow lowers max to 7, so 15s must clamp to 10s."""
    result, writes = _apply(
        {"min": "0", "max": "7", "value": "3", "shown": "Độ dài 6 giây"}, 15
    )
    assert result is True
    assert writes == [7], "clamped to the slider's own max, not the global 15s"


def test_slider_offset_is_read_from_the_dom_not_hardcoded():
    """If Flow renumbers the slider, the offset follows the DOM instead of assuming 3."""
    result, writes = _apply(
        {"min": "0", "max": "9", "value": "2", "shown": "Độ dài 8 giây"}, 10
    )
    assert result is True
    assert writes == [4], "offset is 8-2=6, so 10s is value 4"


def test_no_slider_falls_back_to_the_radio_group():
    """Omni 1.1 / Veo have no range input: the slider declines so the radio path runs."""
    result, writes = _apply(None, 8)
    assert result is False
    assert writes == []


def test_parse_chip_duration_reads_the_composer_chip():
    assert parse_chip_duration("Video · 720p · 8 giây crop_9_16 x1") == 8
    assert parse_chip_duration("Video · 720p · 15 giây") == 15
    assert parse_chip_duration("Video · 720p") is None
    assert parse_chip_duration("") is None


# --------------------------------------------------------------------------- #
# Decoy blocker coverage
# --------------------------------------------------------------------------- #


def test_hook_blocks_every_rpc_that_could_be_the_real_submit():
    """A submit RPC the hook forgets to block is a request that spends real credits.

    `fZytfe` / `IJhj9c` are undocumented but were blocked before Omni 1.2 and still are;
    dropping an id from either list is a credit regression, so pin the union here.
    """
    from src.Bridge.flow_video.constants import VIDEO_DECOY_RPCS, VIDEO_SUBMIT_RPCS
    from src.Bridge.flow_video.hook_js import VIDEO_HOOK_JS

    for shape in SHAPE_RPC.values():
        assert shape in VIDEO_SUBMIT_RPCS, f"{shape} submits credits but is not in VIDEO_SUBMIT_RPCS"
        assert shape in VIDEO_DECOY_RPCS
    # Every decoy must actually appear in the injected hook, not just in the constant.
    for rpcid in VIDEO_DECOY_RPCS:
        assert f"rpcids={rpcid}" in VIDEO_HOOK_JS, f"hook does not block {rpcid}"
    # Legacy ids that were blocked before the Omni 1.2 work must stay blocked.
    for rpcid in ("ogiZ0b", "p0UkFb", "fZytfe", "IJhj9c"):
        assert rpcid in VIDEO_DECOY_RPCS
