"""Discovery: capture the Omni 1.2 Flash video submit body at a given duration (0 credit).

Omni 1.2 Flash replaced the composer's fixed duration radio group (4/6/8/10 giây)
with a slider (:class:`flow-duration-slider`, label "Độ dài"). This probe drives
that slider, then blocks every ``/data/batchexecute`` right before Generate so the
submit body can be read without spending credits.

The two things it answers:

* which model key Omni 1.2 sends (``abra_i2v_*``? something new?), and
* where the duration lands in the payload - baked into the key (Omni 1.1) or in
  its own slot now that the range is continuous.

Blocks EVERY /data/batchexecute right before the click => 0 credit.

Output: traces/submit_bodies/<name>_*.txt + <name>_summary.json

Usage:
    python discovery/probe_omni12_duration.py --cdp-url http://localhost:4022 --dur 3 --name omni12_3s
    python discovery/probe_omni12_duration.py --dur 15 --name omni12_15s
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

from src.Bridge.flow_bridge import DEFAULT_CDP_URL, FlowBridge  # noqa: E402
from src.Bridge.flow_video_bridge import FlowVideoBridge  # noqa: E402

BLOCK_JS = r"""
(() => {
  if (!window.__durCap) {
    window.__durCap = {caps: []};
    const prev = window.fetch;
    window.fetch = function(input, init) {
      let url = '';
      try { url = typeof input === 'string' ? input : (input && input.url) || ''; } catch (e) {}
      if (String(url).indexOf('/data/batchexecute?') >= 0 && window.__durBlock) {
        const m = /rpcids=([^&]+)/.exec(url);
        const rec = {rpcid: m ? decodeURIComponent(m[1]) : '?', url: String(url), body: '', ready: false};
        window.__durCap.caps.push(rec);
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
  window.__durCap.caps = [];
  window.__durBlock = true;
  return true;
})()
"""


# -- composer driving ------------------------------------------------------- #

def open_settings(page) -> bool:
    if page.evaluate("() => !!document.querySelector('.cdk-overlay-pane .settings-content')"):
        return True
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    opened = page.evaluate(
        "() => { const b = document.querySelector('button.settings-trigger-button');"
        " if (!b || !(b.offsetWidth || b.offsetHeight)) return false; b.click(); return true; }"
    )
    page.wait_for_timeout(900)
    return bool(opened)


def close_settings(page) -> None:
    page.keyboard.press("Escape")
    page.wait_for_timeout(350)


def click_toggle(page, group_label: str, item_re: str) -> dict:
    """Click a toggle inside a named ``flow-toggles`` group (real mouse click)."""
    hit = page.evaluate(
        r"""([groupLabel, pattern]) => {
        const n = s => (s || '').replace(/\s+/g, ' ').trim();
        const sc = document.querySelector('.cdk-overlay-pane .settings-content');
        if (!sc) return {ok: false, why: 'no popover'};
        const re = new RegExp(pattern);
        const groups = [...sc.querySelectorAll('flow-toggles')];
        const g = groupLabel ? groups.find(x => x.getAttribute('aria-label') === groupLabel) : null;
        const pool = (g || sc).querySelectorAll('mat-button-toggle');
        const t = [...pool].find(x => re.test(n(x.innerText)));
        if (!t) return {ok: false, why: 'no match', items: [...pool].map(x => n(x.innerText))};
        const r = t.getBoundingClientRect();
        return {ok: true, text: n(t.innerText), x: r.x + r.width / 2, y: r.y + r.height / 2};
      }""",
        [group_label, item_re],
    )
    if hit.get("ok"):
        page.mouse.click(hit["x"], hit["y"])
        page.wait_for_timeout(700)
    return hit


def pick_model(page, label: str) -> dict:
    box = page.evaluate(
        "() => { const sc = document.querySelector('.cdk-overlay-pane .settings-content');"
        " const b = sc && [...sc.querySelectorAll('button')]"
        ".find(x => (x.getAttribute('aria-label') || '') === 'Chọn nhóm mô hình');"
        " if (!b) return null; const r = b.getBoundingClientRect();"
        " return {x: r.x + r.width/2, y: r.y + r.height/2}; }"
    )
    if not box:
        return {"ok": False, "why": "no model button"}
    page.mouse.click(box["x"], box["y"])
    page.wait_for_timeout(900)
    hit = page.evaluate(
        r"""(label) => {
        const n = s => (s || '').replace(/\s+/g, ' ').trim();
        const panes = [...document.querySelectorAll('.cdk-overlay-pane')].filter(p => p.offsetWidth || p.offsetHeight);
        const menu = panes[panes.length - 1];
        const t = [...menu.querySelectorAll('[role=menuitem]')]
          .find(x => n(x.innerText).replace('volume_up ', '').startsWith(label));
        if (!t) return {ok: false, why: 'not offered', offered: [...menu.querySelectorAll('[role=menuitem]')].map(x => n(x.innerText))};
        const r = t.getBoundingClientRect();
        return {ok: true, text: n(t.innerText), x: r.x + r.width / 2, y: r.y + r.height / 2};
      }""",
        label,
    )
    if hit.get("ok"):
        page.mouse.click(hit["x"], hit["y"])
        page.wait_for_timeout(1700)
    return hit


def read_slider(page) -> dict:
    return page.evaluate(
        r"""() => {
        const sc = document.querySelector('.cdk-overlay-pane .settings-content');
        if (!sc) return {found: false};
        const host = sc.querySelector('flow-duration-slider');
        const inp = sc.querySelector('input[type=range].mdc-slider__input') || sc.querySelector('input[type=range]');
        if (!host && !inp) return {found: false};
        return {
          found: true,
          min: inp ? inp.getAttribute('min') : null,
          max: inp ? inp.getAttribute('max') : null,
          step: inp ? inp.getAttribute('step') : null,
          value: inp ? inp.value : null,
          valuetext: inp ? inp.getAttribute('aria-valuetext') : null,
          label: host ? (host.innerText || '').replace(/\s+/g, ' ').trim() : null,
        };
      }"""
    )


def set_duration(page, seconds: int) -> dict:
    """Drive the ``Độ dài`` slider so the composer shows ``seconds``.

    The slider's own value is ``seconds - 3`` (observed: value 5 renders "8 giây"),
    so the offset is read from the DOM rather than hard-coded here.
    """
    before = read_slider(page)
    if not before.get("found"):
        return {"ok": False, "why": "no duration slider"}
    try:
        vmin = int(before.get("min") or 0)
        vmax = int(before.get("max") or 0)
    except (TypeError, ValueError):
        vmin, vmax = 0, 12
    shown = str(before.get("label") or "")
    cur_shown = int("".join(ch for ch in shown if ch.isdigit()) or 8)
    cur_value = int(before.get("value") or 0)
    offset = cur_shown - cur_value
    target = max(vmin, min(vmax, int(seconds) - offset))

    page.evaluate(
        r"""(target) => {
        const inp = document.querySelector('.cdk-overlay-pane .settings-content input[type=range]');
        if (!inp) return false;
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(inp, String(target));
        inp.dispatchEvent(new Event('input', {bubbles: true}));
        inp.dispatchEvent(new Event('change', {bubbles: true}));
        return true;
      }""",
        target,
    )
    page.wait_for_timeout(700)
    after = read_slider(page)
    return {"ok": True, "offset": offset, "target_value": target, "before": before, "after": after}


def decode_args(body: str):
    qs = parse_qs(body, keep_blank_values=True)
    f = qs.get("f.req", [None])[0]
    if not f:
        return None
    return json.loads(json.loads(f)[0][0][1])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    ap.add_argument("--frame", default=None, help="Starting frame image (frames mode). Defaults to newest out/nodes/*.jpg")
    ap.add_argument("--submode", default="Khung hình", choices=("Khung hình", "Thành phần"))
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--model", default="Omni 1.2 Flash")
    ap.add_argument("--res", default="720p")
    ap.add_argument("--dur", type=int, default=8, help="Requested duration in seconds (3..15)")
    ap.add_argument("--prompt", default="slow cinematic camera move for probe")
    ap.add_argument("--name", default=None)
    args = ap.parse_args(argv)
    name = args.name or f"omni12_{args.dur}s"

    frame = Path(args.frame) if args.frame else next(
        (c for c in sorted((ROOT / "out" / "nodes").rglob("*.jpg"), key=lambda x: -x.stat().st_mtime)
         if c.stat().st_size > 20000), None)

    video = FlowVideoBridge(cdp_url=args.cdp_url)
    log: list = []
    with FlowBridge(args.cdp_url) as br:
        page = br.page
        # Leave agent mode: it hides every config control.
        page.evaluate(
            "() => { const b = document.querySelector('button.agent-mode-chip');"
            " if (b && b.getAttribute('aria-pressed') === 'true') b.click(); return true; }"
        )
        page.wait_for_timeout(1200)

        for step, fn in (
            ("Video", lambda: (open_settings(page), click_toggle(page, "Chế độ", r"Video"))[-1]),
            (args.submode, lambda: (open_settings(page), click_toggle(page, "Loại video", args.submode))[-1]),
            (args.aspect, lambda: (open_settings(page), click_toggle(page, "Tỷ lệ khung hình", args.aspect.replace(":", "\\:")))[-1]),
            (args.model, lambda: (open_settings(page), pick_model(page, args.model))[-1]),
            (args.res, lambda: (open_settings(page), click_toggle(page, "Độ phân giải video", args.res))[-1]),
        ):
            close_settings(page)
            log.append((step, fn()))
            close_settings(page)

        close_settings(page)
        open_settings(page)
        log.append((f"dur={args.dur}", set_duration(page, args.dur)))
        close_settings(page)

        chip = br.eval_json(
            "(() => { const b = document.querySelector('button.settings-trigger-button');"
            " return b ? (b.innerText || '').replace(/\\s+/g, ' ').trim() : ''; })()"
        )
        print("chip:", chip)

        if args.submode == "Khung hình":
            if frame is None:
                print("!! no starting frame available under out/nodes", file=sys.stderr)
                return 3
            mid = video.upload_starting_frame_via_paste(br, frame, timeout_s=45.0)
            print("frame:", mid)
            if not page.query_selector("flow-image-ingredient-chip"):
                video._attach_starting_frame_ui_fallback(page, frame)

        br.type_prompt(args.prompt)
        page.wait_for_timeout(700)

        btn = br.eval_json(
            "(() => { const b = [...document.querySelectorAll('button')]"
            ".find(x => (x.getAttribute('aria-label') || '') === 'Bắt đầu tạo');"
            " if (!b) return null; const r = b.getBoundingClientRect();"
            " return {x: r.x + r.width/2, y: r.y + r.height/2, disabled: b.disabled || b.getAttribute('aria-disabled') === 'true'}; })()"
        )
        print("generate:", btn)
        if not btn or btn.get("disabled"):
            return 2

        br._eval(BLOCK_JS)
        page.mouse.click(btn["x"], btn["y"])
        page.wait_for_timeout(5000)
        caps = br.eval_json(
            "(() => window.__durCap ? window.__durCap.caps.map(c => ({rpcid: c.rpcid, url: c.url, body: c.body})) : [])()"
        ) or []
        br._eval("window.__durBlock = false; true")

    dest = ROOT / "traces" / "submit_bodies"
    dest.mkdir(parents=True, exist_ok=True)
    summary = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "combo": vars(args),
        "chip": chip,
        "steps": [{k: v} for k, v in log],
        "rpcids": [],
        "specs": {},
    }
    for c in caps:
        rid = c["rpcid"]
        summary["rpcids"].append(rid)
        body = c.get("body") or ""
        (dest / f"{name}_{rid}.txt").write_text(body, encoding="utf-8")
        try:
            decoded = decode_args(body)
            summary["specs"].setdefault(rid, []).append(decoded)
            print(f"\n--- {rid} ---")
            print(json.dumps(decoded, ensure_ascii=False)[:1600])
        except Exception as exc:  # noqa: BLE001
            print(f"\n--- {rid} --- decode failed: {exc}")

    (dest / f"{name}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nwrote", dest / f"{name}_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
