"""Protocol constants for the video bridge (`docs/api_specs/flow_create_video.md`)."""

from __future__ import annotations

import re
from typing import Callable

LogFn = Callable[[str, str], None]

# --------------------------------------------------------------------------- #
# Protocol Constants (`docs/api_specs/flow_create_video.md`)
# --------------------------------------------------------------------------- #

VIDEO_SUBMIT_RPC = "eb1hJf"
#: Text→video submit RPC, used by the composer's "Thành phần" (ingredients) sub-mode.
#: Captured 0-credit 2026-11-03: traces/submit_bodies/t2v_omni_8s_720p_summary.json.
VIDEO_TEXT_SUBMIT_RPC = "YhhmEf"
VIDEO_INGREDIENTS_SUBMIT_RPC = "MZZa6b"
#: First-frame + last-frame submit RPC (both "Khung hình" slots filled).
#: Captured 0-credit 2026-11-09 on Omni 1.2 Flash: the app switches RPC when the
#: last-frame slot is occupied — `eb1hJf` is single-frame only.
VIDEO_LAST_FRAME_SUBMIT_RPC = "nprQif"
#: Video-as-reference submit RPC ("Thành phần" with a *video* ingredient).
#: Captured 0-credit 2026-11-09: args[0][0] carries `[null, <video_media_id>, 0, 192]`
#: and the model key is `abra_edit` — not the Omni family.
VIDEO_EDIT_RPC = "jIps6"
VIDEO_UPSAMPLE_RPC = "p0UkFb"
VIDEO_POLL_RPC = "jwpduf"
VIDEO_MEDIA_URL_RPC = "as29s"
VIDEO_UPLOAD_RPC = "maseQ"
PROJECT_ITEMS_RPC = "Zzl0ze"

#: Every RPC that can be the decoy (and therefore must be blocked by VIDEO_HOOK_JS).
VIDEO_SUBMIT_RPCS: tuple[str, ...] = (
    VIDEO_SUBMIT_RPC,
    VIDEO_TEXT_SUBMIT_RPC,
    VIDEO_INGREDIENTS_SUBMIT_RPC,
    VIDEO_LAST_FRAME_SUBMIT_RPC,
    VIDEO_EDIT_RPC,
)

#: Non-submit RPCs that also mint a reCAPTCHA token; blocking them keeps the decoy 0-credit
#: when the page happens to be in image mode or the app offers an upscale button.
#:
#: ``fZytfe`` and ``IJhj9c`` are not documented anywhere yet, but the app does fire them
#: from a video composer and blocking them costs nothing while a missed block costs credits.
#: Keep them listed until a capture shows they can no longer be a submit.
VIDEO_DECOY_RPCS: tuple[str, ...] = (
    *VIDEO_SUBMIT_RPCS,
    VIDEO_UPSAMPLE_RPC,
    "ogiZ0b",
    "fZytfe",
    "IJhj9c",
)

#: Upsample step for 1080p. Not a composer model: it is our own post-step on the 720p file.
VIDEO_UPSAMPLE_1080P_MODEL_KEY = "veo_3_1_upsampler_1080p"
VIDEO_TOOL_ID = 22

# --------------------------------------------------------------------------- #
# Omni 1.2 Flash model keys
# --------------------------------------------------------------------------- #
#
# Observed 0-credit 2026-11-09 (traces/submit_bodies/omni12_*_summary.json). Omni 1.2
# replaced Omni 1.1's `abra_*` family and - because the composer exposes a continuous
# 3..15s slider instead of 4/6/8/10s radios - encodes the duration in the key for
# every value in that range:
#
#   macaron_cookie_i2v_<dur>s        image→video, first frame only      (eb1hJf)
#   macaron_cookie_i2v_fl_<dur>s     image→video, first + last frame    (nprQif)
#   macaron_cookie_t2v_<dur>s        text→video, no image references    (YhhmEf)
#   macaron_cookie_r2v_<dur>s        text→video, ≥1 image reference     (MZZa6b)
#
# 360p appends `_360p` after the duration (`macaron_cookie_i2v_4s_360p`).
OMNI12_KEY_PREFIX = "macaron_cookie"
#: ``kind`` values used between the prefix and the duration.
OMNI12_KIND_I2V = "i2v"
OMNI12_KIND_I2V_FL = "i2v_fl"
OMNI12_KIND_T2V = "t2v"
OMNI12_KIND_R2V = "r2v"
#: Model key used by the video-as-reference path; not part of the Omni family.
VIDEO_EDIT_MODEL_KEY = "abra_edit"

#: Omni 1.2's composer slider spans 3..15s (slider value = seconds - 3, i.e. 0..12).
OMNI12_MIN_DURATION_S = 3
OMNI12_MAX_DURATION_S = 15
#: With BOTH frame slots filled the slider's max drops to 10s (value 0..7).
OMNI12_MAX_DURATION_S_WITH_LAST_FRAME = 10
#: Offset between the slider's own value and the seconds it displays.
OMNI12_SLIDER_OFFSET_S = 3

VIDEO_ASPECT_PORTRAIT = 1   # 9:16
VIDEO_ASPECT_LANDSCAPE = 2  # 16:9

#: Example crops seen in captures, kept only to document the slot's *format*
#: (``[x0, y0, x1, y1]`` normalised; ``y0`` stays ``null``). They are NOT defaults: the
#: composer omits the crop tail entirely for a plain pasted frame, so the payload builder
#: must forward ``None`` rather than substituting one of these.
DEFAULT_CROP_916 = [0.003875968992248069, None, 0.9961240310077519, 1]
DEFAULT_CROP_169 = [0.0, None, 1.0, 1]

# --------------------------------------------------------------------------- #
# 360p marker slot, per submit shape
# --------------------------------------------------------------------------- #
#
# 360p is signalled twice: `_360p` on the model key AND a `[4]` marker at a fixed
# absolute index, which pads the spec to a fixed length. The index is a property of the
# shape's spec layout (and therefore of the RPC), so it is tabulated rather than computed:
#
#   first_frame          6 → 10, marker at [9]   (traces/submit_bodies/omni12_360p_eb1hJf_args.json)
#   text                 5 →  8, marker at [7]   (traces/submit_bodies/t2v_omni_4s_360p_summary.json)
#   image_refs           6 → 12, marker at [11]  (traces/submit_bodies/omni12_ing1ref_MZZa6b_args.json)
#   first_and_last_frame 7 →  7, NO marker       (traces/submit_bodies/omni12_fl360p_nprQif_args.json)
#
# `first_and_last_frame` is the odd one: the app sent `macaron_cookie_i2v_fl_5s_360p` with a
# 7-slot spec, i.e. the key suffix alone. Encoding that as "no marker" keeps us
# byte-faithful. Keyed by shape, not by RPC, so a caller cannot forget to pass it.
SPEC_360P_MARKER_INDEX: dict[str, "int | None"] = {
    "first_frame": 9,
    "text": 7,
    "image_refs": 11,
    "first_and_last_frame": None,
    "video_ref": None,
}

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_MEDIA_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?:_upsampled|_4k)?$")
_TOKEN_RE = re.compile(r"^0[0-9A-Za-z][A-Za-z0-9_\-]{400,}$")

