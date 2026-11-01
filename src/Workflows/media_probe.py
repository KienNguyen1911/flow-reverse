"""Media Probe — đo thông số thật của file video/ảnh bằng ffprobe.

Lý do tồn tại: manifest cũ ghi `duration_s: 8` và `resolution: "1080p"` vì đó là **tham số
yêu cầu**, không phải thứ Flow trả về. Editor HyperFrames đọc manifest để đặt thời lượng
clip trên timeline; dùng số mặc định sẽ làm timeline lệch ngay khi Flow trả khác.

Nguyên tắc: luôn đo, không đoán. Không có ffprobe → trả `None` để caller tự quyết định
(gọi bên ngoài sẽ thấy `measured: false` thay vì một con số trông rất chắc chắn nhưng sai).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from typing import Optional

#: Timeout cho một lần gọi ffprobe. File local, 10s là rộng rãi.
_PROBE_TIMEOUT_S = 15.0

#: Phần mở rộng coi là ảnh tĩnh. ffprobe báo JPEG/PNG dưới dạng stream `mjpeg`/`png` có
#: `codec_type=video`, nên không thể chỉ dựa vào codec_type để phân loại.
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".avif"}
_IMAGE_FORMATS = ("image2", "jpeg_pipe", "png_pipe", "webp_pipe", "gif")


def have_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


@dataclass
class MediaInfo:
    """Thông số đo được của một file media."""

    path: str
    kind: str = "unknown"  # "video" | "image" | "unknown"
    width: Optional[int] = None
    height: Optional[int] = None
    duration_s: Optional[float] = None
    fps: Optional[float] = None
    has_audio: bool = False
    codec: Optional[str] = None
    size_bytes: Optional[int] = None
    measured: bool = False  # False = ffprobe không chạy được, các số trên là None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def aspect_ratio(self) -> Optional[str]:
        """Trả '9:16' / '16:9' / '1:1' nếu khớp tỷ lệ quen thuộc, ngược lại None."""
        if not self.width or not self.height:
            return None
        known = {
            (9, 16): "9:16",
            (16, 9): "16:9",
            (1, 1): "1:1",
            (3, 4): "3:4",
            (4, 3): "4:3",
            (2, 3): "2:3",
            (3, 2): "3:2",
        }
        f = Fraction(self.width, self.height)
        return known.get((f.numerator, f.denominator))


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_S,
            encoding="utf-8",
            errors="replace",
        )
        return res.returncode, res.stdout
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - phụ thuộc OS
        return -1, str(exc)


def _parse_rate(value: str) -> Optional[float]:
    """'24/1' → 24.0 ; '30000/1001' → 29.97 ; hỏng → None."""
    if not value:
        return None
    try:
        num, _, den = value.partition("/")
        d = float(den) if den else 1.0
        if d == 0:
            return None
        rate = float(num) / d
    except (TypeError, ValueError):
        return None
    return round(rate, 3) if rate > 0 else None


def probe_media(path: str | Path) -> MediaInfo:
    """Đo width/height/duration/fps/audio của một file. Không bao giờ raise."""
    p = Path(path)
    info = MediaInfo(path=str(p))
    try:
        info.size_bytes = p.stat().st_size
    except OSError:
        info.error = "không đọc được file"

    if not p.is_file():
        info.error = info.error or "file không tồn tại"
        return info

    if not have_ffprobe():
        info.error = "không tìm thấy ffprobe trong PATH"
        return info

    code, out = _run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(p),
    ])
    if code != 0:
        info.error = (out or "ffprobe lỗi").strip()[:200]
        return info

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        info.error = "ffprobe trả JSON không đọc được"
        return info

    streams = data.get("streams") or []
    vstream = next((s for s in streams if s.get("codec_type") == "video"), None)
    astream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    # `disposition.attached_pic` đánh dấu ảnh nhúng (cover art) — không phải video thật.
    if vstream and (vstream.get("disposition") or {}).get("attached_pic") == 1:
        vstream = None

    fmt = data.get("format") or {}
    # ffprobe bọc ảnh JPEG/PNG trong stream `codec_type=video` (mjpeg/png). Phân loại
    # theo đuôi file và format container, không theo codec_type.
    is_image = p.suffix.lower() in _IMAGE_SUFFIXES or any(
        f in str(fmt.get("format_name") or "") for f in _IMAGE_FORMATS
    )

    if vstream:
        info.width = vstream.get("width")
        info.height = vstream.get("height")
        info.codec = vstream.get("codec_name")
        info.fps = _parse_rate(vstream.get("r_frame_rate") or vstream.get("avg_frame_rate") or "")
        info.kind = "image" if is_image else "video"
    elif streams:
        info.kind = "image"
        info.width = streams[0].get("width")
        info.height = streams[0].get("height")
        info.codec = streams[0].get("codec_name")

    info.has_audio = astream is not None

    if info.kind == "image":
        # Ảnh tĩnh: `duration` luôn là rác (0.04s cho một khung), bỏ hẳn để caller
        # không vô tình đặt ảnh lên timeline với thời lượng 0.04 giây.
        info.duration_s = None
        info.fps = None
        info.measured = True
        return info

    # duration: ưu tiên format-level vì stream-level của một số container hay thiếu.
    dur = None
    for cand in (fmt.get("duration"), vstream.get("duration") if vstream else None):
        if cand is None:
            continue
        try:
            dur = float(cand)
            break
        except (TypeError, ValueError):
            continue
    info.duration_s = round(dur, 3) if dur is not None else None

    info.measured = True
    return info


def probe_video(path: str | Path) -> MediaInfo:
    """Như `probe_media` nhưng đảm bảo kết quả là video."""
    info = probe_media(path)
    if info.measured and info.kind != "video":
        info.measured = False
        info.error = "file không phải video"
    return info


__all__ = ["MediaInfo", "have_ffprobe", "probe_media", "probe_video"]
