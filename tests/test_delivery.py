"""Kiểm tra hợp đồng script + delivery export + đo media.

Trọng tâm: manifest phải chứa **số đo thật** (ffprobe), không phải tham số 8s mặc định —
editor HyperFrames đặt clip lên timeline theo manifest, sai số ở đây làm lệch cả bộ phim.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.Workflows.delivery import DeliveryError, RunRef, build_delivery, list_deliveries
from src.Workflows.media_probe import have_ffprobe, probe_media, probe_video
from src.Workflows.script_contract import (
    CLIP_MAX_S,
    ScriptError,
    load_default_script,
    load_script,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_VIDEO = ROOT / "out" / "nodes" / "video_20261030_230016" / "video.mp4"

needs_ffmpeg = pytest.mark.skipif(not have_ffprobe(), reason="ffprobe không có trong PATH")


# --------------------------------------------------------------------------- #
# Script contract
# --------------------------------------------------------------------------- #


def test_default_script_loads_and_validates():
    s = load_default_script()
    assert s is not None
    assert s.slug
    assert s.fps in (24, 30), "fps là trần nguồn, không phải mục tiêu thẩm mỹ"
    assert s.canvas["width"] == 1080 and s.canvas["height"] == 1920
    # Timeline phải phủ đúng tổng độ dài clip.
    assert abs(s.total_clip_duration_s - s.duration_s) < 1e-6


def test_script_rejects_fps_above_source_ceiling():
    raw = json.loads((ROOT / "configs" / "lookbook_script.json").read_text(encoding="utf-8"))
    raw["fps"] = 60
    with pytest.raises(ScriptError, match="fps"):
        load_script(raw)


def test_script_rejects_clip_longer_than_flow_limit():
    raw = json.loads((ROOT / "configs" / "lookbook_script.json").read_text(encoding="utf-8"))
    raw["clips"][0]["duration_s"] = 12
    with pytest.raises(ScriptError, match=str(int(CLIP_MAX_S))):
        load_script(raw)


def test_script_rejects_dangling_chain_and_orphan_shot():
    raw = json.loads((ROOT / "configs" / "lookbook_script.json").read_text(encoding="utf-8"))

    bad_chain = json.loads(json.dumps(raw))
    bad_chain["clips"][1]["chain_from"] = "clip9.last_frame"
    with pytest.raises(ScriptError, match="clip9"):
        load_script(bad_chain)

    bad_shot = json.loads(json.dumps(raw))
    bad_shot["shots"][0]["clip"] = "clip9"
    with pytest.raises(ScriptError, match="clip9"):
        load_script(bad_shot)


def test_script_rejects_shot_overflowing_its_clip():
    raw = json.loads((ROOT / "configs" / "lookbook_script.json").read_text(encoding="utf-8"))
    raw["shots"][0]["duration_s"] = 99
    with pytest.raises(ScriptError, match="kết thúc"):
        load_script(raw)


def test_chain_source_clip_parses_last_frame_notation():
    s = load_default_script()
    clip2 = s.clip("clip2")
    assert clip2.chain_from == "clip1.last_frame"
    assert clip2.chain_source_clip == "clip1"


# --------------------------------------------------------------------------- #
# Media probe
# --------------------------------------------------------------------------- #


@needs_ffmpeg
def test_probe_video_measures_real_source_rate():
    if not SAMPLE_VIDEO.is_file():
        pytest.skip("chưa có video mẫu trong out/nodes")
    info = probe_video(SAMPLE_VIDEO)
    assert info.measured
    assert info.kind == "video"
    # Nguồn Flow: 720×1280 @ 24fps, không audio (bridge strip bằng -an).
    assert (info.width, info.height) == (720, 1280)
    assert info.fps == 24.0
    assert abs((info.duration_s or 0) - 8.0) < 0.1
    assert info.has_audio is False


def test_probe_missing_file_is_graceful():
    info = probe_media("does/not/exist.mp4")
    assert info.measured is False
    assert info.duration_s is None
    assert info.error


@needs_ffmpeg
def test_probe_classifies_still_image_as_image_not_video(tmp_path):
    """ffprobe bọc JPEG trong stream `codec_type=video` — không được coi là video."""
    from PIL import Image

    img = tmp_path / "plate.jpg"
    Image.new("RGB", (768, 1376), (240, 240, 240)).save(img)
    info = probe_media(img)
    assert info.measured
    assert info.kind == "image"
    # Ảnh tĩnh không có thời lượng — 0.04s là rác nếu đem đặt lên timeline.
    assert info.duration_s is None
    assert info.fps is None


# --------------------------------------------------------------------------- #
# Delivery build
# --------------------------------------------------------------------------- #


def _refs():
    return [RunRef(clip_id="clip1", run_id="video_20261030_230016",
                   run_dir="out/nodes/video_20261030_230016")]


def test_delivery_without_runs_still_produces_manifest(tmp_path):
    """Không có run nào cũng phải ra manifest — để người dựng thấy còn thiếu gì."""
    s = load_default_script()
    res = build_delivery(s, [], dest_root=tmp_path)
    m = json.loads(Path(res.manifest_path).read_text(encoding="utf-8"))

    assert m["canvas"]["fps"] == 24
    assert m["canvas"]["width"] == 1080
    assert len(m["clips"]) == len(s.clips)
    assert all(c["path"] is None for c in m["clips"])
    assert any("clips/clip1.mp4" in x for x in m["assets_missing"])
    assert Path(res.readme_path).is_file()


def test_delivery_measures_clip_duration_not_script_value(tmp_path):
    if not SAMPLE_VIDEO.is_file():
        pytest.skip("chưa có video mẫu trong out/nodes")
    s = load_default_script()
    res = build_delivery(s, _refs(), dest_root=tmp_path)
    m = json.loads(Path(res.manifest_path).read_text(encoding="utf-8"))

    clip1 = next(c for c in m["clips"] if c["id"] == "clip1")
    assert clip1["path"] == "clips/clip1.mp4"
    assert (tmp_path / s.slug / "clips" / "clip1.mp4").is_file()
    # Phải là số đo, không phải hằng số 8 trong script.
    assert clip1["duration_s"] == pytest.approx(8.0, abs=0.1)
    assert clip1["fps"] == 24.0
    assert clip1["has_audio"] is False
    # Tham số script vẫn giữ để so sánh.
    assert clip1["script_duration_s"] == 8


def test_delivery_timeline_uses_absolute_composition_time(tmp_path):
    s = load_default_script()
    res = build_delivery(s, [], dest_root=tmp_path)
    m = json.loads(Path(res.manifest_path).read_text(encoding="utf-8"))
    tl = {t["shot"]: t for t in m["timeline"]}

    # clip1 bắt đầu ở 0s, clip2 bắt đầu ở 8s (duration clip1).
    assert tl["s1"]["start_s"] == 0.0
    assert tl["s2"]["start_s"] == 3.0
    assert tl["s3"]["start_s"] == 8.0
    assert tl["s4"]["start_s"] == 13.0
    assert tl["s4"]["end_s"] == 16.0


def test_delivery_refuses_to_clobber_without_overwrite(tmp_path):
    s = load_default_script()
    build_delivery(s, [], dest_root=tmp_path)
    with pytest.raises(DeliveryError, match="đã tồn tại"):
        build_delivery(s, [], dest_root=tmp_path)
    # Có overwrite thì chạy lại được.
    build_delivery(s, [], dest_root=tmp_path, overwrite=True)


def test_delivery_copies_shopee_sources_into_self_contained_dir(tmp_path):
    s = load_default_script()
    res = build_delivery(s, [], dest_root=tmp_path)
    m = json.loads(Path(res.manifest_path).read_text(encoding="utf-8"))
    src_dir = tmp_path / s.slug / "items" / "_source"

    item1 = next(i for i in m["items"] if i["id"] == "item_1")
    real_sources = [p for p in (item1["source_images"] or []) if (tmp_path / s.slug / p).is_file()]
    if item1["source_images"] and not real_sources:
        pytest.skip("ảnh Shopee nguồn không có trên máy này")
    for rel in real_sources:
        assert (tmp_path / s.slug / rel).is_file()
        assert rel.startswith("items/_source/")
    assert src_dir.is_dir() or not real_sources


def test_delivery_warns_when_take_mismatch_audio_present(tmp_path):
    """Clip có audio hoặc sai fps phải cảnh báo, không im lặng."""
    s = load_default_script()
    # Tạo video giả có audio track (1s, 48kHz) để kiểm tra cảnh báo.
    run_dir = tmp_path / "fake_run"
    run_dir.mkdir()
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg không có trong PATH")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=gray:s=720x1280:d=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", "-shortest",
         str(run_dir / "video.mp4")],
        capture_output=True, check=True,
    )
    res = build_delivery(
        s, [RunRef(clip_id="clip1", run_id="fake", run_dir=str(run_dir))],
        dest_root=tmp_path / "deliv",
    )
    m = json.loads(Path(res.manifest_path).read_text(encoding="utf-8"))
    clip1 = next(c for c in m["clips"] if c["id"] == "clip1")
    assert clip1["has_audio"] is True
    assert any("audio" in w for w in m["warnings"]), m["warnings"]
    assert any("lệch" in w or "script khai" in w for w in m["warnings"]), m["warnings"]


def test_delivery_warns_on_legacy_ui_baked_prompt(tmp_path):
    """Clip sinh bằng prompt 'đẩy văng cột UI' phải bị cảnh báo — pixel đã dính UI."""
    s = load_default_script()
    legacy = ("Camera LOCKED. The model pushes the entire left item column out of frame. "
              "The sidebar flies out with motion blur.")
    res = build_delivery(
        s, [RunRef(clip_id="clip1", run_id="legacy", run_dir=str(tmp_path / "nope"),
                   prompt=legacy)],
        dest_root=tmp_path / "deliv",
    )
    assert any("từ vựng UI" in w for w in res.warnings), res.warnings


# --------------------------------------------------------------------------- #
# Phát hiện UI dựng sẵn trong pixel
# --------------------------------------------------------------------------- #

#: Board NABI thật do template cũ sinh (768×1376, cột tối 1/3 trái). Có trong repo nên
#: không phải dựng fixture giả: đây chính là file mà pipeline cũ xuất ra.
BOARD_SAMPLE = ROOT / "out" / "nodes" / "video_20261030_230016" / "starting_frame.jpg"


def _fake_board(path: Path, *, panel_w: int = 260, w: int = 768, h: int = 1376) -> Path:
    """Dựng ảnh board tổng hợp: cột tối bên trái + nền sáng bên phải."""
    from PIL import Image as _Image

    im = _Image.new("RGB", (w, h), (232, 226, 214))
    for y in range(h):
        for x in range(panel_w):
            im.putpixel((x, y), (26, 26, 28))
    im.save(path)
    return path


def _fake_shopee(path: Path, *, w: int = 768, h: int = 1376) -> Path:
    """Dựng ảnh 'chụp thật' tổng hợp: gradient mềm, không cột tối phẳng nào."""
    from PIL import Image as _Image

    im = _Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            v = 140 + (x * 60 // w) + (y * 30 // h)
            px[x, y] = (v, v - 8, v - 20)
    im.save(path)
    return path


def test_detect_baked_ui_panel_flags_real_board():
    if not BOARD_SAMPLE.is_file():
        pytest.skip("không có ảnh board mẫu trong out/nodes")
    from src.Workflows.delivery import detect_baked_ui_panel

    hit = detect_baked_ui_panel(BOARD_SAMPLE)
    assert hit is not None
    # Vùng trái của board tối hẳn, và biên panel là bước nhảy dựng đứng.
    assert hit["left_mean"] < 80
    assert hit["col_jump"] >= 140
    # Board chiếm ~1/3 bề ngang — đúng crop 453px mà pipeline cũ ép lên 1080.
    assert 20 < hit["split_pct"] < 55


def test_detect_baked_ui_panel_ignores_photo_without_panel(tmp_path):
    from src.Workflows.delivery import detect_baked_ui_panel

    assert detect_baked_ui_panel(_fake_shopee(tmp_path / "photo.jpg")) is None


def test_detect_baked_ui_panel_survives_missing_file(tmp_path):
    from src.Workflows.delivery import detect_baked_ui_panel

    assert detect_baked_ui_panel(tmp_path / "nope.jpg") is None


def test_detect_edge_strip_flags_residual_panel_border(tmp_path):
    """Board đang bị xoá để lại vài chục cột đen sát mép — khung đó không dùng làm plate."""
    from src.Workflows.delivery import detect_edge_strip

    strip = _fake_board(tmp_path / "strip.png", panel_w=19)
    assert detect_edge_strip(strip) is not None
    assert detect_edge_strip(_fake_shopee(tmp_path / "clean.jpg")) is None


def test_delivery_prefers_declared_clean_plate_over_baked_frame(tmp_path, monkeypatch):
    """Có plate sạch khai tường minh thì dùng nó, không lấy board `starting_frame`."""
    from src.Workflows import delivery as dv

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _fake_board(run_dir / "starting_frame.jpg")
    clean_plate = _fake_shopee(tmp_path / "plate_clean.jpg")

    # Không có ffmpeg hoặc clip sạch: ép nhánh "không cứu được".
    monkeypatch.setattr(dv, "extract_clean_plate", lambda *a, **k: None)
    s = load_default_script()
    res = build_delivery(
        s,
        [RunRef(clip_id="clip1", run_id="r1", run_dir=str(run_dir),
                 plate_path=str(clean_plate))],
        dest_root=tmp_path / "deliv",
    )
    m = json.loads(Path(res.manifest_path).read_text(encoding="utf-8"))
    # Plate khai tường minh đứng đầu danh sách ứng viên ⇒ board không bao giờ được chọn,
    # nên cũng không cần cảnh báo (không có gì bị bỏ qua).
    assert m["plate"] == "plate.jpg"
    assert m["plate_has_baked_ui"] is False


def test_delivery_skips_baked_frame_when_clean_one_follows(tmp_path, monkeypatch):
    """`starting_frame.jpg` dính UI nhưng run còn `plate.png` sạch ⇒ phải lấy plate.png."""
    from src.Workflows import delivery as dv

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _fake_board(run_dir / "starting_frame.jpg")
    _fake_shopee(run_dir / "plate.png")

    monkeypatch.setattr(dv, "extract_clean_plate", lambda *a, **k: None)
    s = load_default_script()
    res = build_delivery(
        s, [RunRef(clip_id="clip1", run_id="r1", run_dir=str(run_dir))],
        dest_root=tmp_path / "deliv",
    )
    m = json.loads(Path(res.manifest_path).read_text(encoding="utf-8"))
    assert m["plate"] == "plate.png"
    assert m["plate_has_baked_ui"] is False
    assert any("cột UI" in w for w in m["warnings"]), m["warnings"]


def test_delivery_marks_plate_baked_when_no_clean_candidate(tmp_path, monkeypatch):
    from src.Workflows import delivery as dv

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _fake_board(run_dir / "starting_frame.jpg")
    monkeypatch.setattr(dv, "extract_clean_plate", lambda *a, **k: None)

    s = load_default_script()
    res = build_delivery(
        s, [RunRef(clip_id="clip1", run_id="r1", run_dir=str(run_dir))],
        dest_root=tmp_path / "deliv",
    )
    m = json.loads(Path(res.manifest_path).read_text(encoding="utf-8"))
    # Không cứu được thì vẫn xuất file, nhưng cờ phải bật để không ai dựng trên nền dơ.
    assert m["plate_has_baked_ui"] is True


@needs_ffmpeg
def test_delivery_reports_ui_clean_point(tmp_path):
    """Clip legacy còn B-roll sạch từ sau board — manifest phải nói rõ mốc cắt."""
    if not SAMPLE_VIDEO.is_file():
        pytest.skip("chưa có video mẫu trong out/nodes")
    from src.Workflows.delivery import find_ui_clean_point

    at = find_ui_clean_point(SAMPLE_VIDEO)
    if at is None:
        pytest.skip("clip mẫu không dính board")
    assert 0.0 < at < 3.0


# --------------------------------------------------------------------------- #
# Ảnh sản phẩm sinh từ Flow → items/ đúng tên script khai
# --------------------------------------------------------------------------- #


def _fake_product_png(path: Path, *, w: int = 900, h: int = 1100) -> Path:
    """Ảnh sản phẩm tổng hợp có alpha — đạt ngưỡng ≥800px cạnh dài và có alpha."""
    from PIL import Image as _Image

    im = _Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # Khối đục chiếm phần lớn khung để qua `MIN_BBOX_SPAN_PCT` khi kiểm.
    for y in range(80, h - 80):
        for x in range(120, w - 120):
            im.putpixel((x, y), (232, 226, 214, 255))
    # Pillow không ghi được RGBA ra JPEG — ảnh thô Flow là RGB thật.
    if path.suffix.lower() in (".jpg", ".jpeg"):
        im.convert("RGB").save(path, format="JPEG")
    else:
        im.save(path)
    return path


def test_item_refs_are_imported_with_script_filenames(tmp_path):
    """Node ảnh sinh ra `out/nodes/<run>/image.png` — delivery phải copy vào đúng
    `items/item_1_top_front.png` mà script khai, thay vì báo thiếu."""
    from src.Workflows.delivery import ItemRef

    run_dir = tmp_path / "run_front"
    run_dir.mkdir()
    _fake_product_png(run_dir / "image.png")

    s = load_default_script()
    res = build_delivery(
        s,
        [],
        dest_root=tmp_path / "deliv",
        item_refs=[ItemRef(name="Áo Kiểu Nữ Donna", item_id="item_1", run_id="r1", run_dir=str(run_dir))],
    )
    m = json.loads(Path(res.manifest_path).read_text(encoding="utf-8"))

    item1 = next(i for i in m["items"] if i["id"] == "item_1")
    assert item1["front"] == "items/item_1_top_front.png"
    assert (tmp_path / "deliv" / s.slug / "items" / "item_1_top_front.png").is_file()


def test_item_ref_resolves_by_run_id_without_run_dir(tmp_path, monkeypatch):
    """`run_id` một mình phải đủ. Đây là bug thật đã gặp: `jobs.py` điền `run_dir` từ
    `node_out`, nhưng gọi thẳng module (test, CLI) thì `run_dir` rỗng — trước khi sửa,
    delivery báo thiếu dù ảnh có thật trong `out/nodes/<run_id>/`."""
    from src.Workflows import delivery as dv

    fake_root = tmp_path / "repo"
    run_dir = fake_root / "out" / "nodes" / "run_abc"
    run_dir.mkdir(parents=True)
    _fake_product_png(run_dir / "the_actual_image.jpg")

    monkeypatch.setattr(dv, "ROOT", fake_root)
    got = dv._resolve_item_image(dv.ItemRef(name="Donna", item_id="item_1", run_id="run_abc"))
    assert got is not None
    assert got.name == "the_actual_image.jpg"


def test_item_ref_prefers_png_over_jpg(tmp_path, monkeypatch):
    """Ảnh đã tách nền (PNG) phải thắng ảnh Flow thô (JPG) khi cả hai cùng tồn tại."""
    from src.Workflows import delivery as dv

    fake_root = tmp_path / "repo"
    run_dir = fake_root / "out" / "nodes" / "run_xyz"
    run_dir.mkdir(parents=True)
    _fake_product_png(run_dir / "aaa_raw.jpg")
    _fake_product_png(run_dir / "zzz_cut.png")

    monkeypatch.setattr(dv, "ROOT", fake_root)
    got = dv._resolve_item_image(dv.ItemRef(name="Donna", item_id="item_1", run_id="run_xyz"))
    assert got is not None and got.suffix == ".png"


def test_each_item_needs_only_one_image(tmp_path):
    """Mỗi món chỉ cần MỘT ảnh. Sinh ảnh lưng là tuỳ chọn của người dùng, không phải
    yêu cầu của pipeline — item có `cutout_back: null` vẫn dựng phim được đầy đủ."""
    from src.Workflows.delivery import ItemRef

    run_dir = tmp_path / "run_item2"
    run_dir.mkdir()
    _fake_product_png(run_dir / "image.png")

    s = load_default_script()
    res = build_delivery(
        s,
        [],
        dest_root=tmp_path / "deliv",
        item_refs=[ItemRef(name="Sheer Cardigan", item_id="item_2", run_id="r1", run_dir=str(run_dir))],
    )
    m = json.loads(Path(res.manifest_path).read_text(encoding="utf-8"))
    item2 = next(i for i in m["items"] if i["id"] == "item_2")
    # item_2 không khai `cutout_back` ⇒ chỉ một ảnh là đủ, không được báo thiếu gì thêm.
    assert item2["front"] == "items/item_2_cardigan.png"
    assert item2["back"] is None
    assert not any("item_2_cardigan" in x for x in m["assets_missing"]), m["assets_missing"]


def test_item_refs_unknown_item_falls_back_to_name(tmp_path):
    """`item_id` không có trong script KHÔNG còn là lỗi.

    Người bán có hàng trăm món và không khai hết vào `items[]`; ảnh vẫn phải được xuất,
    đặt tên theo tên món người dùng gõ, thay vì bị bỏ qua kèm cảnh báo.
    """
    from src.Workflows.delivery import ItemRef

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _fake_product_png(run_dir / "image.png")

    s = load_default_script()
    res = build_delivery(
        s,
        [],
        dest_root=tmp_path / "deliv",
        item_refs=[ItemRef(name="Áo Thun Basic", item_id="item_99", run_id="r1", run_dir=str(run_dir))],
    )
    m = json.loads(Path(res.manifest_path).read_text(encoding="utf-8"))

    assert (tmp_path / "deliv" / s.slug / "items" / "ao_thun_basic.png").is_file()
    written = next(i for i in m["items"] if i["id"] == "ao_thun_basic")
    assert written["name"] == "Áo Thun Basic"
    assert written["front"] == "items/ao_thun_basic.png"
    assert not any("item_99" in x for x in m["assets_missing"]), m["assets_missing"]


def test_item_ref_without_script_link_is_exported(tmp_path):
    """Đường dẫn chính: node ảnh chỉ tick `is_item` + đặt tên, không gắn script.

    Đây là yêu cầu thật — người dùng có rất nhiều sản phẩm, không muốn khai `items[]`.
    """
    from src.Workflows.delivery import ItemRef

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _fake_product_png(run_dir / "image.png")

    s = load_default_script()
    res = build_delivery(
        s,
        [],
        dest_root=tmp_path / "deliv",
        item_refs=[ItemRef(name="Quần Đầm Đen", run_id="r1", run_dir=str(run_dir))],
    )
    m = json.loads(Path(res.manifest_path).read_text(encoding="utf-8"))

    assert (tmp_path / "deliv" / s.slug / "items" / "quan_dam_den.png").is_file()
    assert any(i["id"] == "quan_dam_den" for i in m["items"]), m["items"]
    # Món script khai vẫn còn trong manifest — thêm vào, không thay thế.
    assert any(i["id"] == "item_1" for i in m["items"])


def test_item_ref_keeps_source_suffix(tmp_path):
    """Ảnh nguồn là .jpg thì file xuất cũng .jpg — không đổi đuôi sau lưng người dùng."""
    from src.Workflows.delivery import ItemRef

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _fake_product_png(run_dir / "image.jpg")

    s = load_default_script()
    build_delivery(
        s,
        [],
        dest_root=tmp_path / "deliv",
        item_refs=[ItemRef(name="Túi Cói", run_id="r1", run_dir=str(run_dir))],
    )
    assert (tmp_path / "deliv" / s.slug / "items" / "tui_coi.jpg").is_file()


def test_item_refs_later_take_wins(tmp_path):
    """Cùng item truyền 2 lần ⇒ take sau thắng, giống quy ước của run_refs."""
    from src.Workflows.delivery import ItemRef

    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _fake_product_png(a / "image.png", w=900, h=1100)
    # Take sau có ảnh to hơn để phân biệt được file nào thắng.
    _fake_product_png(b / "image.png", w=1400, h=1600)

    s = load_default_script()
    res = build_delivery(
        s,
        [],
        dest_root=tmp_path / "deliv",
        item_refs=[
            ItemRef(name="Donna", item_id="item_1", run_id="a", run_dir=str(a)),
            ItemRef(name="Donna", item_id="item_1", run_id="b", run_dir=str(b)),
        ],
    )
    from PIL import Image as _Image

    out = tmp_path / "deliv" / s.slug / "items" / "item_1_top_front.png"
    with _Image.open(out) as im:
        assert im.size == (1400, 1600), "take sau phải thắng take trước"


def test_lint_flags_item_face_in_agent_instruction(tmp_path):
    """Agent phải biết đang dựng MÓN NÀO — nếu không, prompt không bám được phom/màu vải."""
    from src.Workflows.prompt_agent import NodePromptTask, PromptAgent

    agent = PromptAgent.__new__(PromptAgent)  # không cần runner cho phần format
    agent.skill_mgr = __import__(
        "src.Workflows.skill_manager", fromlist=["get_skill_manager"]
    ).get_skill_manager()
    skill = agent.skill_mgr.get_skill("lookbook-item-cutout-prompter")
    assert skill is not None

    out = agent.format_agent_instruction(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                       item_id="item_1"),
        skill, [],
    )
    assert "item_1" in out
    # Không còn khái niệm mặt trước/sau trong pipeline.
    assert "mặt SAU" not in out and "item_face" not in out


def test_list_deliveries_skips_broken_manifest(tmp_path):
    s = load_default_script()
    build_delivery(s, [], dest_root=tmp_path)
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "delivery.json").write_text("{not json", encoding="utf-8")

    items = list_deliveries(tmp_path)
    assert [d["slug"] for d in items] == [s.slug]
