"""Decode Google batchexecute traffic from a raw JSONL trace (produced by sniffer.py).

Two wire formats are handled:

Request (POST body, form-encoded):
    f.req=<urlencoded JSON>&at=<xsrf token>&
    f.req decodes to [[[rpcid, "<args as JSON string>", null, "generic"], ...]].
    Each call's inner args string is JSON-decoded when possible.

Response body (chunked, XSSI-prefixed):
    )]}'
    <length>
    [[\"wrb.fr\", \"<rpcid>\", \"<result as JSON string>\", ...], [\"di\", ...], ...]
    <length>
    [[\"e\", 4, null, null, <body bytes>]]
    The `wrb.fr` rows carry the per-rpc results; the `e` row is the framing footer.
    Length-prefixed chunks are split with a tolerant parser (malformed rows are
    surfaced as {"__raw__": ...} instead of raising).

Usage:
    python discovery/decode_batchexecute.py traces/raw_trace_<UTC>.jsonl
    python discovery/decode_batchexecute.py traces/raw_trace_<UTC>.jsonl --out-dir traces/decoded

Output: one `<stem>__<kind>_<ts>__<rpcid>.json` file per decoded event plus a
stdout summary table. Read-only with respect to the trace file.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path


def decode_request(body: str) -> dict:
    """Decode a batchexecute form body into {'form': {...}, 'rpcs': [...]}."""
    qs = urllib.parse.parse_qs(body, keep_blank_values=True)
    out: dict = {"form": {k: (v[0] if k != "f.req" else "<f.req>") for k, v in qs.items()}}
    if "f.req" in qs:
        try:
            outer = json.loads(qs["f.req"][0])
            rpcs = []
            for batch in outer:
                for call in batch:
                    rpcid = call[0]
                    args_raw = call[1]
                    try:
                        args = json.loads(args_raw)
                    except (TypeError, json.JSONDecodeError):
                        args = args_raw
                    rpcs.append({"rpcid": rpcid, "args": args})
            out["rpcs"] = rpcs
        except (ValueError, IndexError) as exc:
            out["f_req_error"] = repr(exc)
            out["f_req_raw"] = qs["f.req"][0][:4000]
    return out


def decode_response(body: str) -> dict:
    """Decode a batchexecute response body into {'rpcs': [...], 'raw_tail': ...}."""
    text = body
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    chunks = []
    for line in text.split("\n"):
        ls = line.strip()
        if not ls or ls.isdigit():
            continue  # length markers
        try:
            chunks.append(json.loads(ls))
        except json.JSONDecodeError:
            chunks.append({"__raw__": ls[:800]})
    rpcs = []
    for data in chunks:
        if not isinstance(data, list):
            continue
        for item in data:
            if isinstance(item, list) and len(item) >= 3 and item[0] == "wrb.fr":
                payload = item[2]
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except json.JSONDecodeError:
                        pass
                rpcs.append({"rpcid": item[1], "result": payload})
    return {"rpcs": rpcs, "raw_tail": chunks[-1] if chunks else None}


def rpcid_of(url: str) -> str:
    if "rpcids=" not in url:
        return "unknown"
    return url.split("rpcids=", 1)[1].split("&", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("trace", help="Path to raw_trace_<UTC>.jsonl")
    parser.add_argument("--out-dir", default="traces/decoded", help="Directory for decoded JSON files")
    args = parser.parse_args()

    trace = Path(args.trace)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = trace.stem

    counts = {"request": 0, "response": 0}
    summary = []
    for line in trace.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        event = json.loads(line)
        url = event.get("url") or ""
        if "batchexecute" not in url:
            continue
        kind = event.get("kind")
        if kind not in ("request", "response"):
            continue
        body = event.get("req_body") if kind == "request" else event.get("resp_body")
        if not body:
            continue
        decoded = decode_request(body) if kind == "request" else decode_response(body)
        counts[kind] += 1
        rpcid = rpcid_of(url)
        decoded.update(
            {
                "ts_ms": event.get("ts_ms"),
                "status": event.get("status"),
                "rpcid": rpcid,
                "url": url,
            }
        )
        fname = f"{stem}__{kind}_{round(event['ts_ms'])}__{rpcid}.json"
        (out_dir / fname).write_text(json.dumps(decoded, ensure_ascii=False, indent=1), encoding="utf-8")
        summary.append((round(event["ts_ms"]), kind, rpcid, fname))

    print(f"decoded {counts['request']} requests, {counts['response']} responses -> {out_dir}")
    for ts, kind, rpcid, fname in sorted(summary):
        print(f"  {ts}  {kind:<8} {rpcid:<8} {fname}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
