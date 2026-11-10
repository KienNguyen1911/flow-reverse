"""Flow Video Bridge — Protocol-Level ("Bridge Mode") Video Generation, Frame Extraction & Concatenation.

Architecture (see `docs/api_specs/flow_create_video.md`):
1. Starting Frame Upload (`maseQ`, 0 credit):
   - Triggered via synthetic `ClipboardEvent('paste')` on `div.ProseMirror` (or UI fallback).
   - Returns `MediaItem` with `starting_frame_media_id` (`data[0][0]`).
2. Decoy Intercept & Deterministic Submit (`eb1hJf`, Bridge Mode):
   - Arms `VIDEO_HOOK_JS` (`window.__blockVideoGen = true`) to block the app's own `eb1hJf`
     request (0 credit spent on decoy) and borrow its freshly minted single-use reCAPTCHA
     Enterprise token (`0cAFcWeA...` at `args[1][10][0]`).
   - Builds our deterministic `eb1hJf` payload (`build_video_args`: model
     `macaron_cookie_i2v_<n>s` on Omni 1.2 Flash, aspect enum `1` for 9:16 / `2` for 16:9,
     signed int32 `seed`, `starting_frame_media_id`, uppercase UUIDs `u1, u2, gen_id`,
     `_reqid = app_reqid + 100000`) and fires in-page with header `x-harness-ours: 1`.
   - Extracts `video_media_id` directly from `eb1hJf`'s `wrb.fr` JSON envelope.
3. Deterministic Status & Policy Error Polling (`jwpduf`, 0 credit):
   - Polls `jwpduf` (`args = [None, None, [[video_media_id]]]`) every ~4s.
   - Reads `rec[5][8]` and `rec[5][9]` directly from JSON:
     * `rec[5][9] == 1` (`rec[5][8] == [3]`): Video succeeded.
     * `rec[5][9] == 4` (`rec[5][8][0] == 4`): Video failed/rejected with exact server error code
       (e.g. `PUBLIC_ERROR_PROMINENT_PEOPLE_FILTER_FAILED` / `PROMINENT_PERSON`).
4. Signed 6-Hour Video CDN URL Minting & Download (`as29s`, 0 credit):
   - Calls `as29s` (`args = [video_media_id]`) to mint a cookie-free 6h signed URL
     `https://flow-content.google/video/<video_media_id>?Expires=...&KeyName=labs-flow-prod-cdn-key&Signature=...`
     and downloads the full-bitrate `ftypisom` MP4 with magic-byte validation (`ftyp`).

Layout — this module is the public facade; the implementation lives in ``Bridge/flow_video/``:

  constants       RPC ids, model keys, aspect enums, 360p marker table, regexes, ``LogFn``
  models          which key/RPC a submit shape uses, Omni 1.2's duration window
  hook_js         ``VIDEO_HOOK_JS`` (in-page submit block + maseQ spy)
  payload         pure payload builders (every captured submit layout, p0UkFb, jwpduf, as29s)
  parsing         pure parsers for captured decoys and RPC responses
  media_tools     FFmpeg/OpenCV helpers (last frame, strip audio, concat)
  prompt          ``sanitize_video_prompt``
  composer        video composer DOM driving, duration slider, reCAPTCHA readiness, tile cleanup
  last_frame      the "Bắt đầu" / "Kết thúc" frame slots
  starting_frame  starting-frame upload/attach (paste -> maseQ, UI fallback)
  rpc             hook/capture, jwpduf polling, as29s, 1080p upsample, MP4 download
  generation      ``generate_video_flow`` / ``generate_text_video_flow`` orchestration

Every name that used to live here is re-exported so ``from src.Bridge.flow_video_bridge import X``
keeps working.
"""

from __future__ import annotations

import importlib
import sys
from typing import Optional

# ``importlib.reload(flow_video_bridge)`` in a long-lived process re-executes only this file;
# reload the implementation modules too so edits under ``Bridge/flow_video/`` apply.
# On first import ``FlowVideoBridge`` is not yet in globals.
if "FlowVideoBridge" in globals():
    for _name in (
        "constants",
        "models",
        "hook_js",
        "payload",
        "parsing",
        "media_tools",
        "prompt",
        "composer",
        "last_frame",
        "video_ref",
        "starting_frame",
        "rpc",
        "generation",
    ):
        importlib.reload(sys.modules[f"{__package__}.flow_video.{_name}"])

