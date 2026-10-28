"""Discovery: capture the image aspect-ratio enum for each Flow UI ratio (0 credit).

The image request carries the ratio as an integer at ``args[1][0][4]``
(``docs/api_specs/flow_create_image.md`` §2) and only ``16:9 == 3`` is verified.
Guessing the other values risks spending credits on a wrong ratio, so this probe
reads them from the app itself:

1. Attach to the running CloakBrowser (CDP) and open a Flow project.
2. In Settings, pick Image mode + the target ratio.
3. Arm the ``ogiZ0b`` hook (blocks the app's request — 0 credit), type a probe
   prompt and click Generate.
4. Read the blocked request's ``args[1][0][4]`` and record ratio → enum.
5. Merge into ``configs/image_aspect_enums.json`` (read by
   ``src/Workflows/media_service.py``).

Usage (browser must already be running with a Flow tab, 0 credit):

    python discovery/capture_image_aspects.py --project <uuid>
    python discovery/capture_image_aspects.py --project <uuid> --ratios 9:16 1:1 4:3
    python discovery/capture_image_aspects.py --project <uuid> --dump-only   # list radio labels

If a ratio cannot be selected, pass the exact UI label via ``--label``::

    python discovery/capture_image_aspects.py --project <uuid> --ratios 9:16 --label "9:16"

Findings feed ``docs/api_specs/flow_create_image.md`` §2.1 and the config file is
consumed automatically by the node media API (``/api/node/options``).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.Bridge.flow_bridge import (  # noqa: E402
    DEFAULT_CDP_URL,
    BridgeError,
    FlowBridge,
    parse_captured_args,
)

DEFAULT_OUT = ROOT / "configs" / "image_aspect_enums.json"
TRACE_DIR = ROOT / "traces"

#: Best-effort icon names used by the Flow settings chip for each ratio.
RATIO_ICONS = {
    "16:9": ["crop_16_9", "crop_landscape", "16:9"],
    "9:16": ["crop_9_16", "crop_portrait", "9:16"],
    "1:1": ["crop_square", "crop_1_1", "1:1"],
    "4:3": ["crop_4_3", "4:3"],
    "3:4": ["crop_3_4", "3:4"],
    "3:2": ["crop_3_2", "3:2"],
    "2:3": ["crop_2_3", "2:3"],
}

SETTINGS_BTN = "button.settings-trigger-button"


def _dump_radios(page) -> list[str]:
    labels: list[str] = []
    try:
        for el in page.query_selector_all('//button[@role="radio"]'):
            try:
                txt = " ".join((el.inner_text() or "").split())
                aria = el.get_attribute("aria-label") or ""
                labels.append(f"{txt} | aria={aria}".strip(" |"))
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return labels


def _click_radio(page, candidates: list[str]) -> bool:
    for cand in candidates:
        if not cand:
            continue
        for xp in (
            f'//button[@role="radio" and contains(., "{cand}")]',
            f'//button[@role="radio" and @aria-label="{cand}"]',
        ):
            try:
                el = page.query_selector(xp)
            except Exception:  # noqa: BLE001
                continue
            if el:
                try:
                    el.click(force=True)
                    page.wait_for_timeout(400)
                    return True
                except Exception:  # noqa: BLE001
                    continue
    return False


def _open_settings(page) -> bool:
    btn = page.query_selector(SETTINGS_BTN)
    if not btn:
        return False
    btn.click(force=True)
    page.wait_for_timeout(500)
    return True


def _close_settings(page) -> None:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:  # noqa: BLE001
        pass


def _project_from_url(br: FlowBridge) -> str | None:
    url = br.page.url or ""
    if "/project/" not in url:
        return None
    return url.split("/project/")[1].split("/")[0].split("?")[0].strip().lower() or None


def _capture_ratio(br: FlowBridge, project: str, ratio: str, label: str | None, prompt: str) -> dict:
    page = br.page
    br.nav_home()
    br.nav_project(project)
    try:
        br.wait_composer(timeout_s=40.0)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! composer chưa render: {exc}")

    if not _open_settings(page):
        raise BridgeError("Không thấy nút settings (button.settings-trigger-button) — UI Flow đã đổi?")
    # Image mode first (settings dialog mixes image/video radios).
    _click_radio(page, ["Hình ảnh", "Image", "image"])
    candidates = [label] if label else []
    candidates += RATIO_ICONS.get(ratio, []) + [ratio, ratio.replace(":", "x")]
    if not _click_radio(page, [c for c in candidates if c]):
        labels = _dump_radios(page)
        _close_settings(page)
        raise BridgeError(
            f"Không chọn được tỷ lệ {ratio!r}. Radio đang thấy: {labels or 'không có'}. "
            f"Chạy lại với --label <đúng label ở trên>."
        )
    try:
        chip = (page.query_selector(SETTINGS_BTN).inner_text() or "").strip()
    except Exception:  # noqa: BLE001
        chip = ""
    _close_settings(page)

    br.install_hook()
    br.type_prompt(prompt)
    br.click_generate(timeout_s=30.0)
    cap = br.wait_capture(35.0)
    args = parse_captured_args(cap.body)
    try:
        enum = int(args[1][0][4])
    except Exception as exc:  # noqa: BLE001
        raise BridgeError(f"Không đọc được aspect enum tại args[1][0][4]: {exc}; args={str(args)[:300]}")
    return {"ratio": ratio, "enum": enum, "chip": chip, "request_url": cap.url, "args_head": args[1][0][:6]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Capture Flow image aspect enums (0 credit, blocks app request)")
    ap.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    ap.add_argument("--project", default=None, help="UUID dự án (mặc định: lấy từ tab đang mở)")
    ap.add_argument("--ratios", nargs="+", default=["16:9"], help='Danh sách tỷ lệ, vd: 16:9 9:16 1:1 4:3')
    ap.add_argument("--label", default=None, help="Label UI chính xác cho MỌI tỷ lệ (khi tên icon khác dự đoán)")
    ap.add_argument("--prompt", default="aspect probe", help="Prompt thăm dò (request bị chặn, 0 credit)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--dump-only", action="store_true", help="Chỉ in radio labels trong settings, không capture")
    args = ap.parse_args(argv)

    with FlowBridge(args.cdp_url) as br:
        print(f"attached: {br.page.url}")
        project = args.project or _project_from_url(br)
        if not project:
            raise SystemExit("Không có --project và tab hiện tại không ở trong dự án Flow.")

        if args.dump_only:
            br.nav_home()
            br.nav_project(project)
            time.sleep(2.0)
            if not _open_settings(br.page):
                raise SystemExit("Không thấy nút settings.")
            print("radio labels trong settings:")
            for lbl in _dump_radios(br.page):
                print("  -", lbl)
            _close_settings(br.page)
            return 0

        results: list[dict] = []
        for ratio in args.ratios:
            print(f"\n=== {ratio} ===")
            try:
                info = _capture_ratio(br, project, ratio, args.label, args.prompt)
                print(f"  OK: enum={info['enum']} chip={info['chip']!r}")
                results.append(info)
            except Exception as exc:  # noqa: BLE001
                print(f"  FAIL: {type(exc).__name__}: {exc}")
            finally:
                try:
                    br.reload(settle_s=4.0)
                except Exception:  # noqa: BLE001
                    pass

    if not results:
        print("\nKhông capture được tỷ lệ nào.")
        return 1

    out_path = Path(args.out)
    data: dict = {"version": 1, "ratios": {}}
    try:
        if out_path.is_file():
            raw = json.loads(out_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update({"version": raw.get("version", 1)})
                data["ratios"] = dict(raw.get("ratios") or {})
    except Exception:  # noqa: BLE001
        pass
    for info in results:
        data["ratios"][info["ratio"]] = int(info["enum"])
    data["captured_ts"] = datetime.now().isoformat(timespec="seconds")
    data["source"] = "discovery/capture_image_aspects.py"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nĐã ghi {out_path} → {data['ratios']}")

    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    trace = TRACE_DIR / f"image_aspects_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    trace.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Trace: {trace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
