"""Discovery: dump the live Flow video composer option matrix (0 credit).

Reads, straight off the DOM, what the video composer currently offers:
sub-modes, aspect ratios, models, and - per model - resolution, duration and
batch-count groups plus the credit cost the composer advertises.

Nothing is submitted: every option is read from the settings popover.

Usage:
    python discovery/probe_video_model_matrix.py --cdp-url http://localhost:4022
    python discovery/probe_video_model_matrix.py --project <uuid>
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

from src.Bridge.flow_bridge import FlowBridge  # noqa: E402

OPEN_SETTINGS_JS = "() => { const b = document.querySelector('button.settings-trigger-button'); if (!b) return false; b.click(); return true; }"

#: Every visible popover, outermost first. Angular nests the model menu in a second pane.
PANES_JS = "() => [...document.querySelectorAll('.cdk-overlay-pane')].filter(p => p.offsetWidth || p.offsetHeight)"

DUMP_JS = r"""
() => {
  const n = s => (s || '').replace(/\s+/g, ' ').trim();
  const panes = [...document.querySelectorAll('.cdk-overlay-pane')].filter(p => p.offsetWidth || p.offsetHeight);
  const sc = panes.length ? panes[0].querySelector('.settings-content') : null;
  if (!sc) return null;
  const groups = {};
  for (const g of sc.querySelectorAll('flow-toggles')) {
    const label = g.getAttribute('aria-label') || '(unlabelled)';
    groups[label] = [...g.querySelectorAll('mat-button-toggle')].map(t => ({
      text: n(t.innerText),
      checked: t.classList.contains('mat-button-toggle-checked'),
      disabled: t.getAttribute('aria-disabled'),
    }));
  }
  const modelBtn = [...sc.querySelectorAll('button')]
    .find(b => (b.getAttribute('aria-label') || '') === 'Chọn nhóm mô hình');
  const sliders = [...sc.querySelectorAll('input[type=range], mat-slider')].map(s => ({
    min: s.getAttribute('min'), max: s.getAttribute('max'), value: s.getAttribute('aria-valuenow') || s.value,
  }));
  const credit = sc.querySelector('.settings-credit-cost');
  return {
    chip: n(document.querySelector('button.settings-trigger-button')?.innerText || ''),
    model_button: modelBtn ? n(modelBtn.innerText) : null,
    groups, sliders,
    credit_cost: credit ? n(credit.innerText) : null,
    text: n(sc.innerText).slice(0, 2000),
  };
}
"""

MODEL_ITEMS_JS = r"""
() => {
  const n = s => (s || '').replace(/\s+/g, ' ').trim();
  const panes = [...document.querySelectorAll('.cdk-overlay-pane')].filter(p => p.offsetWidth || p.offsetHeight);
  const menu = panes[panes.length - 1];
  if (!menu || menu.querySelector('.settings-content')) return [];
  return [...menu.querySelectorAll('[role=menuitem]')].map(e => {
    const r = e.getBoundingClientRect();
    return { text: n(e.innerText), x: r.x + r.width / 2, y: r.y + r.height / 2 };
  });
}
"""


def _click(page, x: float, y: float) -> None:
    page.mouse.click(x, y)


def _menu_headline(text: str) -> str:
    """Model menu entries render as ``<icon> <label>`` followed by a deprecation note."""
    first = str(text or "").split(" Sẽ ngừng")[0]
    parts = first.split(" ")
    if parts and parts[0] in ("volume_up", "graphic_eq", "mic"):
        parts = parts[1:]
    return " ".join(parts).strip()


def _open_settings(page) -> bool:
    """Ensure the composer's settings popover is open; returns False if it never appears."""
    if page.evaluate("() => !!document.querySelector('.cdk-overlay-pane .settings-content')"):
        return True
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.evaluate(OPEN_SETTINGS_JS)
    page.wait_for_timeout(900)
    return bool(page.evaluate(f"() => ({PANES_JS})().length > 0"))


def _toggle_in_group(page, group_label: str, item_re: str) -> dict:
    """Click the toggle whose text matches ``item_re`` inside the named group."""
    return page.evaluate(
        r"""([groupLabel, pattern]) => {
        const n = s => (s || '').replace(/\s+/g, ' ').trim();
        const panes = [...document.querySelectorAll('.cdk-overlay-pane')].filter(p => p.offsetWidth || p.offsetHeight);
        const sc = panes.length ? panes[0].querySelector('.settings-content') : null;
        if (!sc) return {ok: false, why: 'no settings popover'};
        const re = new RegExp(pattern);
        const groups = [...sc.querySelectorAll('flow-toggles')];
        const g = groupLabel ? groups.find(x => x.getAttribute('aria-label') === groupLabel) : null;
        if (groupLabel && !g) return {ok: false, why: 'no group ' + groupLabel, labels: groups.map(x => x.getAttribute('aria-label'))};
        const pool = (g || sc).querySelectorAll('mat-button-toggle');
        const t = [...pool].find(x => re.test(n(x.innerText)));
        if (!t) return {ok: false, why: 'no item matching ' + pattern, items: [...pool].map(x => n(x.innerText))};
        const r = t.getBoundingClientRect();
        return {ok: true, text: n(t.innerText), x: r.x + r.width / 2, y: r.y + r.height / 2};
      }""",
        [group_label, item_re],
    )


