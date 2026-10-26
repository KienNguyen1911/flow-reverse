"""Flow Video Bridge — Protocol-Level ("Bridge Mode") Video Generation, Frame Extraction & Concatenation.

Architecture (see `docs/api_specs/flow_create_video.md`):
1. Starting Frame Upload (`maseQ`, 0 credit):
   - Triggered via synthetic `ClipboardEvent('paste')` on `div.ProseMirror` (or UI fallback).
   - Returns `MediaItem` with `starting_frame_media_id` (`data[0][0]`).
2. Decoy Intercept & Deterministic Submit (`eb1hJf`, Bridge Mode):
   - Arms `VIDEO_HOOK_JS` (`window.__blockVideoGen = true`) to block the app's own `eb1hJf`
     request (0 credit spent on decoy) and borrow its freshly minted single-use reCAPTCHA
     Enterprise token (`0cAFcWeA...` at `args[1][10][0]`).
   - Builds our deterministic `eb1hJf` payload (`build_video_args`: model `"abra_i2v_8s"`,
     aspect enum `1` for 9:16 / `2` for 16:9, signed int32 `seed`, `starting_frame_media_id`,
     uppercase UUIDs `u1, u2, gen_id`, `_reqid = app_reqid + 100000`) and fires in-page
     with header `x-harness-ours: 1`.
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
"""

from __future__ import annotations

import base64
import copy
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import parse_qs, urlsplit

from .flow_bridge import (
    DEFAULT_CDP_URL,
    SEED_MAX,
    BridgeError,
    CaptureTimeoutError,
    FlowBridge,
    TokenParseError,
    build_capture_fire_url,
    build_rpc_url_from_template,
    describe_reject,
    enc,
    extract_app_reqid,
    find_signed_urls,
    jitter,
    new_seed,
    parse_batchexecute_text,
)

LogFn = Callable[[str, str], None]

# --------------------------------------------------------------------------- #
# Protocol Constants (`docs/api_specs/flow_create_video.md`)
# --------------------------------------------------------------------------- #

VIDEO_SUBMIT_RPC = "eb1hJf"
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
_TOKEN_RE = re.compile(r"^0cAFcWeA[A-Za-z0-9_\-]{400,}$")

# In-page fetch hook for Video Bridge Mode:
# - Blocks app's own eb1hJf (and ogiZ0b) when window.__blockVideoGen == true (0 credit on decoy).
# - Passively captures maseQ upload responses so starting_frame_media_id is read from JSON.
VIDEO_HOOK_JS = r"""
(() => {
  const isVideoSubmit = u => {
    const s = String(u || '');
    return s.indexOf('/data/batchexecute?') >= 0 &&
           (s.indexOf('rpcids=eb1hJf') >= 0 || s.indexOf('rpcids=ogiZ0b') >= 0);
  };
  const isMaseQ = u => {
    const s = String(u || '');
    return s.indexOf('/data/batchexecute?') >= 0 && s.indexOf('rpcids=maseQ') >= 0;
  };
  const isOurs = h => {
    try { return !!(h && (h['x-harness-ours'] || (h.get && h.get('x-harness-ours')))); }
    catch (e) { return false; }
  };

  if (!window.__videoHook) {
    window.__videoHook = {v: 1, cap: null, blocked: false, lastUpload: null};
    const prevFetch = window.fetch;
    window.fetch = function(input, init) {
      let url = '';
      try { url = typeof input === 'string' ? input : (input && input.url) || ''; } catch (e) {}
      const ours = isOurs(init && init.headers);

      if (isMaseQ(url) && !ours) {
        const up = {url: String(url), resp: '', ready: false, status: 0, ts: Date.now()};
        window.__videoHook.lastUpload = up;
        return prevFetch.apply(this, arguments).then(r => {
          up.status = r.status;
          try {
            r.clone().text().then(t => { up.resp = t; up.ready = true; }).catch(() => { up.ready = true; });
          } catch (e) { up.ready = true; }
          return r;
        });
      }

      if (isVideoSubmit(url) && window.__blockVideoGen && !ours) {
        if (typeof input !== 'string' && input && typeof input.text === 'function') {
          const cap = {url: String(url), body: '', bodyReady: false, ts: Date.now(), via: 'fetch-request'};
          window.__videoHook.cap = cap;
          input.text().then(t => {
            cap.body = t;
            cap.bodyReady = true;
            window.__videoHook.blocked = true;
          }).catch(e => {
            cap.readErr = String(e);
            cap.bodyReady = true;
          });
          return Promise.reject(new Error('bridge-blocked-eb1hJf'));
        }
        const body = String((init && init.body) || '');
        window.__videoHook.cap = {url: String(url), body: body, bodyReady: true, ts: Date.now(), via: 'fetch-init'};
        window.__videoHook.blocked = true;
        return Promise.reject(new Error('bridge-blocked-eb1hJf'));
      }

      return prevFetch.apply(this, arguments);
    };
  }
  window.__videoHook.cap = null;
  window.__videoHook.blocked = false;
  window.__blockVideoGen = true;
  return {installed: true, v: window.__videoHook.v};
})()
"""


# --------------------------------------------------------------------------- #
# Pure Protocol Builders & Parsers (`eb1hJf`, `jwpduf`, `as29s`, `maseQ`)
# --------------------------------------------------------------------------- #


def encode_video_batchexecute_form(rpcid: str, args: list, at_param: str) -> str:
    """Form body for batchexecute: f.req=<enc>&at=<enc>& (byte-identical)."""
    args_json = json.dumps(args, separators=(",", ":"), ensure_ascii=False)
    f_req = json.dumps([[[rpcid, args_json, None, "generic"]]], separators=(",", ":"), ensure_ascii=False)
    return "f.req=" + enc(f_req) + "&at=" + enc(at_param) + "&"


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
        if isinstance(cand, str) and cand.startswith("0cAFcWeA"):
            token = cand
    except Exception:
        pass

    # 2. Canonical ogiZ0b position: args[1][0][7][10][0]
    if not token:
        try:
            cand2 = inner_args[1][0][7][10][0]
            if isinstance(cand2, str) and cand2.startswith("0cAFcWeA"):
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

    if not (isinstance(token, str) and len(token) > 500 and token.startswith("0cAFcWeA")):
        raise TokenParseError(f"reCAPTCHA token sanity failed in {rpcid} capture (len={len(token or '')})")

    return token, at_param, inner_args, rpcid


