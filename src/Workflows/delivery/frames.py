"""Pixel/ffmpeg frame work: baked board UI, edge strips, clean-plate extraction.

Nothing here knows the delivery folder layout — these functions only look at
pixels (Pillow/numpy) or shell out to ffmpeg.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ..media_probe import MediaInfo

#: Ngưỡng phát hiện board có cột UI dựng sẵn trong pixel. Đo trên dữ liệu thật của repo
#: (board NABI 768×1376, 42 ảnh Shopee, khung video Flow):
#:   board   → độ sáng trung bình vùng trái 41–46, bước nhảy cột 145–169
#:   ảnh thật → vùng trái sáng 111–255, bước nhảy cột ≤ 120
#: Hai ngưỡng dưới nằm giữa hai cụm, không chạm mép cụm nào.
UI_PANEL_LEFT_MEAN = 80.0
UI_PANEL_COL_JUMP = 140.0


def detect_baked_ui_panel(path: str | Path) -> Optional[dict]:
    """Phát hiện board có cột UI dựng sẵn ở 1/3 trái (kiểu NABI) trong một ảnh.

    Vì sao cần: `plate` của delivery lấy từ `starting_frame.*` của run video. Với các run
    sinh bằng template cũ, chính file đó **là** cái board — export ra là đưa đúng thứ mà
    cả pipeline này tìm cách loại bỏ vào tay người dựng.

    Dấu hiệu — phải hội đủ cả hai, vì mỗi cái riêng lẻ đều gặp phản ví dụ trong dữ liệu:
      1. Vùng trái **tối**: trung bình độ sáng < 80 (board ~41–46; ảnh chụp thật ≥ 111).
      2. Bước nhảy **dựng đứng** ≥ 140 ở 15–55% bề ngang (board 145–169; ảnh thật ≤ 120).
    Đo độ lệch chuẩn theo cột **không** dùng được: board phẳng lì cho std ~100 như nhau ở
    mọi cột, còn ảnh chụp chi tiết nhiều lại cho std cao — dấu hiệu ngược.

    Trả `None` nếu không thấy, ngược lại trả dict số đo để báo cảnh báo có căn cứ.
    """
    try:
        import numpy as np  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError:  # pragma: no cover - Pillow là tùy chọn
        return None

    p = Path(path)
    if not p.is_file():
        return None
    try:
        with Image.open(p) as im:
            gray = np.asarray(im.convert("L")).astype(int)
    except Exception:  # noqa: BLE001 - file hỏng/không phải ảnh thì thôi
        return None

    h, w = gray.shape[:2]
    if w < 40 or h < 40:
        return None

    col_mean = gray.mean(axis=0)
    col_jump, split_x, left_mean = 0.0, 0, 0.0
    for x in range(int(w * 0.15), min(w - 8, int(w * 0.55))):
        left_side = col_mean[max(0, x - 12):x]
        right_side = col_mean[x:x + 12]
        if left_side.size < 6 or right_side.size < 6:
            continue
        jump = abs(float(right_side.mean() - left_side.mean()))
        if jump > col_jump:
            col_jump, split_x = jump, x
            # Đo **bờ trái sát biên**, không đo cả vùng trái: board NABI có các thẻ sản
            # phẩm trắng nằm trong cột tối, lấy trung bình cả vùng sẽ bị kéo sáng và làm
            # mất dấu hiệu (đo thật: bờ biên 41–46, cả vùng ~120).
            left_mean = float(left_side.mean())
    if split_x <= 0:
        return None

    if left_mean < UI_PANEL_LEFT_MEAN and col_jump >= UI_PANEL_COL_JUMP:
        return {
            "left_mean": round(left_mean, 1),
            "col_jump": round(col_jump, 1),
            "split_pct": round(split_x / w * 100, 1),
            "thresholds": {"left_mean": UI_PANEL_LEFT_MEAN, "col_jump": UI_PANEL_COL_JUMP},
        }
    return None


def detect_edge_strip(path: str | Path, *, min_frac: float = 0.5) -> Optional[dict]:
    """Phát hiện dải tối dính sát mép trái — dấu vết board đang bị "xoá ra" khỏi khung.

    `detect_baked_ui_panel` bắt board **đứng yên**; nhưng chuyển cảnh xoá board để lại vài
    chục cột đen ở mép trái trong 1–2 khung. Khung đó không dùng được làm plate dù board
    đã gần biến mất (đo thật: t=1.6s của clip legacy có 19 cột đen sát mép).
    """
    try:
        import numpy as np  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError:  # pragma: no cover
        return None

    p = Path(path)
    if not p.is_file():
        return None
    try:
        with Image.open(p) as im:
            gray = np.asarray(im.convert("L")).astype(int)
    except Exception:  # noqa: BLE001
        return None

    h, w = gray.shape[:2]
    if w < 40:
        return None
    col_dark = (gray < 70).mean(axis=0)
    run = 0
    for frac in col_dark:
        if frac > min_frac:
            run += 1
        else:
            break
    if run >= 3:
        return {"dark_cols": run, "pct_width": round(run / w * 100, 1)}
    return None


def _frame_is_clean(path: Path) -> bool:
    """Khung dùng được làm plate: không board, không dải đen mép trái."""
    return detect_baked_ui_panel(path) is None and detect_edge_strip(path) is None


def _ffmpeg_frame(video: Path, seconds: float, dest: Path) -> bool:
    """Cắt một khung tại mốc `seconds`. Trả False nếu ffmpeg không có/lỗi."""
    try:
        res = subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{seconds:.3f}", "-i", str(video),
             "-frames:v", "1", "-q:v", "1", str(dest)],
            capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0 and dest.is_file() and dest.stat().st_size > 512


def find_ui_clean_point(video: Path, *, step_s: float = 0.1, max_scan_s: float = 3.0) -> Optional[float]:
    """Mốc (giây) đầu tiên mà clip không còn board UI dính pixel.

    Trả `None` nếu khung đầu đã sạch hoặc không đo được. Chỉ quét tối đa `max_scan_s` —
    board trong template cũ biến mất rất sớm; quét hết clip chỉ tốn thời gian.

    Người dựng cần con số này: cắt bỏ 1.3s đầu là mất cả hook, nhưng để nguyên là đưa
    nguyên cột NABI lên sóng. Đây là quyết định của họ, nên phải có số liệu để quyết.
    """
    tmp = video.parent / "_ui_scan"
    tmp.mkdir(exist_ok=True)
    try:
        # Khung 0 sạch ngay ⇒ không có UI, khỏi quét.
        first = tmp / "s000.png"
        if not _ffmpeg_frame(video, 0.0, first) or _frame_is_clean(first):
            return None
        t = step_s
        while t <= max_scan_s:
            cand = tmp / f"s{int(round(t * 100)):04d}.png"
            if _ffmpeg_frame(video, t, cand) and _frame_is_clean(cand):
                return round(t, 3)
            t = round(t + step_s, 3)
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def extract_clean_plate(
    video: Path,
    dest_dir: Path,
    *,
    step_s: float = 0.1,
    settle_s: float = 0.3,
) -> Optional[dict]:
    """Cắt một khung **không dính UI** từ video đã sinh, dùng làm plate dự phòng.

    Vì sao cần: các run sinh bằng template cũ vẫn còn giá trị — chuyển động và người mẫu
    dùng được, chỉ phần đuôi đầu (board) là rác. Quét từng 0.1s tìm mốc board kết thúc,
    rồi lấy khung muộn hơn một nhịp để chuyển động đã ổn định. Không có ffmpeg hoặc cả
    clip đều dính UI thì trả None.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / "_plate_scan"
    tmp.mkdir(exist_ok=True)

    first_clean: Optional[float] = None
    probe = MediaInfo(path=str(video))
    total = probe.duration_s or 8.0
    t = 0.0
    while t < total:
        cand = tmp / f"scan_{int(t * 10):03d}.png"
        if _ffmpeg_frame(video, t, cand) and _frame_is_clean(cand):
            first_clean = t
            break
        t += step_s
    if first_clean is None:
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    # Không lấy mốc sạch **đầu tiên**: ngay sau khi board biến mất vẫn còn 1–2 khung có
    # dải đen mép trái (đo thật: t=1.6s của clip legacy, board đã đi nhưng còn 19 cột đen).
    # Chọn mốc muộn hơn `settle_s`, và nếu mốc đó vẫn dơ thì dò tiếp từng bước.
    out = dest_dir / "plate.png"
    pick_at = min(first_clean + settle_s, max(0.0, total - 0.2))
    chosen_at: Optional[float] = None
    while pick_at < total:
        if _ffmpeg_frame(video, pick_at, out) and _frame_is_clean(out):
            chosen_at = pick_at
            break
        pick_at = round(pick_at + step_s, 3)

    shutil.rmtree(tmp, ignore_errors=True)
    if chosen_at is None:
        out.unlink(missing_ok=True)
        return None
    return {
        "file": out.name,
        "source": str(video),
        "at_s": round(chosen_at, 3),
        "clean_from_s": round(first_clean, 3),
    }
