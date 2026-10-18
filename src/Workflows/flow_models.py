"""Pydantic DTOs + request builders for the Flow client (docs/api_specs/*).

Everything here is pure (no I/O) — ported from the validated Phase-4 recipe:

Image (ogiZ0b), proven E8/R2:
    ref  = [None, 22, None, None, None, project_id, None, None, None, None, [token, 1]]
    spec = [None, None, None, seed, aspect, "BELUGA", None, ref, [[[prompt]]], None, None, None, u1, u2]
    args = [None, [spec], 1, ref, [gen]]          # u1, u2, gen = uuid4().upper()

Project (jHPbke), proven Phase 4:
    args = ["projects/*", [None, [title]], [None, 22]]

Constraints (spec §7.5.2):
    - seed MUST fit signed int32: randint(1, 2147483647)
    - UUIDs uppercase; _reqid = app_reqid + 100000; fire within ~100 ms
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, Field

from ..Bridge.flow_bridge import SEED_MAX, enc, new_seed

IMAGE_MODEL_KEY = "BELUGA"  # Nano Banana image tool key observed in requests
IMAGE_TOOL_ID = 22          # tool id used in ref[1] and jHPbke args
ASPECT_DEFAULT = 3          # verified value (16:9)

# --------------------------------------------------------------------------- #
# DTOs
# --------------------------------------------------------------------------- #


class ProjectInfo(BaseModel):
    id: str
    title: Optional[str] = None
    source: Literal["manual", "created", "listed"] = "manual"
    last_used_ts: Optional[int] = None


class CapturedRequestInfo(BaseModel):
    url: str
    ts_ms: int
    via: str
    body_len: int
    token_len: int
    at_len: int
    app_reqid: Optional[int] = None


class GeneratedImage(BaseModel):
    """Result image metadata (echoed fields prove parameter control)."""

    media_id: Optional[str] = None
    item_id: Optional[str] = None
    generation_id: Optional[str] = None          # ours (uppercase UUID)
    generation_id_echo: Optional[str] = None     # server echo -> match proves ownership
    seed: Optional[int] = None                   # ours
    seed_echo: Optional[int] = None              # server echo
    prompt: Optional[str] = None
    title: Optional[str] = None
    resolution: Optional[list[int]] = None       # e.g. [1376, 768]
    width: Optional[int] = None
    height: Optional[int] = None
    signed_url: Optional[str] = None
    project_id: Optional[str] = None
    file_path: Optional[str] = None
    file_bytes: Optional[int] = None
    media_id_echo: Optional[str] = None


class GenerationResult(BaseModel):
    status: Literal["ok", "rejected", "dry_run", "failed", "ok_no_download"]
    image: Optional[GeneratedImage] = None
    reason: Optional[str] = None          # reject kind / failure kind
    hint: Optional[str] = None            # human explanation (VI)
    detail: Optional[str] = None          # raw server detail (JSON string, truncated)
    grpc_code: Optional[int] = None
    elapsed_s: Optional[float] = None
    run_dir: Optional[str] = None
    seed_used: Optional[int] = None
    anti_abuse: bool = False              # grpc 7 PERMISSION_DENIED (retryable per policy)
    credit_note: str = "~1 credit nếu Google nhận; 0 credit nếu bị từ chối"


class BridgeStatus(BaseModel):
    cdp_url: str
    cdp_ok: bool = False
    browser: Optional[str] = None
    flow_tab_url: Optional[str] = None
    flow_project_id: Optional[str] = None
    page_targets: int = 0
    cooldown_until_ms: int = 0
    cooldown_reason: Optional[str] = None
    error: Optional[str] = None


class ReferenceTemplate(BaseModel):
    """i2i reference captured from the app itself (template-replay bridge mode).

    Google Flow's image2image upload RPC is NOT reverse-engineered; instead the
    app performs the upload when we attach the file in its composer, and we
    capture the app's own blocked ogiZ0b request as a reusable arg template.
    At fire time only ``token`` (fresh capture), ``seed``, ``prompt`` and the
    tracking UUIDs are substituted — the media reference is the app's own.

    Cache: ``configs/reference_media_cache.json`` keyed by account + file sha256
    (media ids are per-account, see plan §2 — sticky reference affinity).
    """

    sha256: str
    project_id: str
    prompt: str = ""                          # prompt typed while capturing (leaf substitution)
    media_id: Optional[str] = None            # best-effort (first UUID candidate)
    candidates: list[str] = Field(default_factory=list)
    template_args: list = Field(default_factory=list)
    source_path: Optional[str] = None
    captured_ts: Optional[int] = None         # epoch ms
    version: int = 1


# --------------------------------------------------------------------------- #
# Builders (pure)
# --------------------------------------------------------------------------- #

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_PROJECT_URL_RE = re.compile(r"/project/([0-9a-fA-F-]{36})")


def validate_seed(seed: int) -> int:
    seed = int(seed)
    if not (1 <= seed <= SEED_MAX):
        raise ValueError(f"seed must fit signed int32: 1..{SEED_MAX} (got {seed}); "
                         "seeds above that get [3] INVALID_ARGUMENT (0 credit).")
    return seed


def parse_project_ref(value: str) -> str:
    """Accept a bare UUID or any Flow URL containing /project/<uuid>."""
    v = (value or "").strip()
    m = _PROJECT_URL_RE.search(v)
    if m:
        v = m.group(1)
    if not UUID_RE.match(v):
        raise ValueError(f"Không phải UUID project hợp lệ: {value!r}")
    return v.lower()


def new_uuids() -> tuple[str, str, str]:
    return (str(uuid.uuid4()).upper(), str(uuid.uuid4()).upper(), str(uuid.uuid4()).upper())


def build_image_args(
    project_id: str,
    prompt: str,
    recaptcha_token: str,
    seed: int,
    aspect: int = ASPECT_DEFAULT,
    u1: Optional[str] = None,
    u2: Optional[str] = None,
    gen_id: Optional[str] = None,
) -> list:
    """Assemble the full ogiZ0b args (E8-validated layout)."""
    u1 = u1 or str(uuid.uuid4()).upper()
    u2 = u2 or str(uuid.uuid4()).upper()
    gen_id = gen_id or str(uuid.uuid4()).upper()
    ref = [None, IMAGE_TOOL_ID, None, None, None, project_id, None, None, None, None, [recaptcha_token, 1]]
    spec = [None, None, None, int(seed), int(aspect), IMAGE_MODEL_KEY, None, ref, [[[prompt]]], None, None, None, u1, u2]
    return [None, [spec], 1, ref, [gen_id]]


def build_create_project_args(title: str) -> list:
    return ["projects/*", [None, [title]], [None, IMAGE_TOOL_ID]]


def build_uptedb_args() -> list:
    """UpteDb = list projects (Observed, docs/api_specs/flow_create_project.md §6)."""
    return ["projects/*", 21, None, None, None, None, [1]]


# --------------------------------------------------------------------------- #
# i2i template replay (pure helpers; layout captured from the app, never guessed)
# --------------------------------------------------------------------------- #

# The exact ref shape of a validated text2image ogiZ0b request (see module doc).
# If a capture's ref (masked) equals this baseline, NO reference image attached.
T2I_REF_BASELINE = [None, IMAGE_TOOL_ID, None, None, None, "<project>", None, None, None, None, ["<token>", 1]]

_TOKEN_RE = re.compile(r"^0cAFcWeA[A-Za-z0-9_\-]{400,}$")


def _apply_repl(leaf: Any, repl: Any) -> Any:
    return repl(leaf) if callable(repl) else repl


def _walk_replace(obj: Any, pred, repl: Any) -> int:
    """In-place recursive leaf replacement (list/dict), returns replacements."""
    n = 0
    if isinstance(obj, list):
        for i, x in enumerate(obj):
            if isinstance(x, (list, dict)):
                n += _walk_replace(x, pred, repl)
            elif pred(x):
                obj[i] = _apply_repl(x, repl)
                n += 1
    elif isinstance(obj, dict):
        for k, x in obj.items():
            if isinstance(x, (list, dict)):
                n += _walk_replace(x, pred, repl)
            elif pred(x):
                obj[k] = _apply_repl(x, repl)
                n += 1
    return n


def _mask_ref_inplace(ref: Any) -> Any:
    if not isinstance(ref, list):
        return ref
    if len(ref) > 5:
        ref[5] = "<project>"
    if len(ref) > 10 and isinstance(ref[10], list) and ref[10]:
        ref[10][0] = "<token>"
    return ref


def captured_args_has_reference(args: Any) -> Optional[bool]:
    """Does a captured ogiZ0b args payload carry a reference image?

    Returns False when the (masked) ref equals the known t2i baseline — i.e.
    the attach did not land and the app sent a plain text2image request.
    Returns None when the structure is unrecognizable (caller continues).
    """
    try:
        ref = args[1][0][7]
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(ref, list):
        return None
    masked = _mask_ref_inplace(copy.deepcopy(ref))
    base = _mask_ref_inplace(copy.deepcopy(T2I_REF_BASELINE))
    if masked == base:
        return False
    if len(masked) == len(base):
        return True
    return None


def mask_template_token(args: list) -> list:
    """Deep-copy args and blank the reCAPTCHA token slot (templates stay small)."""
    out = copy.deepcopy(args)
    try:
        ref = out[1][0][7]
        if isinstance(ref, list) and len(ref) > 10 and isinstance(ref[10], list) and ref[10]:
            if isinstance(ref[10][0], str):
                ref[10][0] = ""
                return out
    except Exception:  # noqa: BLE001
        pass
    n = _walk_replace(out, lambda s: isinstance(s, str) and bool(_TOKEN_RE.match(s)), "")
    if not n:
        return copy.deepcopy(args)  # unrecognizable token slot → keep original capture
    return out


def find_uuid_candidates(args: Any, exclude: Iterable[str] = ()) -> list[str]:
    """Best-effort UUID strings in captured args (reference media ids)."""
    seen: dict[str, None] = {}
    ex = {e.lower() for e in exclude if e}

    def walk(o: Any) -> None:
        if isinstance(o, str):
            if UUID_RE.match(o) and o.lower() not in ex:
                seen.setdefault(o.lower(), None)
        elif isinstance(o, list):
            for x in o:
                walk(x)
        elif isinstance(o, dict):
            for x in o.values():
                walk(x)

    walk(args)
    return list(seen)


def build_args_from_template(
    template_args: list,
    *,
    token: str,
    seed: int,
    prompt: str = "",
    old_prompt: str = "",
    u1: Optional[str] = None,
    u2: Optional[str] = None,
    gen_id: Optional[str] = None,
) -> tuple[list, dict]:
    """Replay an app-captured i2i template with fresh token/seed/prompt/UUIDs.

    The reference media slot(s) stay exactly as the app wrote them — that is
    the whole point of template replay (no guessed upload protocol).
    """
    args = copy.deepcopy(template_args)
    replaced = {"token": False, "seed": False, "prompt": 0, "uuids": 0}

    # 1) reCAPTCHA token — canonical ref[10][0], token-leaf fallback.
    try:
        ref = args[1][0][7]
        if isinstance(ref, list) and len(ref) > 10 and isinstance(ref[10], list) and ref[10]:
            ref[10][0] = token
            replaced["token"] = True
    except Exception:  # noqa: BLE001
        pass
    if not replaced["token"]:
        replaced["token"] = _walk_replace(
            args, lambda s: isinstance(s, str) and bool(_TOKEN_RE.match(s)), token
        ) > 0
    if not replaced["token"]:
        raise ValueError("Template i2i: không tìm thấy chỗ điền token — hãy capture lại template.")

    # 2) seed — canonical spec[3] (same spec layout as t2i).
    try:
        spec = args[1][0]
        if isinstance(spec[3], int) and not isinstance(spec[3], bool):
            spec[3] = int(seed)
            replaced["seed"] = True
    except Exception:  # noqa: BLE001
        pass

    # 3) prompt — leaf substring replace (the app nests it, e.g. [[[prompt]]]).
    if old_prompt and prompt and old_prompt != prompt:
        replaced["prompt"] = _walk_replace(
            args,
            lambda s: isinstance(s, str) and old_prompt in s,
            lambda s: s.replace(old_prompt, prompt),
        )
        if not replaced["prompt"]:
            raise ValueError("Template i2i: prompt cũ không thấy trong args — hãy capture lại template.")

    # 4) tracking UUIDs (best-effort; template values would also work).
    try:
        spec = args[1][0]
        if u1:
            spec[12] = u1
            replaced["uuids"] += 1
        if u2:
            spec[13] = u2
            replaced["uuids"] += 1
    except Exception:  # noqa: BLE001
        pass
    try:
        if gen_id and isinstance(args[4], list) and args[4]:
            args[4][0] = gen_id
            replaced["uuids"] += 1
    except Exception:  # noqa: BLE001
        pass

    return args, replaced


def encode_batchexecute_form(rpcid: str, args: list, at_param: str) -> str:
    """Form body exactly as the app sends: f.req=<enc>&at=<enc>& (E8 byte-identical)."""
    args_json = json.dumps(args, separators=(",", ":"), ensure_ascii=False)
    f_req = json.dumps([[[rpcid, args_json, None, "generic"]]], separators=(",", ":"), ensure_ascii=False)
    return "f.req=" + enc(f_req) + "&at=" + enc(at_param) + "&"


def parse_uptedb_projects(data: Any) -> list[ProjectInfo]:
    """Defensively parse an UpteDb payload into ProjectInfo list (any nesting depth)."""
    out: list[ProjectInfo] = []
    seen: set[str] = set()

    def walk(o: Any) -> None:
        if not isinstance(o, list):
            return
        if len(o) >= 2 and isinstance(o[0], str) and UUID_RE.match(o[0]) and isinstance(o[1], list):
            pid = o[0].lower()
            if pid not in seen:
                seen.add(pid)
                title = o[1][0] if o[1] and isinstance(o[1][0], str) else None
                out.append(ProjectInfo(id=pid, title=title, source="listed"))
            return
        for x in o:
            walk(x)

    walk(data)
    return out


def generate_seed() -> int:
    return new_seed()


# Re-export for callers that prefer importing from models
__all__ = [
    "ProjectInfo", "CapturedRequestInfo", "GeneratedImage", "GenerationResult", "BridgeStatus",
    "ReferenceTemplate",
    "build_image_args", "build_create_project_args", "build_uptedb_args",
    "encode_batchexecute_form", "parse_uptedb_projects", "parse_project_ref",
    "validate_seed", "new_uuids", "generate_seed", "IMAGE_TOOL_ID", "IMAGE_MODEL_KEY", "ASPECT_DEFAULT",
    "captured_args_has_reference", "mask_template_token", "find_uuid_candidates", "build_args_from_template",
]