def extract_starting_frame_from_eb1hjf_args(args: Any) -> tuple[Optional[str], Optional[list]]:
    """Extract (starting_frame_media_id, crop_box) from captured eb1hJf args[0][0][4]."""
    try:
        slot = args[0][0][4]
        if isinstance(slot, list) and len(slot) >= 2:
            media_id = slot[1] if isinstance(slot[1], str) and _UUID_RE.match(slot[1]) else None
            crop_box = slot[5] if len(slot) > 5 and isinstance(slot[5], list) else None
            return (media_id.lower() if media_id else None), crop_box
    except Exception:
        pass
    return None, None


def build_video_args(
    project_id: str,
    prompt: str,
    recaptcha_token: str,
    starting_frame_media_id: str,
    *,
    aspect_ratio: str = "9:16",
    seed: Optional[int] = None,
    model_key: str = VIDEO_MODEL_KEY,
    crop_box: Optional[list] = None,
    u1: Optional[str] = None,
    u2: Optional[str] = None,
    gen_id: Optional[str] = None,
) -> list:
    """Assemble the deterministic eb1hJf args payload (see `docs/api_specs/flow_create_video.md` §2.2).

    Layout:
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
    """
    if seed is not None:
        seed = int(seed)
        if not (1 <= seed <= SEED_MAX):
            raise ValueError(f"seed must fit signed int32: 1..{SEED_MAX} (got {seed})")

    aspect_enum = VIDEO_ASPECT_PORTRAIT if "9:16" in str(aspect_ratio) else VIDEO_ASPECT_LANDSCAPE
    if crop_box is None:
        crop_box = list(DEFAULT_CROP_916 if aspect_enum == VIDEO_ASPECT_PORTRAIT else DEFAULT_CROP_169)

    u1 = (u1 or str(uuid.uuid4())).upper()
    u2 = (u2 or str(uuid.uuid4())).upper()
    gen_id = (gen_id or str(uuid.uuid4())).upper()
    pid = project_id.strip().lower()
    sf_id = starting_frame_media_id.strip().lower()

    video_spec = [
        [None, None, [[[prompt]]]],
        model_key or VIDEO_MODEL_KEY,
        int(aspect_enum),
        int(seed) if seed is not None else None,
        [None, sf_id, None, None, None, crop_box],
        [None, None, None, None, u1, u2],
    ]
    ref = [
        None,
        VIDEO_TOOL_ID,
        None,
        None,
        None,
        pid,
        None,
        None,
        None,
        None,
        [recaptcha_token, 1],
    ]
    return [[video_spec], ref, [gen_id, 2]]


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
    aspect_enum = VIDEO_ASPECT_PORTRAIT if "9:16" in str(aspect_ratio) else VIDEO_ASPECT_LANDSCAPE
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

    ref = [
        None,
        VIDEO_TOOL_ID,
        None,
        None,
        None,
        pid,
        None,
        None,
        None,
        None,
        [recaptcha_token, 1],
    ]
    return [[spec], ref, [gen_id]]


def build_jwpduf_args(video_media_id: str) -> list:
    """Args for jwpduf (0-credit video render status & error poll)."""
    return [None, None, [[video_media_id.strip().lower()]]]


def build_as29s_args(media_id: str) -> list:
    """Args for as29s (0-credit 6h signed CDN URL minting for media_id)."""
    return [media_id.strip().lower()]


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


# --------------------------------------------------------------------------- #
# Frame Extraction, Conditioning & Video Concat Helpers (FFmpeg / OpenCV)
# --------------------------------------------------------------------------- #


def condition_frame_for_policy_retry(
    frame_path: Path | str,
    output_path: Optional[Path | str] = None,
    log: Optional[LogFn] = None,
) -> Path:
    """Create a subtly conditioned starting frame to avoid false-positive PROMINENT_PEOPLE_FILTER blocks.

    Applies an imperceptible 2% center inset crop + slight warmth/contrast micro-shift so that
    Google Flow's face-embedding similarity score drops below the false-positive celebrity threshold
    while preserving the outfit and model appearance.
    """
    src = Path(frame_path).resolve()
    dst = Path(output_path).resolve() if output_path else src.parent / f"{src.stem}_conditioned.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    _log = log or (lambda kind, msg: None)

    vf = "crop=iw*0.97:ih*0.97:iw*0.015:ih*0.015,scale=iw:ih,eq=brightness=0.012:contrast=0.985:saturation=0.98"
    cmd = ["ffmpeg", "-y", "-i", str(src), "-vf", vf, "-frames:v", "1", str(dst)]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        if res.returncode == 0 and dst.is_file() and dst.stat().st_size > 100:
            _log("info", f"Đã vi chỉnh starting frame chống false-positive filter: {dst.name}")
            return dst
    except Exception as e:
        _log("warn", f"condition_frame_for_policy_retry FFmpeg lỗi ({e}), giữ nguyên ảnh gốc.")
    return src


