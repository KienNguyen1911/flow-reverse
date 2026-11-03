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

Module layout
-------------

    models   DTO (RunRef / ItemRef / DeliveryResult), DeliveryError, repo_root()
    frames   pixel + ffmpeg work: baked-UI board detection, clean-frame extraction
    plate    picking and copying the plate image for a delivery
    clips    resolving a run's video, measuring it, attaching raw-video QA
    items    product stills: resolving, importing, copying, alpha checks
    readme   the human handoff README
    builder  build_delivery() and list_deliveries()

Public names are re-exported here, so ``from src.Workflows.delivery import
build_delivery`` keeps working. ``ROOT`` and ``extract_clean_plate`` stay
readable and writable on this package because tests redirect them: submodules
look both of them up here at call time instead of binding them at import.
"""

from ..script_contract import ROOT  # noqa: F401
from .builder import _build_timeline, build_delivery, list_deliveries  # noqa: F401
from .clips import (  # noqa: F401
    _attach_clip_qa,
    _clip_manifest_entry,
    _resolve_video_path,
)
from .frames import (  # noqa: F401
    UI_PANEL_COL_JUMP,
    UI_PANEL_LEFT_MEAN,
    _ffmpeg_frame,
    _frame_is_clean,
    detect_baked_ui_panel,
    detect_edge_strip,
    extract_clean_plate,
    find_ui_clean_point,
)
from .items import (  # noqa: F401
    _copy_items,
    _has_alpha,
    _import_item_images,
    _resolve_item_image,
)
from .models import (  # noqa: F401
    DEFAULT_DELIVERY_ROOT,
    DELIVERY_VERSION,
    DeliveryError,
    DeliveryResult,
    ItemRef,
    RunRef,
    repo_root,
)
from .plate import _resolve_plate_candidates, select_plate  # noqa: F401
from .readme import _render_readme  # noqa: F401

__all__ = [
    "DEFAULT_DELIVERY_ROOT",
    "DeliveryError",
    "DeliveryResult",
    "RunRef",
    "build_delivery",
    "list_deliveries",
]
