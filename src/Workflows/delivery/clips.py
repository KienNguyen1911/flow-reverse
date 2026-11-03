"""Clips inside a delivery: find a run's video, copy it, measure it, grade it."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional

from ..media_probe import MediaInfo, probe_video
from ..script_contract import ClipSpec, LookbookScript
from .frames import find_ui_clean_point
from .models import RunRef, repo_root


def _resolve_video_path(ref: RunRef) -> Optional[Path]:
    """Tìm video thật của một run: `video_path` → `<run_dir>/video.mp4` → mp4 đầu tiên."""
    if ref.video_path:
        p = Path(ref.video_path)
        if p.is_file():
            return p
    if ref.run_dir:
        d = Path(ref.run_dir)
        if not d.is_dir() and not d.is_absolute():
            d = repo_root() / d
        if d.is_dir():
            for name in ("video.mp4", "output.mp4", "final.mp4"):
                cand = d / name
                if cand.is_file():
                    return cand
            mp4s = sorted(p for p in d.glob("*.mp4") if p.is_file())
            if mp4s:
                return mp4s[0]
    return None


def _clip_manifest_entry(
    clip: ClipSpec,
    ref: Optional[RunRef],
    dest_clips_dir: Path,
    missing: list[str],
    warnings: list[str],
) -> dict:
    entry: dict = {
        "id": clip.id,
        "role": clip.role,
        "camera": clip.camera,
        "chain_from": clip.chain_from,
        "path": None,
        "duration_s": None,
        "width": None,
        "height": None,
        "fps": None,
        "has_audio": None,
        "codec": None,
        #: Giây đầu tiên KHÔNG còn board UI dựng sẵn; None = sạch từ đầu / chưa đo được.
        "ui_clean_from_s": None,
        "usable_duration_s": None,
        "source_run_id": ref.run_id if ref else None,
        "take": ref.take if ref else None,
        "prompt": ref.prompt if ref else clip.motion_prompt,
        "seed": ref.seed if ref else None,
        "model": ref.model if ref else "abra_i2v_8s",
        "policy_retries": ref.policy_retries if ref else 0,
        # Giá trị script yêu cầu, để người dựng biết lệch bao nhiêu so với thực đo.
        "script_duration_s": clip.duration_s,
        #: Kết quả QA thô của clip (`raw_video_qa`). Điền sau khi đã copy file, ở
        #: `_attach_clip_qa` — gate khung nối cần biết clip trước đã có file hay chưa.
        "qa": None,
    }

    if ref is None:
        missing.append(f"clips/{clip.id}.mp4 (chưa có run cho clip '{clip.id}')")
        return entry

    # Lint prompt đã dùng: clip sinh từ pipeline cũ ("đẩy văng cột UI") sẽ dính chữ/UI
    # trong pixel, đúng thứ mà lớp dựng không gỡ ra được. Cảnh báo thay vì im lặng.
    prompt_text = entry.get("prompt") or ""
    if prompt_text:
        hits = [t for t in ("sidebar", "item column", "progress bar", "split screen", "card")
                if re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])", prompt_text, re.IGNORECASE)]
        if hits:
            warnings.append(
                f"clip '{clip.id}' được sinh bằng prompt có từ vựng UI ({', '.join(hits)}) — "
                "khả năng cao pixel đã dính UI/chữ. Nên sinh lại bằng ảnh plate sạch."
            )

    src = _resolve_video_path(ref)
    if src is None:
        missing.append(f"clips/{clip.id}.mp4 (run '{ref.run_id}' không có file video)")
        return entry

    dest = dest_clips_dir / f"{clip.id}{src.suffix.lower()}"
    dest_clips_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)

    info: MediaInfo = probe_video(dest)
    entry["path"] = f"clips/{dest.name}"
    entry["width"] = info.width
    entry["height"] = info.height
    entry["duration_s"] = info.duration_s
    entry["fps"] = info.fps
    entry["has_audio"] = info.has_audio
    entry["codec"] = info.codec

    # Đoạn đầu clip sinh bằng template cũ có board UI nằm trong pixel. Người dựng không
    # gỡ được chữ đã burn-in, nên phải biết chính xác nên đặt in-point ở đâu.
    clean_at = find_ui_clean_point(dest)
    entry["ui_clean_from_s"] = clean_at
    if clean_at is not None:
        entry["usable_duration_s"] = (
            round(info.duration_s - clean_at, 3) if info.duration_s else None
        )
        warnings.append(
            f"clip '{clip.id}' dính board UI trong {clean_at}s đầu — muốn dùng làm B-roll "
            f"sạch thì đặt in-point tại {clean_at}s (còn {entry['usable_duration_s']}s). "
            "Tốt nhất vẫn là sinh lại bằng một ảnh plate sạch."
        )

    if not info.measured:
        warnings.append(f"không đo được thông số {dest.name}: {info.error}")
    else:
        if info.duration_s is not None and abs(info.duration_s - clip.duration_s) > 0.25:
            warnings.append(
                f"clip '{clip.id}' đo được {info.duration_s}s nhưng script khai {clip.duration_s}s — "
                "timeline nên dùng số đo thật."
            )
        if info.has_audio:
            warnings.append(
                f"clip '{clip.id}' có audio track — pipeline thường đã strip bằng `-an`; "
                "kiểm tra lại trước khi trộn âm thanh."
            )
        if info.fps and info.fps not in (24.0, 25.0, 30.0):
            warnings.append(f"clip '{clip.id}' ở {info.fps}fps — lạ so với nguồn Flow (24fps).")
    return entry


def _attach_clip_qa(
    script: LookbookScript,
    entries: list[dict],
    dest_clips_dir: Path,
) -> dict:
    """Chấm QA cho từng clip đã copy và gắn vào entry.

    Chạy **sau** vòng copy vì `chain_match` cần khung cuối của clip nguồn, mà clip nguồn
    chỉ có file ở `dest_clips_dir` sau khi chính nó được copy. Chạy trước thì gate nối
    luôn rơi vào `skip` một cách vô cớ.

    Kết quả chỉ **cảnh báo**: không có gì ném ra ngoài, không gate nào chặn export.
    """
    from ..raw_video_qa import evaluate_clip, qa_summary

    by_id = {e["id"]: e for e in entries}
    clips_qa = []
    for clip in script.clips:
        entry = by_id.get(clip.id)
        if entry is None:
            continue

        dst = dest_clips_dir / Path(entry["path"]).name if entry.get("path") else None
        prev_video = None
        if clip.chain_source_clip:
            prev_entry = by_id.get(clip.chain_source_clip)
            if prev_entry and prev_entry.get("path"):
                prev_video = dest_clips_dir / Path(prev_entry["path"]).name

        qa = evaluate_clip(clip, dst, script, prev_video=prev_video)
        entry["qa"] = qa.to_dict()
        clips_qa.append(qa)

    summary = qa_summary(clips_qa)
    # Không nối vào `warnings` của delivery: README đã có bảng QA riêng, và `_clip_manifest_entry`
    # đã cảnh báo board UI theo cách của nó. Nối thêm là mỗi lỗi hiện hai lần.
    return summary
