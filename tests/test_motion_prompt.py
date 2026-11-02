"""Beat → prompt renderer: tất định, sống sót sanitizer, từ vựng đóng.

Vì sao test này là gate chứ không phải kiểm tra phụ: prompt video được gửi Flow **sau** khi đi qua
`sanitize_video_prompt()`. Nếu prompt render ra bị sanitizer viết lại, mọi thứ người viết script khai
(timeline, hook, mệnh đề phủ định) có thể đã bị phá trước khi tới model — và lỗi chỉ lộ ra sau 8 phút
render. Test này bắt trước khi tốn credit.
"""

from __future__ import annotations

import re

import pytest

from src.Bridge.flow_video_bridge import sanitize_video_prompt
from src.Workflows.motion_prompt import (
    MAX_PROMPT_WORDS,
    MotionPromptError,
    beats_to_prompt,
    prompt_warnings,
)
from src.Workflows.script_contract import BeatSpec, ClipSpec, load_default_script

ROOT_CLIP = ClipSpec(
    id="clip1",
    role="hook",
    motion_prompt="",
    duration_s=8.0,
    camera="push_in_slow",
    beats=[
        BeatSpec(at_s=0, duration_s=2, action="Stands square to the lens, holds steady eye contact.",
                 holds_gaze=True, must_not=["turn away"]),
        BeatSpec(at_s=2, duration_s=3, action="Turns a full 360 degrees in place at an even pace."),
        BeatSpec(at_s=5, duration_s=3, action="Completes the turn and settles back into the opening stance.",
                 holds_gaze=True, must_not=["stop mid-turn"]),
    ],
    negative=["One continuous shot, staying inside the frame, with no cut"],
)


# --------------------------------------------------------------------------- #
# Round-trip sanitizer — gate chính
# --------------------------------------------------------------------------- #


def test_sample_script_prompts_survive_sanitizer():
    """Cả hai clip mẫu: sanitize(aggressive=False) phải trả **nguyên văn** prompt đã render."""
    script = load_default_script()
    assert script is not None
    for clip in script.clips:
        prompt = beats_to_prompt(clip)
        out = sanitize_video_prompt(prompt, aggressive=False)
        assert out == prompt.strip(), (
            f"clip '{clip.id}' bị sanitizer viết lại trước khi tới Flow.\n"
            f"  render : {prompt}\n  sent   : {out}"
        )


def test_rendered_prompt_has_no_timecode_labels():
    """Nhãn giây bị sanitizer xoá/để lại rác ⇒ renderer không được sinh ra chúng."""
    prompt = beats_to_prompt(ROOT_CLIP)
    for pattern in (r"\b\d+\s*s\s*[-–]\s*\d+\s*s\s*:", r"\[\s*\d+(?:\.\d+)?s", r"\(\s*\d+(?:\.\d+)?s"):
        assert not re.search(pattern, prompt), f"prompt còn nhãn thời gian {pattern!r}: {prompt}"


def test_beats_become_ordered_prose():
    """Ba beat phải xuất hiện đúng thứ tự và mốc giây được diễn đạt bằng chữ."""
    prompt = beats_to_prompt(ROOT_CLIP)
    assert "For the first two seconds" in prompt
    assert "From the second to the fifth second" in prompt
    assert "In the final three seconds" in prompt
    # Thứ tự phải đúng: beat 1 trước beat 2 trước beat 3.
    assert prompt.index("For the first") < prompt.index("From the second") < prompt.index("In the final")


def test_camera_sentence_leads_prompt():
    prompt = beats_to_prompt(ROOT_CLIP)
    assert prompt.startswith("Camera pushes in slowly at natural real-time speed.")


def test_chain_from_clip_opens_with_continuation():
    """Clip nối tiếp phải mở đầu bằng dấu hiệu nối, nếu không model đặt lại tư thế ở khung đầu."""
    clip = ClipSpec(
        id="clip2", role="showcase", motion_prompt="", duration_s=8.0,
        camera="drift_same_axis", chain_from="clip1.last_frame",
        beats=[BeatSpec(at_s=0, duration_s=8, action="Angles forty-five degrees to one side.")],
    )
    prompt = beats_to_prompt(clip)
    assert prompt.startswith("Continuing from that pose,")