from .flow.common import DEFAULT_CDP_URL  # noqa: E402
from .flow_video.composer import VideoComposerMixin  # noqa: E402
from .flow_video.constants import (  # noqa: E402,F401
    DEFAULT_CROP_169,
    DEFAULT_CROP_916,
    OMNI12_MAX_DURATION_S,
    OMNI12_MAX_DURATION_S_WITH_LAST_FRAME,
    OMNI12_MIN_DURATION_S,
    PROJECT_ITEMS_RPC,
    SPEC_360P_MARKER_INDEX,
    VIDEO_ASPECT_LANDSCAPE,
    VIDEO_ASPECT_PORTRAIT,
    VIDEO_EDIT_MODEL_KEY,
    VIDEO_EDIT_RPC,
    VIDEO_LAST_FRAME_SUBMIT_RPC,
    VIDEO_MEDIA_URL_RPC,
    VIDEO_POLL_RPC,
    VIDEO_SUBMIT_RPC,
    VIDEO_SUBMIT_RPCS,
    VIDEO_TEXT_SUBMIT_RPC,
    VIDEO_TOOL_ID,
    VIDEO_UPLOAD_RPC,
    VIDEO_UPSAMPLE_1080P_MODEL_KEY,
    VIDEO_UPSAMPLE_RPC,
    VIDEO_INGREDIENTS_SUBMIT_RPC,
    LogFn,
)
from .flow_video.generation import VideoGenerationMixin  # noqa: E402
from .flow_video.hook_js import VIDEO_HOOK_JS  # noqa: E402,F401
from .flow_video.last_frame import (  # noqa: E402,F401
    SLOT_LABEL_FIRST,
    SLOT_LABEL_LAST,
    LastFrameMixin,
)
from .flow_video.video_ref import VideoReferenceMixin  # noqa: E402,F401
from .flow_video.media_tools import (  # noqa: E402,F401
    concatenate_two_videos,
    condition_frame_for_policy_retry,
    extract_last_video_frame,
    strip_video_audio,
)
from .flow_video.models import (  # noqa: E402,F401
    SHAPE_FIRST_AND_LAST_FRAME,
    SHAPE_FIRST_FRAME,
    SHAPE_IMAGE_REFS,
    SHAPE_RPC,
    SHAPE_TEXT,
    SHAPE_VIDEO_REF,
    Omni12Duration,
    VideoModelKeyError,
    omni12_duration,
    omni12_model_key,
    resolve_shape,
    submit_rpc_for,
)
from .flow_video.parsing import (  # noqa: E402,F401
    extract_frame_slot,
    extract_last_frame_from_args,
    extract_media_records,
    extract_reference_media_ids,
    extract_reference_video_from_args,
    extract_signed_video_url,
    extract_starting_frame_from_eb1hjf_args,
    extract_video_submit_media_id,
    parse_jwpduf_status,
    parse_video_app_capture,
)
from .flow_video.payload import (  # noqa: E402,F401
    build_as29s_args,
    build_jwpduf_args,
    build_text_video_args,
    build_video_args,
    build_video_edit_args,
    build_video_submit_args,
    build_video_upsample_1080p_args,
    encode_video_batchexecute_form,
)
from .flow_video.prompt import sanitize_video_prompt  # noqa: E402,F401
from .flow_video.rpc import VideoRpcMixin  # noqa: E402
from .flow_video.starting_frame import StartingFrameMixin  # noqa: E402


class FlowVideoBridge(
    VideoGenerationMixin,
    VideoRpcMixin,
    StartingFrameMixin,
    LastFrameMixin,
    VideoReferenceMixin,
    VideoComposerMixin,
):
    """Protocol-level ("Bridge Mode") Video generation on Google Flow.

    Submits through whichever RPC the captured composer state implies (`eb1hJf` for a
    single frame, `nprQif` for first+last, `YhhmEf`/`MZZa6b` for Thành phần with/without
    image references, `jIps6` for a video reference), then polls `jwpduf` and mints a
    signed CDN URL through `as29s`.
    """

    def __init__(
        self,
        cdp_url: str = DEFAULT_CDP_URL,
        log: Optional[LogFn] = None,
    ):
        self.cdp_url = cdp_url
        self._log = log or (lambda kind, msg: None)
