"""Discovery: does Flow expose text-to-video, or only image-to-video? (0 credit)

Everything we reverse-engineered so far is ``abra_i2v_8s`` (image-to-video): the
``eb1hJf`` payload always carries a ``starting_frame_media_id``. A canvas video
node without an attached image therefore needs evidence before we promise it.

This probe:

1. attaches to the running CloakBrowser and opens a Flow project;
2. dumps the composer state + Settings radios (to spot a "no frame" / text mode);
3. arms both hooks (``ogiZ0b`` and ``eb1hJf`` are blocked → 0 credit);
4. switches the composer to Video + Frames mode and clicks Generate **without**
   attaching a starting frame;
5. records whether an ``eb1hJf`` request was captured and whether it contains a
   starting-frame slot.

Output: ``traces/video_composer_probe_<ts>.json`` (Observed Evidence only; no
inference is written into the capture section).

Usage:

    python discovery/probe_video_composer.py --project <uuid>
    python discovery/probe_video_composer.py --project <uuid> --frame out/uploads/x.png

Findings feed ``docs/api_specs/flow_create_video.md`` §2.1 (mode matrix) and the
``supports_text_to_video`` flag in ``/api/node/options``.
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

from src.Bridge.flow_bridge import (  # noqa: E402
    DEFAULT_CDP_URL,
    FlowBridge,
)
from src.Bridge.flow_video_bridge import (  # noqa: E402
    FlowVideoBridge,
    extract_starting_frame_from_eb1hjf_args,
    parse_video_app_capture,
)

TRACE_DIR = ROOT / "traces"
SETTINGS_BTN = "button.settings-trigger-button"


def _dump_buttons(page) -> list[str]:
    out: list[str] = []
    try:
        for b in page.query_selector_all("button"):
            try:
                aria = (b.get_attribute("aria-label") or "").strip()
                text = " ".join((b.inner_text() or "").split())[:60]
                label = f"{aria} | {text}".strip(" |")
                if label:
                    out.append(label)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return out[:80]


def _dump_radios(page) -> list[str]:
    out: list[str] = []
    try:
        for el in page.query_selector_all('//button[@role="radio"]'):
            try:
                txt = " ".join((el.inner_text() or "").split())
                aria = el.get_attribute("aria-label") or ""
                out.append(f"{txt} | aria={aria}".strip(" |"))
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return out


def _composer_state(page) -> dict:
    try:
        chip = (page.query_selector(SETTINGS_BTN).inner_text() or "").strip()
    except Exception:  # noqa: BLE001
        chip = ""
    return {
        "settings_chip": chip,
        "ingredient_chips": len(page.query_selector_all("flow-image-ingredient-chip")),
        "start_buttons": len(page.query_selector_all('//button[contains(., "Bắt đầu") or contains(., "Start")]')),
    }


def _project_from_url(br: FlowBridge) -> str | None:
    url = br.page.url or ""
    if "/project/" not in url:
        return None
    return url.split("/project/")[1].split("/")[0].split("?")[0].strip().lower() or None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Probe video composer for a text-to-video mode (0 credit)")
    ap.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    ap.add_argument("--project", default=None, help="UUID dự án (mặc định: tab đang mở)")
    ap.add_argument("--prompt", default="a slow cinematic camera move", help="Prompt thăm dò")
    ap.add_argument("--frame", default=None, help="(tuỳ chọn) ảnh để chạy đối chứng có starting frame")
    ap.add_argument("--aspect", default="9:16", choices=["9:16", "16:9"])
    args = ap.parse_args(argv)

    trace: dict = {"ts": datetime.now().isoformat(timespec="seconds"), "cdp_url": args.cdp_url}
    video = FlowVideoBridge(cdp_url=args.cdp_url)

    with FlowBridge(args.cdp_url) as br:
        project = args.project or _project_from_url(br)
        if not project:
            raise SystemExit("Không có --project và tab hiện tại không ở trong dự án Flow.")
        trace["project"] = project

        br.nav_home()
        br.nav_project(project)
        try:
            br.wait_composer(timeout_s=40.0)
        except Exception as exc:  # noqa: BLE001
            print(f"composer chưa render: {exc}")

        page = br.page
        trace["composer"] = _composer_state(page)
        trace["buttons"] = _dump_buttons(page)
        print(f"composer: {trace['composer']}")

        btn = page.query_selector(SETTINGS_BTN)
        if btn:
            btn.click(force=True)
            page.wait_for_timeout(600)
            trace["settings_radios"] = _dump_radios(page)
            print("settings radios:")
            for lbl in trace["settings_radios"]:
                print("  -", lbl)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        else:
            trace["settings_radios"] = []

        # Force Video + Frames mode; abort (no click) if the UI does not comply so
        # we never risk an unblocked request.
        mode_ok = False
        try:
            video._ensure_ui_video_frames_mode(page, args.aspect)
            chip = (page.query_selector(SETTINGS_BTN).inner_text() or "").strip()
            icon = f"crop_{args.aspect.replace(':', '_')}"
            mode_ok = ("Video" in chip) and (icon in chip or args.aspect in chip)
            trace["chip_after_mode"] = chip
        except Exception as exc:  # noqa: BLE001
            trace["mode_error"] = f"{type(exc).__name__}: {exc}"
        trace["video_mode_confirmed"] = mode_ok
        print(f"video mode confirmed: {mode_ok}")

        no_frame: dict = {"clicked": False}
        if not mode_ok:
            no_frame["skipped"] = "Không xác nhận được Video + Khung hình mode — không click để tránh tốn credit."
        else:
            br.install_hook()  # blocks ogiZ0b (0 credit) as well
            video.install_video_hook(br)
            br._eval("window.__blockVideoGen = true; window.__videoHook.cap = null;")
            br.type_prompt(args.prompt)
            try:
                br.click_generate(timeout_s=20.0)
                no_frame["clicked"] = True
                cap = video.wait_video_capture(br, timeout_s=20.0)
                _, _at, cap_args, rpcid = parse_video_app_capture(cap["body"])
                sf_id, crop_box = extract_starting_frame_from_eb1hjf_args(cap_args)
                no_frame.update(
                    {
                        "rpcid": rpcid,
                        "captured": True,
                        "has_starting_frame": bool(sf_id),
                        "starting_frame_media_id": sf_id,
                        "crop_box": crop_box,
                        "args_excerpt": str(cap_args)[:600],
                        "capture_url": cap.get("url"),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                no_frame["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                video.disarm_video_hook(br)
                try:
                    br._eval("window.__blockOgi = false; true")
                except Exception:  # noqa: BLE001
                    pass
        trace["no_frame_try"] = no_frame
        print(f"no-frame try: {json.dumps(no_frame, ensure_ascii=False)[:500]}")

        # Optional control: same composer with an attached frame (0 credit, blocked).
        if args.frame:
            control: dict = {}
            try:
                frame = Path(args.frame)
                if not frame.is_file():
                    raise FileNotFoundError(frame)
                br.install_hook()
                video.install_video_hook(br)
                video._ensure_ui_video_frames_mode(page, args.aspect)
                media_id = video.upload_starting_frame_via_paste(br, frame, project_id=project, timeout_s=35.0)
                if not page.query_selector("flow-image-ingredient-chip"):
                    video._attach_starting_frame_ui_fallback(page, frame)
                br._eval("window.__blockVideoGen = true; window.__videoHook.cap = null;")
                br.type_prompt(args.prompt)
                br.click_generate(timeout_s=20.0)
                cap = video.wait_video_capture(br, timeout_s=25.0)
                _, _at, cap_args, rpcid = parse_video_app_capture(cap["body"])
                sf_id, crop_box = extract_starting_frame_from_eb1hjf_args(cap_args)
                control = {
                    "rpcid": rpcid,
                    "captured": True,
                    "uploaded_media_id": media_id,
                    "has_starting_frame": bool(sf_id),
                    "starting_frame_media_id": sf_id,
                    "crop_box": crop_box,
                    "args_excerpt": str(cap_args)[:600],
                }
            except Exception as exc:  # noqa: BLE001
                control = {"error": f"{type(exc).__name__}: {exc}"}
            finally:
                video.disarm_video_hook(br)
            trace["with_frame_control"] = control
            print(f"with-frame control: {json.dumps(control, ensure_ascii=False)[:400]}")

    nf = trace.get("no_frame_try") or {}
    if nf.get("captured") and not nf.get("has_starting_frame"):
        trace["conclusion"] = "eb1hJf không có starting frame → có thể thử payload không frame (cần validate)."
    elif nf.get("captured"):
        trace["conclusion"] = "eb1hJf vẫn có starting frame dù UI không đính ảnh → protocol là i2v-only."
    else:
        trace["conclusion"] = "Không bắt được eb1hJf khi không có frame → nhiều khả năng UI chặn generate (i2v-only)."

    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    out = TRACE_DIR / f"video_composer_probe_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    out.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nTrace: {out}\nKết luận (evidence-based): {trace['conclusion']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
