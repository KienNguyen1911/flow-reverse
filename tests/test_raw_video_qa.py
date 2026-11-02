"""QA clip thô trước khi đưa sang HyperFrames.

Bối cảnh: pipeline chỉ kiểm prompt (`prompt_lint`) — tức kiểm **điều mình xin**, không kiểm
**thứ Flow trả**. Clip thật trong repo chứng minh khoảng trống đó: 720×1280 thay vì
1080×1920, và board UI dựng sẵn trong 1.3s đầu — đúng bằng cửa sổ hook. Người dựng chỉ
phát hiện khi đã lên timeline.

Hai hợp đồng được khoá ở đây:

1. Gate **không bao giờ** trả `fail`: người dùng chọn "chỉ cảnh báo", nên xấu nhất là `warn`,
   và `passes` của delivery không bị gate nào chặn.
2. Gate không đo được trả `skip` **kèm lý do** — không bịa số. `skip` không phải `pass`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.Workflows.raw_video_qa import (
    CHAIN_SSIM_MIN,
    HARD_CUT_THRESHOLD,
    ClipQA,
    Gate,
    evaluate_clip,
    gate_chain_match,
    gate_duration_match,
    gate_fps_ok,
    gate_hook_still,
    gate_no_hard_cut,
    gate_not_frozen,
    gate_resolution_ok,
    hook_window_s,
    qa_summary,
)
from src.Workflows.media_probe import probe_video
from src.Workflows.script_contract import BeatSpec, ClipSpec, load_default_script

ROOT = Path(__file__).resolve().parents[1]
#: Clip thật do Flow sinh, đã nằm trong delivery — dùng làm chuẩn "đo được".
REAL_CLIP = ROOT / "out" / "deliveries" / "havana_donna_set" / "clips" / "clip1.mp4"

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg không có trong PATH")
needs_real = pytest.mark.skipif(not REAL_CLIP.is_file(), reason="chưa có clip thật trong out/deliveries")


def _clip(**kw) -> ClipSpec:
    base = dict(id="c1", role="hook", motion_prompt="x", duration_s=8.0)
    base.update(kw)
    return ClipSpec(**base)


def _gate(clip_qa: ClipQA, name: str) -> Gate:
    hit = next((g for g in clip_qa.gates if g.name == name), None)
    assert hit is not None, f"thiếu gate {name} trong {[g.name for g in clip_qa.gates]}"
    return hit


# --------------------------------------------------------------------------- #
# Hợp đồng: không chặn, không bịa số
# --------------------------------------------------------------------------- #


def test_gate_status_is_only_pass_warn_skip():
    """"Chỉ cảnh báo" là quyết định của người dùng — không có `fail` nào được lọt ra."""
    qa = evaluate_clip(_clip(), None)
    assert qa.status in ("pass", "warn", "skip")
    for g in qa.gates:
        assert g.status in ("pass", "warn", "skip")


def test_missing_clip_is_warn_not_crash(tmp_path):
    qa = evaluate_clip(_clip(), tmp_path / "nope.mp4")
    assert qa.status == "warn"
    assert "chưa được sinh" in qa.gates[0].detail


def test_none_clip_is_warn_not_crash():
    qa = evaluate_clip(_clip(), None)
    assert qa.path is None
    assert qa.status == "warn"


def test_every_skip_gate_carries_a_reason():
    """`skip` không kèm lý do là im lặng giả dạng đã kiểm."""
    qa = evaluate_clip(_clip(), None)
    for g in qa.gates:
        if g.status == "skip":
            assert g.detail, f"gate {g.name} skip mà không nói vì sao"


def test_unmeasurable_media_skips_instead_of_inventing(tmp_path, monkeypatch):
    """Không có ffprobe: gate phải `skip`, tuyệt đối không trả width/duration bịa."""
    import src.Workflows.raw_video_qa as qa_mod

    fake = tmp_path / "video.mp4"
    fake.write_bytes(b"not a video")
    # probe_video trả MediaInfo chưa đo (như khi thiếu ffprobe).
    from src.Workflows.media_probe import MediaInfo

    monkeypatch.setattr(qa_mod, "probe_video", lambda p: MediaInfo(path=str(p), measured=False,
                                                                  error="không tìm thấy ffprobe"))
    qa = evaluate_clip(_clip(), fake, run_gates={"duration_match", "fps_ok", "resolution_ok"})
    assert all(g.status == "skip" for g in qa.gates)
    assert all("ffprobe" in g.detail for g in qa.gates)


# --------------------------------------------------------------------------- #
# Gate đo trên clip thật
# --------------------------------------------------------------------------- #


@needs_ffmpeg
@needs_real
def test_real_clip_passes_duration_fps_and_cuts():
    script = load_default_script()
    clip = script.clip("clip1")
    qa = evaluate_clip(clip, REAL_CLIP, script)

    assert _gate(qa, "duration_match").status == "pass"
    assert _gate(qa, "fps_ok").status == "pass"
    # t=4.0 chỉ là đổi tư thế (điểm 10.79), không phải cắt cảnh — ngưỡng 12 phải im.
    assert _gate(qa, "no_hard_cut").status == "pass"
    assert _gate(qa, "not_frozen").status == "pass"


@needs_ffmpeg
@needs_real
def test_real_clip_warns_about_upscale():
    """720×1280 trong composition 1080×1920: cảnh báo phải nói rõ hệ số 1.5×."""
    script = load_default_script()
    g = _gate(evaluate_clip(script.clip("clip1"), REAL_CLIP, script), "resolution_ok")
    assert g.status == "warn"
    assert "1.5" in g.detail
    assert g.measured["scale"] == 1.5


@needs_ffmpeg
@needs_real
def test_real_clip_warns_board_ui_over_the_hook():
    """Board phủ 1.3s, hook dài 2.0s ⇒ cảnh báo phải nói cắt là mất hook."""
    script = load_default_script()
    qa = evaluate_clip(script.clip("clip1"), REAL_CLIP, script)
    baked = _gate(qa, "no_baked_ui")
    hook = _gate(qa, "hook_clean")
    assert baked.status == "warn"
    assert baked.measured["dirty_until_s"] == pytest.approx(1.3, abs=0.2)
    assert hook.status == "warn"
    assert "mất hook" in hook.detail


@needs_ffmpeg
@needs_real
def test_real_hook_is_still_relative_to_body():
    """Hook 0–1s đo được trung vị 0.95, thân 2–8s 4.55 ⇒ tỉ lệ 0.21, phải đạt ngưỡng 0.6."""
    script = load_default_script()
    g = _gate(evaluate_clip(script.clip("clip1"), REAL_CLIP, script, run_gates={"hook_still"}),
              "hook_still")
    assert g.status == "pass"
    assert g.measured["ratio"] < 0.6
    assert g.measured["hook_median"] < g.measured["body_median"]


# --------------------------------------------------------------------------- #
# Gate phát hiện lỗi (fixture tổng hợp — không có clip hỏng thật trong repo)
# --------------------------------------------------------------------------- #


def _make_video(path: Path, filters: str, *, seconds: float = 2.0) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"testsrc=s=180x320:d={seconds}:r=24", "-vf", filters,
         "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, check=True,
    )
    return path


@needs_ffmpeg
def test_hard_cut_is_detected(tmp_path):
    """Cắt đỏ→xanh cho điểm scdet 15.63, trên ngưỡng 12 ⇒ phải warn."""
    cut = tmp_path / "cut.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=red:s=180x320:d=1:r=24",
         "-f", "lavfi", "-i", "color=blue:s=180x320:d=1:r=24",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
         "-pix_fmt", "yuv420p", str(cut)],
        capture_output=True, check=True,
    )
    g = gate_no_hard_cut(cut)
    assert g.status == "warn"
    assert len(g.measured["cuts"]) == 1
    assert g.measured["cuts"][0]["at_s"] == pytest.approx(1.0, abs=0.05)
    assert g.measured["cuts"][0]["score"] > HARD_CUT_THRESHOLD


@needs_ffmpeg
def test_continuous_motion_has_no_hard_cut(tmp_path):
    moving = _make_video(tmp_path / "moving.mp4", "null")
    assert gate_no_hard_cut(moving).status == "pass"


@needs_ffmpeg
def test_frozen_segment_is_detected(tmp_path):
    """1.2s đứng yên giữa clip phải bị bắt; -40dB báo nhầm nên đã chọn -50dB."""
    frozen = tmp_path / "frozen.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc=s=180x320:d=1:r=24",
         "-f", "lavfi", "-i", "testsrc=s=180x320:d=4:r=24",
         "-filter_complex",
         "[1:v]trim=start=3:end=4,setpts=PTS-STARTPTS,loop=loop=29:size=1:start=0,"
         "setpts=N/24/TB[st];[0:v][st]concat=n=2:v=1:a=0",
         "-pix_fmt", "yuv420p", str(frozen)],
        capture_output=True, check=True,
    )
    g = gate_not_frozen(frozen)
    assert g.status == "warn"
    assert g.measured["segments"]
    assert max(s["duration_s"] for s in g.measured["segments"]) >= 0.5


# --------------------------------------------------------------------------- #
# Ngưỡng lấy từ đo, không phải số tròn
# --------------------------------------------------------------------------- #


def test_hard_cut_threshold_sits_between_measured_clusters():
    """Clip thật đỉnh 10.79; cắt cứng tổng hợp 15.63 ⇒ ngưỡng phải nằm giữa."""
    assert 10.79 < HARD_CUT_THRESHOLD < 15.63


def test_chain_threshold_is_documented_and_strict():
    """Ngưỡng SSIM thấp hơn 0.9 thì hai khung khác cảnh vẫn lọt."""
    assert CHAIN_SSIM_MIN == 0.90


@needs_ffmpeg
def test_chain_mismatch_between_unrelated_clips(tmp_path):
    """Hai clip khác hẳn nội dung: khung nối không khớp ⇒ warn (đây là lỗi `chain_from`)."""
    red = tmp_path / "red.mp4"
    blue = tmp_path / "blue.mp4"
    for colour, path in (("red", red), ("blue", blue)):
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             f"color={colour}:s=180x320:d=1:r=24", "-pix_fmt", "yuv420p", str(path)],
            capture_output=True, check=True,
        )
    g = gate_chain_match(blue, red)
    assert g.status == "warn"
    assert g.measured["ssim"] < CHAIN_SSIM_MIN


def test_chain_match_skips_without_source_clip(tmp_path):
    """Clip không khai `chain_from` thì không có gì để so — phải `skip`, không phải warn."""
    qa = evaluate_clip(_clip(chain_from=None), tmp_path / "whatever.mp4",
                       run_gates={"chain_match"})
    # File không tồn tại nên chỉ có gate `present`; tạo file rỗng để đi tới nhánh chain.
    real = tmp_path / "v.mp4"
    real.write_bytes(b"x")
    qa = evaluate_clip(_clip(chain_from=None), real, run_gates={"chain_match"})
    assert _gate(qa, "chain_match").status == "skip"
    assert "chain_from" in _gate(qa, "chain_match").detail


# --------------------------------------------------------------------------- #
# Cửa sổ hook lấy từ beats, không hardcode
# --------------------------------------------------------------------------- #


def test_hook_window_comes_from_first_beat():
    """Hook của clip 6s khác clip 8s — script là nơi duy nhất khai được."""
    clip = _clip(duration_s=6.0, beats=[
        BeatSpec(at_s=0.0, duration_s=1.5, action="hold"),
        BeatSpec(at_s=1.5, duration_s=4.5, action="turn"),
    ])
    assert hook_window_s(clip) == 1.5


def test_hook_window_falls_back_to_two_seconds():
    assert hook_window_s(_clip()) == 2.0


def test_hook_window_never_exceeds_clip():
    short = _clip(duration_s=1.0)
    assert hook_window_s(short) <= short.duration_s


# --------------------------------------------------------------------------- #
# Tổng hợp
# --------------------------------------------------------------------------- #


def test_summary_status_is_worst_gate():
    good = ClipQA("c1", "a.mp4", [Gate("g", "pass", "ok")])
    bad = ClipQA("c2", "b.mp4", [Gate("g", "warn", "meh")])
    assert qa_summary([good])["status"] == "pass"
    assert qa_summary([good, bad])["status"] == "warn"


def test_summary_counts_skips_separately_and_ok_is_strict():
    """`skip` không phải `pass`: có gate chưa kiểm thì `ok` phải là False."""
    only_pass = ClipQA("c1", "a.mp4", [Gate("g", "pass", "ok")])
    with_skip = ClipQA("c2", "b.mp4", [Gate("g", "pass", "ok"), Gate("h", "skip", "no ffmpeg")])
    s = qa_summary([only_pass, with_skip])
    assert s["counts"] == {"pass": 2, "warn": 0, "skip": 1}
    assert s["ok"] is False
    assert len(s["skipped"]) == 1
    assert qa_summary([only_pass])["ok"] is True


@needs_ffmpeg
@needs_real
def test_full_evaluation_reports_all_gates():
    script = load_default_script()
    qa = evaluate_clip(script.clip("clip1"), REAL_CLIP, script)
    names = {g.name for g in qa.gates}
    assert names >= {
        "duration_match", "fps_ok", "resolution_ok", "no_hard_cut",
        "not_frozen", "no_baked_ui", "hook_clean", "hook_still", "chain_match",
    }


# --------------------------------------------------------------------------- #
# Delivery tích hợp
# --------------------------------------------------------------------------- #


@needs_ffmpeg
def test_delivery_json_carries_qa_and_summary(tmp_path):
    """`delivery.json` phải có `clips[].qa` và `qa_summary` — nếu không, QA vô hình với editor."""
    from src.Workflows.delivery import RunRef, build_delivery

    sample = ROOT / "out" / "nodes" / "video_20261030_230016"
    if not (sample / "video.mp4").is_file():
        pytest.skip("chưa có video mẫu trong out/nodes")

    s = load_default_script()
    res = build_delivery(
        s, [RunRef(clip_id="clip1", run_id="video_20261030_230016",
                   run_dir="out/nodes/video_20261030_230016")],
        dest_root=tmp_path,
    )
    m = json.loads(Path(res.manifest_path).read_text(encoding="utf-8"))

    assert "qa_summary" in m
    assert m["qa_summary"]["status"] in ("pass", "warn", "skip")
    clip1 = next(c for c in m["clips"] if c["id"] == "clip1")
    assert clip1["qa"] is not None
    assert clip1["qa"]["gates"]
    # Clip chưa sinh vẫn phải có entry QA nói rõ — không được bỏ trống.
    clip2 = next(c for c in m["clips"] if c["id"] == "clip2")
    assert clip2["qa"]["status"] == "warn"


@needs_ffmpeg
def test_readme_renders_qa_table_for_warnings(tmp_path):
    from src.Workflows.delivery import RunRef, build_delivery

    sample = ROOT / "out" / "nodes" / "video_20261030_230016"
    if not (sample / "video.mp4").is_file():
        pytest.skip("chưa có video mẫu trong out/nodes")

    s = load_default_script()
    res = build_delivery(
        s, [RunRef(clip_id="clip1", run_id="video_20261030_230016",
                   run_dir="out/nodes/video_20261030_230016")],
        dest_root=tmp_path,
    )
    readme = Path(res.readme_path).read_text(encoding="utf-8")
    assert "Kiểm tra clip thô (QA)" in readme
    assert "| clip | gate | kết quả | số đo |" in readme
    assert "warn" in readme
    # Câu chốt hợp đồng: QA không chặn dựng phim.
    assert "không chặn dựng phim" in readme


def test_readme_omits_qa_table_when_everything_passes(tmp_path):
    """Không có gì bất thường thì đừng làm README rối."""
    from src.Workflows.delivery import DeliveryResult, _render_readme

    manifest = {
        "slug": "s", "title": "t", "created_ts": "now",
        "canvas": {"width": 1080, "height": 1920, "fps": 24, "duration_s": 8},
        "plate": "plate.png", "plate_has_baked_ui": False,
        "clips": [{"id": "clip1", "qa": {"status": "pass", "gates": [
            {"name": "duration_match", "status": "pass", "detail": "ok", "measured": {}}]}}],
        "items": [], "timeline": [],
        "summary": {"has_audio": False, "clips_missing": []},
        "qa_summary": {"status": "pass", "counts": {"pass": 1, "warn": 0, "skip": 0}},
    }
    result = DeliveryResult(slug="s", dest_dir="d", manifest_path="m", readme_path="r")
    readme = _render_readme(manifest, result)
    assert "Kiểm tra clip thô (QA)" not in readme


def test_qa_never_raises_on_broken_file(tmp_path):
    """File rác trong out/ không được làm sập export."""
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"\x00\x01\x02 not a video")
    qa = evaluate_clip(_clip(), broken)
    assert qa.status in ("pass", "warn", "skip")
