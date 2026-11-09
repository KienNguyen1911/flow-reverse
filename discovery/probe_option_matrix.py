"""Discovery: per-model option matrix of the Flow composer (0 credit, read-only).

The composer hides/disables options depending on the selected model (e.g. Veo has
no 360p, some models fix the duration). The node UI must mirror that, so this probe
records, for every image/video model, which aspect / resolution / duration / count
radios exist and whether they are enabled.

Read-only: it only opens the settings popover and reads attributes. It never
clicks Generate, so it spends 0 credits.

Output: ``traces/flow_option_matrix.json``

Usage:

    python discovery/probe_option_matrix.py
    python discovery/probe_option_matrix.py --video-only
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

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:4022"

IMAGE_MODELS = ["🍌 Nano Banana Pro", "🍌 Nano Banana 2 Lite", "🍌 Nano Banana 2.1"]
# Flow removed Omni 1.1 / Veo Fast / Veo Quality on 2026-11-09; these are the survivors.
VIDEO_MODELS = ["Omni 1.2 Flash", "Veo 3.1 - Lite"]

DUMP = r"""
() => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const panes = [...document.querySelectorAll('.cdk-overlay-pane')].filter(p => p.offsetWidth || p.offsetHeight);
  const pane = panes[panes.length - 1];
  if (!pane) return { open: false, panes: panes.length };
  const radios = [...pane.querySelectorAll('[role="radio"], button')].map(el => {
    const r = el.getBoundingClientRect();
    return {
      role: el.getAttribute('role'),
      text: norm(el.innerText),
      icon: norm((el.querySelector('mat-icon, [class*="icon"]') || {}).textContent),
      checked: el.getAttribute('aria-checked'),
      disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true' || el.hasAttribute('disabled'),
      w: Math.round(r.width),
    };
  }).filter(x => x.text || x.role === 'radio');
  return { open: true, count: radios.length, radios };
}
"""


def classify(radios: list[dict]) -> dict:
    """Bucket radios into the composer's option groups by label shape."""
    out: dict[str, dict] = {
        "mode": {}, "sub_mode": {}, "aspect": {}, "resolution": {},
        "duration": {}, "count": {}, "model": {}, "other": {},
    }
    for r in radios:
        t = r.get("text") or ""
        low = t.lower()
        entry = {"checked": r.get("checked"), "disabled": bool(r.get("disabled"))}
        if r.get("role") == "radio" and ("hình ảnh" in low or low.startswith("video")):
            out["mode"][t] = entry
        elif "khung hình" in low or "thành phần" in low or "frames" in low or "ingredients" in low:
            out["sub_mode"][t] = entry
        elif "giây" in low or low.endswith("s"):
            out["duration"][t] = entry
        elif low in ("360p", "720p", "1080p") or low.startswith("360p"):
            out["resolution"][low.split()[0]] = entry
        elif low.startswith("x") and low[1:].isdigit():
            out["count"][t] = entry
        elif ":" in t:
            out["aspect"][t.split()[-1]] = entry
        elif "nano banana" in low or "omni" in low or "veo" in low:
            out["model"][t] = entry
        else:
            out["other"][t] = entry
    return out


def open_chip(pg) -> bool:
    return pg.evaluate(
        "() => { const b = document.querySelector('button.settings-trigger-button');"
        " if (!b || !(b.offsetWidth || b.offsetHeight)) return false; b.click(); return true; }"
    )


def close_overlays(pg, n: int = 2) -> None:
    for _ in range(n):
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)


