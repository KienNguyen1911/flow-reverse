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
#: món đồ; V2 xuống 5.237; V3 cắt phần diễn giải trong khối Height và đổi khối Negative dài thành
#: `Constraints:` khẳng định ⇒ 3.391. 3.600 là trần của template chưa điền, chừa ~200 ký tự headroom
#: cho tên món đồ mà test `test_template_fits_soft_budget` vẫn bắt được nếu ai đó nhét lại phần đã cắt.
TEMPLATE_MAX_CHARS = 3600

#: Cụm mô tả một khuôn mặt cụ thể — không được nằm trong template vì template dùng cho mọi người mẫu
#: và Ảnh 1 đã là nguồn duy nhất. Xem §2.2.3 "Identity Lock không mô tả khuôn mặt".
FACE_CATALOGUE = ("east asian", "high bun", "wispy", "honey-brown", "freckles", "chestnut")


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
        "Constraints:",
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


def test_template_uses_model_image_as_the_only_proportion_reference():
    tpl = _template().lower()
    assert "head-to-body ratio" in tpl
    assert "visible in <<model>>" in tpl
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
    """Cấm nhãn *bịa thêm*, giữ nhãn/mác có thật trên trang phục tham chiếu.

    Ý định giữ nguyên, nhưng không dùng họ từ `brand` nữa: Flow từ chối cả request bằng
    `PUBLIC_ERROR_UNSAFE_GENERATION` khi prompt chứa từ đó (đo trên server thật, xem
    `IMAGE_FILTER_TRIGGER_TERMS` trong `src/Workflows/prompt_lint.py`).
    """
    tpl = _template().lower()
    assert "added logos" in tpl
    assert "no added marks beyond what the reference garment actually carries" in tpl
    assert "any label that is physically part of the garment are reproduced" in tpl
    assert "brand" not in tpl, "template còn họ từ 'brand' ⇒ Flow chặn cả request"


def test_negative_does_not_repeat_positive_instructions():
    """Khối chặn lỗi chỉ để chặn lỗi. Một ý đã nằm ở module 1–6 thì không lặp lại ở đây."""
    neg = _negative().lower()
    tpl = _template().lower()
    for repeated in ("no tall and slim", "no slimmer waist", "no wide-legged stance"):
        assert repeated not in neg
        # ... và nếu skill có nhắc tới chúng, chỉ được nhắc trong phần giải thích, không trong prompt
        assert repeated not in tpl


def test_negative_is_grouped_into_five_families():
    text = _text()
    section = text.split("Constraints — 5 nhóm")[-1][:2500]
    for group in ("1. Identity", "2. Garment", "3. Anatomy", "4. Framing", "5. Graphics"):
        assert group in section, f"thiếu nhóm Constraints {group}"


def test_constraints_report_names_the_five_groups():
    """Phiên bản cũ của test này khớp tên mục; đổi tên mục là nó lặng lẽ pass sai lý do."""
    tpl = _template().lower()
    tail = tpl.split("constraints:")[-1]
    # Mỗi nhóm phải có ít nhất một cụm đại diện trong câu Constraints thật của template.
    for needle in (
        "altered facial identity",
        "garment redesign",
        "overlapping thighs",
        "cropped head or feet",
        "no ui",
    ):
        assert needle in tail, f"Constraints thiếu '{needle}'"


def test_template_has_no_negative_clause():
    """Flow không có trường negative: prompt ảnh là một chuỗi duy nhất trong args `ogiZ0b`
    (`docs/api_specs/flow_create_image.md` §3.1). Khối `Negative:` chỉ là văn xuôi thường gửi
    tới Gemini image, và các cụm danh từ trong đó có thể làm tăng khả năng chúng xuất hiện.
    V3 thay bằng `Constraints:` khẳng định — đừng quay lại.
    """
    tpl = _template()
    assert "Negative:" not in tpl, "template còn khối Negative: — Flow không có kênh negative"
    assert "Constraints:" in tpl
    # Và không được dán lại danh sách cấm dạng thô của §2.3
    assert "text, letters, words, numbers, typography" not in tpl


def test_identity_lock_does_not_catalogue_a_face():
    """Template dùng cho mọi người mẫu; mô tả mặt cụ thể tạo nguồn tham chiếu thứ hai
    đối kháng với pixel của ảnh người mẫu (xem §2.2.3)."""
    tpl = _template().lower()
    for phrase in FACE_CATALOGUE:
        assert phrase not in tpl, f"Identity Lock còn mô tả khuôn mặt cụ thể: '{phrase}'"
    assert "<<model>> is the sole identity reference" in tpl
    assert "do not beautify" in tpl


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

def test_background_is_handled_as_optional():
    tpl = _template()
    assert "If <<background>> is provided" in tpl
    assert "If <<background>> is not provided" in tpl
    # Bối cảnh chỉ được nói môi trường, không được nói người/trang phục
    env = tpl.split("[ENVIRONMENT & LIGHTING]")[-1].split("[PHOTOGRAPHY")[0]
    assert "never the person or the garment from <<background>>" in env


def test_environment_falls_back_to_studio_not_garment_image():
    """V1 lấy bối cảnh ảnh trang phục khi thiếu ảnh background — ảnh Shopee ngoài đường sẽ lọt vào plate."""
    tpl = _template().lower()
    assert "curved white cyclorama" in tpl
    assert "if image 3 is absent" not in tpl