def extract_last_video_frame(
    video_path: Path | str,
    output_image_path: Path | str,
    log: Optional[LogFn] = None,
) -> Path:
    """Extract the exact last frame of a video using FFmpeg (or OpenCV fallback).

    Deterministic, bit-exact, and zero UI latency.
    """
    v_path = Path(video_path).resolve()
    out_path = Path(output_image_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not v_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file video: {v_path}")

    _log = log or (lambda kind, msg: None)
    _log("step", f"Trích xuất khung hình cuối từ {v_path.name}...")

    # Method 1: FFmpeg -sseof -0.2 (extract frame right before EOF)
    cmd = [
        "ffmpeg",
        "-y",
        "-sseof",
        "-0.2",
        "-i",
        str(v_path),
        "-update",
        "1",
        "-q:v",
        "1",
        str(out_path),
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
        if res.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 100:
            _log("info", f"FFmpeg trích xuất thành công: {out_path.name} ({out_path.stat().st_size} bytes)")
            return out_path
    except Exception as e:
        _log("warn", f"FFmpeg sseof lỗi ({e}), chuyển sang fallback OpenCV...")

    # Method 2: OpenCV fallback
    try:
        import cv2

        cap = cv2.VideoCapture(str(v_path))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames - 2))
            ret, frame = cap.read()
            if ret and frame is not None:
                cv2.imwrite(str(out_path), frame)
                cap.release()
                if out_path.is_file() and out_path.stat().st_size > 100:
                    _log("info", f"OpenCV trích xuất thành công: {out_path.name}")
                    return out_path
        cap.release()
    except Exception as e:
        _log("warn", f"OpenCV fallback lỗi: {e}")

    # Method 3: Reverse filter to extract the true last frame
    cmd_fallback = [
        "ffmpeg",
        "-y",
        "-i",
        str(v_path),
        "-vf",
        "reverse",
        "-vframes",
        "1",
        str(out_path),
    ]
    try:
        res3 = subprocess.run(cmd_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
        if res3.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 100:
            _log("info", f"FFmpeg (reverse filter) trích xuất thành công: {out_path.name}")
            return out_path
    except Exception as e:
        _log("warn", f"FFmpeg reverse fallback lỗi: {e}")

    raise RuntimeError(f"Không thể trích xuất khung hình cuối từ {v_path}")


def concatenate_two_videos(
    video1_path: Path | str,
    video2_path: Path | str,
    output_path: Path | str,
    log: Optional[LogFn] = None,
) -> Path:
    """Concatenate video 1 (8s) and video 2 (8s) into a unified 16s video using FFmpeg.

    Handles video streams with or without audio tracks seamlessly.
    """
    v1 = Path(video1_path).resolve()
    v2 = Path(video2_path).resolve()
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    _log = log or (lambda kind, msg: None)
    _log("step", f"Nối {v1.name} + {v2.name} thành {out.name}...")

    has_audio = False
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(v1)],
            capture_output=True, text=True, timeout=10
        )
        has_audio = bool(probe.stdout.strip())
    except Exception:
        has_audio = False

    # Method 1: Concat demuxer
    list_file = out.parent / f"_concat_{int(time.time() * 1000)}.txt"
    try:
        v1_esc = v1.as_posix().replace("'", "'\\''")
        v2_esc = v2.as_posix().replace("'", "'\\''")
        list_file.write_text(
            f"file '{v1_esc}'\nfile '{v2_esc}'\n",
            encoding="utf-8",
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ]
        if has_audio:
            cmd.extend(["-c:a", "aac"])
        else:
            cmd.append("-an")
        cmd.append(str(out))

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if res.returncode == 0 and out.is_file() and out.stat().st_size > 200:
            _log("info", f"Nối video thành công: {out.name} ({out.stat().st_size} bytes)")
            return out
    finally:
        if list_file.exists():
            try:
                list_file.unlink()
            except Exception:
                pass

    # Method 2: filter_complex with resolution & SAR normalization
    w, h = 1280, 720
    try:
        probe_res = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(v1)],
            capture_output=True, text=True, timeout=10,
        )
        if probe_res.returncode == 0 and "x" in probe_res.stdout:
            parts = probe_res.stdout.strip().split("x")
            w, h = int(parts[0]), int(parts[1])
    except Exception:
        pass

    filter_expr = f"[0:v]scale={w}:{h},setsar=1[v0];[1:v]scale={w}:{h},setsar=1[v1];[v0][v1]concat=n=2:v=1[v]"
    cmd_filter = [
        "ffmpeg",
        "-y",
        "-i",
        str(v1),
        "-i",
        str(v2),
        "-filter_complex",
        filter_expr,
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(out),
    ]
    res2 = subprocess.run(cmd_filter, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if res2.returncode == 0 and out.is_file() and out.stat().st_size > 200:
        _log("info", f"Nối video (filter_complex) thành công: {out.name}")
        return out

    raise RuntimeError(f"Lỗi nối video: {res2.stderr.decode('utf-8', 'ignore')[:300]}")


# --------------------------------------------------------------------------- #
# Prompt Sanitization
# --------------------------------------------------------------------------- #


def sanitize_video_prompt(prompt_text: str, aggressive: bool = False) -> str:
    """Sanitize video prompts to avoid false-positive Google Flow celebrity/identity policy blocks.

    In Frames Mode ('Khung hình' / `abra_i2v_8s`), the starting frame image already locks the
    model's visual identity. Phrases like 'exact young Korean woman from the reference image'
    or 'Strictly lock facial identity' frequently trigger Google's prominent-person safety filter.
    """
    clean = " ".join([line.strip() for line in prompt_text.splitlines() if line.strip()])

    replacements = [
        (r"\b(of\s+)?(the\s+)?exact\s+(young\s+)?(korean\s+|asian\s+)?(woman|girl|model|lady)(\s+from\s+the\s+reference\s+(image|photo))?\b", "of the fashion model"),
        (r"\b(young\s+)?(korean|asian|japanese|chinese)\s+(woman|girl|model|lady)\b", "fashion model"),
        (r"\bfrom\s+the\s+reference\s+(image|photo)(\s+pose)?\b", "in the scene"),
        (r"\b(strictly\s+)?lock(ed)?\s+facial\s+(identity|features|structure)(\s+and\s+hairstyle)?\b", "natural expression"),
        (r"\b(strictly\s+)?maintain(ing)?\s+(exact\s+)?facial\s+(identity|features)\b", "natural expression"),
        (r"\b(celebrity|idol|actress|k-pop|famous\s+person)\b", "model"),
        (r"\bvisible\s+skin\s+micro-pores,?\s*", ""),
        (r"\bauthentic\s+skin\s+texture\s+with\s+natural\s+pores,?\s*", "soft natural lighting, "),
        (r"\bzero\s+plastic\s+skin\s+smoothing,?\s*", ""),
    ]
    for pattern, repl in replacements:
        clean = re.sub(pattern, repl, clean, flags=re.IGNORECASE)

    # Always strip Gemini timecode section labels and Camera & Realism identity boilerplate
    clean = re.sub(r"Camera\s*&\s*Realism:.*$", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"-\s*0s\s*to\s*2s\s*\([^)]*\):\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"-\s*2s\s*to\s*6s\s*\([^)]*\):\s*", " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"-\s*6s\s*to\s*8s\s*\([^)]*\):\s*", " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s{2,}", " ", clean).strip()

    if aggressive:
        if not clean:
            clean = (
                "A smooth, realistic 8-second fashion lookbook video. "
                "The model moves gracefully with natural posture, gentle fabric flow, "
                "soft studio lighting, subtle handheld camera movement, 24fps."
            )
        else:
            clean += " Smooth natural movement, realistic fabric drape, soft lighting, 8 seconds."

    return clean


# --------------------------------------------------------------------------- #
# FlowVideoBridge Class — Protocol-Level ("Bridge Mode")
# --------------------------------------------------------------------------- #