def pick(pg, label: str) -> bool:
    return pg.evaluate(
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


def open_models(pg) -> bool:
    return pg.evaluate(
        r"""() => {
        const ps = [...document.querySelectorAll('.cdk-overlay-pane')].filter(p => p.offsetWidth || p.offsetHeight);
        const p = ps[ps.length - 1];
        if (!p) return false;
        const b = [...p.querySelectorAll('button')].find(x => (x.getAttribute('aria-label') || '') === 'Chọn nhóm mô hình');
        if (!b) return false;
        b.click();
        return true;
      }"""
    )


def chip(pg) -> str:
    return pg.evaluate(
        "() => { const b = document.querySelector('button.settings-trigger-button');"
        " return b ? (b.innerText || '').replace(/\\s+/g, ' ').trim() : ''; }"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp-url", default=CDP)
    ap.add_argument("--image-only", action="store_true")
    ap.add_argument("--video-only", action="store_true")
    args = ap.parse_args(argv)

    out = {"ts": datetime.now().isoformat(timespec="seconds"), "url": None, "image": {}, "video": {}}

    with sync_playwright() as p:
        br = p.chromium.connect_over_cdp(args.cdp_url)
        ctx = br.contexts[0]
        pages = [x for x in ctx.pages if "flow.google.com/project" in (x.url or "")]
        if not pages:
            raise SystemExit("no Flow project tab open")
        pg = pages[0]
        out["url"] = pg.url
        print("URL:", pg.url)

        # Agent OFF: with the agent on there is no settings chip at all.
        pg.evaluate(
            "() => { const b = document.querySelector('button.agent-mode-chip');"
            " if (b && b.getAttribute('aria-pressed') === 'true') b.click(); return true; }"
        )
        pg.wait_for_timeout(1300)
        close_overlays(pg, 2)

        if not args.video_only:
            # Baseline: image mode.
            if open_chip(pg):
                pg.wait_for_timeout(600)
                pick(pg, "Hình ảnh")
                pg.wait_for_timeout(400)
            close_overlays(pg, 2)

            for model in IMAGE_MODELS:
                print(f"\n=== IMAGE {model} ===")
                if not open_chip(pg):
                    out["image"][model] = {"error": "no settings chip"}
                    continue
                pg.wait_for_timeout(600)
                if not open_models(pg):
                    out["image"][model] = {"error": "no model menu"}
                    close_overlays(pg, 2)
                    continue
                pg.wait_for_timeout(600)
                picked = pick(pg, model)
                pg.wait_for_timeout(700)
                close_overlays(pg, 2)
                if picked is not True:
                    out["image"][model] = {"error": f"pick={picked}"}
                    continue
                if not open_chip(pg):
                    out["image"][model] = {"error": "chip gone after pick"}
                    continue
                pg.wait_for_timeout(700)
                dump = pg.evaluate(DUMP)
                close_overlays(pg, 2)
                out["image"][model] = {
                    "chip": chip(pg),
                    "groups": classify(dump.get("radios") or []),
                    "raw": dump,
                }
                print("  chip:", out["image"][model]["chip"])
                print("  ", json.dumps(out["image"][model]["groups"], ensure_ascii=False)[:700])

        if not args.image_only:
            # Switch to Video once, then vary the model.
            for label in ("Video",):
                if open_chip(pg):
                    pg.wait_for_timeout(600)
                    pick(pg, label)
                    pg.wait_for_timeout(500)
                close_overlays(pg, 2)

            for model in VIDEO_MODELS:
                print(f"\n=== VIDEO {model} ===")
                if not open_chip(pg):
                    out["video"][model] = {"error": "no settings chip"}
                    continue
                pg.wait_for_timeout(600)
                if not open_models(pg):
                    out["video"][model] = {"error": "no model menu"}
                    close_overlays(pg, 2)
                    continue
                pg.wait_for_timeout(600)
                picked = pick(pg, model)
                pg.wait_for_timeout(800)
                close_overlays(pg, 2)
                if picked is not True:
                    out["video"][model] = {"error": f"pick={picked}"}
                    continue
                if not open_chip(pg):
                    out["video"][model] = {"error": "chip gone after pick"}
                    continue
                pg.wait_for_timeout(700)
                dump = pg.evaluate(DUMP)
                close_overlays(pg, 2)
                out["video"][model] = {
                    "chip": chip(pg),
                    "groups": classify(dump.get("radios") or []),
                    "raw": dump,
                }
                print("  chip:", out["video"][model]["chip"])
                print("  ", json.dumps(out["video"][model]["groups"], ensure_ascii=False)[:900])

        br.close()

    dest = ROOT / "traces" / "flow_option_matrix.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
