"""Hợp đồng `clips[].beats` / `goal` / `negative` trong script Lookbook.

Vì sao kiểm chặt: beat là **mốc neo duy nhất** cho cả prompt lẫn QA. Beat hở nghĩa là không ai biết
giây thứ 4.5 người mẫu làm gì, và gate `hook_still` sẽ so trên khoảng thời gian sai — nó vẫn "pass"
nhưng pass trên dữ liệu vô nghĩa. Validate phải bắt lúc load script, không phải lúc render.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.Workflows.script_contract import BeatSpec, ScriptError, load_default_script, load_script

ROOT = Path(__file__).resolve().parents[1]


def _raw() -> dict:
    return json.loads((ROOT / "configs" / "lookbook_script.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Script mẫu
# --------------------------------------------------------------------------- #


def test_default_script_declares_beats_for_every_clip():
    script = load_default_script()
    assert script is not None
    for clip in script.clips:
        assert clip.has_beats, f"clip '{clip.id}' chưa khai beats"
        assert clip.goal.strip(), f"clip '{clip.id}' chưa khai goal"


def test_default_script_beats_cover_clip_exactly():
    script = load_default_script()
    assert script is not None
    for clip in script.clips:
        assert clip.beats[0].at_s == 0
        assert clip.beats[-1].end_s == clip.duration_s
        for prev, nxt in zip(clip.beats, clip.beats[1:]):
            assert prev.end_s == nxt.at_s


def test_hook_clip_holds_gaze_before_it_turns():
    """3 giây hook: mắt phải khoá ống kính *trước* khi xoay. Đảo thứ tự là mất hook."""
    script = load_default_script()
    assert script is not None
    hook = script.clip("clip1")
    assert hook.role == "hook"
    assert hook.beats[0].holds_gaze, "beat đầu của clip hook phải holds_gaze"
    assert hook.beats[0].at_s == 0


def test_every_holds_gaze_beat_declares_must_not():
    script = load_default_script()
    assert script is not None
    for clip in script.clips:
        for beat in clip.beats:
            if beat.holds_gaze:
                assert beat.must_not, f"clip '{clip.id}' beat {beat.at_s}s holds_gaze nhưng must_not rỗng"


# --------------------------------------------------------------------------- #
# Validate bắt lỗi cấu trúc
# --------------------------------------------------------------------------- #


def test_rejects_beats_not_starting_at_zero():
    raw = _raw()
    raw["clips"][0]["beats"][0]["at_s"] = 1
    with pytest.raises(ScriptError, match="0s"):
        load_script(raw)


def test_rejects_gap_between_beats():
    raw = _raw()
    raw["clips"][0]["beats"][1]["at_s"] = 3  # beat trước kết thúc ở 2
    with pytest.raises(ScriptError, match="hở"):
        load_script(raw)


def test_rejects_overlapping_beats():
    raw = _raw()
    raw["clips"][0]["beats"][1]["at_s"] = 1  # chồng lên beat 0..2
    with pytest.raises(ScriptError, match="chồng lấn"):
        load_script(raw)


def test_rejects_beats_not_covering_clip_duration():
    raw = _raw()
    raw["clips"][0]["beats"][-1]["duration_s"] = 1  # phủ 6s thay vì 8s
    with pytest.raises(ScriptError, match="phải bằng nhau"):
        load_script(raw)


def test_rejects_holds_gaze_without_must_not():
    raw = _raw()
    raw["clips"][0]["beats"][0]["must_not"] = []
    with pytest.raises(ScriptError, match="must_not"):
        load_script(raw)


def test_rejects_zero_duration_beat():
    raw = _raw()
    raw["clips"][0]["beats"][0]["duration_s"] = 0
    with pytest.raises(ScriptError, match="duration_s"):
        load_script(raw)


def test_rejects_empty_action():
    raw = _raw()
    raw["clips"][0]["beats"][0]["action"] = "   "
    with pytest.raises(ScriptError, match="action"):
        load_script(raw)


def test_clip_without_beats_still_loads():
    """Field tuỳ chọn: script cũ (chỉ có motion_prompt) phải load được."""
    raw = _raw()
    for clip in raw["clips"]:
        clip.pop("beats", None)
        clip.pop("goal", None)
        clip.pop("negative", None)
    script = load_script(raw)
    assert all(not c.has_beats for c in script.clips)


def test_brief_exposes_beats_for_the_agent():
    """Agent đọc `brief()`; beats không có ở đây thì agent lại chỉ thấy slug/title."""
    script = load_default_script()
    assert script is not None
    brief = script.brief()
    for entry in brief["clips"]:
        assert entry["beats"], entry["id"]
        for beat in entry["beats"]:
            assert set(beat) >= {"at_s", "duration_s", "action", "holds_gaze", "must_not"}


def test_beat_end_s_is_derived_not_declared():
    beat = BeatSpec(at_s=2.5, duration_s=3, action="Turns.")
    assert beat.end_s == 5.5
