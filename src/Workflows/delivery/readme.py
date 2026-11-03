"""The README.md handoff written into every delivery folder."""

from __future__ import annotations

from .models import DeliveryResult


def _render_readme(manifest: dict, result: DeliveryResult) -> str:
    c = manifest["canvas"]
    lines = [
        f"# Bộ dựng phim — {manifest['title'] or manifest['slug']}",
        "",
        f"- Composition: **{c['width']}×{c['height']} @ {c['fps']}fps**, dài **{c['duration_s']}s**",
        f"- Xuất lúc: {manifest['created_ts']}",
        "- Nguồn: Google Flow (`abra_i2v_8s`, image-to-video, 8s/clip)",
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
        "## Nội dung",
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

    qa = manifest.get("qa_summary") or {}
    flagged = [
        (c["id"], g)
        for c in manifest["clips"]
        for g in ((c.get("qa") or {}).get("gates") or [])
        if g["status"] in ("warn", "skip")
    ]
    if flagged:
        counts = qa.get("counts") or {}
        lines += [
            "",
            "## Kiểm tra clip thô (QA)",
            "",
            f"Kết quả: **{qa.get('status', '?')}** — "
            f"{counts.get('pass', 0)} đạt, {counts.get('warn', 0)} cảnh báo, "
            f"{counts.get('skip', 0)} chưa đo được. Đây là cảnh báo, không chặn dựng phim.",
            "",
            "| clip | gate | kết quả | số đo |",
            "| :-- | :-- | :-- | :-- |",
        ]
        for clip_id, g in flagged:
            mark = "⚠️" if g["status"] == "warn" else "—"
            detail = g["detail"].replace("|", "\\|")
            lines.append(f"| {clip_id} | {g['name']} | {mark} {g['status']} | {detail} |")
        if counts.get("skip"):
            lines += [
                "",
                "`skip` nghĩa là **chưa ai kiểm**, không phải đã đạt — thường do thiếu ffmpeg "
                "hoặc clip chưa sinh.",
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
