"""Agent instruction cho node video: phải thấy clip, phải thấy beat, phải cảnh báo khi thiếu clip.

Bối cảnh lỗi: `CanvasPanel.tsx` / `CanvasDrawer.tsx` gọi `/api/agent/generate-node-prompt` mà không
gửi `clip_id`. `_script_context_lines` khi đó im lặng rơi ra ngoài cả hai nhánh `if is_video and
clip_id:` và `elif not is_video and not task.is_item:` ⇒ node video chỉ nhận slug/title/fps. Hệ quả:
cả hai node video nhận cùng một context, agent đọc cùng một template, và không ai biết clip nào là
hook. Test này khoá cả ba trạng thái.
"""

from __future__ import annotations

import pytest

from src.Workflows.prompt_agent import NodePromptTask, PromptAgent
from src.Workflows.skill_manager import get_skill_manager


@pytest.fixture(scope="module")
def agent() -> PromptAgent:
    return PromptAgent()


@pytest.fixture(scope="module")
def skill():
    s = get_skill_manager().get_skill("lookbook-video-prompter")
    assert s is not None, "skill lookbook-video-prompter phải tồn tại"
    return s


def _instruction(agent: PromptAgent, skill, **kwargs) -> str:
    task = NodePromptTask(
        node_id=kwargs.pop("node_id", "lb_video_1"),
        node_type=kwargs.pop("node_type", "video"),
        upstream_media_urls=kwargs.pop("upstream", []),
        **kwargs,
    )
    return agent.format_agent_instruction(task, skill, [])


# --------------------------------------------------------------------------- #
# Có clip_id: đủ ngữ cảnh
# --------------------------------------------------------------------------- #


def test_clip_id_brings_role_and_goal(agent, skill):
    text = _instruction(agent, skill, clip_id="clip1")
    assert "vai **hook**" in text
    assert "Mục tiêu của clip" in text


def test_clip_id_brings_structured_beats(agent, skill):
    text = _instruction(agent, skill, clip_id="clip1")
    assert "Nhịp 8.0s của clip này" in text
    # Ba mốc, đúng thứ tự.
    assert "0.0–2.0s" in text
    assert "2.0–5.0s" in text
    assert "5.0–8.0s" in text
    assert text.index("0.0–2.0s") < text.index("2.0–5.0s") < text.index("5.0–8.0s")


def test_gaze_beats_are_marked_for_the_agent(agent, skill):
    """`holds_gaze` phải hiện ra như mệnh lệnh, không chỉ nằm trong JSON."""
    text = _instruction(agent, skill, clip_id="clip1")
    assert "GIỮ MẮT với ống kính" in text


def test_must_not_is_surfaced(agent, skill):
    """Payload Flow không có negative prompt ⇒ agent phải biết điều cấm để diễn đạt trong câu."""
    text = _instruction(agent, skill, clip_id="clip1")
    assert "cấm: turn away from the lens" in text


def test_rendered_prompt_is_embedded_verbatim(agent, skill):
    """Agent phải thấy đúng câu sẽ gửi Flow, nếu không nó viết câu khác và gate round-trip vô nghĩa."""
    from src.Workflows.motion_prompt import beats_to_prompt
    from src.Workflows.script_contract import load_default_script

    script = load_default_script()
    assert script is not None
    expected = beats_to_prompt(script.clip("clip1"))

    text = _instruction(agent, skill, clip_id="clip1")
    assert expected in text
    assert "KHÔNG đổi thứ tự beat" in text


def test_shots_are_attached_to_the_right_clip(agent, skill):
    """Shot thuộc clip1 là hook banner; shot cuối thuộc clip2. Lẫn clip là timeline sai."""
    text1 = _instruction(agent, skill, clip_id="clip1")
    assert "Lưng ngắn, vai ngang" in text1
    assert "Lưu ngay set này" not in text1

    text2 = _instruction(agent, skill, clip_id="clip2")
    assert "Lưu ngay set này" in text2
    assert "Lưng ngắn, vai ngang" not in text2


def test_chain_from_is_explained(agent, skill):
    text = _instruction(agent, skill, clip_id="clip2")
    assert "clip1.last_frame" in text


def test_two_clips_produce_different_context(agent, skill):
    """Đây chính là lỗi gốc: hai node video từng nhận context giống hệt nhau."""
    a = _instruction(agent, skill, clip_id="clip1")
    b = _instruction(agent, skill, clip_id="clip2")
    assert a != b


# --------------------------------------------------------------------------- #
# Thiếu clip_id: phải nói thẳng
# --------------------------------------------------------------------------- #


def test_missing_clip_id_warns_instead_of_silence(agent, skill):
    text = _instruction(agent, skill, clip_id=None)
    assert "THIẾU `clip_id`" in text


def test_missing_clip_id_lists_available_clips(agent, skill):
    """Không chỉ báo lỗi — phải nói tên clip để người/agent chọn được."""
    text = _instruction(agent, skill, clip_id=None)
    assert "`clip1` (hook, 8.0s)" in text
    assert "`clip2` (showcase, 8.0s)" in text


def test_missing_clip_id_does_not_fabricate_beats(agent, skill):
    text = _instruction(agent, skill, clip_id=None)
    assert "Nhịp 8.0s của clip này" not in text


def test_missing_clip_id_still_gets_script_header(agent, skill):
    """Warn nhưng không được rỗng: slug/title/canvas vẫn hữu ích."""
    text = _instruction(agent, skill, clip_id=None)
    assert "havana_donna_set" in text


# --------------------------------------------------------------------------- #
# Không đụng node ảnh
# --------------------------------------------------------------------------- #


def test_image_node_does_not_get_video_beat_context(agent, skill):
    """Node ảnh không được nhận context clip/beat.

    Lưu ý: chữ `clips[].beats` có sẵn trong skill markdown (§5 dạy cấu trúc), nên phải kiểm phần
    context ĐỘNG do `_script_context_lines` sinh ra, không kiểm cả chuỗi instruction.
    """
    text = _instruction(agent, skill, node_type="image", clip_id=None, plate_mode=True)
    assert "THIẾU `clip_id`" not in text
    assert "Nhịp 8.0s của clip này" not in text
    assert "vai **hook**" not in text
    assert "GIỮ MẮT với ống kính" not in text
