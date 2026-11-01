"""Cutout cả bộ: alpha có nhiều mảnh rời thì không dùng được làm card sản phẩm."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from scripts.cutout_items import _validate  # noqa: E402


def _plate(path: Path, boxes: list[tuple[int, int, int, int]]) -> Path:
    im = Image.new("RGBA", (900, 1100), (0, 0, 0, 0))
    for x0, x1, y0, y1 in boxes:
        for y in range(y0, y1):
            for x in range(x0, x1):
                im.putpixel((x, y), (200, 120, 80, 255))
    im.save(path)
    return path


def test_single_piece_passes(tmp_path):
    res = _validate(_plate(tmp_path / "one.png", [(300, 600, 200, 900)]))
    assert res["pieces"] == 1
    assert res["ok"] is True


def test_full_set_two_pieces_is_rejected(tmp_path):
    """Cả bộ ⇒ bbox gộp cả hai món, card sẽ hở khoảng trống giữa chúng."""
    res = _validate(
        _plate(tmp_path / "two.png", [(180, 420, 150, 560), (480, 720, 560, 980)])
    )
    assert res["pieces"] == 2
    assert res["ok"] is False
    assert any("CẢ BỘ" in p for p in res["problems"])


def test_tiny_speck_is_not_a_second_piece(tmp_path):
    """Mảnh rác vài pixel (dây, nút rời) không được làm ảnh một món bị loại."""
    res = _validate(
        _plate(tmp_path / "speck.png", [(300, 600, 200, 900), (601, 606, 200, 205)])
    )
    assert res["pieces"] == 1
    assert res["ok"] is True
