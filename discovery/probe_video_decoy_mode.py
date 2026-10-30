"""Live 0-credit probe: verify the video decoy click happens in VIDEO mode (captures eb1hJf, not ogiZ0b).

Regression check for the 2026-10-29 bug where `FlowBridge.click_generate` switched the composer to
Image mode during video generation.

Flow (mirrors `FlowVideoBridge.generate_video_flow` up to the decoy capture, then STOPS):
  1. Attach to CloakBrowser via CDP, open the project.
  2. Optionally force the composer into Image mode first (`--start-image`) to simulate the dirty
     state left behind by a previous image node.
  3. Install VIDEO_HOOK_JS, switch to Video -> Frames mode, paste the starting frame (maseQ).
  4. Type prompt, `click_generate(expected_mode="video")` -> app's eb1hJf is BLOCKED by the hook.
  5. Assert captured rpcid == eb1hJf and the composer is still in Video mode. Nothing is fired,
     so no credit is spent.

Usage:
  python -m discovery.probe_video_decoy_mode --cdp http://127.0.0.1:4024 --project <pid> --frame <jpg> [--start-image]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from src.Bridge.flow_bridge import FlowBridge
from src.Bridge.flow_video_bridge import (
    VIDEO_SUBMIT_RPC,
    FlowVideoBridge,
    parse_video_app_capture,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", default="http://127.0.0.1:4024")
    ap.add_argument("--project", required=True)
    ap.add_argument("--frame", required=True)
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--start-image", action="store_true", help="force Image mode first (dirty-state simulation)")
    args = ap.parse_args()

    def log(kind: str, msg: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {kind:5s} {msg}", flush=True)

    video = FlowVideoBridge(cdp_url=args.cdp, log=log)
    result: dict = {"ok": False}
    with FlowBridge(args.cdp, log=lambda m: log("br", m)) as br:
        page = br.page
        if f"/project/{args.project}" not in page.url:
            br.nav_project(args.project)
        page.keyboard.press("Escape")

        video._ensure_recaptcha_ready(br, args.project)
        if args.start_image:
            br.ensure_ui_image_mode(args.aspect)
            log("info", f"Pre-state forced -> composer_mode={br.composer_mode()}")
        result["mode_before"] = br.composer_mode()

        video.install_video_hook(br)
        video._ensure_ui_video_frames_mode(page, args.aspect)
        media_id = video.upload_starting_frame_via_paste(br, Path(args.frame), project_id=args.project, timeout_s=35.0)
        result["frame_media_id"] = media_id

        br._eval("window.__videoHook.cap = null; window.__blockVideoGen = true;")
        br.type_prompt("A fashion model turns slowly and smiles, natural light, 8 seconds.")
        time.sleep(0.4)
        result["mode_at_click"] = br.composer_mode()
        br.click_generate(timeout_s=15.0, expected_mode="video")
        try:
            cap = video.wait_video_capture(br, timeout_s=25.0)
        finally:
            video.disarm_video_hook(br)
        _, _, _, rpcid = parse_video_app_capture(cap["body"])
        result["captured_rpcid"] = rpcid
        result["mode_after_click"] = br.composer_mode()
        result["ok"] = rpcid == VIDEO_SUBMIT_RPC and result["mode_after_click"] == "video"
        br.reload(settle_s=4.0)  # discard the blocked decoy state; nothing was fired (0 credit)

    print("RESULT " + json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
