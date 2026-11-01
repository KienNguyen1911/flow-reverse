"""Item library — kho ảnh sản phẩm dùng lại được, tách khỏi kịch bản phim.

Vấn đề: một người bán có **hàng trăm** sản phẩm, và cùng một ảnh sản phẩm phục vụ nhiều
bộ phim. Trước đây ảnh sản phẩm chỉ được gắn vào một `items[]` cứng trong
`configs/lookbook_script.json` — nghĩa là mỗi bộ phim phải khai lại danh sách món, và
node ảnh chỉ được chọn trong danh sách đó.

Giờ node ảnh chỉ cần một cờ `is_item`:

    node ảnh (is_item=true)  ──▶  out/items/<project_id>/<tên món>.png

Thư mục này là **thư viện**, không phải hợp đồng: delivery đọc nó như nguồn nguyên liệu,
còn script chỉ nói *món nào lên timeline ở giây nào* nếu muốn đặt tên cụ thể.

Tên file: lấy từ tên món người dùng đặt trên node, slugify để an toàn trên Windows
(không dấu, không khoảng trắng, không ký tự cấm). Trùng tên thì **ghi đè** — đó là chủ ý:
sinh lại một món nên thay ảnh cũ, không đẻ ra `ao_dai (2).png`.
"""

from __future__ import annotations

import os
import re
import shutil
import time
import unicodedata
from pathlib import Path
from typing import Optional

from .script_contract import ROOT

#: `out/items/<project_id>/` — một thư mục cho mỗi workspace project.
PROJECT_ITEMS_ROOT = ROOT / "out" / "items"

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_ITEM_NAME = "item"
_MAX_NAME_LEN = 60

#: Ký tự Windows cấm trong tên file, cộng thêm khoảng trắng/dấu tiếng Việt.
_UNSAFE = re.compile(r"[^a-z0-9]+")


def safe_item_name(name: Optional[str], fallback: str = DEFAULT_ITEM_NAME) -> str:
    """Đổi tên món người dùng gõ thành tên file an toàn.

    Tiếng Việt được bỏ dấu (NFD → ASCII) để tên file không phụ thuộc codepage: `Áo Kiểu
    Nữ Donna` → `ao_kieu_nu_donna`.
    """
    raw = (name or "").strip() or fallback
    decomposed = unicodedata.normalize("NFD", raw)
    ascii_only = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    # `đ` không tách được bằng NFD — xử lý riêng, nếu không "đầm" thành "am".
    ascii_only = ascii_only.replace("đ", "d").replace("Đ", "D")
    slug = _UNSAFE.sub("_", ascii_only.lower()).strip("_")
    return (slug[:_MAX_NAME_LEN].strip("_") or fallback)


def item_dir(project_id: Optional[str], root: Path | None = None) -> Path:
    """Thư mục thư viện của một project. Không có project → thư mục dùng chung."""
    base = Path(root) if root else PROJECT_ITEMS_ROOT
    return base / (project_id or "_shared")


def _stamp_newest(dest: Path, dest_dir: Path) -> None:
    """Đặt mtime của `dest` mới hơn mọi file khác trong thư viện.

    Windows chỉ cho độ phân giải mtime ~15ms, nên hai lần lưu liên tiếp có thể ra **cùng**
    một giá trị — khi đó `list_items` sắp theo mtime sẽ trả thứ tự ngẫu nhiên. Đẩy mtime
    lên trên giá trị lớn nhất hiện có làm thứ tự "mới nhất trước" luôn xác định.

    Không dùng `shutil.copy2`: nó giữ mtime của file nguồn, tức ảnh sản phẩm cũ thêm vào
    hôm nay sẽ nằm cuối danh sách — sai nghĩa "mới nhất".
    """
    try:
        newest = max(
            (p.stat().st_mtime for p in dest_dir.iterdir() if p.is_file() and p != dest),
            default=0.0,
        )
        stamp = max(time.time(), newest + 0.001)
        os.utime(dest, (stamp, stamp))
    except OSError:
        # Không đặt được mtime thì vẫn giữ file; thứ tự có thể lệch, không phải lỗi chặn.
        pass


def save_item(
    src: Path | str,
    *,
    project_id: Optional[str] = None,
    name: Optional[str] = None,
    root: Path | None = None,
) -> Optional[Path]:
    """Chép ảnh vừa sinh vào thư viện, đặt tên theo tên món. Trả `None` nếu không chép được.

    Không ném lỗi: đây là thao tác phụ sau khi sinh ảnh thành công — thư viện hỏng không
    được phép làm job đã thành công quay sang thất bại.
    """
    source = Path(src)
    if not source.is_file():
        return None
    dest_dir = item_dir(project_id, root)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower() if source.suffix.lower() in IMAGE_SUFFIXES else ".png"
        dest = dest_dir / f"{safe_item_name(name)}{suffix}"
        shutil.copy(source, dest)
        _stamp_newest(dest, dest_dir)
        return dest
    except OSError:
        return None


def list_items(
    project_id: Optional[str] = None,
    root: Path | None = None,
) -> list[dict]:
    """Liệt kê thư viện: `[{name, path, size_bytes}]`, mới nhất trước."""
    d = item_dir(project_id, root)
    if not d.is_dir():
        return []
    out: list[dict] = []
    for p in sorted(
        (x for x in d.iterdir() if x.is_file() and x.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    ):
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        out.append({"name": p.stem, "file": p.name, "path": str(p), "size_bytes": size})
    return out


def find_item(
    name: str,
    project_id: Optional[str] = None,
    root: Path | None = None,
) -> Optional[Path]:
    """Tìm ảnh trong thư viện theo tên (đã slugify). Ưu tiên PNG vì thường đã tách nền."""
    slug = safe_item_name(name)
    d = item_dir(project_id, root)
    if not d.is_dir():
        return None
    cands = [
        p
        for p in d.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and p.stem == slug
    ]
    if not cands:
        return None
    cands.sort(key=lambda p: (p.suffix.lower() != ".png", p.name))
    return cands[0]
