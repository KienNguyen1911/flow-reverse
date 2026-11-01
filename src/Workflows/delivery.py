"""Delivery — đóng gói nguyên liệu dựng phim cho HyperFrames desktop.

Vấn đề mà module này giải: pipeline cũ để nguyên liệu **rải rác** — mỗi run một thư mục
riêng trong `out/nodes/`, mỗi thư mục một `manifest.json` riêng, không có gì nói cho editor
biết clip nào lên timeline ở giây thứ mấy. HyperFrames desktop chỉ nhận **file kéo thả**,
không nhận URL, nên kéo từ gallery hiện tại không dùng được.

Delivery xuất một thư mục tự chứa:

    out/deliveries/<slug>/
    ├── delivery.json     ← hợp đồng máy đọc (timeline + thông số đo thật)
    ├── README.md         ← handoff cho người dựng
    ├── plate.png         ← ảnh nền plate (chỉ người mẫu, không UI)
    ├── clips/clip1.mp4 …
    ├── items/item_1_….png + _review.png
    ├── items/_source/    ← ảnh Shopee gốc đã dùng để sinh cutout
    └── audio/            ← rỗng; `has_audio` khai báo rõ là false

Nguyên tắc: **đo, không đoán**. Mọi `duration_s` / `fps` / `width` trong `delivery.json` đến
từ ffprobe. File thiếu thì ghi vào `assets_missing` và `warnings`, không bịa giá trị.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .item_library import IMAGE_SUFFIXES, safe_item_name
from .media_probe import MediaInfo, probe_media, probe_video
from .script_contract import ClipSpec, LookbookScript, ROOT

DEFAULT_DELIVERY_ROOT = ROOT / "out" / "deliveries"

DELIVERY_VERSION = 1


class DeliveryError(RuntimeError):
    """Không dựng được thư mục delivery (thiếu script, trùng slug, …)."""


# --------------------------------------------------------------------------- #
# DTO
# --------------------------------------------------------------------------- #


@dataclass
class RunRef:
    """Một run đã sinh ra file (out/nodes/<run_id>/*)."""

    clip_id: str
    run_id: str
    run_dir: str = ""
    take: int = 1
    prompt: str = ""
    seed: Optional[int] = None
    model: str = "abra_i2v_8s"
    policy_retries: int = 0
    video_path: Optional[str] = None
    plate_path: Optional[str] = None  # starting_frame / ảnh plate dùng làm nền


@dataclass
class ItemRef:
    """Một ảnh sản phẩm đã sinh bằng node ảnh Flow và được đánh dấu `is_item`.

    Tách khỏi `RunRef` (vốn là clip video) vì vòng đời khác: item là **ảnh tĩnh**, không
    có thời lượng/fps/audio.

    Không bắt buộc thuộc một kịch bản: người bán có rất nhiều món, và cùng một ảnh phục
    vụ nhiều bộ phim. `name` là tên người dùng đặt trên node (dùng để đặt tên file);
    `item_id` chỉ có khi người dùng muốn nối ảnh này vào `items[]` của script.

    Mỗi món chỉ cần **một** ảnh — mặt trước. Thẻ sản phẩm trên timeline hiện 2–3s và
    thường bị chữ che; ảnh lưng là credit không đổi lại được gì.
    """

    name: str = ""
    item_id: Optional[str] = None
    run_id: str = ""
    run_dir: str = ""
    #: Đường dẫn file cụ thể; bỏ trống thì tự dò ảnh trong `run_dir`.
    file_path: Optional[str] = None

    @property
    def key(self) -> str:
        """Khoá gộp trùng: `item_id` nếu có, ngược lại tên đã slugify."""
        return self.item_id or safe_item_name(self.name)


@dataclass
class DeliveryResult:
    slug: str
    dest_dir: str
    manifest_path: str
    readme_path: str
    assets_missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    clips_copied: list[str] = field(default_factory=list)
    items_copied: list[str] = field(default_factory=list)
    measured: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "dest_dir": self.dest_dir,
            "manifest_path": self.manifest_path,
            "readme_path": self.readme_path,
            "assets_missing": self.assets_missing,
            "warnings": self.warnings,
            "clips_copied": self.clips_copied,
            "items_copied": self.items_copied,
            "measured": self.measured,
        }


# --------------------------------------------------------------------------- #
# Lấy thông số clip
# --------------------------------------------------------------------------- #


def _resolve_video_path(ref: RunRef) -> Optional[Path]:
    """Tìm video thật của một run: `video_path` → `<run_dir>/video.mp4` → mp4 đầu tiên."""
    if ref.video_path:
        p = Path(ref.video_path)
        if p.is_file():
            return p
    if ref.run_dir:
        d = Path(ref.run_dir)
        if not d.is_dir() and not d.is_absolute():
            d = ROOT / d
        if d.is_dir():
            for name in ("video.mp4", "output.mp4", "final.mp4"):
                cand = d / name
                if cand.is_file():
                    return cand
            mp4s = sorted(p for p in d.glob("*.mp4") if p.is_file())
            if mp4s:
                return mp4s[0]
    return None


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
        from PIL import Image  # type: ignore
        import numpy as np  # type: ignore
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
        from PIL import Image  # type: ignore
        import numpy as np  # type: ignore
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
            d = ROOT / d
        if d.is_dir():
            for pat in ("starting_frame.*", "plate.*", "last_frame.*"):
                for cand in sorted(d.glob(pat)):
                    if cand.is_file() and cand not in found:
                        found.append(cand)
    return found


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


def _resolve_item_image(ref: ItemRef) -> Optional[Path]:
    """Tìm ảnh sản phẩm của một lần sinh: `file_path` → `run_dir` → `out/nodes/<run_id>`.

    Node ảnh Flow ghi file vào `out/nodes/<run_id>/` với tên do bridge đặt, nên phải dò
    chứ không đoán được. Ưu tiên PNG (đã tách nền), rồi mới tới ảnh thô.
    """
    if ref.file_path:
        p = Path(ref.file_path)
        if not p.is_absolute():
            p = ROOT / p
        if p.is_file():
            return p
    for raw in (ref.run_dir, str(ROOT / "out" / "nodes" / ref.run_id) if ref.run_id else ""):
        if not raw:
            continue
        d = Path(raw)
        if not d.is_dir() and not d.is_absolute():
            d = ROOT / d
        if not d.is_dir():
            continue
        cands = sorted(
            (p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
            key=lambda p: (p.suffix.lower() != ".png", p.name),
        )
        if cands:
            return cands[0]
    return None


def _import_item_images(
    script: LookbookScript,
    item_refs: Iterable[ItemRef],
    delivery_root: Path,
    missing: list[str],
    warnings: list[str],
) -> tuple[list[str], list[dict]]:
    """Copy ảnh sản phẩm sinh từ Flow vào `items/`.

    Hai kiểu đặt tên, đều xuất phát từ **người dùng**, không từ danh sách cứng:

    1. `item_id` có trong `items[]` của script ⇒ dùng đúng đường dẫn `cutout` script khai.
       Dành cho người muốn timeline trỏ tới file cố định.
    2. Chỉ có `name` ⇒ đặt tên theo slug của tên món (`ao_kieu_nu_donna.png`). Đây là
       trường hợp phổ biến: người bán có nhiều món, không khai hết vào script.

    Không tách nền ở đây: ảnh Flow sinh ra đã là flat-lay nền trơn, và matting vẫn cần
    mắt người duyệt (`scripts.cutout_items.py`).
    """
    by_key: dict[str, ItemRef] = {}
    for ref in item_refs:
        key = ref.key
        if not key:
            continue
        # Take sau thắng take trước — cùng quy ước với `run_refs`.
        by_key[key] = ref

    imported: list[str] = []
    extra_items: list[dict] = []
    for key, ref in by_key.items():
        rel: Optional[str] = None
        if ref.item_id:
            try:
                item = script.item(ref.item_id)
            except Exception:  # noqa: BLE001 - script_contract.ScriptError
                # Không phải lỗi: script không khai món này thì vẫn xuất được theo tên.
                item = None
            if item is not None:
                rel = item.cutout
                if not rel:
                    warnings.append(
                        f"script khai `{ref.item_id}` nhưng thiếu `cutout` — dùng tên món thay thế."
                    )

        src = _resolve_item_image(ref)
        if src is None:
            target = rel or f"items/{safe_item_name(ref.name or key)}{'.png'}"
            missing.append(target)
            warnings.append(
                f"không tìm thấy ảnh cho '{ref.name or key}' trong run "
                f"'{ref.run_id or ref.run_dir}'."
            )
            continue

        if rel:
            dest = delivery_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            imported.append(rel)
        else:
            # Không thuộc script: lấy tên người dùng đặt, giữ đuôi thật của file nguồn.
            stem = safe_item_name(ref.name or key)
            suffix = src.suffix.lower() if src.suffix.lower() in IMAGE_SUFFIXES else ".png"
            rel = f"items/{stem}{suffix}"
            dest = delivery_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            imported.append(rel)
            extra_items.append({
                "id": stem,
                "name": ref.name or stem,
                "front": rel,
                "back": None,
                "callout": None,
                "focus_s": None,
                "source_images": [],
            })

        if not _has_alpha(dest):
            warnings.append(
                f"{rel} là ảnh từ Flow (nền trơn, chưa có alpha) — chạy "
                "`python -m scripts.cutout_items` để tách nền trước khi dùng làm card."
            )
    return imported, extra_items


def _copy_items(
    script: LookbookScript,
    delivery_root: Path,
    missing: list[str],
    warnings: list[str],
) -> tuple[list[dict], list[str]]:
    """Copy cutout từ `items/` của delivery (nếu đã có) và ảnh Shopee gốc vào `_source/`.

    Module này **không sinh** ảnh cutout: matting phụ thuộc ảnh nguồn và cần mắt người
    duyệt. Nó chỉ kiểm tra tồn tại + kích thước tối thiểu, rồi ghi vào manifest.
    """
    items_dir = delivery_root / "items"
    source_dir = items_dir / "_source"
    out: list[dict] = []
    copied: list[str] = []

    for item in script.items:
        entry: dict = {
            "id": item.id,
            "name": item.name,
            "front": None,
            "back": None,
            "callout": item.callout,
            "focus_s": item.focus_s,
            "source_images": [],
        }
        for key, rel in (("front", item.cutout), ("back", item.cutout_back)):
            if not rel:
                continue
            p = delivery_root / rel
            if not p.is_file():
                missing.append(rel)
                # Nói rõ vì sao thiếu, để người dựng không đi tìm file vô vọng: ảnh Shopee
                # là lifestyle có người mẫu, tách nền trực tiếp ra người chứ không ra áo.
                warnings.append(
                    f"thiếu cutout `{rel}` — chạy node ảnh với skill "
                    "`lookbook-item-cutout-prompter` (sinh flat-lay trên nền trơn từ ảnh "
                    "Shopee), rồi `python -m scripts.cutout_items` để tách nền."
                )
                continue
            info = probe_media(p)
            if info.measured and info.width and info.height:
                if max(info.width, info.height) < 800:
                    warnings.append(
                        f"{rel} chỉ {info.width}×{info.height} — nhỏ hơn 800px cạnh dài, "
                        "sẽ rỗ bẩn khi phóng to trong composition."
                    )
                if not _has_alpha(p):
                    warnings.append(
                        f"{rel} không có kênh alpha — trên nền composition sẽ thành ảnh chữ nhật."
                    )
            entry[key] = rel
            copied.append(rel)

        # Ảnh Shopee gốc: copy để thư mục tự chứa, người dựng đối chiếu được chất liệu.
        for src_str in item.source_images or []:
            src = Path(src_str)
            if not src.is_file():
                missing.append(f"items/_source/{src.name} (ảnh gốc '{src_str}')")
                continue
            source_dir.mkdir(parents=True, exist_ok=True)
            dest = source_dir / f"{item.id}_{src.name}"
            if not dest.exists():
                shutil.copy2(src, dest)
            entry["source_images"].append(f"items/_source/{dest.name}")
        out.append(entry)

    return out, copied


def _has_alpha(path: Path) -> bool:
    """True nếu ảnh có kênh alpha. Dùng Pillow nếu có, ngược lại đoán theo đuôi file."""
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as im:
            return im.mode in ("RGBA", "LA") or "transparency" in im.info
    except Exception:  # noqa: BLE001 - Pillow không bắt buộc
        return path.suffix.lower() in {".png", ".webp"}


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
# README
# --------------------------------------------------------------------------- #


def _render_readme(manifest: dict, result: DeliveryResult) -> str:
    c = manifest["canvas"]
    lines = [
        f"# Bộ dựng phim — {manifest['title'] or manifest['slug']}",
        "",
        f"- Composition: **{c['width']}×{c['height']} @ {c['fps']}fps**, dài **{c['duration_s']}s**",
        f"- Xuất lúc: {manifest['created_ts']}",
        f"- Nguồn: Google Flow (`abra_i2v_8s`, image-to-video, 8s/clip)",
        "",
        "## Cách dựng trong HyperFrames desktop",
        "",
        "1. Mở HyperFrames desktop, tạo composition **dọc** "
        f"{c['width']}×{c['height']}, timeline {c['duration_s']}s, fps {c['fps']}.",
        f"2. Kéo `{manifest['plate'] or 'plate.png (chưa có)'}` vào track 0 làm nền — "
        "đây là ảnh plate, không có chữ/UI.",
        "3. Kéo từng file trong `clips/` vào track 1 theo đúng `delivery.json → timeline`. "
        "Nếu clip có `ui_clean_from_s` khác null thì **đặt in-point tại mốc đó** — trước mốc "
        "ấy pixel còn board UI dựng sẵn, không gỡ ra được.",
        "4. Kéo cutout trong `items/` vào track 2 khi shot có `emphasis_item`.",
        "5. Thêm chữ theo `timeline[].text` (`text_enter` gợi ý hiệu ứng vào).",
        "",
        "## Quan trọng",
        "",
        f"- **Clip KHÔNG có audio** (`has_audio: {manifest['summary']['has_audio']}`) — "
        "phải thêm BGM riêng.",
        f"- **Nguồn là {c['fps']}fps** — đừng đặt composition 60fps, chỉ nhân bản khung.",
        "- `duration_s` trong manifest là **số đo ffprobe**, không phải tham số yêu cầu; "
        "timeline dùng số đo.",
        "",
        f"## Nội dung",
        "",
        f"- Clips: {len(manifest['clips'])}",
        f"- Items: {len(manifest['items'])}",
        f"- Shots: {len(manifest['timeline'])}",
    ]

    if manifest.get("plate_has_baked_ui"):
        lines += [
            "",
            "## ⚠️ Plate đang dính UI",
            "",
            "Không tìm được ảnh nền sạch cho bộ này. File `"
            f"{manifest.get('plate')}` vẫn còn cột UI dựng sẵn trong pixel.",
            "Chạy node ảnh (skill `try-on-image-prompter`, chế độ plate) rồi export lại — "
            "đừng dựng phim trên nền này.",
        ]

    if manifest["summary"]["clips_missing"] or result.warnings:
        lines += ["", "## Cần kiểm tra", ""]
        for m in manifest["summary"]["clips_missing"]:
            lines.append(f"- ❌ thiếu: `{m}`")
        for w in result.warnings:
            lines.append(f"- ⚠️ {w}")

    lines += ["", "## Timeline", "", "| shot | clip | bắt đầu | dài | chữ | nhấn item |", "| :-- | :-- | --: | --: | :-- | :-- |"]
    for t in manifest["timeline"]:
        text = (t["text"] or "").replace("|", "\\|")
        lines.append(
            f"| {t['shot']} | {t['clip']} | {t['start_s']}s | {t['duration_s']}s | "
            f"{text or '—'} | {t['emphasis_item'] or '—'} |"
        )
    lines.append("")
    return "\n".join(lines)


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

    # Plate: lấy từ clip đầu tiên có ảnh nền, ưu tiên file đã khai tường minh.
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
            salvaged = extract_clean_plate(video, delivery_root) if video else None
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


__all__ = [
    "DEFAULT_DELIVERY_ROOT",
    "DeliveryError",
    "DeliveryResult",
    "RunRef",
    "build_delivery",
    "list_deliveries",
]
