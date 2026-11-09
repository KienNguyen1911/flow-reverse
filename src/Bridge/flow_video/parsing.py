"""Pure parsers for captured decoy requests and `maseQ` / `eb1hJf` / `jwpduf` / `as29s` responses."""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional
from urllib.parse import parse_qs

from ..flow_bridge import TokenParseError, find_signed_urls
from .constants import _MEDIA_ID_RE, _TOKEN_RE, _UUID_RE


def parse_video_app_capture(body: str) -> tuple[str, str, list, str]:
    """Extract (recaptcha_token, at_param, inner_args, rpcid) from a captured eb1hJf or ogiZ0b body.

    In `eb1hJf`, the reCAPTCHA Enterprise token is at `args[1][10][0]`.
    In `ogiZ0b`, the reCAPTCHA Enterprise token is at `args[1][0][7][10][0]`.
    """
    try:
        qs = parse_qs(body, keep_blank_values=True)
        f_req_raw = qs.get("f.req", [None])[0]
        at_param = qs.get("at", [None])[0]
        if not f_req_raw or not at_param:
            raise TokenParseError("missing f.req or at in captured video request body")
        outer = json.loads(f_req_raw)
        rpcid = str(outer[0][0][0] or "")
        inner_args = json.loads(outer[0][0][1])
    except TokenParseError:
        raise
    except Exception as e:
        raise TokenParseError(f"failed to decode captured f.req: {e}") from e

    token: Optional[str] = None
    # 1. Canonical eb1hJf position: args[1][10][0]
    try:
        cand = inner_args[1][10][0]
        if isinstance(cand, str) and len(cand) >= 400:
            token = cand
    except Exception:
        pass

    # 2. Canonical ogiZ0b position: args[1][0][7][10][0]
    if not token:
        try:
            cand2 = inner_args[1][0][7][10][0]
            if isinstance(cand2, str) and len(cand2) >= 400:
                token = cand2
        except Exception:
            pass

    # 3. Recursive leaf scan fallback
    if not token:
        def _find_tok(o: Any) -> Optional[str]:
            if isinstance(o, str) and _TOKEN_RE.match(o):
                return o
            if isinstance(o, list):
                for x in o:
                    r = _find_tok(x)
                    if r:
                        return r
            elif isinstance(o, dict):
                for x in o.values():
                    r = _find_tok(x)
                    if r:
                        return r
            return None

        token = _find_tok(inner_args)

    if not (isinstance(token, str) and len(token) >= 400):
        ref_len = len(inner_args[1]) if (isinstance(inner_args, list) and len(inner_args) > 1 and isinstance(inner_args[1], list)) else -1
        raise TokenParseError(
            f"reCAPTCHA token sanity failed in {rpcid} capture (len={len(token or '')}, ref_len={ref_len})"
        )

    return token, at_param, inner_args, rpcid


def extract_frame_slot(slot: Any) -> tuple[Optional[str], Optional[list]]:
    """Read ``(media_id, crop_box)`` out of one captured frame slot.

    The slot shape is ``[null, media_id, ..., crop_box]`` — ``eb1hJf`` (single frame) and
    ``nprQif`` (first + last) use the same layout, only the index differs.
    """
    if isinstance(slot, list) and len(slot) >= 2:
        media_id = slot[1] if isinstance(slot[1], str) and _UUID_RE.match(slot[1]) else None
        crop_box = slot[5] if len(slot) > 5 and isinstance(slot[5], list) else None
        return (media_id.lower() if media_id else None), crop_box
    return None, None


def extract_starting_frame_from_eb1hjf_args(args: Any) -> tuple[Optional[str], Optional[list]]:
    """Extract (starting_frame_media_id, crop_box) from captured submit args[0][0][4]."""
    try:
        return extract_frame_slot(args[0][0][4])
    except Exception:
        return None, None


def extract_last_frame_from_args(args: Any) -> tuple[Optional[str], Optional[list]]:
    """Extract ``(last_frame_media_id, crop_box)`` from a captured ``nprQif`` decoy.

    ``nprQif`` carries ``spec[4]`` = first frame and ``spec[5]`` = last frame; an
    ``eb1hJf`` spec has the UUID slot at [5] instead, so a UUID-only slot reads as empty.
    """
    try:
        return extract_frame_slot(args[0][0][5])
    except Exception:
        return None, None