def select_model(page, model_label: str) -> dict:
    """Open the nested model menu and pick ``model_label`` with a real mouse click."""
    box = page.evaluate(
        r"""() => {
        const n = s => (s || '').replace(/\s+/g, ' ').trim();
        const panes = [...document.querySelectorAll('.cdk-overlay-pane')].filter(p => p.offsetWidth || p.offsetHeight);
        const sc = panes.length ? panes[0].querySelector('.settings-content') : null;
        if (!sc) return null;
        const b = [...sc.querySelectorAll('button')].find(x => (x.getAttribute('aria-label') || '') === 'Chọn nhóm mô hình');
        if (!b) return null;
        const r = b.getBoundingClientRect();
        return {x: r.x + r.width / 2, y: r.y + r.height / 2};
      }"""
    )
    if not box:
        return {"ok": False, "why": "no model button"}
    _click(page, box["x"], box["y"])
    page.wait_for_timeout(900)
    items = page.evaluate(MODEL_ITEMS_JS) or []
    # Menu items carry the material icon ligature in their innerText ("volume_up Omni 1.2 Flash"),
    # so compare on the headline (first line) instead of the raw string.
    hit = next((i for i in items if _menu_headline(i["text"]).startswith(model_label)), None)
    if not hit:
        return {"ok": False, "why": "model not offered", "offered": [_menu_headline(i["text"]) for i in items]}
    _click(page, hit["x"], hit["y"])
    page.wait_for_timeout(1800)
    # Angular closes the popover after a model pick; reopen for the next read.
    return {"ok": True, "item": hit["text"]}


def dump_matrix(page) -> dict:
    """Read the open settings popover, then the model list if it is reachable."""
    state = page.evaluate(DUMP_JS)
    if not state:
        return {"opened": False}
    state["opened"] = True
    return state


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp-url", default="http://localhost:4022")
    ap.add_argument("--project", default=None, help="Flow project uuid to open first")
    ap.add_argument("--out", default="traces/video_model_matrix.json")
    args = ap.parse_args(argv)

    report: dict = {"ts": datetime.now().isoformat(timespec="seconds"), "models": {}, "surfaces": {}}
    with FlowBridge(args.cdp_url, log=lambda m: None) as br:
        page = br.page
        if args.project:
            br.nav_project(args.project)
            page.wait_for_timeout(3500)
        report["url"] = page.url

        if not _open_settings(page):
            print("!! settings popover did not open", file=sys.stderr)
            return 2

        # 1. Image mode first: it is what the page loads with, and its model list is
        #    where Omni 1.2 shows up even before the Video tab is selected.
        report["surfaces"]["image_mode"] = dump_matrix(page)

        # 2. Switch to Video.
        picked = _toggle_in_group(page, "Chế độ", r"Video")
        report["surfaces"]["switch_to_video"] = picked
        if picked.get("ok"):
            _click(page, picked["x"], picked["y"])
            page.wait_for_timeout(1800)
        report["surfaces"]["video_mode"] = dump_matrix(page)

        # 3. Model list (nested pane).
        if _open_settings(page):
            box = page.evaluate(
                "() => { const sc = document.querySelector('.cdk-overlay-pane .settings-content');"
                " const b = sc && [...sc.querySelectorAll('button')].find(x => (x.getAttribute('aria-label')||'') === 'Chọn nhóm mô hình');"
                " if (!b) return null; const r = b.getBoundingClientRect();"
                " return {x: r.x + r.width/2, y: r.y + r.height/2}; }"
            )
            if box:
                _click(page, box["x"], box["y"])
                page.wait_for_timeout(900)
                report["surfaces"]["model_menu"] = page.evaluate(MODEL_ITEMS_JS) or []
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)

        # 4. Per model: reopen the popover, pick the model, read its option groups.
        models = [_menu_headline(i["text"]) for i in report["surfaces"].get("model_menu") or []]
        for label in models:
            if not _open_settings(page):
                report["models"][label] = {"error": "popover did not reopen"}
                continue
            res = select_model(page, label)
            if not res.get("ok"):
                report["models"][label] = res
                continue
            if not _open_settings(page):
                report["models"][label] = {"error": "popover did not reopen after pick"}
                continue
            snap = dump_matrix(page)
            snap["picked"] = res.get("item")
            report["models"][label] = snap
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