def test_two_image_node_instruction_matches_the_skill():
    """Agent instruction và skill phải cùng một quy tắc, nếu không agent được dặn ngược lại."""
    from src.Workflows.prompt_agent import NodePromptTask, PromptAgent

    agent = PromptAgent.__new__(PromptAgent)  # chỉ cần phần format
    lines = agent._image_role_lines(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[]),
        ["out/uploads/model.jpg", "out/uploads/garment.jpg"],
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
    # Template phải nằm dưới trần ký tự, nếu không thì chính skill tự dạy agent viết prompt quá dài.
    assert not [w for w in result.warnings if w.code == "image_prompt_too_long"]
    # Họ từ `brand` làm Flow chặn cả request — xem `test_linter_flags_unsafe_generation_words`.
    assert not [w for w in result.warnings if w.code == "filter_trigger"]


#: Đo trên server thật 2026‑11‑12 (profile `aaaaa`): chỉ những prompt này bị REJECT.
_FILTER_TRIGGERS = ("Avoid: no brand logo.", "Avoid: no brand.")
#: Cùng vị trí, cùng ảnh tham chiếu, nhưng đã qua 200 OK.
_FILTER_CLEAN = ("Avoid: no logo.", "Avoid: no watermark.", "Avoid: no added marks.")


@pytest.mark.parametrize("phrase", _FILTER_TRIGGERS)
def test_linter_flags_unsafe_generation_words(phrase: str):
    """Từ `brand` bị Flow đọc thành vi phạm, kể cả khi đứng sau `no`.

    Đây là lỗi thật đã đốt ba lần chạy: nhãn `PUBLIC_ERROR_UNSAFE_GENERATION` khiến mọi
    người đi tìm ảnh tham chiếu và mô tả cơ thể, trong khi thủ phạm là một từ trong danh
    sách phủ định. Linter phải bắt trước khi tiêu credit.
    """
    result = lint_image_prompt(_template() + "\n" + phrase)
    assert not result.ok
    assert [w for w in result.warnings if w.code == "filter_trigger"]


@pytest.mark.parametrize("phrase", _FILTER_CLEAN)
def test_linter_does_not_flag_clean_negative_phrases(phrase: str):
    """Luật phải hẹp: `no logo` / `no watermark` đã qua 200 OK, cấm báo nhầm."""
    result = lint_image_prompt(_template() + "\n" + phrase)
    assert not [w for w in result.warnings if w.code == "filter_trigger"]


# --------------------------------------------------------------------------- #
# 8. Neo độ dài khi ảnh trang phục là coordinate sheet (§2.1.1)
# --------------------------------------------------------------------------- #

#: Tên file thật của sheet đã gây lỗi 2026‑11‑12.
_SHEET_FILE = "out/uploads/1794478054426_editorial_fashion_coordinate_sheet_verti.jpg"
_PERSON_FILE = "out/uploads/1794458265956_ao_xanhqxanh_nhat.jpg"


def test_sheet_is_detected_from_filename_but_person_photo_is_not():
    """Nhận diện bằng tên file: tín hiệu chắc chắn duy nhất mà không cần đọc pixel.

    Prompt thật không hề viết "flat-lay", nên một luật dò chữ trong prompt sẽ không bao giờ
    cháy — tức là guard giả. Tên file thì pipeline tự đặt theo loại ảnh.
    """
    from src.Workflows.prompt_lint import SHEET_FILENAME_RE

    assert SHEET_FILENAME_RE.search(_SHEET_FILE)
    assert not SHEET_FILENAME_RE.search(_PERSON_FILE)


def test_agent_demands_length_anchor_only_for_sheet_garment():
    """Sheet ⇒ bắt buộc có câu neo; người mặc thật ⇒ không được thêm.

    Thêm câu neo vào ảnh người mặc thật là tạo mâu thuẫn với pixel: tỷ lệ đã đúng sẵn.
    """
    from src.Workflows.prompt_agent import PromptAgent

    for_sheet = "\n".join(PromptAgent._sheet_garment_lines([_SHEET_FILE], garment_slot="<<garment>>"))
    assert for_sheet, "sheet phải sinh chỉ dẫn neo độ dài"
    assert "mid-thigh" in for_sheet
    assert "Length is anchored" in for_sheet
    assert "<<garment>>" in for_sheet

    assert PromptAgent._sheet_garment_lines([_PERSON_FILE], garment_slot="<<garment>>") == []
    assert PromptAgent._sheet_garment_lines([], garment_slot="<<garment>>") == []


def test_skill_documents_the_length_anchor_and_the_measurement():
    """Số đo phải nằm trong skill, nếu không sáu tháng nữa không ai biết vì sao có luật này."""
    text = _text()
    assert "2.1.1" in text
    section = text.split("#### 2.1.1")[1][:3000]
    assert "0.755" in section, "thiếu số đo shorts/áo trên sheet"
    assert "mid-thigh" in section
    assert "Length is anchored" in section


def test_plate_mode_does_not_swap_the_shoes():
    """V1 cho phép thay giày bằng kitten heels trong chế độ plate — trái Garment Fidelity."""
    text = _text()
    section = text.split("**2.5.4")[-1][:1200]
    assert "elongating footwear" not in section.lower(), "còn câu positive đổi giày"
    assert "không bao giờ đổi sản phẩm" in section.lower()


def test_linter_flags_prompt_that_grows_back_to_v1_size():
    """Guardrail: prompt phình lại cỡ V1 (~7.000 ký tự) phải bị cảnh báo, nếu không sáu tháng nữa
    không ai phát hiện. Đây là warn chứ không phải error — outfit nhiều món thật sự cần dài hơn."""
    from src.Workflows.prompt_lint import IMAGE_PROMPT_MAX_CHARS

    tpl = _template()
    assert len(tpl) < IMAGE_PROMPT_MAX_CHARS

    bloated = tpl + "\nAdditional styling notes: " + ("extra redundant instruction. " * 400)
    codes = {w.code for w in lint_image_prompt(bloated).warnings}
    assert "image_prompt_too_long" in codes
    # ... và vẫn là warn, không chặn
    assert lint_image_prompt(bloated).ok

