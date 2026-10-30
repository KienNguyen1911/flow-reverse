"""Kiểm tra 3 skill mới: prompt sinh ra có sống sót qua sanitize + parse không.

Chạy:  python tests/test_prompt_skills_contract.py
"""
from __future__ import annotations

import re
from pathlib import Path

from src.Bridge.flow_video_bridge import sanitize_video_prompt
from src.Bridge.gemini_bridge import parse_gemini_video_prompts
from src.Workflows.skill_manager import get_skill_manager

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "prompt-skills"

# Cụm mà bộ lọc aggressive sẽ viết lại (xem prompt-skills/lookbook-video-prompter.md mục 0)
FORBIDDEN_VIDEO_PHRASES = [
    "glances over her shoulder",
    "looks at the camera",
    "looking directly at the camera",
    "facing the camera",
    "the woman",
    "the girl",
    "the lady",
    "slow-motion",
    "slow motion",
]

# Header mốc thời gian bị regex cắt hoặc để lại rác
FORBIDDEN_VIDEO_HEADERS = [
    "Camera & Realism:",
    "- 0s to 3s",
    "- 2s to 6s",
    "[0-3s]",
]


def test_skills_load_and_have_policy():
    mgr = get_skill_manager()
    mgr.reload()
    ids = {s.id for s in mgr.list_skills()}
    assert {"lookbook-image-prompter", "lookbook-video-prompter", "try-on-image-prompter"} <= ids
    for sid in ("lookbook-image-prompter", "lookbook-video-prompter", "try-on-image-prompter"):
        skill = mgr.get_skill(sid)
        assert skill is not None
        assert "fictional" in skill.policy_clause.lower(), sid


def test_image_skill_has_nabi_split_screen_template():
    """Template prompt của skill ảnh lookbook phải có cột NABI và model toàn thân."""
    text = (SKILLS / "lookbook-image-prompter.md").read_text(encoding="utf-8")
    assert "nabi" in text.lower()
    assert "head-to-toe" in text.lower() or "head to toe" in text.lower()
    assert "[policy compliance]" in text.lower()


def test_video_skill_templates_survive_sanitizer():
    """Hai prompt mẫu trong skill phải đi qua sanitize ở cả 2 chế độ mà không bị xoá nội dung."""
    text = (SKILLS / "lookbook-video-prompter.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```text\n(.*?)\n```", text, re.DOTALL)
    prompts = [b.strip() for b in blocks if b.strip().startswith(("Camera", "Continuing"))]
    assert len(prompts) == 2, f"expected 2 clip prompts, got {len(prompts)}"

    for p in prompts:
        for mode in (False, True):
            out = sanitize_video_prompt(p, aggressive=mode)
            assert out.strip(), f"prompt bị xoá sạch (aggressive={mode})"
            # Không mất quá 15% nội dung
            assert len(out) > len(p) * 0.85, f"mất nội dung (aggressive={mode}): {out!r}"
            # Chuyển động cốt lõi phải còn
            assert "camera" in out.lower()
        # Không vượt ngân sách 80 từ
        assert len(p.split()) <= 80, len(p.split())


def test_video_skill_avoids_filtered_phrases():
    """Skill phải dạy tránh đúng những cụm bị bộ lọc viết lại — kiểm tra ở phần template,
    không kiểm tra ở phần bảng cảnh báo (bảng có nhắc tới chúng để dặn tránh)."""
    text = (SKILLS / "lookbook-video-prompter.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```text\n(.*?)\n```", text, re.DOTALL)
    templates = [b for b in blocks if b.strip().startswith(("Camera", "Continuing"))]
    assert templates
    for tpl in templates:
        for bad in FORBIDDEN_VIDEO_PHRASES:
            assert bad not in tpl.lower(), f"template chứa cụm bị lọc: {bad}"
        for hdr in FORBIDDEN_VIDEO_HEADERS:
            assert hdr not in tpl, f"template chứa header bị cắt: {hdr}"


def test_gemini_parser_reads_skill_output_shape():
    """Output của skill là 2 code block riêng biệt — parser Pattern C phải đọc ra đúng 2 prompt.

    Ghi chú: header dạng `[Video Prompt 2]` (có ngoặc vuông) làm parser Pattern A để lại
    rác `[` ở cuối prompt 1, nên skill cố ý KHÔNG dùng header đó.
    """
    p1 = (
        "Camera pushes in slowly at natural real-time speed. The model holds steady eye contact "
        "with the lens for three seconds, then turns a full 360 degrees in place."
    )
    p2 = (
        "Continuing from that pose, the model angles forty-five degrees and returns to the lens. "
        "Camera drifts closer on the same axis as the model settles into the opening stance."
    )
    raw = f"```text\n{p1}\n```\n\n```text\n{p2}\n```\n"
    a, b = parse_gemini_video_prompts(raw)
    assert a.strip() == p1
    assert b.strip() == p2
    # Không được sót ký tự rác từ header
    assert "[" not in a and "[" not in b


def test_tryon_skill_documents_aggressive_rewrites():
    text = (SKILLS / "try-on-image-prompter.md").read_text(encoding="utf-8")
    for phrase in ("glances over her shoulder", "looks at the camera", "the fashion subject"):
        assert phrase.lower() in text.lower(), phrase
    assert "sanitize_video_prompt" in text
