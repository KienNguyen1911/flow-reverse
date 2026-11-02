"""Discovery: what does video sub-mode "Thành phần" (ingredients) submit? (0 credit)

The composer has two video sub-modes: "Khung hình" (crop_free, needs a starting
frame) and "Thành phần" (chrome_extension, the app's default). Our pipeline only
implements the first one. This probe selects "Thành phần", types a prompt, clicks
Generate and reads every blocked batchexecute body, so we learn whether it is a
real text-to-video path or just an ingredients composer.

Blocks EVERY /data/batchexecute right before the click => 0 credit.

Output: traces/submit_bodies/ingredients_*.

Usage: python discovery/probe_submode_ingredients.py
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
    return json.loads(json.loads(f)[0][0][1])


def pick(page, label: str):
    return page.evaluate(
        r"""(label) => {
        const n = s => (s || '').replace(/\s+/g, ' ').trim();
        const ps = [...document.querySelectorAll('.cdk-overlay-pane')].filter(p => p.offsetWidth || p.offsetHeight);
        const p = ps[ps.length - 1];
        if (!p) return false;
        const els = [...p.querySelectorAll('[role="radio"], [role="menuitem"], button')];
        const el = els.find(e => n(e.innerText) === label)
          || els.find(e => n(e.innerText).endsWith(' ' + label))
          || els.find(e => n(e.innerText).startsWith(label + ' '));
        if (!el) return false;
        if (el.disabled === true || el.getAttribute('aria-disabled') === 'true') return 'disabled';
        el.click();
        return true;
      }""",
        label,
    )


def open_settings(page) -> bool:
    return page.evaluate(
        "() => { const b = document.querySelector('button.settings-trigger-button');"
        " if (!b || !(b.offsetWidth || b.offsetHeight)) return false; b.click(); return true; }"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    ap.add_argument("--submode", default="Thành phần")
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--model", default=None)
    ap.add_argument("--res", default=None)
    ap.add_argument("--dur", default=None)
    ap.add_argument("--count", default=None)
    ap.add_argument("--name", default="ingredients")
    args = ap.parse_args(argv)

    with FlowBridge(args.cdp_url) as br:
        page = br.page
        print("URL:", page.url)
        page.evaluate(
            "() => { const b = document.querySelector('button.agent-mode-chip');"
            " if (b && b.getAttribute('aria-pressed') === 'true') b.click(); return true; }"
        )
        page.wait_for_timeout(1300)

        for label in ("Video", args.submode, args.aspect):
            if not open_settings(page):
                print("no settings chip")
                return 2
            page.wait_for_timeout(550)
            print(f"pick {label}:", pick(page, label))
            page.wait_for_timeout(450)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        extra = [x for x in (args.model, args.res, args.dur, args.count) if x]
        for label in extra:
            if not open_settings(page):
                print("no settings chip")
                return 2
            page.wait_for_timeout(550)
            if label == args.model:
                page.evaluate(
                    r"""() => { const ps = [...document.querySelectorAll('.cdk-overlay-pane')].filter(p => p.offsetWidth || p.offsetHeight);
                    const p = ps[ps.length - 1]; if (!p) return false;
                    const b = [...p.querySelectorAll('button')].find(x => (x.getAttribute('aria-label') || '') === 'Chọn nhóm mô hình');
                    if (!b) return false; b.click(); return true; }"""
                )
                page.wait_for_timeout(550)
            print(f"pick {label}:", pick(page, label))
            page.wait_for_timeout(450)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        print("chip:", br.eval_json(
            "(() => { const b = document.querySelector('button.settings-trigger-button');"
            " return b ? (b.innerText || '').replace(/\\s+/g, ' ').trim() : ''; })()"
        ))
        print("composer buttons:", br.eval_json(
            "(() => [...document.querySelectorAll('button')].filter(b => (b.offsetWidth || b.offsetHeight))"
            ".map(b => ({aria: b.getAttribute('aria-label'), txt: (b.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 40)})).slice(-25))()"
        ))

        br.type_prompt("a calm ocean wave at sunrise, cinematic")
        page.wait_for_timeout(700)

        btn = br.eval_json(
            "(() => { const b = [...document.querySelectorAll('button')]"
            ".find(x => (x.getAttribute('aria-label') || '') === 'Bắt đầu tạo');"
            " if (!b) return null; const r = b.getBoundingClientRect();"
            " return {x: r.x + r.width/2, y: r.y + r.height/2, disabled: b.disabled || b.getAttribute('aria-disabled') === 'true'}; })()"
        )
        print("generate btn:", btn)
        if not btn or btn.get("disabled"):
            print("generate unavailable in this sub-mode — dumping composer instead")
            br._eval("window.__broadBlock = false; true")
            return 3

        br._eval(BROAD)
        page.mouse.click(btn["x"], btn["y"])
        page.wait_for_timeout(5000)
        caps = br.eval_json(
            "(() => window.__broadCap ? window.__broadCap.caps.map(c => ({rpcid: c.rpcid, url: c.url, body: c.body})) : [])()"
        ) or []
        br._eval("window.__broadBlock = false; true")

    dest = ROOT / "traces" / "submit_bodies"
    dest.mkdir(parents=True, exist_ok=True)
    summary = {"ts": datetime.now().isoformat(timespec="seconds"), "combo": vars(args), "rpcids": [], "decoded": {}}
    for c in caps:
        rid = c["rpcid"]
        summary["rpcids"].append(rid)
        (dest / f"{args.name}_{rid}.txt").write_text(c.get("body") or "", encoding="utf-8")
        try:
            args_dec = decode_args(c.get("body") or "")
            summary["decoded"].setdefault(rid, []).append(args_dec)
            print(f"\n--- {rid} ---")
            print(json.dumps(args_dec, ensure_ascii=False)[:1200])
        except Exception as exc:  # noqa: BLE001
            print(f"\n--- {rid} --- decode failed: {exc}")
    (dest / f"{args.name}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nrpcids:", summary["rpcids"])
    print("wrote", dest / f"{args.name}_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
