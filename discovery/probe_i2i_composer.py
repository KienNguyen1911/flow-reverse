"""Discovery probe: i2i composer affordances on the live Flow tab (0 credit).

Read-only DOM inspection over CDP — attaches to the existing flow.google.com
tab, runs ``FlowBridge.composer_probe()`` and prints the result. Nothing is
clicked, typed, attached or navigated *unless* ``--project <uuid>`` is given
(then an SPA navigation to that project happens first, like a normal job does).

Usage:
    python discovery/probe_i2i_composer.py                  # probe current tab
    python discovery/probe_i2i_composer.py --project <uuid> # probe inside a project

Findings feed ``docs/api_specs/flow_image2image.md`` (template-replay i2i).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.Bridge.flow_bridge import DEFAULT_CDP_URL, FlowBridge  # noqa: E402

BUTTONS_JS = (
    "(() => { const out = []; "
    "for (const b of Array.from(document.querySelectorAll('button'))) { "
    "  const aria = String(b.getAttribute('aria-label') || '').trim(); "
    "  const text = String(b.textContent || '').trim().slice(0, 40); "
    "  const t = (aria + (aria && text ? ' | ' : '') + text).trim(); "
    "  if (t) out.push(t); } "
    "return out.slice(0, 60); })()"
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Probe composer i2i affordances (read-only, 0 credit)")
    ap.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    ap.add_argument("--project", default=None, help="UUID dự án — nếu có sẽ SPA-nav vào dự án trước khi probe")
    ap.add_argument("--fresh", action="store_true", help="Full-navigate về flow.google.com trước khi probe (reset SPA kẹt)")
    args = ap.parse_args(argv)

    with FlowBridge(args.cdp_url) as br:
        print(f"attached: {br.page.url}")
        if args.fresh:
            print("full-navigate về https://flow.google.com/ (reset SPA)…")
            br.page.goto("https://flow.google.com/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(6.0)
            print(f"now at: {br.page.url}")
        if args.project:
            print(f"SPA-nav vào project {args.project[:8]}… (giống job thường)")
            br.nav_home()
            br.nav_project(args.project)
            try:
                pos = br.wait_composer(timeout_s=40.0)
                print(f"composer render OK (ProseMirror @ {pos})")
            except Exception as exc:  # noqa: BLE001
                print(f"composer chưa render sau 40s: {exc}")
        probe = br.composer_probe()
        print("composer_probe:")
        print(json.dumps(probe, ensure_ascii=False, indent=1))
        buttons = br.eval_json(BUTTONS_JS) or []
        print(f"buttons ({len(buttons)}):")
        for t in buttons:
            print("  -", t)
        fi = probe.get("file_inputs") or []
        if fi:
            print(f"OK: {len(fi)} file input(s) — attach_reference có thể hoạt động.")
        else:
            print(
                "CẢNH BÁO: không thấy <input type=file> trên trang hiện tại.\n"
                "  → thử --project <uuid> (composer chỉ xuất hiện trong trang dự án).\n"
                "  → nếu trong dự án vẫn không có: cập nhật selector trong flow_bridge.attach_reference\n"
                "    (xem docs/api_specs/flow_image2image.md §Discovery)."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
