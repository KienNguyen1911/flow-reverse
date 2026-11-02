"""Capture how count (x2) and resolution (360p) change the payload, 0 credit."""

from __future__ import annotations

import argparse
import json
import sys
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
      let url=''; try { url = typeof input==='string'? input : (input&&input.url)||''; } catch(e){}
      if (String(url).indexOf('/data/batchexecute?') >= 0 && window.__broadBlock) {
        const m = /rpcids=([^&]+)/.exec(url);
        const rec = {rpcid: m?decodeURIComponent(m[1]):'?', body:'', ready:false};
        window.__broadCap.caps.push(rec);
        if (typeof input !== 'string' && input && typeof input.text === 'function') {
          input.text().then(t=>{rec.body=t;rec.ready=true;}).catch(()=>{rec.ready=true;});
        } else { rec.body = String((init&&init.body)||''); rec.ready = true; }
        return Promise.reject(new Error('probe-blocked'));
      }
      return prev.apply(this, arguments);
    };
  }
  window.__broadCap.caps = []; window.__broadBlock = true; return true;
})()
"""


def decode(body: str):
    qs = parse_qs(body, keep_blank_values=True)
    f = qs.get("f.req", [None])[0]
    return json.loads(json.loads(f)[0][0][1]) if f else None


def pick(page, label):
    return page.evaluate(
        r"""(label) => { const n=s=>(s||'').replace(/\s+/g,' ').trim();
        const ps=[...document.querySelectorAll('.cdk-overlay-pane')].filter(p=>p.offsetWidth||p.offsetHeight);
        const p=ps[ps.length-1]; if(!p) return false;
        const els=[...p.querySelectorAll('[role="radio"], [role="menuitem"], button')];
        const el=els.find(e=>n(e.innerText)===label)||els.find(e=>n(e.innerText).endsWith(' '+label))
              ||els.find(e=>n(e.innerText).startsWith(label+' '));
        if(!el) return false; if(el.getAttribute('aria-checked')==='true') return true;
        el.click(); return true; }""", label)


def open_settings(page):
    return page.evaluate("() => { const b=document.querySelector('button.settings-trigger-button');"
                         " if(!b||!(b.offsetWidth||b.offsetHeight)) return false; b.click(); return true; }")


def open_models(page):
    return page.evaluate(r"""() => { const ps=[...document.querySelectorAll('.cdk-overlay-pane')].filter(p=>p.offsetWidth||p.offsetHeight);
        const p=ps[ps.length-1]; if(!p) return false;
        const b=[...p.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||'')==='Chọn nhóm mô hình');
        if(!b) return false; b.click(); return true; }""")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="image", choices=["image", "video"])
    ap.add_argument("--name", default="probe")
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--model", default=None)
    ap.add_argument("--res", default=None)
    ap.add_argument("--dur", default=None)
    ap.add_argument("--count", default="x1")
    args = ap.parse_args(argv)

    video = FlowVideoBridge(cdp_url=DEFAULT_CDP_URL)
    with FlowBridge(DEFAULT_CDP_URL) as br:
        page = br.page
        page.evaluate("() => { const b=document.querySelector('button.agent-mode-chip');"
                      " if(b&&b.getAttribute('aria-pressed')==='true') b.click(); return true; }")
        page.wait_for_timeout(1200)

        # mode
        open_settings(page); page.wait_for_timeout(550)
        pick(page, "Hình ảnh" if args.kind == "image" else "Video")
        page.wait_for_timeout(400)
        page.keyboard.press("Escape"); page.wait_for_timeout(300)

        if args.kind == "video":
            open_settings(page); page.wait_for_timeout(550)
            pick(page, "Khung hình"); page.wait_for_timeout(400)
            page.keyboard.press("Escape"); page.wait_for_timeout(300)
            frame = next((c for c in sorted((ROOT / "out" / "nodes").rglob("*.jpg"),
                                            key=lambda x: -x.stat().st_mtime) if c.stat().st_size > 20000), None)
            video.upload_starting_frame_via_paste(br, frame, timeout_s=45.0)

        for label in [args.aspect] + ([args.model] if args.model else []) + \
                     ([args.res] if args.res else []) + ([args.dur] if args.dur else []) + [args.count]:
            if not label:
                continue
            open_settings(page); page.wait_for_timeout(550)
            if args.model and label == args.model:
                open_models(page); page.wait_for_timeout(500)
            print(f"  pick {label}:", pick(page, label))
            page.wait_for_timeout(400)
            page.keyboard.press("Escape"); page.wait_for_timeout(300)

        print("  chip:", br.eval_json(
            "(() => { const b=document.querySelector('button.settings-trigger-button');"
            " return b ? (b.innerText||'').replace(/\\s+/g,' ').trim() : ''; })()"))

        br.type_prompt("probe for count and resolution")
        page.wait_for_timeout(600)
        btn = br.eval_json(
            "(() => { const b=[...document.querySelectorAll('button')]"
            ".find(x=>(x.getAttribute('aria-label')||'')==='Bắt đầu tạo');"
            " if(!b) return null; const r=b.getBoundingClientRect();"
            " return {x:r.x+r.width/2,y:r.y+r.height/2,disabled:b.disabled||b.getAttribute('aria-disabled')==='true'}; })()")
        if not btn or btn.get("disabled"):
            print("  generate disabled:", btn)
            return 2

        br._eval(BROAD)
        page.mouse.click(btn["x"], btn["y"])
        page.wait_for_timeout(5000)
        caps = br.eval_json("(() => window.__broadCap ? window.__broadCap.caps.map(c=>({rpcid:c.rpcid, body:c.body})) : [])()") or []
        br._eval("window.__broadBlock=false; true")

    dest = ROOT / "traces" / "submit_bodies"
    dest.mkdir(parents=True, exist_ok=True)
    out = {"name": args.name, "args": vars(args), "rpcids": [], "decoded": {}}
    for c in caps:
        out["rpcids"].append(c["rpcid"])
        try:
            out["decoded"].setdefault(c["rpcid"], []).append(decode(c["body"]))
        except Exception as exc:  # noqa: BLE001
            out["decoded"].setdefault(c["rpcid"], []).append(f"ERR {exc}")
    (dest / f"{args.name}_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("  rpcids:", out["rpcids"])
    for rid, payloads in out["decoded"].items():
        for p in payloads:
            print(f"  {rid}:", json.dumps(p, ensure_ascii=False)[:700])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
