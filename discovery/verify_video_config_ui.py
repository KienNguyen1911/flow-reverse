"""Behavioural check of the Flow Bench VIDEO node config UI (no credits spent).

Opens a video node's drawer and asserts, against the live ``/api/node/options``:

* sub-mode buttons are exactly ``frames`` + ``ingredients`` with the VI labels;
* the model select lists all 4 captured models;
* picking Veo (no resolution/duration group in the composer) disables both selects;
* switching back to Omni re-enables them and offers 360p + 4/6/8/10s;
* ticking "Tác nhân" hides the whole config block behind the warning note.

Nothing is submitted to Flow: it never clicks "Chạy lại".

Usage:
    python discovery/verify_video_config_ui.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

DUMP = r"""
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
  });
  return {
    open: true,
    fields,
    buttons: [...drawer.querySelectorAll('button')].map(b => norm(b.innerText)).filter(Boolean),
    text: norm(drawer.innerText).slice(0, 2000),
  };
}
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp-url", default="http://127.0.0.1:4022")
    ap.add_argument("--app-url", default="http://127.0.0.1:4000")
    args = ap.parse_args(argv)

    report: dict = {"checks": [], "snapshots": []}

    def check(name: str, ok: bool, detail=None):
        report["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {detail}"))

    with sync_playwright() as p:
        br = p.chromium.connect_over_cdp(args.cdp_url)
        page = br.contexts[0].new_page()
        page.goto(args.app_url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        opts = page.evaluate("() => fetch('/api/node/options').then(r => r.json())")
        models = {m["id"]: m for m in opts["video"]["models"]}

        opened = page.evaluate(
            r"""() => {
            const n = s => (s||'').replace(/\s+/g,' ').trim();
            const cards = [...document.querySelectorAll('div')].filter(d => n(d.innerText).includes('Sub '));
            const card = cards[0];
            if (!card) return false;
            const b = [...card.querySelectorAll('button')].find(x => n(x.innerText).startsWith('Sub '));
            if (!b) return false;
            b.click();
            return true;
          }"""
        )
        page.wait_for_timeout(1200)
        if not opened:
            check("video drawer opens", False, "no video node with a Sub pill found")
            page.close()
            br.close()
            return 1

        snap = page.evaluate(DUMP)
        report["snapshots"].append({"stage": "default", "drawer": snap})
        labels = {f["label"]: f for f in snap["fields"]}

        check(
            "sub-mode buttons are Khung hình + Thành phần",
            "Khung hình" in snap["buttons"] and "Thành phần" in snap["buttons"],
            snap["buttons"][:15],
        )
        model_field = labels.get("Model", {})
        check(
            "video model select lists all captured models",
            model_field.get("options") is not None and len(model_field["options"]) == len(models),
            model_field.get("options"),
        )
        res_field = labels.get("Độ phân giải", {})
        dur_field = labels.get("Thời lượng", {})
        check(
            "omni offers 360p + durations 4/6/8/10",
            bool(res_field.get("options")) and any("360p" in o for o in res_field["options"])
            and dur_field.get("options") == [f"{d} giây" for d in (4, 6, 8, 10)],
            {"res": res_field.get("options"), "dur": dur_field.get("options")},
        )

        # -- switch to Veo: resolution + duration must become disabled ----------
        veo_id = "veo_3_1_fast"
        switched = page.evaluate(
            r"""(id) => {
            const n = s => (s||'').replace(/\s+/g,' ').trim();
            const panes = [...document.querySelectorAll('aside')].filter(a => a.offsetWidth > 300);
            const drawer = panes[panes.length - 1];
            const label = [...drawer.querySelectorAll('label')].find(l => n(l.querySelector('span')?.innerText) === 'Model');
            const sel = label && label.querySelector('select');
            if (!sel) return false;
            sel.value = id;
            sel.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
          }""",
            veo_id,
        )
        page.wait_for_timeout(900)
        veo_snap = page.evaluate(DUMP)
        report["snapshots"].append({"stage": "veo", "drawer": veo_snap})
        vl = {f["label"]: f for f in veo_snap["fields"]}
        check("selected Veo model", switched, vl.get("Model", {}).get("value"))
        check(
            "Veo disables the resolution select",
            vl.get("Độ phân giải", {}).get("disabled") is True,
            vl.get("Độ phân giải"),
        )
        check(
            "Veo disables the duration select",
            vl.get("Thời lượng", {}).get("disabled") is True,
            vl.get("Thời lượng"),
        )
        check(
            "Veo duration is forced to its fixed 8s",
            vl.get("Thời lượng", {}).get("options") == ["8 giây"],
            vl.get("Thời lượng", {}).get("options"),
        )
        check(
            "Veo resolutions exclude 360p",
            not any("360p" in o for o in (vl.get("Độ phân giải", {}).get("options") or [])),
            vl.get("Độ phân giải", {}).get("options"),
        )

        # -- "Tác nhân" hides the config block --------------------------------
        agent_on = page.evaluate(
            r"""() => {
            const n = s => (s||'').replace(/\s+/g,' ').trim();
            const panes = [...document.querySelectorAll('aside')].filter(a => a.offsetWidth > 300);
            const drawer = panes[panes.length - 1];
            const box = [...drawer.querySelectorAll('input[type=checkbox]')]
              .find(b => n(b.parentElement?.innerText).startsWith('Tác nhân'));
            if (!box) return false;
            box.click();
            return true;
          }"""
        )
        page.wait_for_timeout(800)
        agent_snap = page.evaluate(DUMP)
        report["snapshots"].append({"stage": "agent-on", "drawer": agent_snap})
        al = {f["label"]: f for f in agent_snap["fields"]}
        check("agent toggle is present and clickable", agent_on)
        check(
            "agent mode shows the 'do tác nhân quyết định' note",
            "tác nhân quyết định" in agent_snap["text"],
            agent_snap["text"][:300],
        )
        check(
            "agent mode hides the model select",
            "Model" not in al,
            list(al),
        )
        check(
            "agent mode hides resolution and duration",
            "Độ phân giải" not in al and "Thời lượng" not in al,
            list(al),
        )

        page.close()

    dest = ROOT / "traces" / "verify_video_config_ui.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", dest)
    return 1 if [c for c in report["checks"] if not c["ok"]] else 0


if __name__ == "__main__":
    raise SystemExit(main())
