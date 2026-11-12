"""Tách nền cutout sản phẩm từ ảnh flat-lay có sẵn.

Công cụ **độc lập**, không phải bước nào của pipeline bảng phối: coordinate sheet
(`lookbook-item-cutout-prompter`) có chữ nằm sẵn trong pixel, rembg sẽ cắt luôn chữ.
Dùng script này khi bạn đã có ảnh sản phẩm trên nền trơn và muốn card có alpha thật.

Vì sao **không** dùng `npx hyperframes remove-background`:
    Lệnh đó chạy `u2net_human_seg` — model huấn luyện cho **người**. Ảnh nguồn Shopee là
    ảnh lifestyle có người mẫu, chạy model đó sẽ tách **cả người**, không tách chiếc áo.
    Ngay cả khi đã có ảnh flat-lay sạch, `human_seg` vẫn là model sai loại.

Quy trình (có mắt người ở giữa):
    A. Có ảnh một món trên nền trơn (chụp lại, hoặc thuê ngoài tách).
    B. Chạy script này: rembg (u2net **general**) → kiểm tra → contact sheet để duyệt.

Script cố ý nằm ngoài `src/Workflows/` (không thuộc vòng production): chất lượng matting
phụ thuộc ảnh nguồn và cần mắt người duyệt trước khi đưa vào bộ dựng phim.

Dùng:
    python scripts/cutout_items.py --src out/deliveries/<slug>/items \\
        --dest out/deliveries/<slug>/items

    # hoặc trỏ thẳng thư mục ảnh AI sinh
    python scripts/cutout_items.py --src out/uploads --pattern "cutout_*.png"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

#: Cạnh dài tối thiểu để ảnh chịu được phóng to trong composition 1080×1920.
MIN_LONG_EDGE = 800
#: Tối thiểu % pixel trong suốt — thấp hơn nghĩa là ảnh vẫn còn nền.
MIN_TRANSPARENT_PCT = 5.0
#: Cạnh dài của bounding box phải chiếm tối thiểu % cạnh dài khung.
#: Đo theo cạnh dài chứ không theo diện tích: một chiếc áo hai dây là hình cao–hẹp, diện
#: tích bbox nhỏ nhưng vẫn đúng chuẩn. Đo diện tích sẽ báo lỗi nhầm loại này.
MIN_BBOX_SPAN_PCT = 45.0
#: Một mảnh alpha nhỏ hơn % này bị coi là rác (dây, nút rời) chứ không phải món thứ hai.
#: Đo trên ảnh downsample, nên ngưỡng tính theo % diện tích khung: món thật luôn lớn hơn
#: nhiều so với mảnh rác cỡ vài pixel.
MIN_PIECE_AREA_PCT = 3.0


#: Nền studio phải gần như đồng nhất. Ảnh lifestyle (café, tường, cây) cho độ lệch lớn.
MAX_BACKGROUND_STD = 26.0
#: Tỷ lệ pixel "nền" (gần màu góc ảnh) phải cao — flat-lay thật thường >55%.
MIN_BACKGROUND_PCT = 45.0
#: Nền trơn + `u2net_human_seg` phủ ≥ ngưỡng này **và** mask người cao ≥ `MIN_HUMAN_BBOX_H_PCT`
#: khung ⇒ ảnh studio CÓ NGƯỜI MẪU, không phải flat-lay. Đây là bẫy thật: ảnh lookbook studio
#: trơn (Sugal 2.jpg, 8.jpg) qua được test nền nhưng vật thể nổi bật vẫn là người.
#:
#: Phải dùng **hai** tín hiệu, không dùng riêng `human_pct`: số đo thật trên 8.jpg cho
#: coverage chỉ 11.5% (ảnh có viền trắng rộng + người mảnh) nhưng bbox người cao tới 85.4%
#: khung. Coverage một mình sẽ để lọt ảnh đó. Flat-lay thật (bảng size 3.jpg) có bbox 31%.
MIN_HUMAN_PCT = 8.0
MIN_HUMAN_BBOX_H_PCT = 55.0

#: Bảng size / bảng thông số trên nền trắng cũng qua được cả hai tầng trên: nền trơn, không
#: người. `u2net` sẽ tách nguyên cái bảng (khung kẻ + chữ) thành "sản phẩm" — vô dụng cho
#: lớp card. Nhận diện bằng **đường kẻ dài**: bảng luôn có hàng/cột kẻ ngang dọc gần hết bề
#: ngang/đứng khung; ảnh sản phẩm thật thì không.
MIN_TABLE_LINES = 6
#: Pixel được coi là "mực" khi dò đường kẻ. Chỉ dùng trong nhánh nền trơn (xem call site).
DARK_INK = 110


def _check_source_flatlay(path: Path, session=None) -> dict:
    """Đoán ảnh nguồn có phải flat-lay trên nền trơn không.

    Đây là guard quan trọng nhất của script. `u2net` (general) tách **vật thể nổi bật**;
    trên ảnh có người mẫu, vật thể nổi bật là **con người**, nên kết quả là cutout người
    mẫu chứ không phải món đồ — hoàn toàn vô dụng cho lớp card sản phẩm.

    Kiểm tra hai tầng, vì nền trơn **không đủ** để kết luận:
      1. Nền đồng nhất? (rẻ, từ chối ảnh lifestyle/café/tường)
      2. Có người trong ảnh không? (`u2net_human_seg` — studio trơn vẫn thường có model.)
         Nếu human_seg phủ phần lớn khung thì vật thể nổi bật là NGƯỜI, không phải áo.
    """
    from PIL import Image, ImageStat  # type: ignore

    with Image.open(path) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size
        # 4 góc, mỗi góc một ô 12% cạnh — flat-lay luôn để trống ở góc.
        box_w, box_h = max(8, int(w * 0.12)), max(8, int(h * 0.12))
        corners = [
            rgb.crop((0, 0, box_w, box_h)),
            rgb.crop((w - box_w, 0, w, box_h)),
            rgb.crop((0, h - box_h, box_w, h)),
            rgb.crop((w - box_w, h - box_h, w, h)),
        ]
        stats = [ImageStat.Stat(c) for c in corners]
        means = [tuple(s.mean) for s in stats]
        r_mean = sum(m[0] for m in means) / 4
        g_mean = sum(m[1] for m in means) / 4
        b_mean = sum(m[2] for m in means) / 4
        # Độ lệch giữa các góc — flat-lay đồng nhất, lifestyle thì không.
        spread = max(
            max(abs(m[i] - (r_mean, g_mean, b_mean)[i]) for m in means) for i in range(3)
        )

        # % pixel gần màu nền (dùng downsample cho nhanh)
        small = rgb.resize((96, 96))
        raw = small.tobytes()
        px = [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]
        near_bg = sum(
            1 for (r, g, b) in px
            if abs(r - r_mean) < 34 and abs(g - g_mean) < 34 and abs(b - b_mean) < 34
        )
        bg_pct = round(near_bg / len(px) * 100, 1)

    uniform = spread < MAX_BACKGROUND_STD and bg_pct >= MIN_BACKGROUND_PCT
    result = {
        "bg_color": [round(r_mean), round(g_mean), round(b_mean)],
        "bg_corner_spread": round(spread, 1),
        "bg_uniform_pct": bg_pct,
        "bg_uniform": uniform,
        "human_pct": None,
        "human_bbox_h_pct": None,
        "table_lines": None,
        "is_size_chart": False,
        "looks_like_flatlay": uniform,
    }

    if not uniform:
        return result

    # Tầng 2: bảng size / bảng thông số. Chỉ chạy khi nền đã trơn — ảnh lifestyle tối
    # (HAVANA 3.jpg: 187 hàng "tối") sẽ đánh lừa phép dò đường kẻ, nhưng chúng đã bị tầng 1
    # loại rồi.
    table = _table_line_count(path)
    result["table_lines"] = table
    if table >= MIN_TABLE_LINES:
        result["is_size_chart"] = True
        result["looks_like_flatlay"] = False
        return result

    # Tầng 3: có người mẫu không. Nền trơn **không đủ** để kết luận — ảnh studio lookbook
    # vẫn thường có model đứng toàn thân.
    if session is not None:
        human = _human_mask_stats(path, session)
        result["human_pct"] = human["coverage_pct"]
        result["human_bbox_h_pct"] = human["bbox_h_pct"]
        # Người phủ nhiều VÀ mask người cao gần hết khung ⇒ đó là ảnh chụp toàn thân người mẫu.
        if human["coverage_pct"] >= MIN_HUMAN_PCT and human["bbox_h_pct"] >= MIN_HUMAN_BBOX_H_PCT:
            result["looks_like_flatlay"] = False
    return result


def _components(alpha, min_area_pct: float) -> int:
    """Đếm số mảnh rời đáng kể trong alpha — để nhận ra ảnh **cả bộ**.

    Ảnh nhiều món xếp cạnh nhau có 2+ món, mỗi món là một đảo alpha riêng. rembg vẫn