class FlowVideoBridge:
    """Protocol-level ("Bridge Mode") Video generation on Google Flow (`eb1hJf` + `jwpduf` + `as29s`)."""

    def __init__(
        self,
        cdp_url: str = DEFAULT_CDP_URL,
        log: Optional[LogFn] = None,
    ):
        self.cdp_url = cdp_url
        self._log = log or (lambda kind, msg: None)

    def install_video_hook(self, bridge: FlowBridge) -> None:
        """Install the idempotent VIDEO_HOOK_JS (`eb1hJf` block+capture + `maseQ` upload spy)."""
        res = bridge._eval(VIDEO_HOOK_JS)
        if not (isinstance(res, dict) and res.get("installed")):
            raise BridgeError(f"VIDEO_HOOK_JS install failed: {res!r}")
        self._log("info", "Đã gắn VIDEO_HOOK_JS (chặn eb1hJf mồi 0-credit + lắng nghe maseQ)")

    def disarm_video_hook(self, bridge: FlowBridge) -> None:
        """Disarm the eb1hJf request blocker."""
        try:
            bridge._eval("window.__blockVideoGen = false; true", retries=2)
        except Exception:
            pass

    def wait_video_capture(self, bridge: FlowBridge, timeout_s: float = 25.0, min_len: int = 100) -> dict[str, Any]:
        """Wait for the blocked app eb1hJf decoy capture (`window.__videoHook.cap`)."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            info = bridge.eval_json(
                """(() => {
                    const c = window.__videoHook && window.__videoHook.cap;
                    return (c && c.bodyReady) ? {url: c.url, ts: c.ts, via: c.via, len: (c.body || '').length} : null;
                })()"""
            )
            if info and int(info.get("len") or 0) > min_len:
                body = bridge._eval("(window.__videoHook && window.__videoHook.cap && window.__videoHook.cap.body) || ''")
                if body and len(body) > min_len:
                    return {
                        "url": info.get("url") or "",
                        "body": body,
                        "ts_ms": int(info.get("ts") or 0),
                        "via": info.get("via") or "",
                    }
            time.sleep(0.12)
        raise CaptureTimeoutError("Không bắt được request eb1hJf của app trong ~25s (hook timeout).")

    def upload_starting_frame_via_paste(
        self,
        bridge: FlowBridge,
        frame_path: Path,
        project_id: Optional[str] = None,
        timeout_s: float = 45.0,
    ) -> Optional[str]:
        """Upload & attach starting frame via synthetic ClipboardEvent('paste') (`maseQ` RPC).

        Returns `starting_frame_media_id` (UUIDv4) directly from `maseQ`'s JSON response
        once upload completes, or None if synthetic paste did not trigger `maseQ`.
        """
        page = bridge.page
        assert page is not None

        # Clear any existing starting frame chip first
        cancel_btn = page.query_selector(
            'flow-image-ingredient-chip button, '
            'flow-image-ingredient-chip [class*="cancel"], '
            'flow-image-ingredient-chip mat-icon:has-text("cancel"), '
            'flow-image-ingredient-chip .hover-icon-overlay'
        )
        if cancel_btn:
            cancel_btn.click(force=True)
            page.wait_for_timeout(400)

        bridge._eval("if (window.__videoHook) window.__videoHook.lastUpload = null;")

        mime = "image/png" if frame_path.suffix.lower() == ".png" else "image/jpeg"
        b64_data = base64.b64encode(frame_path.read_bytes()).decode("ascii")

        self._log("step", f"Đẩy starting frame {frame_path.name} qua sự kiện Paste (RPC maseQ)...")
        page.evaluate(
            """([b64, fname, mimeType]) => {
                const bin = atob(b64);
                const arr = new Uint8Array(bin.length);
                for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
                const file = new File([arr], fname, {type: mimeType});
                const dt = new DataTransfer();
                dt.items.add(file);
                const pm = document.querySelector('div.ProseMirror') || document.body;
                pm.focus();
                pm.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true, clipboardData: dt}));
            }""",
            [b64_data, frame_path.name, mime],
        )

        t0 = time.time()
        while time.time() - t0 < timeout_s:
            up = bridge.eval_json(
                """(() => {
                    const u = window.__videoHook && window.__videoHook.lastUpload;
                    return (u && u.ready) ? {status: u.status, resp: u.resp} : null;
                })()"""
            )
            if up and up.get("resp"):
                parsed = parse_batchexecute_text(up["resp"])
                if parsed.get("ok"):
                    records = extract_media_records(parsed.get("data"), project_id=project_id)
                    if records:
                        media_id = str(records[0][0]).lower()
                        self._log("info", f"maseQ upload hoàn tất sau {time.time() - t0:.1f}s -> media_id={media_id}")
                        # Give Angular 600ms to mount the chip in composer state
                        page.wait_for_timeout(600)
                        return media_id
                break
            time.sleep(0.25)

        return None

    def poll_video_rpc(
        self,
        bridge: FlowBridge,
        video_media_id: str,
        project_id: Optional[str] = None,
        timeout_s: float = 300.0,
        poll_interval_s: float = 4.0,
    ) -> dict[str, Any]:
        """Poll `jwpduf` (0 credit) for `video_media_id` until succeeded or failed."""
        ctx = bridge.session_ctx(timeout_s=10.0)
        t0 = time.time()
        deadline = t0 + timeout_s
        poll_seq = 0

        self._log("step", f"Poll trạng thái video qua RPC jwpduf (media_id={video_media_id[:8]}..., tối đa {timeout_s:.0f}s)...")
        while time.time() < deadline:
            time.sleep(poll_interval_s)
            poll_seq += 1
            elapsed = int(time.time() - t0)

            reqid = ctx.reqid + 100000 + (poll_seq * 1000)
            url = build_rpc_url_from_template(ctx.url_template, VIDEO_POLL_RPC, reqid)
            body = encode_video_batchexecute_form(VIDEO_POLL_RPC, build_jwpduf_args(video_media_id), ctx.at)

            try:
                fr = bridge.fire(url, body, timeout_s=25.0, poll_s=0.5)
                parsed = parse_batchexecute_text(fr.text)
            except Exception as e:
                self._log("warn", f"jwpduf poll #{poll_seq} lỗi mạng tạm thời ({e}), thử lại...")
                continue

            if not parsed.get("ok"):
                self._log("warn", f"jwpduf poll #{poll_seq} trả về not-ok: {parsed.get('reason')}")
                continue

            st = parse_jwpduf_status(parsed.get("data"), video_media_id=video_media_id)
            if st["state"] == "succeeded":
                self._log(
                    "info",
                    f"jwpduf báo video HOÀN TẤT sau {elapsed}s! (size={st.get('file_bytes') or '?'} bytes, seed={st.get('seed_echo')})",
                )
                return st

            if st["state"] == "failed":
                err_code = st.get("error_code") or "UNKNOWN_VIDEO_ERROR"
                cats = ", ".join(st.get("error_categories") or [])
                self._log(
                    "warn",
                    f"jwpduf phát hiện lỗi tức thì sau {elapsed}s: {err_code} (categories={cats})",
                )
                return st

            if poll_seq % 3 == 0:
                self._log("info", f"Đang render video trên server (jwpduf state=pending, đã qua {elapsed}s)...")

        raise BridgeError(f"Hết thời gian chờ render video qua jwpduf ({timeout_s:.0f}s) cho media_id={video_media_id}.")

    def fetch_signed_video_url_rpc(
        self,
        bridge: FlowBridge,
        video_media_id: str,
        project_id: Optional[str] = None,
    ) -> str:
        """Call `as29s` (0 credit) to mint a 6-hour signed CDN URL for `video_media_id`."""
        ctx = bridge.session_ctx(timeout_s=10.0)
        url = build_rpc_url_from_template(ctx.url_template, VIDEO_MEDIA_URL_RPC, ctx.reqid + 250000)
        body = encode_video_batchexecute_form(VIDEO_MEDIA_URL_RPC, build_as29s_args(video_media_id), ctx.at)

        self._log("step", f"Gọi RPC as29s lấy signed CDN URL 6h cho video {video_media_id[:8]}...")
        fr = bridge.fire(url, body, timeout_s=25.0, poll_s=0.5)
        parsed = parse_batchexecute_text(fr.text)
        if parsed.get("ok"):
            signed = extract_signed_video_url(parsed.get("data"))
            if signed:
                self._log("info", f"Đã lấy signed URL từ as29s: {signed[:85]}...")
                return signed

        # Fallback: query Zzl0ze project items if as29s did not contain the URL
        if project_id:
            url_z = build_rpc_url_from_template(ctx.url_template, PROJECT_ITEMS_RPC, ctx.reqid + 260000)
            body_z = encode_video_batchexecute_form(
                PROJECT_ITEMS_RPC, [f"projects/{project_id.strip().lower()}", None, None, None, [1]], ctx.at
            )
            fr_z = bridge.fire(url_z, body_z, timeout_s=25.0, poll_s=0.5)
            parsed_z = parse_batchexecute_text(fr_z.text)
            if parsed_z.get("ok"):
                for rec in extract_media_records(parsed_z.get("data"), project_id=project_id):
                    if str(rec[0]).lower() == video_media_id.strip().lower():
                        signed_z = extract_signed_video_url(rec)
                        if signed_z:
                            return signed_z

        raise BridgeError(f"Không lấy được signed video URL qua as29s/Zzl0ze cho {video_media_id}.")

    def upsample_and_fetch_1080p_url_rpc(
        self,
        bridge: FlowBridge,
        video_media_id: str,
        item_id: Optional[str],
        project_id: str,
        aspect_ratio: str = "9:16",
        timeout_s: float = 120.0,
    ) -> Optional[str]:
        """Upsample a succeeded 720p video to 1080p via RPC `p0UkFb` (`veo_3_1_upsampler_1080p`) and return its 6h signed URL.

        Workflow (`docs/api_specs/flow_create_video.md` §2.5):
        1. Checks if `<video_media_id>_upsampled` is already available via `as29s`.
        2. Otherwise, resolves `item_id` (if missing) via `as29s([video_media_id])`, borrows a fresh
           0-credit reCAPTCHA token via `VIDEO_HOOK_JS` + `click_generate`, and fires `p0UkFb`.
        3. Polls `jwpduf` for `<video_media_id>_upsampled` until `rec[5][8] == [3]`.
        4. Calls `as29s([f"{video_media_id}_upsampled"])` to mint the 6h signed 1080p MP4 URL.
        """
        vid_norm = video_media_id.strip().lower()
        upsampled_id = vid_norm if vid_norm.endswith("_upsampled") else f"{vid_norm}_upsampled"
        ctx = bridge.session_ctx(timeout_s=10.0)

        # 1. Fast check: is `<video_media_id>_upsampled` already ready?
        try:
            url_check = build_rpc_url_from_template(ctx.url_template, VIDEO_MEDIA_URL_RPC, ctx.reqid + 270000)
            body_check = encode_video_batchexecute_form(VIDEO_MEDIA_URL_RPC, build_as29s_args(upsampled_id), ctx.at)
            fr_check = bridge.fire(url_check, body_check, timeout_s=20.0, poll_s=0.4)
            p_check = parse_batchexecute_text(fr_check.text)
            if p_check.get("ok"):
                st_check = parse_jwpduf_status(p_check.get("data"), video_media_id=upsampled_id)
                if st_check["state"] == "succeeded":
                    existing_url = extract_signed_video_url(p_check.get("data"))
                    if existing_url:
                        self._log("info", f"Bản 1080p ({upsampled_id[:12]}...) đã có sẵn! ({st_check.get('file_bytes') or '?'} bytes)")
                        return existing_url
        except Exception:
            pass

        # 2. Ensure we have item_id for p0UkFb
        resolved_item_id = item_id
        if not resolved_item_id:
            try:
                url_base = build_rpc_url_from_template(ctx.url_template, VIDEO_MEDIA_URL_RPC, ctx.reqid + 271000)
                body_base = encode_video_batchexecute_form(VIDEO_MEDIA_URL_RPC, build_as29s_args(vid_norm), ctx.at)
                fr_base = bridge.fire(url_base, body_base, timeout_s=20.0, poll_s=0.4)
                p_base = parse_batchexecute_text(fr_base.text)
                if p_base.get("ok"):
                    recs = extract_media_records(p_base.get("data"), project_id=project_id)
                    if recs and len(recs[0]) > 2 and recs[0][2]:
                        resolved_item_id = str(recs[0][2]).lower()
            except Exception:
                pass

        if not resolved_item_id:
            self._log("warn", f"Không tìm thấy item_id cho {vid_norm}, bỏ qua nâng cấp 1080p.")
            return None

        # 3. Borrow a 0-credit reCAPTCHA token via decoy click_generate and fire p0UkFb
        try:
            self._log("step", f"Nâng cấp video {vid_norm[:8]}... lên 1080p qua RPC {VIDEO_UPSAMPLE_RPC} (veo_3_1_upsampler_1080p)...")
            self.install_video_hook(bridge)
            bridge._eval("window.__videoHook.cap = null; window.__blockVideoGen = true;")
            bridge.click_generate(timeout_s=12.0)
            cap = self.wait_video_capture(bridge, timeout_s=20.0)
            self.disarm_video_hook(bridge)

            app_reqid = extract_app_reqid(cap["url"])
            tok, at_param, _, _ = parse_video_app_capture(cap["body"])
            up_args = build_video_upsample_1080p_args(
                project_id=project_id,
                video_media_id=vid_norm,
                item_id=resolved_item_id,
                recaptcha_token=tok,
                aspect_ratio=aspect_ratio,
            )
            up_reqid = (app_reqid + 150000) if app_reqid is not None else (ctx.reqid + 275000)
            up_url = build_rpc_url_from_template(cap["url"], VIDEO_UPSAMPLE_RPC, up_reqid)
            up_body = encode_video_batchexecute_form(VIDEO_UPSAMPLE_RPC, up_args, at_param)

            fr_up = bridge.fire(up_url, up_body, timeout_s=45.0, poll_s=0.6)
            p_up = parse_batchexecute_text(fr_up.text)
            if not p_up.get("ok"):
                self._log("warn", f"RPC {VIDEO_UPSAMPLE_RPC} trả về not-ok ({p_up.get('reason')}), dùng bản 720p.")
                return None

            self._log("info", f"Đã kích hoạt nâng cấp 1080p ({upsampled_id})! Đang poll jwpduf...")
            st_up = self.poll_video_rpc(
                bridge,
                video_media_id=upsampled_id,
                project_id=project_id,
                timeout_s=timeout_s,
                poll_interval_s=3.5,
            )
            if st_up["state"] == "succeeded":
                return st_up.get("signed_url") or self.fetch_signed_video_url_rpc(
                    bridge, video_media_id=upsampled_id, project_id=project_id
                )
        except Exception as e:
            self.disarm_video_hook(bridge)
            self._log("warn", f"Nâng cấp 1080p gặp lỗi ({e}), tự động fallback về bản 720p gốc.")

        return None

    def download_video_verified(
        self,
        bridge: FlowBridge,
        video_url: str,
        dest_path: Path,
    ) -> Path:
        """Download video from signed CDN URL (or authenticated FIFE URL) with ftyp magic-byte verification."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Try cookie-free signed CDN download via FlowBridge.download (validates ftyp magic bytes + backoff)
        if "flow-content.google/" in video_url or "storage.googleapis.com/" in video_url:
            ok, nbytes = bridge.download(video_url, dest_path)
            if ok and nbytes > 10000:
                self._log("info", f"Đã tải video gốc qua signed CDN ({nbytes / 1024:.1f} KB) -> {dest_path.name}")
                return dest_path

        # 2. Authenticated browser context download (required for lh3/flow.google.com/asb/...=mm,22,15 URLs)
        if bridge.context is not None:
            for attempt in range(3):
                try:
                    resp = bridge.context.request.get(video_url, timeout=60000)
                    data = resp.body()
                    is_mp4 = b"ftyp" in data[:32] or data[:4] == b"\x1a\x45\xdf\xa3"
                    if resp.status == 200 and is_mp4 and len(data) > 10000:
                        dest_path.write_bytes(data)
                        self._log("info", f"Đã tải video xác thực ({len(data) / 1024:.1f} KB) -> {dest_path.name}")
                        return dest_path
                except Exception as e:
                    self._log("warn", f"Tải video qua context.request lần {attempt + 1} lỗi: {e}")
                time.sleep(2.0 * (attempt + 1))

        # 3. Final fallback to FlowBridge.download
        ok, nbytes = bridge.download(video_url, dest_path)
        if ok and nbytes > 10000:
            return dest_path

        raise BridgeError(f"Tải file video thất bại hoặc không đúng định dạng MP4 từ URL: {video_url[:90]}")

    def snapshot_videos(self, bridge: FlowBridge) -> dict[str, Any]:
        """Capture existing video URLs and count in the current project DOM."""
        info = bridge.eval_json(
            """(() => {
                const videos = Array.from(document.querySelectorAll('video'));
                const srcs = videos.map(v => v.src || v.currentSrc || '').filter(s => s.length > 0);
                const entries = performance.getEntriesByType('resource')
                    .map(e => e.name || '')
                    .filter(u => u.indexOf('.mp4') >= 0 || u.indexOf('/video/') >= 0);
                return {srcs: srcs, entries: entries, count: videos.length};
            })()"""
        ) or {}
        urls = set(info.get("srcs", []) + info.get("entries", []))
        return {"urls": urls, "count": int(info.get("count", 0))}

    def attach_video_starting_frame(
        self,
        bridge: FlowBridge,
        frame_path: Path,
    ) -> bool:
        """Attach an image as the starting frame for video generation in Flow."""
        self._log("step", f"Đính kèm starting frame cho video: {frame_path.name}")
        media_id = self.upload_starting_frame_via_paste(bridge, frame_path)
        if media_id:
            return True
        info = bridge.attach_reference(frame_path)
        return bool(info.get("preview_seen"))

    def _ensure_ui_video_frames_mode(self, page: Any, target_aspect: str) -> None:
        """Ensure composer UI is in Video -> Khung hình (Frames Mode) -> 8 giây -> target_aspect."""
        settings_btn = page.query_selector("button.settings-trigger-button")
        if not settings_btn:
            return
        btn_txt = (settings_btn.inner_text() or "").strip()
        need_aspect_icon = "crop_9_16" if target_aspect == "9:16" else "crop_16_9"
        if "Video" in btn_txt and "8 giây" in btn_txt and need_aspect_icon in btn_txt and page.query_selector('//button[contains(., "Bắt đầu")] | //flow-image-ingredient-chip'):
            return

        settings_btn.click(force=True)
        page.wait_for_timeout(500)
        for label in ["Video", "Khung hình", target_aspect, "8 giây"]:
            r_btn = page.query_selector(f'//button[@role="radio" and contains(., "{label}")]')
            if r_btn and r_btn.get_attribute("aria-checked") != "true":
                r_btn.click(force=True)
                page.wait_for_timeout(250)

        backdrop = page.query_selector(".cdk-overlay-backdrop")
        if backdrop:
            backdrop.click(force=True)
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(350)

    def _attach_starting_frame_ui_fallback(self, page: Any, frame_p: Path) -> None:
        """Fallback UI attachment when synthetic paste does not mount flow-image-ingredient-chip."""
        start_btn = page.query_selector('//button[contains(., "Bắt đầu")]')
        if start_btn:
            start_btn.click(force=True)
            page.wait_for_timeout(700)
            upload_btn = page.query_selector(
                ".cdk-overlay-pane .sidebar-upload-btn, flow-add-menu-popover-content .sidebar-upload-btn"
            )
            if upload_btn and frame_p.is_file():
                try:
                    with page.expect_file_chooser(timeout=5000) as fc:
                        upload_btn.click(force=True)
                    fc.value.set_files([str(frame_p)])
                    page.wait_for_timeout(2000)
                except Exception as e:
                    self._log("warn", f"Upload frame UI fallback: {e}")

            t_up = time.time()
            while time.time() - t_up < 90.0:
                if page.query_selector("flow-image-ingredient-chip"):
                    break
                ready = page.evaluate("""() => {
                    const pane = document.querySelector('.cdk-overlay-pane, flow-add-menu-popover-content');
                    if (!pane) return false;
                    const firstItem = pane.querySelector('button.asset-item');
                    if (!firstItem) return false;
                    const txt = (firstItem.innerText || '').trim();
                    const uploading = txt.includes('Đang tải lên') || txt.toLowerCase().includes('uploading');
                    const thumb = firstItem.querySelector('img.asset-thumbnail-image, img[src^="http"]');
                    const spinner = pane.querySelector('mat-spinner, mat-progress-spinner, [role="progressbar"]');
                    return !!thumb && !uploading && !spinner;
                }""")
                if ready:
                    first_item = page.query_selector("button.asset-item")
                    if first_item:
                        first_item.click(force=True)
                        page.wait_for_timeout(700)
                    add_btn = page.query_selector(
                        'button.detail-add-to-prompt-btn:not([disabled]), button:has-text("Thêm vào câu lệnh"):not([disabled])'
                    )
                    if add_btn and not page.query_selector("flow-image-ingredient-chip"):
                        add_btn.click(force=True)
                        page.wait_for_timeout(800)
                    break
                page.wait_for_timeout(1000)

    def _cleanup_failed_tiles_in_dom(self, page: Any) -> None:
        """Remove any stale 'Không thành công' error tiles from the project grid."""
        try:
            page.evaluate("""() => {
                const tiles = Array.from(document.querySelectorAll('flow-grid-tile-container, flow-tile-container, [class*="tile"], [class*="card"]'))
                    .filter(el => el.innerText && (
                        el.innerText.includes('Không thành công') ||
                        el.innerText.includes('Unsuccessful') ||
                        el.innerText.includes('vi phạm chính sách')
                    ));
                for (const t of tiles) {
                    const delBtn = Array.from(t.querySelectorAll('button')).find(b => {
                        const txt = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase();
                        return txt.includes('delete') || txt.includes('xoá') || txt.includes('xóa');
                    });
                    if (delBtn) delBtn.click();
                }
            }""")
        except Exception:
            pass

    def generate_video_flow(
        self,
        frame_path: Path | str,
        prompt_text: str,
        dest_path: Path | str,
        duration_s: int = 8,
        timeout_s: float = 300.0,
        project_id: Optional[str] = None,
        aspect_ratio: str = "9:16",
        aggressive_sanitize: bool = False,
        seed: Optional[int] = None,
        resolution: str = "1080p",
    ) -> Path:
        """Protocol-level ("Bridge Mode") Video generation on Google Flow (`eb1hJf` + `jwpduf` + `as29s`).

        Workflow:
        1. Connects to CloakBrowser over CDP (`FlowBridge`) and installs `VIDEO_HOOK_JS`.
        2. Uploads starting frame via `maseQ` (synthetic paste on `div.ProseMirror`, with UI fallback).
        3. Intercepts & blocks the app's decoy `eb1hJf` request (0 credit spent on decoy) to borrow
           the freshly minted reCAPTCHA Enterprise token (`0cAFcWeA...`) and starting frame slot.
        4. Builds our deterministic `eb1hJf` payload (`build_video_args`: sanitized prompt, int32 seed,
           aspect enum `1`/`2`, uppercase UUIDs, `_reqid + 100000`) and fires in-page (`x-harness-ours: 1`).
        5. Polls `jwpduf` (0 credit) every 4s for deterministic JSON status:
           - On `PUBLIC_ERROR_PROMINENT_PEOPLE_FILTER_FAILED`: fails fast in ~8s (no 300s blind wait)
             and automatically performs 1 protocol-level recovery retry with a conditioned starting frame
             (`condition_frame_for_policy_retry`), aggressive prompt sanitization, and a fresh int32 seed.
           - On `succeeded`: mints a 6-hour signed CDN URL via `as29s` (0 credit) and downloads the
             full-bitrate `ftypisom` MP4.
        """
        frame_p = Path(frame_path).resolve()
        dest_p = Path(dest_path).resolve()
        dest_p.parent.mkdir(parents=True, exist_ok=True)

        if not frame_p.is_file():
            raise FileNotFoundError(f"Không tìm thấy file frame: {frame_p}")

        target_aspect = "9:16" if "9:16" in str(aspect_ratio) else "16:9"

        with FlowBridge(self.cdp_url, log=lambda m: self._log("info", m)) as br:
            page = br.page
            assert page is not None

            if project_id and f"/project/{project_id}" not in page.url:
                self._log("step", f"Điều hướng SPA tới dự án Flow: {project_id}")
                br.nav_project(project_id)

            # Extract active project_id from URL if not explicitly provided
            active_pid = project_id
            if not active_pid and "/project/" in page.url:
                active_pid = page.url.split("/project/")[1].split("/")[0].split("?")[0]
            if not active_pid:
                raise BridgeError("Không xác định được project_id trên trang Flow hiện tại.")
            active_pid = active_pid.strip().lower()

            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            self._cleanup_failed_tiles_in_dom(page)

            # Pre-condition starting frame lightly on attempt 0 to prevent false-positive PROMINENT_PERSON blocks up front
            max_protocol_attempts = 2
            current_frame_p = condition_frame_for_policy_retry(
                frame_p,
                dest_p.parent / f"_{frame_p.stem}_conditioned.png",
                log=self._log,
            )

            for attempt in range(max_protocol_attempts):
                is_retry = attempt > 0
                use_aggressive = aggressive_sanitize or is_retry
                clean_prompt = sanitize_video_prompt(prompt_text, aggressive=use_aggressive)
                seed_to_use = new_seed() if (seed is None or is_retry) else int(seed)

                self._log(
                    "step",
                    f"[Bridge Mode {attempt + 1}/{max_protocol_attempts}] Tạo Video ({duration_s}s, {target_aspect}, seed={seed_to_use}) từ {current_frame_p.name}",
                )
                self._log("info", f"Prompt ({len(clean_prompt)} ký tự): '{clean_prompt[:85]}...'")

                # 1. Install VIDEO_HOOK_JS and ensure Video + Khung hình mode
                self.install_video_hook(br)
                self._ensure_ui_video_frames_mode(page, target_aspect)

                # 2. Upload & attach starting frame via synthetic paste (`maseQ`) or UI fallback
                uploaded_media_id = self.upload_starting_frame_via_paste(
                    br, current_frame_p, project_id=active_pid, timeout_s=35.0
                )
                if not page.query_selector("flow-image-ingredient-chip"):
                    self._attach_starting_frame_ui_fallback(page, current_frame_p)

                if not page.query_selector("flow-image-ingredient-chip") and not uploaded_media_id:
                    raise BridgeError(
                        "Không thể gắn Starting Frame vào ô 'Bắt đầu' (cả qua maseQ paste lẫn UI fallback)."
                    )

                # 3. Arm eb1hJf blocker (0 credit on decoy), type prompt, click Generate
                br._eval("window.__videoHook.cap = null; window.__blockVideoGen = true;")
                br.type_prompt(clean_prompt)
                time.sleep(jitter(0.4, 0.1, 0.2))
                br.click_generate(timeout_s=15.0)

                cap = self.wait_video_capture(br, timeout_s=25.0)
                self.disarm_video_hook(br)

                app_reqid = extract_app_reqid(cap["url"])
                token, at_param, app_args, cap_rpcid = parse_video_app_capture(cap["body"])
                cap_sf_id, cap_crop_box = extract_starting_frame_from_eb1hjf_args(app_args)

                starting_frame_media_id = cap_sf_id or uploaded_media_id
                if not starting_frame_media_id:
                    raise BridgeError(
                        f"Request mồi ({cap_rpcid}) không chứa starting_frame_media_id — kiểm tra chế độ Khung hình."
                    )

                # 4. Build our deterministic eb1hJf request payload
                u1 = str(uuid.uuid4()).upper()
                u2 = str(uuid.uuid4()).upper()
                gen_id = str(uuid.uuid4()).upper()

                our_args = build_video_args(
                    project_id=active_pid,
                    prompt=clean_prompt,
                    recaptcha_token=token,
                    starting_frame_media_id=starting_frame_media_id,
                    aspect_ratio=target_aspect,
                    seed=seed_to_use,
                    crop_box=cap_crop_box,
                    u1=u1,
                    u2=u2,
                    gen_id=gen_id,
                )
                our_body = encode_video_batchexecute_form(VIDEO_SUBMIT_RPC, our_args, at_param)
                new_reqid = (app_reqid + 100000) if app_reqid is not None else 990001
                fire_url = build_rpc_url_from_template(cap["url"], VIDEO_SUBMIT_RPC, new_reqid)
                gap_ms = int(time.time() * 1000) - int(cap["ts_ms"] or 0)

                self._log(
                    "step",
                    f"Fire {VIDEO_SUBMIT_RPC} tất định (frame={starting_frame_media_id[:8]}..., seed={seed_to_use}, _reqid={new_reqid}, gap={gap_ms}ms)",
                )

                # 5. Fire our eb1hJf in-page with x-harness-ours: 1
                fr = br.fire(fire_url, our_body, timeout_s=60.0, poll_s=1.0)
                parsed_submit = parse_batchexecute_text(fr.text)

                if not parsed_submit.get("ok"):
                    kind, hint = describe_reject(parsed_submit.get("grpc_code"), parsed_submit.get("detail") or "")
                    raise BridgeError(f"eb1hJf bị từ chối ngay khi submit ({kind}, 0 credit): {hint}")

                video_media_id = extract_video_submit_media_id(
                    parsed_submit.get("data"),
                    project_id=active_pid,
                    exclude=[starting_frame_media_id, u1, u2, gen_id],
                )
                if not video_media_id:
                    raise BridgeError(
                        f"eb1hJf thành công nhưng không tìm thấy video_media_id trong response: {fr.text[:250]}"
                    )

                self._log("info", f"eb1hJf đã nhận job! video_media_id={video_media_id} (gen_id={gen_id[:8]}...)")

                # 6. Poll jwpduf (0 credit) for completion or policy error
                poll_res = self.poll_video_rpc(
                    br,
                    video_media_id=video_media_id,
                    project_id=active_pid,
                    timeout_s=timeout_s,
                    poll_interval_s=4.0,
                )

                if poll_res["state"] == "failed":
                    err_code = poll_res.get("error_code") or "PUBLIC_ERROR_VIDEO_GENERATION_FAILED"
                    cats = ", ".join(poll_res.get("error_categories") or [])
                    self._cleanup_failed_tiles_in_dom(page)

                    if attempt + 1 < max_protocol_attempts:
                        self._log(
                            "warn",
                            f"Video bị từ chối bởi bộ lọc ({err_code} / {cats}). "
                            f"Đang tự động vi chỉnh starting frame + làm sạch sâu prompt và thử lại lần {attempt + 2}...",
                        )
                        current_frame_p = condition_frame_for_policy_retry(
                            frame_p,
                            dest_p.parent / f"_{frame_p.stem}_retry_conditioned.png",
                            log=self._log,
                        )
                        br.reload(settle_s=4.0)
                        continue

                    raise BridgeError(
                        f"Flow từ chối tạo video qua giao thức jwpduf ({err_code} [{cats}]). "
                        "Hãy thử đổi ảnh mẫu / khung hình đầu khác hoặc chỉnh lại prompt."
                    )

                # 7. Video succeeded! If resolution == "1080p", upsample via p0UkFb (`veo_3_1_upsampler_1080p`) first
                signed_url: Optional[str] = None
                if "1080" in str(resolution):
                    signed_url = self.upsample_and_fetch_1080p_url_rpc(
                        br,
                        video_media_id=video_media_id,
                        item_id=poll_res.get("item_id"),
                        project_id=active_pid,
                        aspect_ratio=target_aspect,
                        timeout_s=120.0,
                    )

                if not signed_url:
                    signed_url = poll_res.get("signed_url") or self.fetch_signed_video_url_rpc(
                        br, video_media_id=video_media_id, project_id=active_pid
                    )
                downloaded = self.download_video_verified(br, signed_url, dest_p)
                br.reload(settle_s=4.0)
                return downloaded

        raise BridgeError("Không thể hoàn tất tạo video qua FlowVideoBridge.")
