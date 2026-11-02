"""0-credit check: drive the Flow composer exactly like a node run does.

Calls the same helpers a real node uses (``_ensure_ui_video_mode`` /
``_select_image_model``) and reads back the composer chip. It never clicks
Generate, so nothing is submitted and no credits are spent.

Usage:
    python discovery/verify_composer_drivers.py
    python discovery/verify_composer_drivers.py --project 01c4173f-...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.Bridge.flow_bridge import DEFAULT_CDP_URL, FlowBridge
from src.Bridge.flow_video_bridge import FlowVideoBridge, VIDEO_SUBMIT_RPC


def _chip(page) -> str:
    btn = page.query_selector("button.settings-trigger-button")
    txt = (btn.inner_text() if btn else "") or ""
    return " ".join(txt.split())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    ap.add_argument("--project", default=None)
    args = ap.parse_args(argv)

    vb = FlowVideoBridge(args.cdp_url)
    with FlowBridge(args.cdp_url) as br:
        page = br.page
        assert page is not None
        if args.project and f"/project/{args.project}" not in (page.url or ""):
            br.nav_project(args.project)
            page.wait_for_timeout(2500)
        print("URL:", page.url)

        # Agent OFF so the settings chip exists (Agent ON hides it entirely).
        page.evaluate(
            "() => { const b = document.querySelector('button.agent-mode-chip');"
            " if (b && b.getAttribute('aria-pressed') === 'true') b.click(); return true; }"
        )
        page.wait_for_timeout(1200)
        page.keyboard.press("Escape")

        combos = [
            dict(sub_mode="frames", target_aspect="9:16", model_label="Omni 1.1 Flash",
                 duration_s=4, resolution="360p", count=2),
            dict(sub_mode="frames", target_aspect="16:9", model_label="Veo 3.1 - Fast",
                 duration_s=8, resolution="720p", count=1, offer_resolution=False,
                 offer_duration=False),
            dict(sub_mode="ingredients", target_aspect="9:16", model_label="Veo 3.1 - Quality",
                 duration_s=8, resolution="720p", count=4, offer_resolution=False,
                 offer_duration=False),
        ]
        results = []
        for combo in combos:
            chip = vb._ensure_ui_video_mode(page, **combo)
            # Reading the same signal `generate_video_flow` uses to reject a wrong mode.
            composer_mode = br.eval_json(
                "(() => { const b = document.querySelector('button.settings-trigger-button');"
                " return {text: b ? (b.innerText||'').replace(/\\s+/g,' ').trim() : '',"
                " video: !!(b && b.innerHTML.includes('videocam'))}; })()"
            )
            row = {"combo": {k: v for k, v in combo.items()}, "chip": chip, "composer": composer_mode}
            results.append(row)
            print(json.dumps(row, ensure_ascii=False))

        # Image side: model + count selection.
        br.ensure_ui_image_mode("1:1", model_label="Nano Banana Pro", count=3)
        img_chip = _chip(page)
        print(json.dumps({"image_chip": img_chip}, ensure_ascii=False))
        results.append({"image_chip": img_chip})

        page.keyboard.press("Escape")
        print("\nVIDEO_SUBMIT_RPC =", VIDEO_SUBMIT_RPC)

    dest = ROOT / "traces" / "verify_composer_drivers.json"
    dest.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
