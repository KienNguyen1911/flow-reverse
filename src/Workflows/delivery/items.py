"""Product stills: find the image a Flow run produced, import it, check it."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable, Optional

from ..item_library import IMAGE_SUFFIXES, safe_item_name
from ..media_probe import probe_media
from ..script_contract import LookbookScript
from .models import ItemRef, repo_root


def _resolve_item_image(ref: ItemRef) -> Optional[Path]:
    """Tìm ảnh sản phẩm của một lần sinh: `file_path` → `run_dir` → `out/nodes/<run_id>`.

    Node ảnh Flow ghi file vào `out/nodes/<run_id>/` với tên do bridge đặt, nên phải dò
    chứ không đoán được. Ưu tiên PNG (đã tách nền), rồi mới tới ảnh thô.
    """
    if ref.file_path:
        p = Path(ref.file_path)
        if not p.is_absolute():
            p = repo_root() / p
        if p.is_file():
            return p
    for raw in (ref.run_dir, str(repo_root() / "out" / "nodes" / ref.run_id) if ref.run_id else ""):
        if not raw:
            continue
        d = Path(raw)
        if not d.is_dir() and not d.is_absolute():
            d = repo_root() / d
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
