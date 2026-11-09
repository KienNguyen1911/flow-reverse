"""Delivery DTOs, the error type, and how relative paths find the repo root."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..item_library import safe_item_name
from ..script_contract import ROOT

DEFAULT_DELIVERY_ROOT = ROOT / "out" / "deliveries"

DELIVERY_VERSION = 1


def repo_root() -> Path:
    """Repo root used to resolve relative run/item paths.

    Read off the `delivery` package at call time (not bound at import) so that
    `monkeypatch.setattr(delivery, "ROOT", ...)` still redirects every lookup.
    """
    from .. import delivery

    return delivery.ROOT


class DeliveryError(RuntimeError):
    """Không dựng được thư mục delivery (thiếu script, trùng slug, …)."""


@dataclass
class RunRef:
    """Một run đã sinh ra file (out/nodes/<run_id>/*)."""

    clip_id: str
    run_id: str
    run_dir: str = ""
    take: int = 1
    prompt: str = ""
    seed: Optional[int] = None
    model: str = "macaron_cookie_i2v_8s"
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
