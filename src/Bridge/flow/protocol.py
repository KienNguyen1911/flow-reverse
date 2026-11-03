"""Pure (no I/O) batchexecute protocol helpers: data carriers, envelope parsing, URL building."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qs, unquote_plus

from .common import TokenParseError

# --------------------------------------------------------------------------- #
# Small data carriers
# --------------------------------------------------------------------------- #

@dataclass
class AppCapture:
    url: str
    body: str
    ts_ms: int
    via: str


@dataclass
class FireResult:
    status: int
    text: str
    elapsed_ms: int
    fire_ts_ms: int


@dataclass
class SessionCtx:
    """Fresh page-session params for firing arbitrary batchexecute RPCs."""
    at: str
    f_sid: str
    bl: str
    hl: str
    reqid: int
    url_template: str  # a real batchexecute URL captured from the app (perf entry)


# --------------------------------------------------------------------------- #
# Envelope parsing / URL building (pure functions)
# --------------------------------------------------------------------------- #

def parse_app_capture(body: str) -> tuple[str, str]:
    """Extract (recaptcha_token, at_param) from the captured app ogiZ0b body."""
    token = ""
    at_param = ""
    try:
        qs = parse_qs(body, keep_blank_values=True)
        obj = json.loads(qs.get("f.req", [""])[0])
        app_args = json.loads(obj[0][0][1])
        token = app_args[1][0][7][10][0]
        at_param = qs.get("at", [""])[0]
    except Exception:
        pass
    if not token:
        m = re.search(r"0cAFcWeA[A-Za-z0-9_\-]{400,}", body)
        token = m.group(0) if m else ""
    if not at_param:
        m = re.search(r"(?:^|&)at=([^&]+)", body)
        at_param = unquote_plus(m.group(1)) if m else ""
    if not (len(token) > 2000 and token.startswith("0cAFcWeA")):
        raise TokenParseError(f"reCAPTCHA token sanity failed (len={len(token)})")
    if len(at_param) < 10:
        raise TokenParseError("at param missing in captured app body")
    return token, at_param


def extract_app_reqid(url: str) -> Optional[int]:
    m = re.search(r"([?&]_reqid=)(\d+)", url or "")
    return int(m.group(2)) if m else None


def parse_captured_args(body: str) -> list:
    """Extract the raw args JSON (``f.req[0][0][1]``) from a captured ogiZ0b body."""
    qs = parse_qs(body, keep_blank_values=True)
    obj = json.loads(qs.get("f.req", ["[]"])[0])
    return json.loads(obj[0][0][1])


def build_capture_fire_url(captured_url: str, new_reqid: int) -> str:
    """Replace _reqid in the app's own (captured) ogiZ0b URL — proven in R2."""
    if re.search(r"([?&]_reqid=)\d+", captured_url):
        return re.sub(r"([?&]_reqid=)\d+", lambda m: m.group(1) + str(new_reqid), captured_url)
    return captured_url + ("&" if "?" in captured_url else "?") + "_reqid=" + str(new_reqid)


def build_rpc_url_from_template(template_url: str, rpcid: str, new_reqid: int) -> str:
    """Reuse a real batchexecute URL (bl/f.sid/hl/source-path) for another RPC."""
    url = template_url or ""
    if re.search(r"([?&]rpcids=)[^&]*", url):
        url = re.sub(r"([?&]rpcids=)[^&]*", lambda m: m.group(1) + rpcid, url)
    else:
        url += ("&" if "?" in url else "?") + "rpcids=" + rpcid
    if re.search(r"([?&]_reqid=)\d+", url):
        url = re.sub(r"([?&]_reqid=)\d+", lambda m: m.group(1) + str(new_reqid), url)
    else:
        url += "&_reqid=" + str(new_reqid)
    return url


