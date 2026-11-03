"""Pick the plate (backdrop) for a delivery: prefer a clean file, else salvage one."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from ..script_contract import LookbookScript
from .clips import _resolve_video_path
from .frames import detect_baked_ui_panel
from .models import RunRef, repo_root


def _resolve_plate_candidates(ref: RunRef) -> list[Path]:
    """Ảnh nền ứng viên: plate_path → starting_frame.* → plate.* của run."""
    found: list[Path] = []
    if ref.plate_path:
        p = Path(ref.plate_path)
        if p.is_file():
            found.append(p)
    d = Path(ref.run_dir) if ref.run_dir else None
    if d is not None:
        if not d.is_absolute():
            d = repo_root() / d
        if d.is_dir():
            for pat in ("starting_frame.*", "plate.*", "last_frame.*"):
                for cand in sorted(d.glob(pat)):
                    if cand.is_file() and cand not in found:
                        found.append(cand)
    return found


def select_plate(
    script: LookbookScript,
    refs_by_clip: dict[str, RunRef],
    delivery_root: Path,
    missing: list[str],
    warnings: list[str],
) -> tuple[Optional[str], Optional[dict]]:
    """Chọn + copy `plate.*` vào `delivery_root`.

    Trả `(plate_rel, plate_baked_ui)`: `plate_baked_ui` khác None khi plate cuối vẫn dính
    cột UI dựng sẵn.
    """
    # `extract_clean_plate` được tra trên package lúc gọi để test có thể patch nó ở đó.
    from .. import delivery as _delivery
    plate_rel: Optional[str] = None
    plate_baked_ui: Optional[dict] = None
    for clip in script.clips:
        ref = refs_by_clip.get(clip.id)
        if not ref:
            continue
        cands = _resolve_plate_candidates(ref)
        if not cands:
            continue
        # Bỏ qua ứng viên có cột UI dựng sẵn — ưu tiên file sạch đứng sau nó.
        chosen: Optional[Path] = None
        chosen_baked: Optional[dict] = None
        for cand in cands:
            baked = detect_baked_ui_panel(cand)
            if baked is None:
                chosen = cand
                break
            warnings.append(
                f"bỏ qua plate '{cand.name}' của clip '{clip.id}': phát hiện cột UI dựng sẵn "
                f"trong pixel (vùng trái sáng TB {baked['left_mean']}, bước nhảy cột "
                f"{baked['col_jump']} tại {baked['split_pct']}% bề ngang). "
                "Board cũ không dùng được làm nền — sinh lại bằng skill "
                "`try-on-image-prompter` (chế độ plate)."
            )
        if chosen is None:
            # Cả bộ ứng viên đều dính UI. Trước khi bỏ cuộc, thử cắt một khung sạch từ
            # chính clip: board chỉ nằm ở đoạn đầu, phần còn lại là plate sạch thật.
            video = _resolve_video_path(ref)
            salvaged = _delivery.extract_clean_plate(video, delivery_root) if video else None
            if salvaged:
                plate_rel = salvaged["file"]
                warnings.append(
                    f"plate của clip '{clip.id}' được cắt từ {Path(salvaged['source']).name} tại "
                    f"{salvaged['at_s']}s — board dính UI chỉ nằm ở {salvaged['clean_from_s']}s đầu. "
                    "Khung này sạch nhưng vẫn là ảnh chụp từ video (720×1280), không phải plate "
                    "sinh riêng; muốn nét tối đa thì sinh lại bằng `try-on-image-prompter` "
                    "(chế độ plate)."
                )
                break
            # Không cứu được: vẫn xuất cái cuối để người dựng thấy tận mắt, nhưng ghi cờ
            # trong manifest để không ai dựng phim trên nền dính UI mà không biết.
            chosen = cands[-1]
            chosen_baked = detect_baked_ui_panel(cands[-1]) or {"file": cands[-1].name}
        plate_rel = f"plate{chosen.suffix.lower()}"
        shutil.copy2(chosen, delivery_root / plate_rel)
        if chosen_baked is not None:
            plate_baked_ui = {"file": chosen.name, **chosen_baked}
        break
    if not plate_rel:
        missing.append("plate.png (không tìm thấy starting_frame/plate của clip nào)")
        # Chừa chỗ để người dùng thả file vào sau — thư mục vẫn dùng được.
        (delivery_root / "plate.README.txt").write_text(
            "Chưa có ảnh nền. Chạy node ảnh plate (skill `try-on-image-prompter`, chế độ plate) "
        "rồi export lại, hoặc thả ảnh vào đây "
            "và đổi tên thành plate.png.\n",
            encoding="utf-8",
        )
    return plate_rel, plate_baked_ui
