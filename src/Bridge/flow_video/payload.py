"""Pure builders for video batchexecute payloads (`eb1hJf`, `YhhmEf`, `p0UkFb`, `jwpduf`, `as29s`)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..flow_bridge import SEED_MAX, enc, new_seed
from .constants import (
    DEFAULT_CROP_169,
    DEFAULT_CROP_916,
    VIDEO_ASPECT_LANDSCAPE,
    VIDEO_ASPECT_PORTRAIT,
    VIDEO_MODEL_KEY,
    VIDEO_TOOL_ID,
    VIDEO_UPSAMPLE_1080P_MODEL_KEY,
)


def encode_video_batchexecute_form(rpcid: str, args: list, at_param: str) -> str:
    """Form body for batchexecute: f.req=<enc>&at=<enc>& (byte-identical)."""
    args_json = json.dumps(args, separators=(",", ":"), ensure_ascii=False)
    f_req = json.dumps([[[rpcid, args_json, None, "generic"]]], separators=(",", ":"), ensure_ascii=False)
    return "f.req=" + enc(f_req) + "&at=" + enc(at_param) + "&"


def _validated_seed(seed: Optional[int]) -> Optional[int]:
    """``None`` stays ``None``; otherwise coerce to int and require signed int32 (1..SEED_MAX)."""
    if seed is not None:
        seed = int(seed)
        if not (1 <= seed <= SEED_MAX):
            raise ValueError(f"seed must fit signed int32: 1..{SEED_MAX} (got {seed})")
    return seed


def _aspect_enum(aspect_ratio: str) -> int:
    return VIDEO_ASPECT_PORTRAIT if "9:16" in str(aspect_ratio) else VIDEO_ASPECT_LANDSCAPE


def _submit_ref(project_id_norm: str, recaptcha_token: str) -> list:
    """Shared ``ref`` block of every video submit/upsample payload (tool id, project, reCAPTCHA token)."""
    return [
        None,
        VIDEO_TOOL_ID,
        None,
        None,
        None,
        project_id_norm,
        None,
        None,
        None,
        None,
        [recaptcha_token, 1],
    ]


def build_video_args(
    project_id: str,
    prompt: str,
    recaptcha_token: str,
    starting_frame_media_id: Optional[str],
    *,
    aspect_ratio: str = "9:16",
    seed: Optional[int] = None,
    model_key: str = VIDEO_MODEL_KEY,
    crop_box: Optional[list] = None,
    u1: Optional[str] = None,
    u2: Optional[str] = None,
    gen_id: Optional[str] = None,
    count: int = 1,
    resolution: str = "720p",
) -> list:
    """Assemble the deterministic eb1hJf args payload (see `docs/api_specs/flow_create_video.md` §2.2).

    Layout (image→video, ``starting_frame_media_id`` set)::

        video_spec = [
            [None, None, [[[prompt]]]],
            "abra_i2v_8s",
            aspect_enum,  # 1 = 9:16 (Portrait), 2 = 16:9 (Landscape)
            seed_or_null, # int32 (1..2147483647) or None
            [None, starting_frame_media_id, None, None, None, crop_box],
            [None, None, None, None, u1, u2],
        ]
        ref = [None, 22, None, None, None, project_id, None, None, None, None, [recaptcha_token, 1]]
        args = [[video_spec], ref, [gen_id, 2]]

    360p (captured): the model key gains a ``_360p`` suffix and the spec grows to 10
    entries with ``spec[9] = [4]``. ``count`` > 1 duplicates the spec, one ``u1``/``u2``
    pair per render (captured: ``x2`` → ``args[0]`` has two specs).
    """
    seed = _validated_seed(seed)

    aspect_enum = _aspect_enum(aspect_ratio)
    if crop_box is None:
        crop_box = list(DEFAULT_CROP_916 if aspect_enum == VIDEO_ASPECT_PORTRAIT else DEFAULT_CROP_169)

    u1 = (u1 or str(uuid.uuid4())).upper()
    u2 = (u2 or str(uuid.uuid4())).upper()
    gen_id = (gen_id or str(uuid.uuid4())).upper()
    pid = project_id.strip().lower()
    sf_id = starting_frame_media_id.strip().lower() if starting_frame_media_id else None

    # 360p is signalled twice: `_360p` on the model key and `spec[9] = [4]`, which makes
    # the spec 10 long instead of 6 (captured: traces/submit_bodies/vid_360p_summary.json).
    is_360 = str(resolution or "").strip().lower().startswith("360")
    model_key = model_key or VIDEO_MODEL_KEY
    if is_360 and not model_key.endswith("_360p"):
        model_key = f"{model_key}_360p"

    def _spec(idx: int) -> list:
        s_u1 = u1 if idx == 0 else str(uuid.uuid4()).upper()
        s_u2 = u2 if idx == 0 else str(uuid.uuid4()).upper()
        s_seed = (int(seed) if seed is not None else None) if idx == 0 else (
            new_seed() if seed is not None else None
        )
        spec: list[Any] = [
            [None, None, [[[prompt]]]],
            model_key,
            int(aspect_enum),
            s_seed,
            [None, sf_id, None, None, None, crop_box],
            [None, None, None, None, s_u1, s_u2],
        ]
        if is_360:
            spec.extend([None, None, None, [4]])
        return spec

    specs = [_spec(i) for i in range(max(1, int(count)))]

    ref = _submit_ref(pid, recaptcha_token)
    return [specs, ref, [gen_id, 2]]


def build_text_video_args(
    project_id: str,
    prompt: str,
    recaptcha_token: str,
    *,
    aspect_ratio: str = "9:16",
    seed: Optional[int] = None,
    model_key: str = "abra_t2v_8s",
    u1: Optional[str] = None,
    u2: Optional[str] = None,
    gen_id: Optional[str] = None,
    count: int = 1,
    resolution: str = "720p",
) -> list:
    """Assemble the ``YhhmEf`` args payload for the "Thành phần" (text→video) sub-mode.

    Captured 0-credit (``traces/submit_bodies/t2v_omni_8s_720p_summary.json``)::

        spec = [
            [None, None, [[[prompt]]]],
            "abra_t2v_8s",          # model key, prefix abra_t2v_*/veo_3_1_t2v*
            aspect_enum,            # 1 = 9:16, 2 = 16:9
            seed_or_null,
            [None, None, None, None, u1, u2],   # NO starting frame
        ]
        ref   = [None, 22, None, None, None, project_id, None, None, None, None, [token, 1]]
        args  = [[spec, ...], ref, [gen_id, 2]]

    360p grows the spec to 8 entries with ``spec[7] = [4]``.
    """
    seed = _validated_seed(seed)

    aspect_enum = _aspect_enum(aspect_ratio)
    u1 = (u1 or str(uuid.uuid4())).upper()
    u2 = (u2 or str(uuid.uuid4())).upper()
    gen_id = (gen_id or str(uuid.uuid4())).upper()
    pid = project_id.strip().lower()

    is_360 = str(resolution or "").strip().lower().startswith("360")
    if is_360 and not model_key.endswith("_360p"):
        model_key = f"{model_key}_360p"

    def _spec(idx: int) -> list:
        s_u1 = u1 if idx == 0 else str(uuid.uuid4()).upper()
        s_u2 = u2 if idx == 0 else str(uuid.uuid4()).upper()
        s_seed = seed if idx == 0 else (new_seed() if seed is not None else None)
        spec: list[Any] = [
            [None, None, [[[prompt]]]],
            model_key,
            int(aspect_enum),
            s_seed,
            [None, None, None, None, s_u1, s_u2],
        ]
        if is_360:
            spec.extend([None, None, [4]])
        return spec

    specs = [_spec(i) for i in range(max(1, int(count)))]
    ref = _submit_ref(pid, recaptcha_token)
    return [specs, ref, [gen_id, 2]]


def build_video_upsample_1080p_args(
    project_id: str,
    video_media_id: str,
    item_id: str,
    recaptcha_token: str,
    *,
    aspect_ratio: str = "9:16",
    u1: Optional[str] = None,
    gen_id: Optional[str] = None,
) -> list:
    """Assemble the deterministic p0UkFb args payload for 1080p video upsampling (`veo_3_1_upsampler_1080p`).

    Creates media_id `<video_media_id>_upsampled` (1080x1920 for 9:16 or 1920x1080 for 16:9).
    """
    aspect_enum = _aspect_enum(aspect_ratio)
    u1 = (u1 or str(uuid.uuid4())).upper()
    gen_id = (gen_id or str(uuid.uuid4())).upper()
    pid = project_id.strip().lower()
    vid = video_media_id.strip().lower()
    iid = item_id.strip().lower()

    spec: list[Any] = [None] * 32
    spec[0] = [None, vid]
    spec[2] = int(aspect_enum)
    spec[4] = [None, iid, None, None, u1]
    spec[6] = 2
    spec[31] = VIDEO_UPSAMPLE_1080P_MODEL_KEY

    ref = _submit_ref(pid, recaptcha_token)
    return [[spec], ref, [gen_id]]


def build_jwpduf_args(video_media_id: str) -> list:
    """Args for jwpduf (0-credit video render status & error poll)."""
    return [None, None, [[video_media_id.strip().lower()]]]


def build_as29s_args(media_id: str) -> list:
    """Args for as29s (0-credit 6h signed CDN URL minting for media_id)."""
    return [media_id.strip().lower()]

