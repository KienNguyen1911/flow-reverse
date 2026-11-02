"""Contract cho kiến trúc prompt V2 của `try-on-image-prompter`.

V2 không thêm tính năng mới — nó **bỏ xung đột**. Ba lỗi đã làm V1 không ổn định dù rất dài:

1. Vừa đòi "giữ đúng tỷ lệ Ảnh 1" vừa áp `seven-and-a-half head-to-body ratio`.
2. Vừa đòi "đọc ra cao" vừa cấm `tall and slim` trong Negative.
3. Vừa đòi chép đúng trang phục vừa cấm tuyệt đối `logo`.

Mỗi test dưới đây khoá đúng một xung đột đã sửa, để lần sau không ai "bổ sung cho chắc" rồi tái tạo
lại chúng. Chạy: `python -m pytest tests/test_tryon_prompt_v2.py`
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.Workflows.prompt_lint import lint_image_prompt

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "prompt-skills" / "try-on-image-prompter.md"

#: Ngân sách mềm cho một prompt try-on. V1 (mẫu người dùng dán) dài ~7.000 ký tự sau khi điền tên
#: món đồ; V2 phải ngắn hơn mà không mất mốc định lượng. 6.000 là trần của template chưa điền.
TEMPLATE_MAX_CHARS = 6000


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _blocks() -> list[str]:
    return re.findall(r"```text\n(.*?)\n```", _text(), re.DOTALL)


def _template() -> str:
    return next(b for b in _blocks() if b.strip().startswith("Try-on photograph"))


def _negative(template: str | None = None) -> str:
    tpl = template if template is not None else _template()
    return tpl.split("Negative:")[-1]


# --------------------------------------------------------------------------- #
# 1. Kiến trúc 7 module, đúng thứ tự ưu tiên
# --------------------------------------------------------------------------- #

def test_template_has_seven_modules_in_priority_order():
    tpl = _template()
    order = [
        "[IDENTITY LOCK]",
        "[GARMENT FIDELITY]",
        "[ANATOMY & POSE]",
        "[HEIGHT & PROPORTION OPTIMIZATION]",
        "[ENVIRONMENT & LIGHTING]",
        "[PHOTOGRAPHY AESTHETICS]",
        "Negative:",
    ]
    positions = []
    for marker in order:
        assert marker in tpl, f"template thiếu module {marker}"
        positions.append(tpl.index(marker))
    assert positions == sorted(positions), "module bị đảo thứ tự — thứ tự là thứ tự ưu tiên"


def test_skill_states_conflict_priority():
    """Khi hai mục tiêu đá nhau, thứ tự phải được viết ra; nếu không agent tự chọn mỗi lần một kiểu."""
    text = _text()
    assert "Identity consistency" in text
    assert "Garment consistency" in text
    assert "Presentation consistency" in text
    # Thứ tự: identity trước garment trước anatomy trước presentation
    assert (
        text.index("Identity consistency")
        < text.index("Garment consistency")
        < text.index("Anatomy consistency")
        < text.index("Presentation consistency")
    )


# --------------------------------------------------------------------------- #
# 2. Không áp tỷ lệ đầu-thân cố định (Critical #1)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "phrase",
    ["seven-and-a-half head-to-body ratio", "7.5 head", "slim build", "small head", "long neck"],
)
def test_template_does_not_impose_a_body(phrase: str):
    """Đây là các cụm mô tả *một người khác*, không phải người trong Ảnh 1.

    V1 dùng chúng để "chắc chắn cao"; hệ quả là model phải chọn giữa giữ tỷ lệ thật và đạt tỷ lệ
    vàng — chọn cái nào cũng sai.
    """
    assert phrase not in _template().lower(), f"template còn áp đặt '{phrase}'"


def test_template_uses_image_1_as_the_only_proportion_reference():
    tpl = _template().lower()
    assert "head-to-body ratio" in tpl
    assert "visible in image 1" in tpl
    assert "that body is the only proportion reference" in tpl


def test_pose_library_anchor_is_documented_as_an_exception():
    """Thư viện pose *được phép* neo 168 cm + 7.5 đầu vì đó là nhân vật tự định nghĩa.

    Nếu skill không nói rõ ngoại lệ này, lần sau ai đó sẽ "đồng bộ" hai bên và phá một trong hai.
    """
    text = _text()
    section = text.split("V2 đã bỏ gì khỏi khối Height")[-1][:900]
    assert "poses_reference.md" in section
    assert "nhân vật do mình định nghĩa" in section


# --------------------------------------------------------------------------- #
# 3. Positive và Negative không được đá nhau (Critical #3)
# --------------------------------------------------------------------------- #

VERBOTEN_IN_TEMPLATE = (
    "tall and slim",
    "no tall",
    "no logo,",
    "no logo.",
    "zero floor space",
    "ankle-cutting boots",
)


@pytest.mark.parametrize("phrase", VERBOTEN_IN_TEMPLATE)
def test_template_drops_self_cancelling_negatives(phrase: str):
    assert phrase not in _template().lower(), f"template còn cụm tự phủ định chính nó: '{phrase}'"


def test_logo_rule_is_conditional_not_absolute():
    """Cấm logo *bịa thêm*, giữ logo có thật trên trang phục tham chiếu."""
    tpl = _template().lower()
    assert "added logos" in tpl
    assert "branding beyond what the reference garment actually carries" in tpl
    assert "branding that are physically part of the garment are reproduced" in tpl


def test_negative_does_not_repeat_positive_instructions():
    """Negative chỉ để chặn lỗi. Một ý đã nằm ở module 1–6 thì không lặp lại ở đây."""
    neg = _negative().lower()
    tpl = _template().lower()
    for repeated in ("no tall and slim", "no slimmer waist", "no wide-legged stance"):
        assert repeated not in neg
        # ... và nếu skill có nhắc tới chúng, chỉ được nhắc trong phần giải thích, không trong prompt
        assert repeated not in tpl


def test_negative_is_grouped_into_five_families():
    text = _text()
    section = text.split("Negative — 5 nhóm")[-1][:2500]
    for group in ("1. Identity", "2. Garment", "3. Anatomy", "4. Framing", "5. Graphics"):
        assert group in section, f"thiếu nhóm Negative {group}"


# --------------------------------------------------------------------------- #
# 4. Hướng đầu tách khỏi hướng thân (High)
# --------------------------------------------------------------------------- #

def test_head_direction_is_controlled_separately_from_torso():
    """Thân ba phần tư + mặt quay đi quá xa = mất identity. Phải nói rõ hướng đầu."""
    tpl = _template().lower()
    assert "head turned gently back toward the camera" in tpl
    assert "while the torso keeps its angle" in tpl

    # Cả hai mode thủ công cũng phải có câu hướng đầu, không chỉ template.
    pose_section = _text().split("--- Mode A (default) ---")[-1].split("CẤM**")[0].lower()
    assert pose_section.count("head") >= 2, "Mode A/B thiếu câu hướng đầu"


def test_shared_stance_clause_is_declared_once():
    """V1 lặp danh sách cấm chân ở 4 chỗ. V2 gom về một câu positive dùng chung."""
    text = _text()
    assert "Natural stance: the two legs clearly separated" in text


# --------------------------------------------------------------------------- #
# 5. Ảnh 3 là tuỳ chọn (Critical #2)
# --------------------------------------------------------------------------- #

def test_image_3_is_handled_as_optional():
    tpl = _template()
    assert "If Image 3 is provided" in tpl
    assert "If Image 3 is not provided" in tpl
    # Ảnh 3 chỉ được nói môi trường, không được nói người/trang phục
    env = tpl.split("[ENVIRONMENT & LIGHTING]")[-1].split("[PHOTOGRAPHY")[0]
    assert "never the person or the garment from Image 3" in env


def test_environment_falls_back_to_studio_not_image_2():
    """V1 lấy bối cảnh Ảnh 2 khi thiếu Ảnh 3 — ảnh Shopee ngoài đường sẽ lọt vào plate."""
    tpl = _template().lower()
    assert "curved white cyclorama" in tpl
    assert "if image 3 is absent" not in tpl


def test_two_image_node_instruction_matches_the_skill():
    """Agent instruction và skill phải cùng một quy tắc, nếu không agent được dặn ngược lại."""
    from src.Workflows.prompt_agent import NodePromptTask, PromptAgent

    agent = PromptAgent.__new__(PromptAgent)  # chỉ cần phần format
    lines = agent._image_role_lines(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[]), 2
    )
    joined = " ".join(lines).lower()
    assert "studio" in joined
    assert "không kế thừa" in joined


# --------------------------------------------------------------------------- #
# 6. Tiêu cự không được bán như bộ bảo đảm phối cảnh (Medium)
# --------------------------------------------------------------------------- #

def test_focal_length_is_not_sold_as_perspective_compression():
    tpl = _template().lower()
    assert "focal length alone does not compress" in tpl
    assert "same subject-to-camera distance" in tpl


# --------------------------------------------------------------------------- #
# 7. Ngân sách ký tự
# --------------------------------------------------------------------------- #

def test_template_fits_soft_budget():
    tpl = _template()
    assert len(tpl) <= TEMPLATE_MAX_CHARS, f"template dài {len(tpl)} ký tự — vượt ngân sách {TEMPLATE_MAX_CHARS}"


def test_template_passes_image_lint():
    result = lint_image_prompt(_template())
    assert result.ok, [w.to_dict() for w in result.warnings]
    assert not [w for w in result.warnings if w.code == "anatomy_rewrite"]


def test_plate_mode_does_not_swap_the_shoes():
    """V1 cho phép thay giày bằng kitten heels trong chế độ plate — trái Garment Fidelity."""
    text = _text()
    section = text.split("**2.5.4")[-1][:1200]
    assert "elongating footwear" not in section.lower(), "còn câu positive đổi giày"
    assert "không bao giờ đổi sản phẩm" in section.lower()
