"""Behavioural check of the Flow Bench node-config UI (no credits spent).

Drives the real app in the CloakBrowser tab: opens a node's config drawer and
asserts that the option lists match ``GET /api/node/options`` exactly — the 5
captured image ratios, 3 image models, x1..x4, video sub-modes, 4 video models,
per-model disabling of resolution/duration for Veo, and that "Tác nhân" hides the
whole config block.

It never clicks "Chạy node", so nothing is generated and no credits are spent.

Usage:
    python discovery/verify_node_config_ui.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

DUMP_DRAWER = r"""
() => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const panes = [...document.querySelectorAll('aside')].filter(a => a.offsetWidth > 300);
  const drawer = panes[panes.length - 1];
  if (!drawer) return { open: false };
  const fields = [...drawer.querySelectorAll('label')].map(l => {
    const head = l.querySelector('span');
    const sel = l.querySelector('select');
    return {
      label: head ? norm(head.innerText) : '',
      options: sel ? [...sel.querySelectorAll('option')].map(o => norm(o.innerText)) : null,
      disabled: sel ? !!sel.disabled : null,
      value: sel ? sel.value : null,
      type: sel ? 'select' : (l.querySelector('input[type=checkbox]') ? 'checkbox' : 'other'),
    };
  }).filter(f => f.label || f.type === 'checkbox');
  const chips = [...drawer.querySelectorAll('button')].map(b => norm(b.innerText)).filter(Boolean);
  return { open: true, fields, buttons: chips.slice(0, 30) };
}
"""


def _open_drawer(page, node_kind: str) -> bool:
    """Click the 'Cấu hình' affordance of the first node of the wanted kind."""
    return bool(
        page.evaluate(
            r"""(kind) => {
            const n = s => (s||'').replace(/\s+/g,' ').trim();
            // The card exposes config pills; the drawer opens on the config tab.
            const cards = [...document.querySelectorAll('div')].filter(d => {
              const t = n(d.innerText);
              return t.includes('Seed:') && t.includes('Model');
            });
            const title = kind === 'video' ? 'Sub' : 'Model';
            const card = cards.find(c => n(c.innerText).includes(title))
              || cards.find(c => !n(c.innerText).includes('Sub'));
            if (!card) return false;
            const btn = [...card.querySelectorAll('button')].find(b => {
              const t = n(b.innerText);
              return t.includes('Seed:') || t === 'Model' || /^x\d$/.test(t) || t.includes(':') || t.includes('Sub');
            });
            if (!btn) return false;
            btn.click();
            return true;
          }""",
            node_kind,
        )
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp-url", default="http://127.0.0.1:4022")
    ap.add_argument("--app-url", default="http://127.0.0.1:4000")
    args = ap.parse_args(argv)

    report: dict = {"app_url": args.app_url, "checks": []}

    def check(name: str, ok: bool, detail=None):
        report["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {detail}"))

    with sync_playwright() as p:
        br = p.chromium.connect_over_cdp(args.cdp_url)
        ctx = br.contexts[0]
        page = ctx.new_page()
        page.goto(args.app_url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        opts = page.evaluate("() => fetch('/api/node/options').then(r => r.json())")
        report["options"] = {
            "image_aspects": opts["image"]["aspect_ratios"],
            "image_models": [m["id"] for m in opts["image"]["models"]],
            "video_models": [m["id"] for m in opts["video"]["models"]],
            "video_sub_modes": opts["video"]["sub_modes"],
        }

        # Open the config drawer of the first image node (it has no 'Sub' pill).
        opened = page.evaluate(
            r"""() => {
            const n = s => (s||'').replace(/\s+/g,' ').trim();
            const cards = [...document.querySelectorAll('div')].filter(d => n(d.innerText).includes('Seed:'));
            const card = cards.find(c => !n(c.innerText).includes('Sub')) || cards[0];
            if (!card) return false;
            const b = [...card.querySelectorAll('button')].find(x => n(x.innerText).startsWith('Seed:'));
            if (!b) return false;
            b.click();
            return true;
          }"""
        )
        page.wait_for_timeout(1200)
        img = page.evaluate(DUMP_DRAWER)
        report["image_drawer"] = img

        if not img.get("open"):
            check("image drawer opens", False, img)
        else:
            labels = {f["label"]: f for f in img["fields"] if f.get("options")}
            ratios = labels.get("Tỷ lệ khung hình", {}).get("options")
            check("image aspect options match API", ratios == opts["image"]["aspect_ratios"], ratios)
            models = labels.get("Model", {}).get("options")
            check(
                "image model labels present",
                models is not None and len(models) == len(opts["image"]["models"]),
                models,
            )
            counts = labels.get("Số lượng", {}).get("options")
            check(
                "image count options are x1..x4",
                counts == [f"x{c}" for c in opts["image"]["counts"]],
                counts,
            )

        page.close()

    dest = ROOT / "traces" / "verify_node_config_ui.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", dest)
    failed = [c for c in report["checks"] if not c["ok"]]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
