"""Thư viện ảnh sản phẩm — `out/items/<project_id>/`.

Yêu cầu gốc: người dùng có **rất nhiều** sản phẩm, nên không thể buộc mọi ảnh phải khớp
một danh sách `items[]` cố định trong kịch bản. Node ảnh chỉ tick "đây là ảnh sản phẩm"
và ảnh được lưu vào một thư viện dùng lại được cho nhiều bộ phim.
"""

from __future__ import annotations

import pytest

from src.Workflows import item_library as lib


def _png(path, size=(64, 64)):
    from PIL import Image

    Image.new("RGBA", size, (200, 30, 30, 255)).save(path, format="PNG")
    return path


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Áo Kiểu Nữ Donna", "ao_kieu_nu_donna"),
        ("SHEER CARDIGAN", "sheer_cardigan"),
        # "đ" không tách được bằng NFD — phải xử lý riêng, nếu không thành "am".
        ("Quần đầm đen", "quan_dam_den"),
        # Ký tự Windows cấm không được lọt vào tên file.
        ("a/b:c*?d", "a_b_c_d"),
        ("", "item"),
        ("   ", "item"),
    ],
)
def test_safe_item_name(raw, expected):
    assert lib.safe_item_name(raw) == expected


def test_safe_item_name_is_length_capped():
    assert len(lib.safe_item_name("a" * 200)) <= lib._MAX_NAME_LEN


def test_save_item_uses_the_name_the_user_typed(tmp_path):
    src = _png(tmp_path / "generated.png")
    saved = lib.save_item(src, project_id="prj_1", name="Áo Kiểu Nữ Donna", root=tmp_path / "lib")

    assert saved is not None
    assert saved.parent.name == "prj_1"
    assert saved.name == "ao_kieu_nu_donna.png"
    assert saved.read_bytes() == src.read_bytes()


def test_save_item_overwrites_on_rerun(tmp_path):
    """Sinh lại một món phải thay ảnh cũ, không đẻ ra `ao_dai (2).png`."""
    root = tmp_path / "lib"
    a = _png(tmp_path / "a.png", size=(32, 32))
    b = _png(tmp_path / "b.png", size=(128, 128))

    first = lib.save_item(a, project_id="p", name="Ao Dai", root=root)
    second = lib.save_item(b, project_id="p", name="Ao Dai", root=root)

    assert first == second
    assert len(list((root / "p").iterdir())) == 1


def test_projects_are_isolated(tmp_path):
    root = tmp_path / "lib"
    src = _png(tmp_path / "x.png")
    lib.save_item(src, project_id="prj_a", name="Tui", root=root)
    lib.save_item(src, project_id="prj_b", name="Tui", root=root)

    assert [i["name"] for i in lib.list_items("prj_a", root=root)] == ["tui"]
    assert [i["name"] for i in lib.list_items("prj_b", root=root)] == ["tui"]


def test_list_items_newest_first(tmp_path):
    root = tmp_path / "lib"
    lib.save_item(_png(tmp_path / "a.png"), project_id="p", name="first", root=root)
    lib.save_item(_png(tmp_path / "b.png"), project_id="p", name="second", root=root)

    names = [i["name"] for i in lib.list_items("p", root=root)]
    assert names[0] == "second"


def test_find_item_prefers_png(tmp_path):
    """PNG thường đã tách nền — ưu tiên hơn ảnh thô cùng tên."""
    from PIL import Image

    root = tmp_path / "lib"
    d = lib.item_dir("p", root)
    d.mkdir(parents=True)
    Image.new("RGB", (8, 8), (0, 0, 0)).save(d / "tui.jpg", format="JPEG")
    _png(d / "tui.png")

    found = lib.find_item("Túi", project_id="p", root=root)
    assert found is not None and found.suffix == ".png"


def test_missing_source_is_not_an_error(tmp_path):
    """Node có thể báo `ok_no_download` — không có file thì thư viện bỏ qua, không ném."""
    assert lib.save_item(tmp_path / "nope.png", project_id="p", root=tmp_path / "lib") is None


def test_empty_library_lists_nothing(tmp_path):
    assert lib.list_items("chua_co", root=tmp_path / "lib") == []
    assert lib.find_item("gi", project_id="chua_co", root=tmp_path / "lib") is None