def test_holds_gaze_beat_mentions_eye_contact_even_if_action_omits_it():
    """`holds_gaze` là hợp đồng với QA, không được phụ thuộc việc người viết có nhắc hay không."""
    clip = ClipSpec(
        id="c", role="hook", motion_prompt="", duration_s=8.0, camera="locked",
        beats=[BeatSpec(at_s=0, duration_s=2, action="Stands still.", holds_gaze=True,
                        must_not=["turn away"])],
    )
    assert "steady eye contact with the lens" in beats_to_prompt(clip)


def test_negative_clauses_are_sentences():
    """Mệnh đề phủ định phải viết hoa đầu câu: chúng đứng sau dấu chấm."""
    prompt = beats_to_prompt(ROOT_CLIP)
    assert "One continuous shot, staying inside the frame, with no cut." in prompt


# --------------------------------------------------------------------------- #
# Bộ từ vựng đóng — chặn trước khi tốn credit
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("action,needle", [
    ("Looks at the camera and smiles.", "looks at the camera"),
    ("Facing the camera, she turns slowly.", "facing the camera"),
    ("The woman stands still.", "the woman"),
    ("She turns a full 360 degrees.", "she"),
    ("Stands still in slow motion.", "slow motion"),
    ("Is wearing a cream silk camisole.", "is"),  # động từ ngoài MOTION_VERBS
])
def test_rejects_actions_that_the_filter_would_rewrite(action, needle):
    clip = ClipSpec(
        id="c", role="hook", motion_prompt="", duration_s=8.0, camera="locked",
        beats=[BeatSpec(at_s=0, duration_s=8, action=action)],
    )
    with pytest.raises(MotionPromptError) as exc:
        beats_to_prompt(clip)
    assert needle in str(exc.value).lower() or "MOTION_VERBS" in str(exc.value)


def test_ui_vocabulary_matches_word_boundary_not_substring():
    """`cardigan` không được bị coi là `card`, giống test của linter."""
    clip = ClipSpec(
        id="c", role="showcase", motion_prompt="", duration_s=8.0, camera="locked",
        beats=[BeatSpec(at_s=0, duration_s=8, action="Lifts the sheer cardigan higher on the shoulder.")],
    )
    assert "cardigan" in beats_to_prompt(clip)


def test_ui_vocabulary_still_caught_as_whole_word():
    clip = ClipSpec(
        id="c", role="hook", motion_prompt="", duration_s=8.0, camera="locked",
        beats=[BeatSpec(at_s=0, duration_s=8, action="Turns with a glowing card in frame.")],
    )
    with pytest.raises(MotionPromptError):
        beats_to_prompt(clip)


def test_only_supported_camera_keys():
    clip = ClipSpec(
        id="c", role="hook", motion_prompt="", duration_s=8.0, camera="dramatic_swoop",
        beats=[BeatSpec(at_s=0, duration_s=8, action="Stands still.")],
    )
    with pytest.raises(MotionPromptError):
        beats_to_prompt(clip)


def test_clip_without_beats_refuses_to_render():
    """Không có beat thì renderer không bịa; agent tự viết theo skill."""
    clip = ClipSpec(id="c", role="hook", motion_prompt="legacy", duration_s=8.0)
    with pytest.raises(MotionPromptError):
        beats_to_prompt(clip)


# --------------------------------------------------------------------------- #
# Tất định + ngân sách
# --------------------------------------------------------------------------- #


def test_render_is_deterministic():
    """Cùng script → cùng prompt. Nếu không, gate round-trip mất giá trị."""
    a = beats_to_prompt(ROOT_CLIP)
    b = beats_to_prompt(ROOT_CLIP)
    assert a == b


def test_all_renders_fit_hard_ceiling():
    script = load_default_script()
    assert script is not None
    for clip in script.clips:
        assert len(beats_to_prompt(clip).split()) <= MAX_PROMPT_WORDS


def test_warnings_flag_missing_negative():
    clip = ClipSpec(
        id="c", role="hook", motion_prompt="", duration_s=8.0, camera="locked",
        beats=[BeatSpec(at_s=0, duration_s=8, action="Stands still.")],
    )
    assert any("negative" in w for w in prompt_warnings(clip, beats_to_prompt(clip)))


def test_sample_script_renders_without_warnings():
    """Script mẫu là tài liệu sống: nó phải sạch, nếu không người đọc sẽ copy cái sai."""
    script = load_default_script()
    assert script is not None
    for clip in script.clips:
        prompt = beats_to_prompt(clip)
        assert prompt_warnings(clip, prompt) == [], f"clip '{clip.id}': {prompt_warnings(clip, prompt)}"
