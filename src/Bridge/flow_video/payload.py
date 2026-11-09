"""Pure builders for video batchexecute payloads (`eb1hJf`, `nprQif`, `YhhmEf`, `MZZa6b`, `jIps6`, `p0UkFb`, `jwpduf`, `as29s`).

Every layout below was captured 0-credit from the live composer; the wiki-comment on
each builder names the trace that pins it. The builders are pure: they take already
resolved values (model key, media ids, seeds) and never infer a composer option.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..flow_bridge import SEED_MAX, enc, new_seed
from .constants import (
    SPEC_360P_MARKER_INDEX,
    VIDEO_ASPECT_LANDSCAPE,
    VIDEO_ASPECT_PORTRAIT,
    VIDEO_EDIT_MODEL_KEY,
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


def _uuid_slot(idx: int, u1: str, u2: str) -> list:
    return [
        None, None, None, None,
        u1 if idx == 0 else str(uuid.uuid4()).upper(),
        u2 if idx == 0 else str(uuid.uuid4()).upper(),
    ]


def _seed_for(idx: int, seed: Optional[int]) -> Optional[int]:
    if seed is None:
        return None
    return int(seed) if idx == 0 else new_seed()


def _frame_slot(media_id: Optional[str], crop_box: Optional[list]) -> list:
    """``[None, media_id]``, plus the crop tail only when the composer actually sent one.

    The app omits the tail for a freshly pasted frame (``[null, <id>]``) and fills it when
    the frame is letterboxed to the target aspect. A crop is therefore *composer state*,
    not a default: inventing one would ask the server for a framing the user never chose.
    """
    slot: list[Any] = [None, media_id]
    if crop_box is not None:
        slot.extend([None, None, None, list(crop_box)])
    return slot


def _apply_360p_marker(spec: list, shape: str) -> list:
    """Pad ``spec`` to the 360p layout for ``shape`` (see ``SPEC_360P_MARKER_INDEX``)."""
    index = SPEC_360P_MARKER_INDEX.get(str(shape or ""))
    if index is None:
        return spec
    while len(spec) < index:
        spec.append(None)
    spec.append([4])
    return spec


def build_video_submit_args(
    project_id: str,
    prompt: str,
    recaptcha_token: str,
    *,
    shape: str,
    model_key: str,
    aspect_ratio: str = "9:16",
    seed: Optional[int] = None,
    starting_frame_media_id: Optional[str] = None,
    last_frame_media_id: Optional[str] = None,
    starting_frame_crop: Optional[list] = None,
    last_frame_crop: Optional[list] = None,
    reference_image_media_ids: Optional[list[str]] = None,
    reference_video_media_id: Optional[str] = None,
    reference_video_frame_count: int = 192,
    u1: Optional[str] = None,
    u2: Optional[str] = None,
    gen_id: Optional[str] = None,
    count: int = 1,
    resolution: str = "720p",
) -> list:
    """Assemble the submit ``args`` for any video shape (see ``flow_video.models``).

    One builder for five captured layouts, because they differ only in which slots exist
    and where the prompt / model key / references sit:

    ``first_frame`` (``eb1hJf``, 6 slots)::

        [[None, None, [[[prompt]]]], key, aspect, seed,
         [None, first_id, ...crop], [None, None, None, None, u1, u2]]

    ``first_and_last_frame`` (``nprQif``, 7 slots) — one extra frame slot before the
    UUID slot::

        [[None, None, [[[prompt]]]], key, aspect, seed,
         [None, first_id, ...crop], [None, last_id, ...crop], uuid]

    ``text`` (``YhhmEf``, 5 slots) — no frame slot at all::

        [[None, None, [[[prompt]]]], key, aspect, seed, uuid]

    ``image_refs`` (``MZZa6b``, 6 slots) — the reference list moves to index 1 and the
    model key to index 2::

        [[None, None, [[[prompt]]]], [[None, ref_id], ...], key, aspect, seed, uuid]

    ``video_ref`` (``jIps6``, 5 slots) — the clip *is* the first slot, there is no seed::

        [[None, video_id, 0, frames], [None, None, [[[prompt]]]], "abra_edit", aspect, uuid]

    360p is signalled twice (``_360p`` on the key plus a ``[4]`` marker at a per-shape
    index); ``SPEC_360P_MARKER_INDEX`` holds the index and omits it for the
    first+last-frame shape, which the app left unpadded.

    ``count`` > 1 duplicates the spec with a fresh ``u1``/``u2`` pair and a fresh seed
    per extra render, which is what the app does for ``x2``..``x4``.
    """
    seed = _validated_seed(seed)
    aspect_enum = _aspect_enum(aspect_ratio)
    u1 = (u1 or str(uuid.uuid4())).upper()
    u2 = (u2 or str(uuid.uuid4())).upper()
    gen_id = (gen_id or str(uuid.uuid4())).upper()
    pid = project_id.strip().lower()

    if not model_key:
        raise ValueError("build_video_submit_args needs an explicit model_key")
    is_360 = str(resolution or "").strip().lower().startswith("360")
    if is_360 and not model_key.endswith("_360p"):
        model_key = f"{model_key}_360p"

    frame_id = starting_frame_media_id.strip().lower() if starting_frame_media_id else None
    last_id = last_frame_media_id.strip().lower() if last_frame_media_id else None
    ref_ids = [str(x).strip().lower() for x in (reference_image_media_ids or []) if x]
    vid_ref = reference_video_media_id.strip().lower() if reference_video_media_id else None
    prompt_slot = [None, None, [[[prompt]]]]

    def _spec(idx: int) -> list:
        slot = _uuid_slot(idx, u1, u2)
        s_seed = _seed_for(idx, seed)

        if shape == "video_ref":
            if not vid_ref:
                raise ValueError("video_ref cần reference_video_media_id")
            return [
                [None, vid_ref, 0, int(reference_video_frame_count)],
                list(prompt_slot),
                model_key or VIDEO_EDIT_MODEL_KEY,
                int(aspect_enum),
                slot,
            ]

        if shape == "image_refs":
            if not ref_ids:
                raise ValueError("image_refs cần ít nhất một reference_image_media_id")
            return [
                list(prompt_slot),
                [[None, rid] for rid in ref_ids],
                model_key,
                int(aspect_enum),
                s_seed,
                slot,
            ]

        if shape == "text":
            return [list(prompt_slot), model_key, int(aspect_enum), s_seed, slot]

        if shape == "first_and_last_frame":
            if not frame_id or not last_id:
                raise ValueError("first_and_last_frame cần cả starting_frame và last_frame")
            return [
                list(prompt_slot),
                model_key,
                int(aspect_enum),
                s_seed,
                _frame_slot(frame_id, starting_frame_crop),
                _frame_slot(last_id, last_frame_crop),
                slot,
            ]

        # Default: first_frame (the original eb1hJf layout).
        spec = [
            list(prompt_slot),
            model_key,
            int(aspect_enum),
            s_seed,
            _frame_slot(frame_id, starting_frame_crop),
            slot,
        ]
        return spec

    specs = []
    for i in range(max(1, int(count))):
        spec = _spec(i)
        if is_360:
            spec = _apply_360p_marker(spec, shape)
        specs.append(spec)

    ref = _submit_ref(pid, recaptcha_token)
    return [specs, ref, [gen_id, 2]]


def build_video_args(
    project_id: str,
    prompt: str,
    recaptcha_token: str,
    starting_frame_media_id: Optional[str],
    *,
    aspect_ratio: str = "9:16",
    seed: Optional[int] = None,
    model_key: str = "",
    crop_box: Optional[list] = None,
    u1: Optional[str] = None,
    u2: Optional[str] = None,
    gen_id: Optional[str] = None,
    count: int = 1,
    resolution: str = "720p",
    last_frame_media_id: Optional[str] = None,
    last_frame_crop: Optional[list] = None,
) -> list:
    """Image→video submit args for the ``Khung hình`` sub-mode.

    Thin wrapper over :func:`build_video_submit_args`: one frame gives the ``eb1hJf``
    layout, two frames switch to the ``nprQif`` layout (the app swaps RPC when the
    "Kết thúc" slot is filled). ``model_key`` is required — the duration is baked into
    it, so a default here would silently submit the wrong clip length.

    ``crop_box`` must be the crop the composer itself reported for that frame (read it off
    the blocked decoy request with ``parsing.extract_starting_frame_from_eb1hjf_args``).
    ``None`` means "no crop", which is what the app sends for a plain paste; don't fill in
    ``DEFAULT_CROP_916``/``DEFAULT_CROP_169`` — those are captured *examples*, not defaults.
    """
    if not model_key:
        raise ValueError("build_video_args needs an explicit model_key (duration is part of the key)")

    shape = "first_and_last_frame" if last_frame_media_id else "first_frame"
    return build_video_submit_args(
        project_id,
        prompt,
        recaptcha_token,
        shape=shape,
        model_key=model_key,
        aspect_ratio=aspect_ratio,
        seed=seed,
        starting_frame_media_id=starting_frame_media_id,
        last_frame_media_id=last_frame_media_id,
        starting_frame_crop=crop_box,
        last_frame_crop=last_frame_crop,
        u1=u1,
        u2=u2,
        gen_id=gen_id,
        count=count,
        resolution=resolution,
    )


def build_text_video_args(
    project_id: str,
    prompt: str,
    recaptcha_token: str,
    *,
    aspect_ratio: str = "9:16",
    seed: Optional[int] = None,
    model_key: str = "",
    u1: Optional[str] = None,
    u2: Optional[str] = None,
    gen_id: Optional[str] = None,
    count: int = 1,
    resolution: str = "720p",
    reference_image_media_ids: Optional[list[str]] = None,
) -> list:
    """``Thành phần`` submit args: ``YhhmEf`` without references, ``MZZa6b`` with them.

    Thin wrapper over :func:`build_video_submit_args`; ``model_key`` is required for the
    same reason as in :func:`build_video_args`.
    """
    if not model_key:
        raise ValueError("build_text_video_args needs an explicit model_key (duration is part of the key)")
    shape = "image_refs" if reference_image_media_ids else "text"
    return build_video_submit_args(
        project_id,
        prompt,
        recaptcha_token,
        shape=shape,
        model_key=model_key,
        aspect_ratio=aspect_ratio,
        seed=seed,
        reference_image_media_ids=reference_image_media_ids,
        u1=u1,
        u2=u2,
        gen_id=gen_id,
        count=count,
        resolution=resolution,
    )


def build_video_edit_args(
    project_id: str,
    prompt: str,
    recaptcha_token: str,
    *,
    reference_video_media_id: str,
    aspect_ratio: str = "9:16",
    reference_video_frame_count: int = 192,
    u1: Optional[str] = None,
    u2: Optional[str] = None,
    gen_id: Optional[str] = None,
    count: int = 1,
) -> list:
    """``jIps6`` args for a **video** used as a ``Thành phần`` reference.

    Captured 0-credit 2026-11-09 (``traces/submit_bodies/omni12_ingvideo_jIps6_args.json``).
    The clip id becomes ``spec[0][1]`` with its frame count at ``spec[0][3]``, the model
    key is ``abra_edit`` (the Omni family is not involved), and there is no seed slot.
    """
    return build_video_submit_args(
        project_id,
        prompt,
        recaptcha_token,
        shape="video_ref",
        model_key=VIDEO_EDIT_MODEL_KEY,
        aspect_ratio=aspect_ratio,
        reference_video_media_id=reference_video_media_id,
        reference_video_frame_count=reference_video_frame_count,
        u1=u1,
        u2=u2,
        gen_id=gen_id,
        count=count,
    )



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

