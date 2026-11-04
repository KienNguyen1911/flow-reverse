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
VIDEO_UPSAMPLE_RPC = "p0UkFb"
VIDEO_POLL_RPC = "jwpduf"
VIDEO_MEDIA_URL_RPC = "as29s"
VIDEO_UPLOAD_RPC = "maseQ"
PROJECT_ITEMS_RPC = "Zzl0ze"

VIDEO_MODEL_KEY = "abra_i2v_8s"
VIDEO_UPSAMPLE_1080P_MODEL_KEY = "veo_3_1_upsampler_1080p"
VIDEO_TOOL_ID = 22

VIDEO_ASPECT_PORTRAIT = 1   # 9:16
VIDEO_ASPECT_LANDSCAPE = 2  # 16:9

DEFAULT_CROP_916 = [0.003875968992248069, None, 0.9961240310077519, 1]
DEFAULT_CROP_169 = [0.0, None, 1.0, 1]

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_MEDIA_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?:_upsampled|_4k)?$")
_TOKEN_RE = re.compile(r"^0[0-9A-Za-z][A-Za-z0-9_\-]{400,}$")
