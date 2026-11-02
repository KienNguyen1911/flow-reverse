"""Raw Video QA — chấm clip Flow trả về **trước khi** đưa sang HyperFrames.

Lý do tồn tại: prompt video chỉ là mong muốn. Flow trả về cái nó muốn — có clip dính board
UI dựng sẵn trong 1.3s đầu, có clip cắt cảnh giữa chừng vì prompt dài, có clip trả 720×1280
trong khi composition 1080×1920. Người dựng chỉ thấy lỗi sau khi đã dựng xong 16 giây.

Nguyên tắc của module này:

1. **Đo, không đoán.** Mỗi gate phải có số đo từ ffmpeg/ffprobe. Không đo được thì trả
   `skip` kèm lý do — không bao giờ bịa một con số trông chắc chắn.
2. **Không chặn.** Người dùng chọn "chỉ cảnh báo": gate xấu nhất cũng chỉ là `warn`.
   Delivery vẫn xuất; quyết định dựng hay sinh lại là của người.

Ngưỡng dưới đây không phải số tròn cho đẹp — chúng lấy từ clip thật trong repo
(`out/deliveries/havana_donna_set/clips/clip1.mp4`, 720×1280/24fps/8.000s):

    scdet  điểm cao nhất                      10.79  (t=4.0 — đổi tư thế, không phải cắt)
    scdet  cắt cứng tổng hợp (đỏ→xanh)        15.63
    ⇒ ngưỡng 12 nằm giữa hai cụm.

    freezedetect -50dB:d=0.5 trên clip thật   không phát hiện
    freezedetect -50dB:d=0.5 trên đoạn đứng   freeze_start=1.0 dài 1.33s
    ⇒ -40dB báo nhầm (đoạn 0.5–0.875s chỉ là chuyển động rất chậm), -50dB mới đúng.

    tblend|YAVG  trung vị 0–1s                0.95
    tblend|YAVG  trung vị 2–8s                4.55
    ⇒ hook đứng yên thật; tỉ lệ 0.21, ngưỡng 0.6 là rộng rãi.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .media_probe import MediaInfo, probe_video
from .script_contract import ClipSpec, LookbookScript

#: `scdet` báo cắt cảnh khi điểm vượt ngưỡng này. 12 tách sạch hai cụm đo được (10.79 vs 15.63).
HARD_CUT_THRESHOLD = 12.0

#: `freezedetect` coi khung là đứng yên dưới mức nhiễu này. -50dB không báo nhầm trên clip thật
#: nhưng vẫn bắt được đoạn đứng 1.3s; -40dB thì báo nhầm chuyển động chậm.
FREEZE_NOISE_DB = -50

#: Đoạn đứng yên ngắn hơn mức này là nhịp thở, không phải clip hỏng.
FREEZE_MIN_S = 0.5

#: Ngưỡng cảnh báo độ lệch khung nối (`chain_from`). SSIM < 0.90 là hai khung khác cảnh.
CHAIN_SSIM_MIN = 0.90

#: Hook phải đứng yên hơn phần thân clip. Tỉ lệ trung vị chuyển động hook/thân ≤ mức này.
HOOK_STILL_RATIO_MAX = 0.6

#: Sai số thời lượng chấp nhận được giữa số đo và script.
DURATION_TOL_S = 0.10

#: fps nguồn Flow. Lệch khỏi đây là dấu hiệu file đã bị xử lý lại ở đâu đó.
ACCEPTED_FPS = (24.0, 25.0, 30.0)

_STATUS_ORDER = {"pass": 0, "skip": 1, "warn": 2}


@dataclass
class Gate:
    """Một điều kiện kiểm trên clip, kèm số đo đã dùng để kết luận.

    `status` chỉ nhận `pass` / `warn` / `skip`. Không có `fail`: QA này cảnh báo, không chặn.
    """

    name: str
    status: str
    detail: str
    measured: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "measured": self.measured,
        }


@dataclass
class ClipQA:
    clip_id: str
    path: Optional[str]
    gates: list[Gate] = field(default_factory=list)

    @property
    def status(self) -> str:
        return max((g.status for g in self.gates), key=lambda s: _STATUS_ORDER[s], default="skip")

    @property
    def warnings(self) -> list[str]:
        return [f"{self.clip_id}/{g.name}: {g.detail}" for g in self.gates if g.status == "warn"]

    @property
    def skipped(self) -> list[str]:
        return [f"{self.clip_id}/{g.name}: {g.detail}" for g in self.gates if g.status == "skip"]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "gates": [g.to_dict() for g in self.gates],
        }


# --------------------------------------------------------------------------- #
# Gọi ffmpeg
# --------------------------------------------------------------------------- #

#: Đo chuyển động bằng chênh lệch khung liên tiếp ở 12fps/180px. Hạ mẫu để 8s clip chạy ~0.3s,
#: và `tblend=difference` + `signalstats` cho trung bình độ sáng của ảnh hiệu — càng lớn càng động.
_MOTION_VF = "fps=12,scale=180:-1,tblend=all_mode=difference,signalstats,metadata=print"


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _ffmpeg(video: Path, vf: str, timeout: float = 60.0) -> tuple[int, str]:
    try:
        res = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
             "-vf", vf, "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - phụ thuộc OS
        return -1, str(exc)
    return res.returncode, res.stderr or ""


def _scene_cuts(video: Path, threshold: float = HARD_CUT_THRESHOLD) -> Optional[list[dict]]:
    """Mốc cắt cảnh cứng theo `scdet`. `None` = không đo được (không có ffmpeg/lỗi)."""
    code, err = _ffmpeg(video, f"scdet=threshold={threshold:g}")
    if code != 0:
        return None
    hits: list[dict] = []
    for line in err.splitlines():
        m = re.search(r"lavfi\.scd\.score:\s*([\d.]+),\s*lavfi\.scd\.time:\s*([\d.]+)", line)
        if m:
            hits.append({"at_s": round(float(m.group(2)), 3), "score": round(float(m.group(1)), 2)})
    return hits


def _freezes(video: Path, noise_db: int = FREEZE_NOISE_DB, min_s: float = FREEZE_MIN_S) -> Optional[list[dict]]:
    """Đoạn đứng yên do `freezedetect` tìm thấy. `None` = không đo được."""
    code, err = _ffmpeg(video, f"freezedetect=n={noise_db}dB:d={min_s:g}")
    if code != 0:
        return None
    segs: list[dict] = []
    cur: dict = {}
    for line in err.splitlines():
        if "freeze_start" in line:
            cur = {"start_s": round(float(line.rsplit(":", 1)[1]), 3)}
        elif "freeze_duration" in line and cur:
            cur["duration_s"] = round(float(line.rsplit(":", 1)[1]), 3)
        elif "freeze_end" in line and cur:
            cur["end_s"] = round(float(line.rsplit(":", 1)[1]), 3)
            if "duration_s" in cur:
                segs.append(cur)
            cur = {}
    return segs


def _motion_curve(video: Path) -> Optional[list[tuple[float, float]]]:
    """Chuỗi `(giây, độ chênh khung)` ở 12fps. `None` = không đo được."""
    code, err = _ffmpeg(video, _MOTION_VF)
    if code != 0:
        return None
    out: list[tuple[float, float]] = []
    t: Optional[float] = None
    for line in err.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1))
            continue
        m = re.search(r"YAVG=([\d.]+)", line)
        if m and t is not None:
            out.append((t, float(m.group(1))))
    return out or None


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _ssim_between(a: Path, b: Path) -> Optional[float]:
    """SSIM giữa hai ảnh. `None` = không đo được."""
    code, err = _ffmpeg_pair(a, b)
    if code != 0:
        return None
    m = re.search(r"All:([\d.]+)", err)
    return round(float(m.group(1)), 4) if m else None


def _ffmpeg_pair(a: Path, b: Path) -> tuple[int, str]:
    try:
        res = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(a), "-i", str(b),
             "-lavfi", "ssim", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60.0,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return -1, str(exc)
    return res.returncode, res.stderr or ""


def _grab_frame(video: Path, seconds: float, dest: Path) -> bool:
    try:
        res = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(video),
             "-frames:v", "1", str(dest)],
            capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0 and dest.is_file() and dest.stat().st_size > 512


def _grab_last_frame(video: Path, dest: Path) -> bool:
    """Khung cuối của clip.

    Không dùng `_grab_frame(video, 1e6, ...)`: ffmpeg nhận mốc `-ss` vượt độ dài file nhưng
    trả về **không khung nào**, nên gate im lặng rơi vào `skip` dù file hoàn toàn đọc được.
    `-sseof` đếm ngược từ cuối file nên luôn rơi vào khung cuối thật.
    """
    try:
        res = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-sseof", "-0.1", "-i", str(video),
             "-frames:v", "1", "-update", "1", str(dest)],
            capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0 and dest.is_file() and dest.stat().st_size > 512


# --------------------------------------------------------------------------- #
# Gate lẻ — mỗi hàm chỉ đo một thứ và trả về một `Gate`
# --------------------------------------------------------------------------- #


def gate_duration_match(info: MediaInfo, clip: ClipSpec) -> Gate:
    """Clip dài đúng như script khai? Lệch thời lượng làm trượt cả timeline."""
    if not info.measured or info.duration_s is None:
        return Gate("duration_match", "skip",
                    f"chưa đo được thời lượng: {info.error or 'thiếu ffprobe'}")
    delta = round(info.duration_s - clip.duration_s, 3)
    measured = {"duration_s": info.duration_s, "script_duration_s": clip.duration_s, "delta_s": delta}
    if abs(delta) <= DURATION_TOL_S:
        return Gate("duration_match", "pass",
                    f"{info.duration_s}s khớp script {clip.duration_s}s", measured)
    return Gate(
        "duration_match", "warn",
        f"đo được {info.duration_s}s nhưng script khai {clip.duration_s}s (lệch {delta:+.3f}s) — "
        "timeline phải dùng số đo thật",
        measured,
    )


def gate_fps_ok(info: MediaInfo) -> Gate:
    """fps lạ là dấu hiệu file đã qua xử lý khác (hoặc Flow đổi nguồn)."""
    if not info.measured or info.fps is None:
        return Gate("fps_ok", "skip", f"chưa đo được fps: {info.error or 'thiếu ffprobe'}")
    if info.fps in ACCEPTED_FPS:
        return Gate("fps_ok", "pass", f"{info.fps}fps", {"fps": info.fps})
    allowed = "/".join(f"{f:g}" for f in ACCEPTED_FPS)
    return Gate(
        "fps_ok", "warn",
        f"{info.fps}fps — ngoài nguồn Flow ({allowed}), kiểm tra lại là file nào",
        {"fps": info.fps},
    )


def gate_resolution_ok(info: MediaInfo, script: Optional[LookbookScript] = None) -> Gate:
    """Khung hình đúng composition chưa? 720×1280 phóng lên 1080×1920 là mất nét 1.5×."""
    if not info.measured or not info.width or not info.height:
        return Gate("resolution_ok", "skip",
                    f"chưa đo được kích thước: {info.error or 'thiếu ffprobe'}")
    have = f"{info.width}×{info.height}"
    measured: dict = {"width": info.width, "height": info.height}
    if script is None:
        return Gate("resolution_ok", "skip", f"đo được {have} nhưng không có script để so", measured)

    want_w, want_h = script.canvas.get("width"), script.canvas.get("height")
    if not want_w or not want_h:
        return Gate("resolution_ok", "skip", f"đo được {have} nhưng script không khai canvas",
                    measured)

    want = f"{want_w}×{want_h}"
    measured["canvas"] = want
    if (info.width, info.height) == (want_w, want_h):
        return Gate("resolution_ok", "pass", have, measured)

    scale = round(max(want_w / info.width, want_h / info.height), 2)
    measured["scale"] = scale
    # Cùng tỉ lệ nhưng nhỏ hơn: không méo, chỉ mất nét khi phóng.
    if abs(info.width / info.height - want_w / want_h) < 0.01:
        verb = "phóng" if scale > 1 else "thu"
        return Gate(
            "resolution_ok", "warn",
            f"{have} so với composition {want} — phải {verb} {scale}×, {verb} là mất nét",
            measured,
        )
    return Gate(
        "resolution_ok", "warn",
        f"{have} khác tỉ lệ composition {want} — sẽ phải crop hoặc thêm viền",
        measured,
    )


def gate_no_hard_cut(video: Path, threshold: float = HARD_CUT_THRESHOLD) -> Gate:
    """Một cảnh liền mạch hay bị cắt? Prompt dài dễ làm Flow cắt giữa clip."""
    cuts = _scene_cuts(video, threshold)
    if cuts is None:
        return Gate("no_hard_cut", "skip", "ffmpeg không chạy được scdet")
    if not cuts:
        return Gate("no_hard_cut", "pass",
                    f"không có cắt cảnh nào (ngưỡng điểm {threshold:g})",
                    {"threshold": threshold, "cuts": []})
    at = ", ".join(f"{c['at_s']}s ({c['score']})" for c in cuts[:4])
    more = f" +{len(cuts) - 4}" if len(cuts) > 4 else ""
    return Gate(
        "no_hard_cut", "warn",
        f"{len(cuts)} cắt cảnh cứng tại {at}{more} — clip lẽ ra phải liền một cảnh",
        {"threshold": threshold, "cuts": cuts},
    )


def gate_not_frozen(video: Path, noise_db: int = FREEZE_NOISE_DB,
                    min_s: float = FREEZE_MIN_S) -> Gate:
    """Đoạn đứng yên dài bất thường = Flow treo, hoặc model bỏ phần chuyển động."""
    segs = _freezes(video, noise_db, min_s)
    if segs is None:
        return Gate("not_frozen", "skip", "ffmpeg không chạy được freezedetect")
    measured = {"noise_db": noise_db, "min_s": min_s, "segments": segs}
    if not segs:
        return Gate("not_frozen", "pass", f"không có đoạn đứng yên ≥{min_s}s", measured)
    worst = max(segs, key=lambda s: s.get("duration_s") or 0)
    return Gate(
        "not_frozen", "warn",
        f"{len(segs)} đoạn đứng yên, dài nhất {worst.get('duration_s')}s "
        f"(từ {worst.get('start_s')}s) — kiểm tra Flow có trả lại khung đứng không",
        measured,
    )


# --------------------------------------------------------------------------- #
# Board UI dựng sẵn trong pixel
# --------------------------------------------------------------------------- #
#
# Hai gate dưới đây dùng chung một lần quét khung, nên kết quả được nhớ theo (file, mtime).
# Quét 30 khung/0.1s bằng ffmpeg rồi phân tích ảnh — lặp lại hai lần là gấp đôi thời gian
# export mà không thêm thông tin nào.

_UI_SCAN_CACHE: dict[tuple[str, float], dict] = {}


def _scan_ui(video: Path, *, step_s: float = 0.1, max_scan_s: float = 3.0) -> dict:
    """Tìm mốc clip hết dính board UI.

    Khác `delivery.find_ui_clean_point` ở chỗ **phân biệt được ba trạng thái**, thứ mà
    `None` không nói được: khung đầu đã sạch / sạch từ giây X / quét hết vẫn dơ. QA cần
    trạng thái thứ ba để cảnh báo "cả đoạn đầu dính UI" thay vì im lặng.

    Trả `{"state": "clean", "dirty_until_s": None}` khi khung đầu sạch,
    `{"state": "recovers", "dirty_until_s": x}` khi sạch lại từ x,
    `{"state": "dirty", "scanned_to_s": n}` khi quét hết `max_scan_s` vẫn dơ,
    `{"state": "unmeasurable", "reason": ...}` khi không có ffmpeg/Pillow.
    """
    try:
        key = (str(video.resolve()), video.stat().st_mtime)
    except OSError:
        return {"state": "unmeasurable", "reason": "không đọc được file"}
    cached = _UI_SCAN_CACHE.get(key)
    if cached is not None:
        return cached

    from .delivery import _frame_is_clean

    tmp = Path(tempfile.mkdtemp(prefix="qa_ui_"))
    try:
        first = tmp / "s000.png"
        if not _grab_frame(video, 0.0, first):
            res = {"state": "unmeasurable", "reason": "ffmpeg không cắt được khung đầu"}
        elif _frame_is_clean(first):
            res = {"state": "clean", "dirty_until_s": None}
        else:
            res = {"state": "dirty", "scanned_to_s": round(max_scan_s, 3)}
            t = step_s
            while t <= max_scan_s + 1e-9:
                cand = tmp / f"s{int(round(t * 100)):04d}.png"
                if _grab_frame(video, t, cand) and _frame_is_clean(cand):
                    res = {"state": "recovers", "dirty_until_s": round(t, 3)}
                    break
                t = round(t + step_s, 3)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    _UI_SCAN_CACHE[key] = res
    return res


def gate_no_baked_ui(video: Path) -> Gate:
    """Pixel có board UI dựng sẵn không? Chữ burn-in thì HyperFrames không gỡ được."""
    scan = _scan_ui(video)
    state = scan["state"]
    if state == "unmeasurable":
        return Gate("no_baked_ui", "skip", scan.get("reason") or "không quét được khung")
    if state == "clean":
        return Gate("no_baked_ui", "pass", "không có board UI trong pixel", scan)
    if state == "recovers":
        return Gate(
            "no_baked_ui", "warn",
            f"board UI nằm trong {scan['dirty_until_s']}s đầu — đặt in-point tại "
            f"{scan['dirty_until_s']}s hoặc sinh lại bằng plate sạch",
            scan,
        )
    return Gate(
        "no_baked_ui", "warn",
        f"quét tới {scan['scanned_to_s']}s vẫn còn board UI — clip này không dùng được "
        "làm B-roll sạch, phải sinh lại bằng plate sạch",
        scan,
    )


def gate_hook_clean(video: Path, hook_end_s: float) -> Gate:
    """Hook là thứ người lướt đọc đầu tiên — chữ/board trên đó là mất cả hook."""
    scan = _scan_ui(video)
    state = scan["state"]
    if state == "unmeasurable":
        return Gate("hook_clean", "skip", scan.get("reason") or "không quét được khung")
    if state == "clean":
        return Gate("hook_clean", "pass", f"{hook_end_s}s hook không dính UI",
                    {"hook_end_s": hook_end_s, **scan})

    dirty_until = scan.get("dirty_until_s")
    if dirty_until is None:
        dirty_until = scan.get("scanned_to_s")
    measured = {"hook_end_s": hook_end_s, "dirty_until_s": dirty_until, **scan}
    # Board đã hết trước khi hook kết thúc ⇒ chữ đè đúng phần hook.
    if dirty_until is not None and dirty_until < hook_end_s:
        return Gate(
            "hook_clean", "warn",
            f"board UI phủ {dirty_until}s đầu, tức gần trọn hook {hook_end_s}s — "
            "cắt bỏ là mất hook, để nguyên là đưa chữ lên sóng",
            measured,
        )
    return Gate(
        "hook_clean", "warn",
        f"hook {hook_end_s}s vẫn còn board UI (dơ tới {dirty_until}s) — phải sinh lại hook",
        measured,
    )


# --------------------------------------------------------------------------- #
# Nối clip & độ tĩnh của hook
# --------------------------------------------------------------------------- #


def gate_chain_match(video: Path, prev_video: Path, *, ssim_min: float = CHAIN_SSIM_MIN) -> Gate:
    """Khung cuối clip trước có khớp khung đầu clip này? `chain_from` mà lệch là nhảy cảnh.

    Đo trên dữ liệu thật: SSIM giữa khung đầu và khung cuối của **cùng** clip1 là 0.475,
    nên ngưỡng này chỉ có nghĩa cho cặp hai clip liên tiếp — nó bắt đúng trường hợp Flow
    trả khung mở đầu khác hẳn ảnh `last_frame` mình gửi.
    """
    tmp = Path(tempfile.mkdtemp(prefix="qa_chain_"))
    try:
        last = tmp / "prev_last.png"
        first = tmp / "next_first.png"
        if not prev_video.is_file() or not video.is_file():
            return Gate("chain_match", "skip", "thiếu file của một trong hai clip")
        if not _grab_last_frame(prev_video, last) or not _grab_frame(video, 0.0, first):
            return Gate("chain_match", "skip", "ffmpeg không cắt được khung nối")
        score = _ssim_between(last, first)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if score is None:
        return Gate("chain_match", "skip", "ffmpeg không tính được SSIM")
    measured = {"ssim": score, "ssim_min": ssim_min, "from": prev_video.name}
    if score >= ssim_min:
        return Gate("chain_match", "pass", f"SSIM {score} ≥ {ssim_min}", measured)
    return Gate(
        "chain_match", "warn",
        f"khung nối chỉ đạt SSIM {score} < {ssim_min} — clip trước kết thúc khác cảnh với "
        f"khung mở đầu clip này, sẽ thấy nhảy hình",
        measured,
    )


def gate_hook_still(video: Path, hook_end_s: float, *,
                    ratio_max: float = HOOK_STILL_RATIO_MAX) -> Gate:
    """Hook phải đứng yên hơn phần thân, nếu không người xem không kịp đọc chữ.

    Đo bằng trung vị chênh lệch khung liên tiếp (12fps): nhiễu chuyển động rất chậm không
    kéo trung vị lệch như khi lấy trung bình. Clip thật: hook 0–1s = 0.95, thân 2–8s = 4.55
    ⇒ tỉ lệ 0.21, cách xa ngưỡng 0.6.
    """
    curve = _motion_curve(video)
    if curve is None:
        return Gate("hook_still", "skip", "ffmpeg không đo được chuyển động")
    total = curve[-1][0] if curve else 0.0
    if hook_end_s <= 0 or total <= hook_end_s:
        return Gate("hook_still", "skip", f"clip quá ngắn để tách hook {hook_end_s}s")

    hook = [v for t, v in curve if t < hook_end_s]
    body = [v for t, v in curve if t >= hook_end_s]
    if not hook or not body:
        return Gate("hook_still", "skip", "không đủ khung ở một trong hai nửa clip")

    hook_med, body_med = round(_median(hook), 3), round(_median(body), 3)
    measured = {
        "hook_end_s": hook_end_s,
        "hook_median": hook_med,
        "body_median": body_med,
        "ratio_max": ratio_max,
    }
    # Thân clip cũng gần như đứng yên ⇒ tỉ lệ vô nghĩa, không kết luận.
    if body_med < 0.5:
        return Gate("hook_still", "skip",
                    f"thân clip cũng gần như đứng yên (trung vị {body_med}) — không so được",
                    measured)
    ratio = round(hook_med / body_med, 3)
    measured["ratio"] = ratio
    if ratio <= ratio_max:
        return Gate("hook_still", "pass",
                    f"hook đứng yên bằng {ratio}× thân clip (≤ {ratio_max})", measured)
    return Gate(
        "hook_still", "warn",
        f"hook chuyển động bằng {ratio}× thân clip (ngưỡng {ratio_max}) — người xem không "
        "kịp đọc chữ hook, nên làm chậm 2 giây đầu",
        measured,
    )


# --------------------------------------------------------------------------- #
# Tổng hợp
# --------------------------------------------------------------------------- #


def hook_window_s(clip: ClipSpec) -> float:
    """Hook kéo dài tới đâu: hết beat đầu tiên nếu có beat, ngược lại 2s mặc định.

    Lấy từ `beats[0].end_s` chứ không hằng số — hook của clip 6s khác hook của clip 8s, và
    script là nơi duy nhất khai được điều đó.
    """
    if clip.beats:
        return clip.beats[0].end_s
    return min(2.0, clip.duration_s)


def evaluate_clip(
    clip: ClipSpec,
    video: str | Path | None,
    script: Optional[LookbookScript] = None,
    *,
    prev_video: str | Path | None = None,
    run_gates: Optional[set[str]] = None,
    info: Optional[MediaInfo] = None,
) -> ClipQA:
    """Chấm một clip đã sinh. Không bao giờ raise, không bao giờ trả `fail`.

    `prev_video`: clip nguồn của `chain_from`, để chấm `chain_match`.
    `run_gates`: chạy con của tập gate (dùng cho test/CLI nhanh); mặc định chạy hết.
    `info`: `MediaInfo` đã đo sẵn — `delivery` đã probe trước khi gọi, đo lại là phí.
    """
    if video is None:
        return ClipQA(
            clip_id=clip.id,
            path=None,
            gates=[Gate("present", "warn", "clip chưa được sinh — không có gì để chấm")],
        )

    p = Path(video)
    if not p.is_file():
        return ClipQA(
            clip_id=clip.id,
            path=str(p),
            gates=[Gate("present", "warn", f"không thấy file {p.name} — clip chưa được sinh")],
        )

    def want(name: str) -> bool:
        return run_gates is None or name in run_gates

    if info is None:
        info = probe_video(p)
    gates: list[Gate] = []

    if want("duration_match"):
        gates.append(gate_duration_match(info, clip))
    if want("fps_ok"):
        gates.append(gate_fps_ok(info))
    if want("resolution_ok"):
        gates.append(gate_resolution_ok(info, script))
    if want("no_hard_cut"):
        gates.append(gate_no_hard_cut(p))
    if want("not_frozen"):
        gates.append(gate_not_frozen(p))
    if want("no_baked_ui"):
        gates.append(gate_no_baked_ui(p))

    hook_end = hook_window_s(clip)
    if want("hook_clean"):
        gates.append(gate_hook_clean(p, hook_end))
    if want("hook_still"):
        gates.append(gate_hook_still(p, hook_end))

    if want("chain_match"):
        if clip.chain_source_clip is None:
            gates.append(Gate("chain_match", "skip",
                              "clip này không nối từ clip nào (`chain_from` rỗng)"))
        elif prev_video is None:
            gates.append(Gate("chain_match", "skip",
                              f"cần clip nguồn `{clip.chain_source_clip}` để so khung nối"))
        else:
            gates.append(gate_chain_match(p, Path(prev_video)))

    return ClipQA(clip_id=clip.id, path=str(p), gates=gates)


def qa_summary(clips_qa: list[ClipQA]) -> dict:
    """Bảng tổng cho `delivery.json` + README.

    `status` gộp theo mức xấu nhất. `ok` chỉ đúng khi mọi gate đều `pass` — một `skip` nghĩa
    là có thứ chưa ai kiểm, không được tính là đạt.
    """
    counts = {"pass": 0, "warn": 0, "skip": 0}
    for qa in clips_qa:
        for g in qa.gates:
            counts[g.status] = counts.get(g.status, 0) + 1
    worst = max((qa.status for qa in clips_qa), key=lambda s: _STATUS_ORDER[s], default="skip")
    return {
        "status": worst,
        "clips": len(clips_qa),
        "counts": counts,
        "ok": worst == "pass" and all(g.status == "pass" for qa in clips_qa for g in qa.gates),
        "warnings": [w for qa in clips_qa for w in qa.warnings],
        "skipped": [s for qa in clips_qa for s in qa.skipped],
    }


