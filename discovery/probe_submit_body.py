"""Dump the full submit body (any RPC) for a given video combo, 0 credit.

Blocks every /data/batchexecute right after Generate so nothing reaches the server,
then writes each blocked body to traces/submit_bodies/<name>_<rpcid>.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.Bridge.flow_bridge import DEFAULT_CDP_URL, FlowBridge
from src.Bridge.flow_video_bridge import FlowVideoBridge

BROAD = r"""
(() => {
  if (!window.__broadCap) {
    window.__broadCap = {caps: []};
    const prev = window.fetch;
    window.fetch = function(input, init) {
      let url = '';
      try { url = typeof input === 'string' ? input : (input && input.url) || ''; } catch (e) {}
      if (String(url).indexOf('/data/batchexecute?') >= 0 && window.__broadBlock) {
        const m = /rpcids=([^&]+)/.exec(url);
        const rec = {rpcid: m ? decodeURIComponent(m[1]) : '?', url: String(url), body: '', ready: false};
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


def decode_args(body: str):
    qs = parse_qs(body, keep_blank_values=True)
    f = qs.get("f.req", [None])[0]
    if not f:
        return None
    outer = json.loads(f)
    return json.loads(outer[0][0][1])


def pick(page, label: str) -> bool:
    return page.evaluate(
        r"""(label) => { const n=s=>(s||'').replace(/\s+/g,' ').trim();
        const ps=[...document.querySelectorAll('.cdk-overlay-pane')].filter(p=>p.offsetWidth||p.offsetHeight);
        const p=ps[ps.length-1]; if(!p) return false;
        const els=[...p.querySelectorAll('[role="radio"], [role="menuitem"], button')];
        const el=els.find(e=>n(e.innerText)===label)||els.find(e=>n(e.innerText).endsWith(' '+label))
              ||els.find(e=>n(e.innerText).startsWith(label+' '));
        if(!el) return false;
        if(el.getAttribute('aria-checked')==='true') return true;
        el.click(); return true; }""",
        label,
    )


def open_settings(page) -> bool:
    return page.evaluate(
        "() => { const b=document.querySelector('button.settings-trigger-button');"
        " if(!b||!(b.offsetWidth||b.offsetHeight)) return false; b.click(); return true; }"
    )


def open_models(page) -> bool:
    return page.evaluate(
        r"""() => { const ps=[...document.querySelectorAll('.cdk-overlay-pane')].filter(p=>p.offsetWidth||p.offsetHeight);
        const p=ps[ps.length-1]; if(!p) return false;
        const b=[...p.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||'')==='Chọn nhóm mô hình');
        if(!b) return false; b.click(); return true; }"""
    )


def apply(page, submode, aspect, model, res, dur):
    log = []
    for group in ([("Video", 0)], [(submode, 0)], [(aspect, 0)],
                  [(model, 1)], [(res, 0), (dur, 0)]):
        if not open_settings(page):
            return log + [("NO_CHIP", submode)]
        page.wait_for_timeout(550)
        for label, menu in group:
            if menu:
                log.append(("open_models", open_models(page)))
                page.wait_for_timeout(550)
            log.append((label, pick(page, label)))
            page.wait_for_timeout(420)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    return log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    ap.add_argument("--frame", default=None)
    ap.add_argument("--submode", default="Khung hình")
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--model", default="Omni 1.2 Flash")
    ap.add_argument("--res", default="720p")
    ap.add_argument("--dur", default="8 giây")
    ap.add_argument("--name", default="probe")
    args = ap.parse_args(argv)

    frame = Path(args.frame) if args.frame else next(
        (c for c in sorted((ROOT / "out" / "nodes").rglob("*.jpg"), key=lambda x: -x.stat().st_mtime)
         if c.stat().st_size > 20000), None)

    video = FlowVideoBridge(cdp_url=args.cdp_url)
    with FlowBridge(args.cdp_url) as br:
        page = br.page
        page.evaluate(
            "() => { const b=document.querySelector('button.agent-mode-chip');"
            " if(b&&b.getAttribute('aria-pressed')==='true') b.click(); return true; }"
        )
        page.wait_for_timeout(1200)

        print("set:", apply(page, args.submode, args.aspect, args.model, args.res, args.dur))
        print("chip:", br.eval_json(
            "(() => { const b=document.querySelector('button.settings-trigger-button');"
            " return b ? (b.innerText||'').replace(/\\s+/g,' ').trim() : ''; })()"
        ))

        if args.submode == "Khung hình":
            mid = video.upload_starting_frame_via_paste(br, frame, timeout_s=45.0)
            print("frame:", mid)
            if not page.query_selector("flow-image-ingredient-chip"):
                video._attach_starting_frame_ui_fallback(page, frame)

        br.type_prompt("slow cinematic camera move for probe")
        page.wait_for_timeout(600)

        btn = br.eval_json(
            "(() => { const b=[...document.querySelectorAll('button')]"
            ".find(x=>(x.getAttribute('aria-label')||'')==='Bắt đầu tạo');"
            " if(!b) return null; const r=b.getBoundingClientRect();"
            " return {x:r.x+r.width/2,y:r.y+r.height/2,disabled:b.disabled||b.getAttribute('aria-disabled')==='true'}; })()"
        )
        print("btn:", btn)
        if not btn or btn.get("disabled"):
            return 2

        br._eval(BROAD)
        page.mouse.click(btn["x"], btn["y"])
        page.wait_for_timeout(5000)
        caps = br.eval_json(
            "(() => window.__broadCap ? window.__broadCap.caps.map(c=>({rpcid:c.rpcid, url:c.url, body:c.body})) : [])()"
        ) or []
        br._eval("window.__broadBlock=false; true")

    dest_dir = ROOT / "traces" / "submit_bodies"
    dest_dir.mkdir(parents=True, exist_ok=True)
    summary = {"ts": datetime.now().isoformat(timespec="seconds"), "combo": vars(args), "rpcids": [], "specs": {}}
    for c in caps:
        rid = c["rpcid"]
        summary["rpcids"].append(rid)
        body = c.get("body") or ""
        (dest_dir / f"{args.name}_{rid}.txt").write_text(body, encoding="utf-8")
        try:
            a = decode_args(body)
            summary["specs"][rid] = a
            print(f"\n--- {rid} ---")
            print(json.dumps(a, ensure_ascii=False)[:1500])
        except Exception as exc:  # noqa: BLE001
            print(f"\n--- {rid} --- decode failed: {exc}")

    (dest_dir / f"{args.name}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote", dest_dir / f"{args.name}_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
