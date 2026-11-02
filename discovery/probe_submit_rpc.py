"""Discover which RPC the Flow app submits for video, safely (0 credit).

Blocks EVERY /data/batchexecute request right after the Generate click and records
rpcids + bodies. Nothing reaches the server, so no credits are spent.

Usage: python discovery/probe_submit_rpc.py --mode video
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.Bridge.flow_bridge import DEFAULT_CDP_URL, FlowBridge

BROAD_BLOCK_JS = r"""
(() => {
  if (!window.__broadCap) {
    window.__broadCap = {caps: []};
    const prev = window.fetch;
    window.__origFetchBroad = prev;
    window.fetch = function(input, init) {
      let url = '';
      try { url = typeof input === 'string' ? input : (input && input.url) || ''; } catch (e) {}
      const isBx = String(url).indexOf('/data/batchexecute?') >= 0;
      if (isBx && window.__broadBlock) {
        let m = /rpcids=([^&]+)/.exec(url);
        const rid = m ? decodeURIComponent(m[1]) : '?';
        const rec = {rpcid: rid, url: String(url).slice(0, 400), body: '', ready: false, ts: Date.now()};
        window.__broadCap.caps.push(rec);
        if (typeof input !== 'string' && input && typeof input.text === 'function') {
          input.text().then(t => { rec.body = t; rec.ready = true; }).catch(() => { rec.ready = true; });
        } else {
          rec.body = String((init && init.body) || '');
          rec.ready = true;
        }
        return Promise.reject(new Error('probe-blocked'));
      }
      return prev.apply(this, arguments);
    };
  }
  window.__broadCap.caps = [];
  window.__broadBlock = true;
  return true;
})()
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    ap.add_argument("--mode", default="video", choices=["video", "image"])
    ap.add_argument("--prompt", default="slow cinematic camera move")
    ap.add_argument("--frame", default=None)
    args = ap.parse_args(argv)

    out = {"ts": datetime.now().isoformat(timespec="seconds"), "mode": args.mode}

    with FlowBridge(args.cdp_url) as br:
        page = br.page
        print("URL:", page.url)
        page.evaluate(
            "() => { const b=document.querySelector('button.agent-mode-chip');"
            " if (b && b.getAttribute('aria-pressed')==='true') b.click(); return true; }"
        )
        page.wait_for_timeout(1200)

        print("chip before:", br.eval_json(
            "(() => { const b=document.querySelector('button.settings-trigger-button');"
            " return b ? (b.innerText||'').replace(/\\s+/g,' ').trim() : ''; })()"
        ))

        # Ensure a starting frame exists for video mode
        if args.mode == "video":
            from src.Bridge.flow_video_bridge import FlowVideoBridge

            video = FlowVideoBridge(cdp_url=args.cdp_url)
            frame = Path(args.frame) if args.frame else next(
                (c for c in sorted((ROOT / "out" / "nodes").rglob("*.jpg"), key=lambda x: -x.stat().st_mtime)
                 if c.stat().st_size > 20000), None
            )
            if frame:
                video._ensure_ui_video_frames_mode(page, "9:16")
                mid = video.upload_starting_frame_via_paste(br, frame, timeout_s=45.0)
                print("frame media_id:", mid)

        # Type prompt and verify
        br.type_prompt(args.prompt)
        page.wait_for_timeout(700)
        typed = br.eval_json(
            "(() => { const pm=document.querySelector('div.ProseMirror');"
            " return pm ? (pm.innerText||'').slice(0,120) : null; })()"
        )
        print("typed:", typed)
        out["typed"] = typed

        btn = br.eval_json(
            "(() => { const b=[...document.querySelectorAll('button')]"
            ".find(x=>(x.getAttribute('aria-label')||'')==='Bắt đầu tạo');"
            " if(!b) return null; const r=b.getBoundingClientRect();"
            " return {x:r.x+r.width/2, y:r.y+r.height/2, disabled: b.disabled || b.getAttribute('aria-disabled')==='true'}; })()"
        )
        print("generate btn:", btn)
        if not btn or btn.get("disabled"):
            print("generate disabled — abort")
            return 2

        # Arm broad block BEFORE clicking (0 credit)
        br._eval(BROAD_BLOCK_JS)
        page.mouse.click(btn["x"], btn["y"])
        page.wait_for_timeout(5000)

        caps = br.eval_json(
            "(() => window.__broadCap ? window.__broadCap.caps.map(c=>({rpcid:c.rpcid, len:(c.body||'').length, ready:c.ready, url:c.url})) : [])()"
        )
        print("captured rpcids:", json.dumps(caps, ensure_ascii=False, indent=1)[:3000])
        out["rpcids"] = caps

        full = br.eval_json(
            "(() => window.__broadCap ? window.__broadCap.caps.map(c=>({rpcid:c.rpcid, body:(c.body||'')})) : [])()"
        )
        out["caps"] = full
        br._eval("window.__broadBlock = false; true")

    dest = ROOT / "traces" / f"submit_rpc_probe_{args.mode}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