def parse_batchexecute_text(txt: str) -> dict:
    """Two-layer JSON decode of a batchexecute response body.

    Returns {ok, data, reason, detail, grpc_code}.
    Success: frame `[["wrb.fr", id, <payload-json>, ...]]` -> arr[0][2] -> json.
    Failure: payload null, frame col 5 carries the gRPC canonical status
             (`[3]` INVALID_ARGUMENT, `[7, ...ErrorInfo]` PERMISSION_DENIED, ...).
    """
    payload = None
    for line in (txt or "").splitlines():
        ls = line.strip()
        if ls.startswith('[["wrb.fr"'):
            payload = ls
            break
    if payload is None:
        return {"ok": False, "reason": "no_wrbfr_payload"}
    try:
        arr = json.loads(payload)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"payload_json_error: {e!r}"}
    if not arr or not isinstance(arr[0], list):
        return {"ok": False, "reason": "unexpected_payload_shape"}
    row = arr[0]
    if len(row) >= 3 and row[2]:
        try:
            return {"ok": True, "data": json.loads(row[2])}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "reason": f"inner_json_error: {e!r}"}
    detail = row[5] if len(row) > 5 else row
    grpc_code = None
    if isinstance(detail, list) and detail and isinstance(detail[0], int):
        grpc_code = detail[0]
    return {
        "ok": False,
        "reason": "rpc_error",
        "detail": json.dumps(detail, ensure_ascii=False)[:1200],
        "grpc_code": grpc_code,
    }


def find_signed_urls(obj: Any) -> list[str]:
    """Recursively collect signed CDN URLs (prefix walk — never regex: `\\u003d` trap)."""
    acc: list[str] = []

    def walk(o: Any) -> None:
        if isinstance(o, str):
            if o.startswith("https://flow-content.google/image/"):
                acc.append(o)
        elif isinstance(o, list):
            for x in o:
                walk(x)
        elif isinstance(o, dict):
            for x in o.values():
                walk(x)

    walk(obj)
    out = list(dict.fromkeys(acc))
    return out


def describe_reject(grpc_code: Optional[int], detail: str) -> tuple[str, str]:
    """Map a gRPC rejection to (short kind, human hint, VI)."""
    detail_str = str(detail or "")
    if "PUBLIC_ERROR_PROMINENT_PEOPLE" in detail_str or "PROMINENT_PERSON" in detail_str:
        return (
            "PROMINENT_PEOPLE_FILTER",
            "Bị bộ lọc nhận diện người nổi tiếng của Google Flow từ chối (PUBLIC_ERROR_PROMINENT_PEOPLE_FILTER). Khuôn mặt trong ảnh bắt đầu hoặc prompt giống người nổi tiếng. Hãy thử đổi ảnh mẫu khác hoặc che bớt chi tiết khuôn mặt.",
        )
    if "PUBLIC_ERROR_UNSAFE_GENERATION" in detail_str:
        return (
            "UNSAFE_GENERATION",
            "Nội dung bị bộ lọc an toàn (Safety Filter / NSFW) của Google từ chối do prompt hoặc ảnh chứa chi tiết nhạy cảm (ví dụ: 'deep V-neckline', 'underbust'...). Hãy điều chỉnh lại prompt mô tả trang phục kín đáo hơn. Không mất credit.",
        )
    if "PUBLIC_ERROR_UNUSUAL_ACTIVITY" in detail_str or grpc_code == 7:
        return (
            "PERMISSION_DENIED",
            "Bị hệ thống chống lạm dụng từ chối (PUBLIC_ERROR_UNUSUAL_ACTIVITY). Không mất credit; nên chờ vài phút rồi thử lại.",
        )
    if grpc_code == 3:
        return (
            "INVALID_ARGUMENT",
            f"Tham số không hợp lệ từ Google: {detail_str[:120] if detail_str else 'kiểm tra lại prompt/aspect'}. Không mất credit.",
        )
    if grpc_code == 16:
        return ("UNAUTHENTICATED", "Phiên đăng nhập có vấn đề. Kiểm tra lại tab Flow trong browser.")
    return (f"RPC_ERROR[{grpc_code}]", detail_str[:280] if detail_str else "Lỗi RPC không rõ nguyên nhân.")