def extract_reference_media_ids(args: Any) -> list[str]:
    """Read the ingredient media ids out of a captured ``MZZa6b`` decoy.

    ``MZZa6b`` puts the reference list at ``args[0][0][1]`` as ``[[null, media_id], ...]``;
    a ``YhhmEf`` spec has the model key there instead, so a non-list reads as empty.
    """
    ids: list[str] = []
    try:
        refs = args[0][0][1]
    except Exception:
        return ids
    if not isinstance(refs, list):
        return ids
    for entry in refs:
        if not isinstance(entry, list):
            continue
        for value in entry:
            if isinstance(value, str) and _UUID_RE.match(value):
                ids.append(value.lower())
                break
    return ids


def extract_reference_video_from_args(args: Any) -> tuple[Optional[str], Optional[int]]:
    """Read ``(video_media_id, frame_count)`` out of a captured ``jIps6`` decoy.

    ``jIps6`` puts the clip at ``args[0][0][0]`` as ``[null, media_id, 0, frame_count]``.
    """
    try:
        slot = args[0][0][0]
    except Exception:
        return None, None
    if not isinstance(slot, list) or len(slot) < 2:
        return None, None
    media_id = slot[1] if isinstance(slot[1], str) and _UUID_RE.match(slot[1]) else None
    frames = slot[3] if len(slot) > 3 and isinstance(slot[3], int) else None
    return (media_id.lower() if media_id else None), frames


def extract_media_records(data: Any, project_id: Optional[str] = None) -> list[list]:
    """Recursively find all MediaItem tuples `[media_id, project_id, item_id, ...]` in a decoded payload."""
    found: list[list] = []
    seen: set[str] = set()
    pid_norm = project_id.strip().lower() if project_id else None

    def _walk(o: Any) -> None:
        if not isinstance(o, list):
            return
        if (
            len(o) >= 6
            and isinstance(o[0], str)
            and _MEDIA_ID_RE.match(o[0])
            and isinstance(o[1], str)
            and _UUID_RE.match(o[1])
            and (o[2] is None or (isinstance(o[2], str) and _UUID_RE.match(o[2])))
            and isinstance(o[5], list)
        ):
            if pid_norm is None or o[1].lower() == pid_norm:
                mid = o[0].lower()
                if mid not in seen:
                    seen.add(mid)
                    found.append(o)
                return
        for x in o:
            _walk(x)

    _walk(data)
    return found


def extract_video_submit_media_id(
    data: Any,
    *,
    project_id: Optional[str] = None,
    exclude: Iterable[str] = (),
) -> Optional[str]:
    """Extract the newly created video_media_id from an eb1hJf response payload."""
    ex = {str(x).strip().lower() for x in exclude if x}
    if project_id:
        ex.add(project_id.strip().lower())

    # 1. Canonical MediaItem records
    records = extract_media_records(data, project_id=project_id)
    for rec in records:
        mid = str(rec[0]).lower()
        if mid not in ex:
            return mid

    # 2. Fallback: walk all UUID strings in data
    candidates: list[str] = []

    def _walk_uuid(o: Any) -> None:
        if isinstance(o, str):
            if _UUID_RE.match(o) and o.lower() not in ex:
                candidates.append(o.lower())
        elif isinstance(o, list):
            for x in o:
                _walk_uuid(x)
        elif isinstance(o, dict):
            for x in o.values():
                _walk_uuid(x)

    _walk_uuid(data)
    return candidates[0] if candidates else None


