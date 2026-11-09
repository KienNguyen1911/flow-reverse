"""Capture eb1hJf args per video config combo, 0 credit (broad batchexecute block).

Proven path: block EVERY /data/batchexecute right before the Generate click (nothing
reaches the server) and read the eb1hJf body from the blocked record.

Only ONE request per combo is allowed through the block, so this costs 0 credits.
Re-run only when the Flow composer contract changes.

Usage: python discovery/capture_video_matrix.py
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
from src.Bridge.flow_video.composer import parse_chip_duration
from src.Bridge.flow_video_bridge import (
    FlowVideoBridge,
    extract_starting_frame_from_eb1hjf_args,
    parse_video_app_capture,
)

BROAD_BLOCK_JS = r"""
(() => {
  if (!window.__broadCap) {
    window.__broadCap = {caps: []};
    const prev = window.fetch;
    window.fetch = function(input, init) {
      let url = '';
      try { url = typeof input === 'string' ? input : (input && input.url) || ''; } catch (e) {}
      const isBx = String(url).indexOf('/data/batchexecute?') >= 0;
      if (isBx && window.__broadBlock) {
        const m = /rpcids=([^&]+)/.exec(url);
        const rec = {rpcid: m ? decodeURIComponent(m[1]) : '?', url: String(url).slice(0, 300), body: '', ready: false};
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


def pick(page, label: str) -> bool:
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
        if (el.getAttribute('aria-checked') === 'true') return true;
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


def open_models(page) -> bool:
    return page.evaluate(
        r"""() => { const ps=[...document.querySelectorAll('.cdk-overlay-pane')].filter(p=>p.offsetWidth||p.offsetHeight);
          const p=ps[ps.length-1]; if(!p) return false;
          const b=[...p.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||'')==='Chọn nhóm mô hình');
          if(!b) return false; b.click(); return true; }"""
    )


def chip_text(page) -> str:
    return page.evaluate(
        "() => { const b=document.querySelector('button.settings-trigger-button');"
        " return b ? (b.innerText||'').replace(/\\s+/g,' ').trim() : ''; }"
    )


def esc(page, n=1):
    for _ in range(n):
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)


def apply_combo(page, submode, aspect, model, res, dur, count="x1", video=None) -> list:
    """Drive the settings popover into one combo and report what could be picked.

    Duration is no longer a radio inside the popover: Omni 1.2 exposes it on
    ``flow-duration-slider``. Pass ``video`` (a :class:`FlowVideoBridge`) so the duration is
    written through the bridge's own slider helper instead of a ``"N giây"`` chip that no
    longer exists; ``None`` skips duration (Veo hides that group anyway).
    """
    log = []
    groups = [[("Video", False)], [(submode, False)], [(aspect, False)],
              [(model, True)], [(res, False), (count, False)]]
    for group in groups:
        if not open_settings(page):
            log.append(("NO_CHIP", group[0][0]))
            return log
        page.wait_for_timeout(550)
        for label, need_menu in group:
            if need_menu:
                log.append(("open_models", open_models(page)))
                page.wait_for_timeout(550)
            log.append((label, pick(page, label)))
            page.wait_for_timeout(420)
        esc(page)
        page.wait_for_timeout(300)
    seconds = parse_chip_duration(dur)
    if seconds is not None and video is not None:
        log.append((f"duration {seconds}s", video._set_duration_slider(page, seconds)))
    return log


COMBOS = {
    "omni_3s_720p_916": ("Khung hình", "9:16", "Omni 1.2 Flash", "720p", "3 giây"),
    "omni_8s_720p_916": ("Khung hình", "9:16", "Omni 1.2 Flash", "720p", "8 giây"),
    "omni_8s_720p_169": ("Khung hình", "16:9", "Omni 1.2 Flash", "720p", "8 giây"),
    "omni_4s_360p_916": ("Khung hình", "9:16", "Omni 1.2 Flash", "360p", "4 giây"),
    "omni_15s_720p_916": ("Khung hình", "9:16", "Omni 1.2 Flash", "720p", "15 giây"),
    "veo_lite_8s_720p": ("Khung hình", "9:16", "Veo 3.1 - Lite", "720p", "8 giây"),
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    ap.add_argument("--frame", default=None)
    ap.add_argument("--only", default=None, help="capture a single combo by name")
    args = ap.parse_args(argv)

    frame = Path(args.frame) if args.frame else next(
        (c for c in sorted((ROOT / "out" / "nodes").rglob("*.jpg"), key=lambda x: -x.stat().st_mtime)
         if c.stat().st_size > 20000), None)
    if frame is None:
        raise SystemExit("no frame image found")

    out = {"ts": datetime.now().isoformat(timespec="seconds"), "frame": str(frame), "runs": {}}
    video = FlowVideoBridge(cdp_url=args.cdp_url)

    with FlowBridge(args.cdp_url) as br:
        page = br.page
        print("URL:", page.url)
        page.evaluate(
            "() => { const b=document.querySelector('button.agent-mode-chip');"
            " if (b && b.getAttribute('aria-pressed')==='true') b.click(); return true; }"
        )
        page.wait_for_timeout(1300)

        print("setup:", apply_combo(page, "Khung hình", "9:16", "Omni 1.2 Flash", "720p", "8 giây",
                                    video=video))
        print("chip:", chip_text(page))

        mid = video.upload_starting_frame_via_paste(br, frame, timeout_s=45.0)
        print("frame media_id:", mid)
        if not page.query_selector("flow-image-ingredient-chip"):
            video._attach_starting_frame_ui_fallback(page, frame)
        br.type_prompt("slow cinematic camera move for probe")
        page.wait_for_timeout(700)

        items = {k: v for k, v in COMBOS.items() if not args.only or k == args.only}
        for name, (submode, aspect, model, res, dur) in items.items():
            print(f"\n=== {name} ===")
            print("  set:", apply_combo(page, submode, aspect, model, res, dur, video=video))
            chip = chip_text(page)
            print("  chip:", chip)

            # Prompt is cleared after each submit; re-type and confirm before reading the button.
            br.type_prompt("slow cinematic camera move for probe")
            page.wait_for_timeout(700)
            typed = br.eval_json(
                "(() => { const pm=document.querySelector('div.ProseMirror');"
                " return pm ? (pm.innerText||'').trim() : ''; })()"
            )
            if not typed:
                page.click("div.ProseMirror")
                page.wait_for_timeout(250)
                page.keyboard.type("slow cinematic camera move for probe", delay=10)
                page.wait_for_timeout(600)

            btn = br.eval_json(
                "(() => { const b=[...document.querySelectorAll('button')]"
                ".find(x=>(x.getAttribute('aria-label')||'')==='Bắt đầu tạo');"
                " if(!b) return null; const r=b.getBoundingClientRect();"
                " return {x:r.x+r.width/2, y:r.y+r.height/2, disabled: b.disabled || b.getAttribute('aria-disabled')==='true'}; })()"
            )
            entry = {"chip": chip}
            if not btn or btn.get("disabled"):
                entry["error"] = f"generate disabled: {btn}"
                out["runs"][name] = entry
                print("  ->", entry["error"])
                continue

            br._eval(BROAD_BLOCK_JS)
            page.mouse.click(btn["x"], btn["y"])
            page.wait_for_timeout(4500)
            caps = br.eval_json(
                "(() => window.__broadCap ? window.__broadCap.caps.map(c=>({rpcid:c.rpcid, body:(c.body||'')})) : [])()"
            ) or []
            br._eval("window.__broadBlock = false; true")

            eb = next((c for c in caps if c["rpcid"] == "eb1hJf"), None)
            entry["rpcids"] = [c["rpcid"] for c in caps]
            if eb and eb.get("body"):
                try:
                    _t, _at, cap_args, rpcid = parse_video_app_capture(eb["body"])
                    spec = cap_args[0][0]
                    sf, crop = extract_starting_frame_from_eb1hjf_args(cap_args)
                    entry.update({
                        "rpcid": rpcid,
                        "spec": spec,
                        "spec_len": len(spec),
                        "starting_frame": sf,
                        "crop_box": crop,
                    })
                except Exception as exc:  # noqa: BLE001
                    entry["parse_error"] = f"{type(exc).__name__}: {exc}"
            out["runs"][name] = entry
            print("  spec:", json.dumps(entry.get("spec"), ensure_ascii=False)[:600])

    dest = ROOT / "traces" / "video_config_matrix.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