tách
    được, nhưng khung chữ nhật của bbox gộp cả bộ nên card sản phẩm sẽ hở khoảng trống
giữa
    các món — không dùng được cho composition.
    """
    w, h = alpha.size
    total = w * h
    if not total:
        return 0
    # Downsample trước: quét pixel-level trên 1080×1920 là chậm và không cần độ chính xác.
    small = alpha.resize((min(w, 160), min(h, 160)))
    sw, sh = small.size
    px = small.load()
    seen = set()
    min_area = sw * sh * min_area_pct / 100.0
    count = 0
    for y0 in range(sh):
        for x0 in range(sw):
            if (x0, y0) in seen or px[x0, y0] < 128:
                continue
            # Flood-fill lặp, tránh đệ quy sâu trên ảnh lớn.
            stack = [(x0, y0)]
            seen.add((x0, y0))
            area = 0
            while stack:
                x, y = stack.pop()
                area += 1
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < sw and 0 <= ny < sh and (nx, ny) not in seen and px[nx, ny] >= 128:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            if area >= min_area:
                count += 1
    return count


def _table_line_count(path: Path) -> int:
    """Đếm số hàng + cột bị "mực" phủ gần hết bề ngang/đứng — dấu hiệu bảng kẻ.

    Downsample 256px cho nhanh; bảng size thật ra 10–13 đường, sản phẩm thật ra 0.
    """
    from PIL import Image  # type: ignore

    with Image.open(path) as im:
        g = im.convert("L").resize((256, 256))
    w, h = g.size
    px = g.load()
    ink_rows = 0
    for y in range(h):
        dark = 0
        for x in range(w):
            if px[x, y] < DARK_INK:
                dark += 1
        if dark >= w * 0.62:
            ink_rows += 1
    ink_cols = 0
    for x in range(w):
        dark = 0
        for y in range(h):
            if px[x, y] < DARK_INK:
                dark += 1
        if dark >= h * 0.62:
            ink_cols += 1
    return ink_rows + ink_cols


def _human_mask_stats(path: Path, session) -> dict:
    """Đo mask `u2net_human_seg`: % diện tích phủ và chiều cao bbox theo % khung.

    Cần cả hai vì mỗi cái đều có ca lọt: ảnh viền trắng rộng làm coverage tụt dù vẫn là
    người mẫu đứng; ảnh crop cận cảnh làm bbox thấp dù người phủ đầy khung.
    """
    from PIL import Image  # type: ignore
    from rembg import remove  # type: ignore

    with Image.open(path) as im:
        mask = remove(im, session=session, only_mask=True).convert("L")
    w, h = mask.size
    total = w * h
    if not total:
        return {"coverage_pct": 0.0, "bbox_h_pct": 0.0}

    hist = mask.histogram()
    coverage = sum(hist[128:]) / total * 100
    # Bbox phải tính trên mask đã ngưỡng hoá — `getbbox()` mặc định coi mọi pixel > 0 là
    # "có", nhưng mask rembg để lại vài pixel nhiễu mờ ở rìa.
    binary = mask.point(lambda v: 255 if v >= 128 else 0)
    bbox = binary.getbbox()
    bbox_h = (bbox[3] - bbox[1]) if bbox else 0
    return {"coverage_pct": round(coverage, 1), "bbox_h_pct": round(bbox_h / h * 100, 1)}


def _require(mod: str, hint: str):
    try:
        return __import__(mod)
    except ImportError:
        print(f"❌ Thiếu thư viện '{mod}'. {hint}", file=sys.stderr)
        raise SystemExit(2)


def load_rembg():
    try:
        from rembg import new_session, remove  # type: ignore
        return remove, new_session
    except ImportError:
        print(
            "❌ Thiếu 'rembg'. Cài:  pip install rembg onnxruntime pillow\n"
            "   (rembg tải model u2net ~176MB ở lần chạy đầu)",
            file=sys.stderr,
        )
        raise SystemExit(2)


def cutout_one(path: Path, dest: Path, session) -> dict:
    """Tách nền một ảnh. Trả dict thông tin để ghi báo cáo."""
    from PIL import Image  # type: ignore

    remove, _ = load_rembg()
    with Image.open(path) as im:
        src_size = im.size
        out = remove(im, session=session, post_process_mask=True)

    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest, format="PNG")

    return {
        "source": str(path),
        "output": str(dest),
        "source_size": list(src_size),
        **_validate(dest),
    }


def _validate(png_path: Path) -> dict:
    """Kiểm tra cutout đủ tiêu chuẩn dùng trong composition."""
    from PIL import Image  # type: ignore

    with Image.open(png_path) as im:
        if im.mode not in ("RGBA", "LA"):
            im = im.convert("RGBA")
        alpha = im.getchannel("A")
        w, h = im.size
        total = w * h
        hist = alpha.histogram()
        transparent = sum(hist[:16])  # alpha < 16 ≈ trong suốt
        bbox = alpha.getbbox()

    transparent_pct = round(transparent / total * 100, 2) if total else 0.0
    long_edge = max(w, h)

    problems: list[str] = []
    if long_edge < MIN_LONG_EDGE:
        problems.append(f"cạnh dài {long_edge}px < {MIN_LONG_EDGE}px")
    if transparent_pct < MIN_TRANSPARENT_PCT:
        problems.append(f"chỉ {transparent_pct}% trong suốt — nền chưa tách sạch")
    pieces = 0
    if not bbox:
        problems.append("alpha rỗng — ảnh hoàn toàn trong suốt")
        span_pct = 0.0
    else:
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        span_pct = round(max(bw, bh) / long_edge * 100, 2)
        if span_pct < MIN_BBOX_SPAN_PCT:
            problems.append(
                f"vùng đục chỉ chiếm {span_pct}% cạnh dài — ảnh bị crop cụt hoặc tách nhầm mảnh"
            )
        pieces = _components(alpha, MIN_PIECE_AREA_PCT)
        if pieces > 1:
            problems.append(
                f"alpha có {pieces} mảnh rời — đây là ảnh CẢ BỘ (nhiều món xếp cạnh "
                "nhau). Card sản phẩm cần MỘT món; tách riêng từng ảnh."
            )

    return {
        "size": [w, h],
        "transparent_pct": transparent_pct,
        "bbox_span_pct": span_pct,
        "pieces": pieces,
        "ok": not problems,
        "problems": problems,
    }


def build_contact_sheet(entries: list[dict], dest: Path, thumb: int = 320) -> Path | None:
    """Ghép contact-sheet để duyệt cả bộ trong một lần nhìn."""
    from PIL import Image  # type: ignore

    ok = [e for e in entries if Path(e["output"]).is_file()]
    if not ok:
        return None

    cols = min(4, len(ok))
    rows = (len(ok) + cols - 1) // cols
    pad = 16
    label_h = 34
    cell_w, cell_h = thumb + pad * 2, thumb + pad * 2 + label_h
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (24, 24, 27))

    try:
        from PIL import ImageDraw  # type: ignore

        draw = ImageDraw.Draw(sheet)
    except ImportError:  # pragma: no cover
        draw = None

    for i, e in enumerate(ok):
        r, c = divmod(i, cols)
        with Image.open(e["output"]) as im:
            im = im.convert("RGBA")
            im.thumbnail((thumb, thumb))
        # Nền caro để thấy vùng trong suốt
        x0, y0 = c * cell_w + pad, r * cell_h + pad
        checker = Image.new("RGB", (thumb, thumb), (60, 60, 66))
        for yy in range(0, thumb, 16):
            for xx in range((yy // 16) % 2 * 16, thumb, 32):
                checker.paste((84, 84, 92), (xx, yy, min(xx + 16, thumb), min(yy + 16, thumb)))
        ox = x0 + (thumb - im.width) // 2
        oy = y0 + (thumb - im.height) // 2
        checker.paste(im, (ox - x0, oy - y0), im)
        sheet.paste(checker, (x0, y0))
        if draw:
            mark = "OK" if e["ok"] else "!!"
            stem = Path(e["output"]).stem
            if len(stem) > 22:
                stem = stem[:21] + "…"
            draw.text((x0 + 4, y0 + thumb + 6), f"{mark} {stem}", fill=(230, 230, 235))

    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest, format="PNG")
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tách nền cutout sản phẩm bằng rembg (u2net general)")
    ap.add_argument("--src", required=True, help="thư mục ảnh flat-lay nguồn")
    ap.add_argument("--dest", required=True, help="thư mục ghi PNG cutout")
    ap.add_argument("--pattern", default="*", help="glob lọc file, ví dụ 'item_*.png'")
    ap.add_argument("--suffix", default="_cutout", help="hậu tố file ra (rỗng = trùng tên)")
    ap.add_argument(
        "--rename",
        default="",
        help="ánh xạ tên file ra: 'nguon=đích,nguon2=đích2' (bỏ .png). "
             "Dùng để ghi thẳng vào đúng tên item trong script, ví dụ "
             "'pink_wrap=item_1_top_front'.",
    )
    ap.add_argument("--overwrite", action="store_true", help="ghi đè file cutout đã có")
    ap.add_argument(
        "--force",
        action="store_true",
        help="tách nền cả ảnh không phải flat-lay (mặc định bỏ qua vì sẽ ra cutout người mẫu)",
    )
    ap.add_argument(
        "--no-human-check",
        action="store_true",
        help="bỏ tầng kiểm 'có người trong ảnh' (nhanh hơn, nhưng ảnh studio có model sẽ lọt)",
    )
    ap.add_argument("--sheet", default="_review.png", help="tên contact sheet trong --dest")
    args = ap.parse_args(argv)

    src = Path(args.src)
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    if not src.is_dir():
        print(f"❌ không có thư mục nguồn: {src}", file=sys.stderr)
        return 2

    files = sorted(
        p for p in src.glob(args.pattern)
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and not p.name.startswith("_")
    )
    if not files:
        print(f"❌ không tìm thấy ảnh nào khớp '{args.pattern}' trong {src}", file=sys.stderr)
        return 2

    rename_map: dict[str, str] = {}
    for pair in filter(None, (s.strip() for s in args.rename.split(","))):
        if "=" not in pair:
            print(f"❌ --rename sai định dạng: '{pair}' (cần nguon=đích)", file=sys.stderr)
            return 2
        k, _, v = pair.partition("=")
        rename_map[k.strip()] = v.strip()

    remove, new_session = load_rembg()
    # u2net (general) — KHÔNG phải u2net_human_seg. Quần áo không phải người.
    session = new_session("u2net")
    # human_seg chỉ dùng để PHÁT HIỆN người trong ảnh nguồn, không dùng để tách nền.
    human_session = new_session("u2net_human_seg") if not args.no_human_check else None

    entries: list[dict] = []
    skipped_not_flatlay: list[str] = []
    for p in files:
        src_info = _check_source_flatlay(p, human_session)
        if not src_info["looks_like_flatlay"] and not args.force:
            human_pct = src_info.get("human_pct")
            if src_info.get("is_size_chart"):
                reason = (
                    f"nền trơn nhưng là BẢNG SIZE/thông số ({src_info.get('table_lines')} "
                    "đường kẻ dài) → tách ra sẽ là cả cái bảng, không phải món đồ."
                )
            elif human_pct is not None and human_pct >= MIN_HUMAN_PCT:
                # Nền trơn nhưng có người: trường hợp hay lọt nhất (ảnh studio lookbook).
                reason = (
                    f"nền trơn nhưng có NGƯỜI MẪU (human_seg phủ {human_pct}%, "
                    f"cao {src_info.get('human_bbox_h_pct')}% khung) "
                    "→ tách ra sẽ là cả người, không phải món đồ."
                )
            else:
                reason = (
                    f"nền không đồng nhất (lệch góc {src_info['bg_corner_spread']}, "
                    f"nền chiếm {src_info['bg_uniform_pct']}%) → đây là ảnh lifestyle, "
                    "cắt ra sẽ là cả NGƯỜI MẪU chứ không phải món đồ."
                )
            print(
                f"⏭  bỏ qua {p.name}: {reason}\n"
                "   Cần ảnh MỘT món trên nền trơn trước, "
                "hoặc dùng --force nếu chắc chắn.",
                file=sys.stderr,
            )
            skipped_not_flatlay.append(str(p))
            continue

        out_name = rename_map.get(p.stem) or f"{p.stem}{args.suffix}"
        out = dest / f"{out_name}.png"
        if out.exists() and not args.overwrite:
            print(f"· bỏ qua (đã có): {out.name}")
            entries.append({
                "source": str(p), "output": str(out), "source_check": src_info,
                **_validate(out),
            })
            continue
        print(f"→ tách nền: {p.name}")
        entries.append({**cutout_one(p, out, session), "source_check": src_info})

    sheet = build_contact_sheet(entries, dest / args.sheet)
    report = {
        "src": str(src),
        "dest": str(dest),
        "model": "u2net (general, không phải human_seg)",
        "thresholds": {
            "min_long_edge_px": MIN_LONG_EDGE,
            "min_transparent_pct": MIN_TRANSPARENT_PCT,
            "min_bbox_span_pct": MIN_BBOX_SPAN_PCT,
        },
        "contact_sheet": str(sheet) if sheet else None,
        "entries": entries,
        "skipped_not_flatlay": skipped_not_flatlay,
        "ok_count": sum(1 for e in entries if e["ok"]),
        "fail_count": sum(1 for e in entries if not e["ok"]),
    }
    (dest / "_cutout_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    for e in entries:
        mark = "✅" if e["ok"] else "❌"
        print(f"{mark} {Path(e['output']).name}  {e['size'][0]}×{e['size'][1]}  "
              f"trong suốt {e['transparent_pct']}%  bbox {e['bbox_span_pct']}%")
        for prob in e["problems"]:
            print(f"     · {prob}")
    if skipped_not_flatlay:
        print(f"\n⏭  Bỏ qua {len(skipped_not_flatlay)} ảnh không phải flat-lay (xem lý do ở trên).")
    if sheet:
        print(f"\n👀 Duyệt bằng mắt: {sheet}")
    print(f"📄 Báo cáo: {dest / '_cutout_report.json'}")
    return 0 if report["fail_count"] == 0 and not skipped_not_flatlay else 1


if __name__ == "__main__":
    raise SystemExit(main())