def extract_signed_video_url(data: Any) -> Optional[str]:
    """Extract the best signed video download URL from an as29s / jwpduf / Zzl0ze payload.

    Priority:
    1. `https://flow-content.google/video/<id>?Expires=...` (6-hour cookie-free signed CDN URL, full-bitrate MP4).
    2. `https://storage.googleapis.com/ai-sandbox-videofx/video/...` (if present).
    3. `https://lh3.googleusercontent.com/asb/<token>=mm,22,15` (FIFE stream fallback).
    """
    urls = find_signed_urls(data)
    # 1. Prefer direct flow-content.google/video/ signed URLs
    for u in urls:
        if "flow-content.google/video/" in u:
            return u

    # 2. Scan for any string containing /video/ with Signature=
    video_urls: list[str] = []

    def _walk(o: Any) -> None:
        if isinstance(o, str):
            if o.startswith("https://") and ("/video/" in o or ".mp4" in o):
                video_urls.append(o)
        elif isinstance(o, list):
            for x in o:
                _walk(x)
        elif isinstance(o, dict):
            for x in o.values():
                _walk(x)

    _walk(data)
    if video_urls:
        return video_urls[0]

    # 3. Fallback: FIFE lh3.googleusercontent.com/asb/<token> -> append =mm,22,15
    for u in urls:
        if "googleusercontent.com/asb/" in u or "flow.google.com/asb/" in u:
            base = u.split("=")[0]
            return f"{base}=mm,22,15"

    return None


def parse_jwpduf_status(data: Any, video_media_id: Optional[str] = None) -> dict[str, Any]:
    """Decode a jwpduf status response (`docs/api_specs/flow_create_video.md` §2.3).

    Returns a dict:
        {
            "state": "pending" | "succeeded" | "failed",
            "media_id": str | None,
            "item_id": str | None,
            "status_code": int | None,     # 1 = succeeded, 4 = failed
            "error_code": str | None,      # e.g. "PUBLIC_ERROR_PROMINENT_PEOPLE_FILTER_FAILED"
            "error_categories": list[str], # e.g. ["PROMINENT_PERSON"]
            "seed_echo": int | None,
            "file_bytes": int | None,
            "signed_url": str | None,
        }
    """
    records = extract_media_records(data)
    target_rec: Optional[list] = None
    vid_norm = video_media_id.strip().lower() if video_media_id else None

    for rec in records:
        if vid_norm is None or str(rec[0]).lower() == vid_norm:
            target_rec = rec
            break
    if target_rec is None and records:
        target_rec = records[0]

    out: dict[str, Any] = {
        "state": "pending",
        "media_id": str(target_rec[0]).lower() if target_rec else vid_norm,
        "item_id": str(target_rec[2]).lower() if (target_rec and len(target_rec) > 2 and target_rec[2]) else None,
        "status_code": None,
        "error_code": None,
        "error_categories": [],
        "seed_echo": None,
        "file_bytes": None,
        "signed_url": None,
    }
    if target_rec is None:
        return out

    meta = target_rec[5] if len(target_rec) > 5 and isinstance(target_rec[5], list) else []
    status_detail = meta[8] if len(meta) > 8 and isinstance(meta[8], list) else None
    status_code = meta[9] if len(meta) > 9 and isinstance(meta[9], int) else None
    file_bytes = meta[13] if len(meta) > 13 and isinstance(meta[13], int) else None

    out["status_code"] = status_code
    out["file_bytes"] = file_bytes

    # Extract seed_echo from rec[7][0][1]
    try:
        vblock = target_rec[7]
        if isinstance(vblock, list) and vblock and isinstance(vblock[0], list) and len(vblock[0]) > 1:
            if isinstance(vblock[0][1], int):
                out["seed_echo"] = vblock[0][1]
    except Exception:
        pass

    # Check failure / policy rejection: status_code == 4 or status_detail[0] == 4
    is_failed = (status_code == 4) or (
        isinstance(status_detail, list) and len(status_detail) > 0 and status_detail[0] == 4
    )
    if is_failed:
        out["state"] = "failed"
        if isinstance(status_detail, list):
            if len(status_detail) > 1 and isinstance(status_detail[1], list) and len(status_detail[1]) > 1:
                out["error_code"] = str(status_detail[1][1])
            if len(status_detail) > 2 and isinstance(status_detail[2], list):
                out["error_categories"] = [str(c) for c in status_detail[2] if isinstance(c, str)]
        return out

    # Check succeeded: status_detail[0] == 3 (while rendering, meta[9] is already 1 but meta[8] is [1]/[2] and meta[13] is None)
    is_succeeded = (
        isinstance(status_detail, list)
        and len(status_detail) > 0
        and status_detail[0] == 3
    )
    if is_succeeded:
        out["state"] = "succeeded"
        out["signed_url"] = extract_signed_video_url(target_rec)
        return out

    return out
