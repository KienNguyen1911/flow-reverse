"""Build a delivery folder (`build_delivery`) and list the ones already built."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from ..script_contract import LookbookScript
from .clips import _attach_clip_qa, _clip_manifest_entry
from .items import _copy_items, _import_item_images
from .models import (
    DEFAULT_DELIVERY_ROOT,
    DELIVERY_VERSION,
    DeliveryError,
    DeliveryResult,
    ItemRef,
    RunRef,
)
from .plate import select_plate
from .readme import _render_readme

# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #


def _build_timeline(script: LookbookScript) -> list[dict]:
    """Đổi `shots[]` (thời gian tương đối trong clip) → thời gian tuyệt đối trên composition."""
    clip_start: dict[str, float] = {}
    cursor = 0.0
    for clip in script.clips:
        clip_start[clip.id] = round(cursor, 3)
        cursor += clip.duration_s

    timeline = []
    for shot in script.shots:
        base = clip_start[shot.clip]
        timeline.append({
            "shot": shot.id,
            "clip": shot.clip,
            "start_s": round(base + shot.clip_offset_s, 3),
            "duration_s": round(shot.duration_s, 3),
            "end_s": round(base + shot.end_s, 3),
            "text": shot.text,
            "text_enter": shot.text_enter,
            "emphasis_item": shot.emphasis_item,
            "transition": shot.transition,
        })
    return timeline


# --------------------------------------------------------------------------- #
# API chính
# --------------------------------------------------------------------------- #


def build_delivery(
    script: LookbookScript,
    run_refs: Iterable[RunRef] = (),
    dest_root: str | Path | None = None,
    *,
    overwrite: bool = False,
    extra_items_source: Optional[Path] = None,
    item_refs: Iterable[ItemRef] = (),
) -> DeliveryResult:
    """Dựng thư mục nguyên liệu cho HyperFrames desktop.

    `run_refs` nối `clips[].id` của script với run đã sinh thật. Clip không có run thì
    vẫn xuất hiện trong manifest với `path: null` và nằm trong `assets_missing` — để
    người dựng biết còn thiếu gì thay vì im lặng bỏ qua.
    """
    root = Path(dest_root) if dest_root else DEFAULT_DELIVERY_ROOT
    delivery_root = root / script.slug

    if delivery_root.exists() and not overwrite:
        raise DeliveryError(
            f"thư mục '{delivery_root}' đã tồn tại. Đặt `overwrite=True` nếu muốn ghi đè."
        )
    delivery_root.mkdir(parents=True, exist_ok=True)
    (delivery_root / "clips").mkdir(exist_ok=True)
    (delivery_root / "items").mkdir(exist_ok=True)
    (delivery_root / "audio").mkdir(exist_ok=True)

    refs_by_clip: dict[str, RunRef] = {}
    for ref in run_refs:
        # Take sau thắng take trước — cho phép truyền nhiều phương án rồi chọn cái cuối.
        prev = refs_by_clip.get(ref.clip_id)
        if prev is None or ref.take >= prev.take:
            refs_by_clip[ref.clip_id] = ref

    missing: list[str] = []
    warnings: list[str] = []

    clip_entries = [
        _clip_manifest_entry(clip, refs_by_clip.get(clip.id), delivery_root / "clips", missing, warnings)
        for clip in script.clips
    ]

    # QA chạy sau khi đã copy đủ clip: gate `chain_match` cần khung cuối của clip nguồn.
    qa_summary_data = _attach_clip_qa(script, clip_entries, delivery_root / "clips")

    # Plate: lấy từ clip đầu tiên có ảnh nền, ưu tiên file đã khai tường minh.
    plate_rel, plate_baked_ui = select_plate(
        script, refs_by_clip, delivery_root, missing, warnings
    )


    # Ảnh sản phẩm sinh từ Flow phải được đưa vào `items/` TRƯỚC khi `_copy_items` kiểm tra,
    # nếu không nó sẽ báo thiếu dù ảnh đã được sinh ra ở out/nodes/.
    imported, extra_items = _import_item_images(
        script, item_refs, delivery_root, missing, warnings
    )
    item_entries, items_copied = _copy_items(script, delivery_root, missing, warnings)
    # Ảnh `is_item` không thuộc `items[]` của script vẫn phải vào manifest — nếu không
    # người dựng mở delivery.json sẽ không biết chúng tồn tại và phải tự dò thư mục.
    declared = {e["id"] for e in item_entries}
    for extra in extra_items:
        if extra["id"] not in declared:
            item_entries.append(extra)
    if imported:
        warnings.append(
            f"đã lấy {len(imported)} ảnh sản phẩm từ run đã sinh: {', '.join(imported)}."
        )
    if extra_items_source and Path(extra_items_source).is_dir():
        extra_dir = delivery_root / "items" / "_source"
        extra_dir.mkdir(parents=True, exist_ok=True)
        for f in sorted(Path(extra_items_source).iterdir()):
            if f.is_file():
                shutil.copy2(f, extra_dir / f.name)

    timeline = _build_timeline(script)

    measured_clips = [c for c in clip_entries if c["duration_s"] is not None]
    has_audio_any = any(bool(c["has_audio"]) for c in clip_entries)
    measured_total = round(sum(c["duration_s"] for c in measured_clips), 3) if measured_clips else 0.0
    # Chỉ so tổng khi đã có ĐỦ clip — thiếu clip là lỗi khác, đã nằm trong `missing`.
    if len(measured_clips) == len(clip_entries) and abs(measured_total - script.total_clip_duration_s) > 0.5:
        warnings.append(
            f"tổng thời lượng đo được {measured_total}s lệch so với script "
            f"{script.total_clip_duration_s}s — kiểm tra lại timeline."
        )

    created = datetime.now().isoformat(timespec="seconds")
    manifest: dict = {
        "version": DELIVERY_VERSION,
        "slug": script.slug,
        "title": script.title,
        "created_ts": created,
        "generator": "Flow Bench / src/Workflows/delivery.py",
        "canvas": {
            "width": script.canvas.get("width", 1080),
            "height": script.canvas.get("height", 1920),
            "fps": script.fps,
            "duration_s": script.duration_s,
            "aspect": script.aspect,
        },
        "plate": plate_rel,
        # True ⇒ plate đang dùng vẫn dính cột UI. Người dựng phải biết trước khi đặt lên
        # timeline, thay vì phát hiện chữ trong pixel khi đã dựng xong.
        "plate_has_baked_ui": plate_baked_ui is not None,
        "clips": clip_entries,
        "items": item_entries,
        "timeline": timeline,
        #: QA thô của toàn bộ clip: trạng thái xấu nhất + từng cảnh báo/gate chưa đo được.
        "qa_summary": qa_summary_data,
        "audio": {
            "bgm": script.audio.get("bgm"),
            "bgm_start_s": script.audio.get("bgm_start_s"),
            "sfx": script.audio.get("sfx") or [],
            # Pipeline strip audio bằng `-an` ở bridge + watermark remover.
            "has_audio": has_audio_any,
        },
        "summary": {
            "clips_expected": len(script.clips),
            "clips_measured": len(measured_clips),
            "clips_missing": [m for m in missing if m.startswith("clips/")],
            "measured_total_s": measured_total,
            "has_audio": has_audio_any,
            "source_fps": next((c["fps"] for c in measured_clips if c["fps"]), None),
        },
        "warnings": warnings,
        "assets_missing": missing,
    }

    manifest_path = delivery_root / "delivery.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    result = DeliveryResult(
        slug=script.slug,
        dest_dir=str(delivery_root.resolve()),
        manifest_path=str(manifest_path.resolve()),
        readme_path=str((delivery_root / "README.md").resolve()),
        assets_missing=missing,
        warnings=warnings,
        clips_copied=[c["path"] for c in clip_entries if c["path"]],
        items_copied=items_copied,
        measured={
            "clips": {
                c["id"]: {
                    "duration_s": c["duration_s"],
                    "fps": c["fps"],
                    "size": f"{c['width']}×{c['height']}" if c["width"] else None,
                    "has_audio": c["has_audio"],
                }
                for c in clip_entries
            },
            "total_s": measured_total,
        },
    )

    (delivery_root / "README.md").write_text(_render_readme(manifest, result), encoding="utf-8")
    return result


def list_deliveries(dest_root: str | Path | None = None) -> list[dict]:
    """Liệt kê các delivery đã dựng (đọc `delivery.json`, bỏ qua thư mục hỏng)."""
    root = Path(dest_root) if dest_root else DEFAULT_DELIVERY_ROOT
    out: list[dict] = []
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        mf = d / "delivery.json"
        if not mf.is_file():
            continue
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append({
            "slug": data.get("slug") or d.name,
            "title": data.get("title"),
            "dest_dir": str(d.resolve()),
            "manifest_path": str(mf.resolve()),
            "created_ts": data.get("created_ts"),
            "canvas": data.get("canvas"),
            "summary": data.get("summary"),
            "warnings": len(data.get("warnings") or []),
            "missing": len(data.get("assets_missing") or []),
        })
    return out
