"""Differential analysis between two sniffer traces (JSONL from sniffer.py).

Pairs request/response events of trace A and trace B by (method, url) - first
match wins per side - then reports exactly what changed between the two
observed payloads:

    * JSON bodies      -> deep diff: every changed/added/removed JSON path with
                          the value from trace A vs trace B.
    * binary/protobuf  -> size + content-type + first differing byte offset +
                          ~100-byte hex preview from that offset.
    * headers          -> per-key diff (a vs b).
    * endpoints without a counterpart are listed explicitly (only-in-A,
      only-in-B, extra repeated instances).

Only the standard library is used (json, argparse, base64).

Usage:
    python discovery/payload_differ.py traces/a.jsonl traces/b.jsonl \
        [--url-contains /v1/projects] [--out report.json]

Stdout gets the human-readable report; ``--out`` additionally writes the full
machine-readable report as JSON.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PREVIEW_BYTES = 100  # hex preview size for binary diffs
CLIP_VALUE = 400  # max chars per printed/JSON-encoded scalar value
MAX_PRINTED_DIFF_ROWS = 40  # stdout stays readable; the JSON report is complete

EndpointKey = tuple[str, str]


# --------------------------------------------------------------------- loading
def load_events(path: Path, url_filter: Optional[str]) -> tuple[list[dict[str, Any]], int]:
    """Read a JSONL trace; returns (events, malformed_line_count)."""
    events: list[dict[str, Any]] = []
    bad = 0
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if url_filter and url_filter not in str(event.get("url") or ""):
            continue
        events.append(event)
    return events, bad


def endpoint_key(event: dict[str, Any]) -> EndpointKey:
    return (str(event.get("method") or "").upper(), str(event.get("url") or ""))


def index_trace(events: list[dict[str, Any]]) -> tuple[dict[EndpointKey, list[dict]], dict[EndpointKey, list[dict]]]:
    """Index request/response events by (method, url), preserving arrival order."""
    requests: dict[EndpointKey, list[dict]] = {}
    responses: dict[EndpointKey, list[dict]] = {}
    for event in events:
        kind = event.get("kind")
        if kind == "request":
            requests.setdefault(endpoint_key(event), []).append(event)
        elif kind == "response":
            responses.setdefault(endpoint_key(event), []).append(event)
    return requests, responses


# ----------------------------------------------------------------- diff utils
def clip_value(value: Any, limit: int = CLIP_VALUE) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"...<+{len(value) - limit} chars>"
    return value


def json_one(value: Any) -> str:
    return json.dumps(clip_value(value), ensure_ascii=False)


def deep_json_diff(a: Any, b: Any, path: str = "root") -> list[dict[str, Any]]:
    """Recursively compare two decoded JSON values and list every difference."""
    out: list[dict[str, Any]] = []

    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            child = f"{path}.{key}"
            if key not in a:
                out.append({"path": child, "op": "added", "a": None, "b": clip_value(b[key])})
            elif key not in b:
                out.append({"path": child, "op": "removed", "a": clip_value(a[key]), "b": None})
            else:
                out.extend(deep_json_diff(a[key], b[key], child))
        return out

    if isinstance(a, list) and isinstance(b, list):
        common = min(len(a), len(b))
        for i in range(common):
            out.extend(deep_json_diff(a[i], b[i], f"{path}[{i}]"))
        for i in range(common, len(a)):
            out.append({"path": f"{path}[{i}]", "op": "removed", "a": clip_value(a[i]), "b": None})
        for i in range(common, len(b)):
            out.append({"path": f"{path}[{i}]", "op": "added", "a": None, "b": clip_value(b[i])})
        return out

    # Scalars and type changes (bool vs int counts as a change on purpose).
    if type(a) is not type(b) or a != b:
        out.append({"path": path, "op": "changed", "a": clip_value(a), "b": clip_value(b)})
    return out


def _try_json(data: Optional[bytes]) -> Any:
    if data is None:
        return None
    try:
        return json.loads(data.decode("utf-8-sig"))
    except Exception:  # noqa: BLE001 - not JSON (binary/protobuf/text)
        return None


def _preview_text(data: bytes, offset: int, size: int = PREVIEW_BYTES) -> Optional[str]:
    """Text preview from ``offset`` - only when the whole body is valid UTF-8."""
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return data[offset : offset + size].decode("utf-8", errors="replace")


def binary_diff(a: bytes, b: bytes) -> dict[str, Any]:
    """Byte-level diff: sizes, first differing offset, hex (+text) previews."""
    common = min(len(a), len(b))
    offset: Optional[int] = next((i for i in range(common) if a[i] != b[i]), None)
    if offset is None and len(a) != len(b):
        offset = common  # one body is a prefix of the other
    info: dict[str, Any] = {"equal": offset is None, "size_a": len(a), "size_b": len(b), "first_diff_offset": offset}
    if offset is not None:
        info["preview_a_hex"] = a[offset : offset + PREVIEW_BYTES].hex()
        info["preview_b_hex"] = b[offset : offset + PREVIEW_BYTES].hex()
        text_a = _preview_text(a, offset)
        text_b = _preview_text(b, offset)
        if text_a is not None and text_b is not None:
            info["preview_a_text"] = text_a
            info["preview_b_text"] = text_b
    return info


def decode_body(event: dict[str, Any]) -> tuple[Optional[bytes], dict[str, Any]]:
    """Return (raw bytes, meta) for the body carried by a sniffer event.

    Body field mapping: requests -> req_body, responses -> resp_body, ws_frame
    "sent" -> req_body, ws_frame "received" -> resp_body.
    """
    kind = event.get("kind")
    if kind == "request":
        field = "req_body"
    elif kind == "response":
        field = "resp_body"
    elif kind == "ws_frame":
        field = "req_body" if event.get("frame_direction") == "sent" else "resp_body"
    else:
        return None, {}
    raw = event.get(field)
    meta: dict[str, Any] = {
        "truncated": bool(event.get("truncated")),
        "body_error": event.get("body_error"),
    }
    if raw is None:
        return None, meta
    if event.get("encoding") == "base64":
        try:
            return base64.b64decode(raw), meta
        except Exception as exc:  # noqa: BLE001
            meta["decode_error"] = f"base64 decode failed: {exc}"
            return None, meta
    return str(raw).encode("utf-8"), meta


def content_type_of(event: dict[str, Any]) -> Optional[str]:
    headers = event.get("headers") or {}
    for key, value in headers.items():
        if str(key).lower() == "content-type":
            return str(value)
    return None


def diff_body(event_a: dict[str, Any], event_b: dict[str, Any]) -> dict[str, Any]:
    """Compare the bodies of two paired events; JSON-aware, binary fallback."""
    data_a, meta_a = decode_body(event_a)
    data_b, meta_b = decode_body(event_b)
    result: dict[str, Any] = {
        "content_type_a": content_type_of(event_a),
        "content_type_b": content_type_of(event_b),
        "size_a": None if data_a is None else len(data_a),
        "size_b": None if data_b is None else len(data_b),
    }
    for suffix, meta in (("a", meta_a), ("b", meta_b)):
        if meta.get("truncated"):
            result[f"truncated_{suffix}"] = True
        if meta.get("body_error"):
            result[f"body_error_{suffix}"] = meta["body_error"]

    if data_a is None and data_b is None:
        result["format"] = "none"
        result["changed"] = bool(meta_a.get("truncated") != meta_b.get("truncated"))
        return result
    if (data_a is None) != (data_b is None):
        result["format"] = "one-side-missing"
        result["changed"] = True
        return result

    json_a = _try_json(data_a)
    json_b = _try_json(data_b)
    if json_a is not None and json_b is not None:
        entries = deep_json_diff(json_a, json_b)
        result["format"] = "json"
        result["json_diff"] = entries
        result["changed"] = bool(entries)
        return result

    result["format"] = "binary"
    result.update(binary_diff(data_a, data_b))
    result["changed"] = not result.pop("equal")
    return result


def diff_headers(event_a: dict[str, Any], event_b: dict[str, Any]) -> dict[str, dict[str, Any]]:
    headers_a = {str(k).lower(): str(v) for k, v in (event_a.get("headers") or {}).items()}
    headers_b = {str(k).lower(): str(v) for k, v in (event_b.get("headers") or {}).items()}
    out: dict[str, dict[str, Any]] = {}
    for key in sorted(set(headers_a) | set(headers_b)):
        value_a = headers_a.get(key)
        value_b = headers_b.get(key)
        if value_a != value_b:
            out[key] = {"a": clip_value(value_a), "b": clip_value(value_b)}
    return out


# --------------------------------------------------------------- pair builder
def build_pairs(
    events_a: list[dict[str, Any]], events_b: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    requests_a, responses_a = index_trace(events_a)
    requests_b, responses_b = index_trace(events_b)

    pairs: list[dict[str, Any]] = []
    only_in_a: list[dict[str, Any]] = []
    only_in_b: list[dict[str, Any]] = []
    extra_in_a: list[dict[str, Any]] = []
    extra_in_b: list[dict[str, Any]] = []

    for key in sorted(set(requests_a) | set(requests_b)):
        method, url = key
        list_a = requests_a.get(key, [])
        list_b = requests_b.get(key, [])
        if list_a and not list_b:
            only_in_a.append({"method": method, "url": url, "count": len(list_a)})
            continue
        if list_b and not list_a:
            only_in_b.append({"method": method, "url": url, "count": len(list_b)})
            continue
        matched = min(len(list_a), len(list_b))
        for i in range(matched):
            resp_a_list = responses_a.get(key, [])
            resp_b_list = responses_b.get(key, [])
            pairs.append(
                {
                    "method": method,
                    "url": url,
                    "index": i,
                    "req_a": list_a[i],
                    "req_b": list_b[i],
                    "resp_a": resp_a_list[i] if i < len(resp_a_list) else None,
                    "resp_b": resp_b_list[i] if i < len(resp_b_list) else None,
                }
            )
        for i in range(matched, len(list_a)):
            extra_in_a.append({"method": method, "url": url, "index": i})
        for i in range(matched, len(list_b)):
            extra_in_b.append({"method": method, "url": url, "index": i})

    unpaired = {
        "only_in_a": only_in_a,
        "only_in_b": only_in_b,
        "extra_instances_in_a": extra_in_a,
        "extra_instances_in_b": extra_in_b,
    }
    return pairs, unpaired


def diff_request(pair: dict[str, Any]) -> dict[str, Any]:
    header_diff = diff_headers(pair["req_a"], pair["req_b"])
    body_diff = diff_body(pair["req_a"], pair["req_b"])
    return {
        "changed": bool(header_diff) or bool(body_diff.get("changed")),
        "header_diff": header_diff,
        "body": body_diff,
    }


def diff_response(pair: dict[str, Any]) -> dict[str, Any]:
    resp_a, resp_b = pair["resp_a"], pair["resp_b"]
    if resp_a is None and resp_b is None:
        return {"present": False, "changed": False}
    if (resp_a is None) != (resp_b is None):
        return {
            "present": True,
            "changed": True,
            "note": "response captured in only one trace",
            "status_a": None if resp_a is None else resp_a.get("status"),
            "status_b": None if resp_b is None else resp_b.get("status"),
        }
    header_diff = diff_headers(resp_a, resp_b)
    body_diff = diff_body(resp_a, resp_b)
    status_a, status_b = resp_a.get("status"), resp_b.get("status")
    return {
        "present": True,
        "changed": status_a != status_b or bool(header_diff) or bool(body_diff.get("changed")),
        "status_a": status_a,
        "status_b": status_b,
        "header_diff": header_diff,
        "body": body_diff,
    }


def build_report(events_a, bad_a, events_b, bad_b, trace_a: str, trace_b: str, url_filter: Optional[str]) -> dict[str, Any]:
    raw_pairs, unpaired = build_pairs(events_a, events_b)
    pairs: list[dict[str, Any]] = []
    for pair in raw_pairs:
        request_diff = diff_request(pair)
        response_diff = diff_response(pair)
        pairs.append(
            {
                "method": pair["method"],
                "url": pair["url"],
                "index": pair["index"],
                "request": request_diff,
                "response": response_diff,
                "changed": request_diff["changed"] or response_diff["changed"],
            }
        )
    counts_a = {
        "events": len(events_a),
        "requests": sum(len(v) for v in index_trace(events_a)[0].values()),
        "malformed_lines": bad_a,
    }
    counts_b = {
        "events": len(events_b),
        "requests": sum(len(v) for v in index_trace(events_b)[0].values()),
        "malformed_lines": bad_b,
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace_a": trace_a,
        "trace_b": trace_b,
        "url_contains": url_filter,
        "counts_a": counts_a,
        "counts_b": counts_b,
        "summary": {
            "pairs": len(pairs),
            "pairs_with_changes": sum(1 for p in pairs if p["changed"]),
            "only_in_a": len(unpaired["only_in_a"]),
            "only_in_b": len(unpaired["only_in_b"]),
            "extra_instances_in_a": len(unpaired["extra_instances_in_a"]),
            "extra_instances_in_b": len(unpaired["extra_instances_in_b"]),
        },
        "pairs": pairs,
        "unpaired": unpaired,
    }


# ---------------------------------------------------------------- text render
def _render_json_diff_rows(entries: list[dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    for entry in entries[:MAX_PRINTED_DIFF_ROWS]:
        op = entry.get("op")
        if op == "added":
            rows.append(f"      + {entry['path']} = {json_one(entry['b'])}")
        elif op == "removed":
            rows.append(f"      - {entry['path']} (was {json_one(entry['a'])})")
        else:
            rows.append(f"      ~ {entry['path']}: {json_one(entry['a'])}  ->  {json_one(entry['b'])}")
    if len(entries) > MAX_PRINTED_DIFF_ROWS:
        rows.append(f"      ... (+{len(entries) - MAX_PRINTED_DIFF_ROWS} more paths, see full JSON report)")
    return rows


def _render_body_diff(body: dict[str, Any], label: str) -> list[str]:
    rows = [f"    {label}:"]
    fmt = body.get("format")
    if fmt == "none":
        rows.append("      (no body captured on either side)")
        return rows
    if fmt == "one-side-missing":
        rows.append(
            f"      body present only on one side "
            f"(size_a={body.get('size_a')}, size_b={body.get('size_b')})"
        )
        return rows
    if fmt == "json":
        entries = body.get("json_diff") or []
        if not entries:
            rows.append("      identical JSON body")
        else:
            rows.append(f"      json: {len(entries)} changed path(s)")
            rows.extend(_render_json_diff_rows(entries))
        return rows

    # binary/protobuf
    rows.append(
        f"      binary: size {body.get('size_a')} -> {body.get('size_b')}"
        + (f", content-type: {body.get('content_type_a')}" if body.get("content_type_a") else "")
    )
    if body.get("changed"):
        rows.append(f"      first differing byte @ offset {body.get('first_diff_offset')}")
        rows.append(f"      A hex: {body.get('preview_a_hex')}")
        rows.append(f"      B hex: {body.get('preview_b_hex')}")
        if "preview_a_text" in body:
            rows.append(f"      A txt: {body.get('preview_a_text')!r}")
            rows.append(f"      B txt: {body.get('preview_b_text')!r}")
    else:
        rows.append("      identical bytes")
    if body.get("truncated_a") or body.get("truncated_b"):
        rows.append("      note: body was truncated by sniffer --max-body; differences beyond the cut are invisible")
    return rows


def render_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    counts_a, counts_b = report["counts_a"], report["counts_b"]
    lines.append("=== Differential analysis (payload_differ) ===")
    lines.append(f"trace A: {report['trace_a']}")
    lines.append(f"         {counts_a['events']} events, {counts_a['requests']} requests, {counts_a['malformed_lines']} malformed lines")
    lines.append(f"trace B: {report['trace_b']}")
    lines.append(f"         {counts_b['events']} events, {counts_b['requests']} requests, {counts_b['malformed_lines']} malformed lines")
    if report.get("url_contains"):
        lines.append(f"url filter: contains {report['url_contains']!r}")

    pairs = report["pairs"]
    for i, pair in enumerate(pairs, 1):
        lines.append("")
        lines.append(f"[{i}/{len(pairs)}] {pair['method']} {pair['url']}")
        request = pair["request"]
        if request["changed"]:
            lines.append("  REQUEST changed")
            for key, values in request["header_diff"].items():
                lines.append(f"    header {key}: {json_one(values['a'])} -> {json_one(values['b'])}")
            lines.extend(_render_body_diff(request["body"], "body"))
        else:
            lines.append("  REQUEST identical")
        response = pair["response"]
        if not response.get("present"):
            lines.append("  RESPONSE (not captured in either trace)")
        elif response["changed"]:
            status_note = (
                f" (status {response.get('status_a')} -> {response.get('status_b')})"
                if response.get("status_a") != response.get("status_b")
                else ""
            )
            lines.append(f"  RESPONSE changed{status_note}")
            if response.get("note"):
                lines.append(f"    note: {response['note']}")
            for key, values in (response.get("header_diff") or {}).items():
                lines.append(f"    header {key}: {json_one(values['a'])} -> {json_one(values['b'])}")
            lines.extend(_render_body_diff(response.get("body") or {"format": "none"}, "body"))
        else:
            lines.append(f"  RESPONSE identical (status {response.get('status_a')})")

    unpaired = report["unpaired"]
    lines.append("")
    lines.append("=== Unpaired endpoints ===")
    if not any(unpaired.values()):
        lines.append("(none - every endpoint paired cleanly)")
    for title, entries in (
        ("only in A (no counterpart in B)", unpaired["only_in_a"]),
        ("only in B (no counterpart in A)", unpaired["only_in_b"]),
        ("extra repeated instances in A", unpaired["extra_instances_in_a"]),
        ("extra repeated instances in B", unpaired["extra_instances_in_b"]),
    ):
        if entries:
            lines.append(f"  {title}: {len(entries)}")
            for entry in entries:
                suffix = f" #{entry['index']}" if "index" in entry else f" x{entry.get('count', 1)}"
                lines.append(f"    {entry['method']} {entry['url']}{suffix}")

    summary = report["summary"]
    lines.append("")
    lines.append(
        f"Summary: {summary['pairs']} pair(s), {summary['pairs_with_changes']} with differences | "
        f"only-in-A {summary['only_in_a']}, only-in-B {summary['only_in_b']}, "
        f"extra-A {summary['extra_instances_in_a']}, extra-B {summary['extra_instances_in_b']}"
    )
    return "\n".join(lines)


# ----------------------------------------------------------------------- main
def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diff two sniffer JSONL traces: JSON paths + binary byte diffs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("trace_a", help="First trace (baseline), e.g. traces/raw_trace_X.jsonl")
    parser.add_argument("trace_b", help="Second trace (variant)")
    parser.add_argument("--url-contains", default=None, help="Only analyse endpoints whose URL contains this substring")
    parser.add_argument("--out", default=None, help="Optional path to write the full JSON report")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass

    args = parse_args(argv)
    path_a, path_b = Path(args.trace_a), Path(args.trace_b)
    for path in (path_a, path_b):
        if not path.is_file():
            print(f"[differ] !! trace not found: {path}", file=sys.stderr)
            return 2

    events_a, bad_a = load_events(path_a, args.url_contains)
    events_b, bad_b = load_events(path_b, args.url_contains)
    report = build_report(events_a, bad_a, events_b, bad_b, str(path_a), str(path_b), args.url_contains)
    print(render_text(report))

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n[differ] full JSON report written to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
