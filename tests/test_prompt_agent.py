"""Tests for Local Agent Runner, Skill Manager, and Prompt Agent API endpoints."""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.WebUI.app import create_app
from src.Workflows.skill_manager import get_skill_manager
from src.Workflows.local_agent_runner import (
    LocalAgentConfig,
    extract_clean_prompt_from_agent_output,
    find_agent_binary,
)


@pytest.fixture(scope="module")
def client(tmp_path_factory) -> TestClient:
    base = tmp_path_factory.mktemp("agent_api")
    app = create_app(
        out_dir=base / "playground",
        pool_config=base / "pool.json",
        pool_state=base / "pool_state.json",
        web_dist=base / "dist",
    )
    return TestClient(app)


def test_skill_manager_loads_skills():
    mgr = get_skill_manager()
    mgr.reload()
    skills = mgr.list_skills()
    assert len(skills) >= 2
    ids = [s.id for s in skills]
    assert "try-on-image-prompter" in ids
    assert "lookbook-item-cutout-prompter" in ids

    tryon = mgr.get_skill("try-on-image-prompter")
    assert tryon is not None


def test_extract_clean_prompt_codeblock():
    raw = """
Here is your prompt:
```markdown
A young woman in a beige knit cardigan, soft lighting, 8k.
```
Hope this helps!
"""
    cleaned = extract_clean_prompt_from_agent_output(raw)
    assert "beige knit cardigan" in cleaned
    assert "Hope this helps" not in cleaned


def test_find_agent_binaries():
    # agy should be found on this machine
    agy_path = find_agent_binary("agy")
    assert agy_path is not None
    assert Path(agy_path).exists()


def test_api_agent_skills(client: TestClient):
    r = client.get("/api/agent/skills")
    assert r.status_code == 200
    data = r.json()
    assert "skills" in data
    assert len(data["skills"]) >= 2


def test_api_agent_config(client: TestClient):
    r = client.get("/api/agent/config")
    assert r.status_code == 200
    cfg = r.json()
    assert "preferred_agent" in cfg
    assert "agy_model" in cfg

    # Update config
    r2 = client.post("/api/agent/config", json={"preferred_agent": "agy", "agy_model": "gemini-3.8-flash-low"})
    assert r2.status_code == 200
    assert r2.json()["config"]["agy_model"] == "gemini-3.8-flash-low"


# -- coordinate sheet: skill ảnh sản phẩm chỉ có một đường ra ------------------ #


def _agent_with_skills():
    from src.Workflows.prompt_agent import PromptAgent

    agent = PromptAgent.__new__(PromptAgent)  # không cần runner cho phần format
    agent.skill_mgr = get_skill_manager()
    return agent


def test_item_node_always_asks_for_coordinate_sheet():
    """Không có phạm vi để chọn: node ảnh sản phẩm luôn ra coordinate sheet.

    Trước đây agent phải được chỉ định `item_scope`, vì skill còn 4 đường ra (áo / quần /
    cả bộ / bộ phối). Skill giờ chỉ còn sheet, nên mọi node ảnh sản phẩm nhận cùng một
    instruction — không còn giá trị nào để truyền sai.
    """
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    skill = agent.skill_mgr.get_skill("lookbook-item-cutout-prompter")
    assert skill is not None

    out = agent.format_agent_instruction(
        NodePromptTask(
            node_id="n",
            node_type="image",
            upstream_media_urls=[],
            is_item=True,
            item_name="Set Donna",
        ),
        skill,
        [],
    )
    assert "COORDINATE SHEET" in out
    assert "Bộ phối cần dựng" in out
    # Không còn khối "Phạm vi cần tách" của 4 chế độ cũ.
    assert "Phạm vi cần tách" not in out


def test_sheet_instruction_keeps_typography_and_drops_plate_negatives():
    """Sheet là ngoại lệ có chủ đích của quy tắc "một món": có chữ, nhiều món, không rembg.

    Hai lỗi phá sheet ngay: (1) bê negative của ảnh plate (`no text`, `no collage`,
    `no grid`, `no multiple items`) — xoá đúng thứ sheet cần; (2) quên palette 5 ô. Túi và
    giày là món BẮT BUỘC nên không được nằm trong danh sách loại trừ.
    """
    from src.Workflows.prompt_agent import COORDINATE_SHEET_EXCLUDE, COORDINATE_SHEET_RULE

    assert "3.1" in COORDINATE_SHEET_RULE
    assert "bag" not in COORDINATE_SHEET_EXCLUDE.lower()
    assert "shoes" not in COORDINATE_SHEET_EXCLUDE.lower()
    assert "color palette" in COORDINATE_SHEET_RULE.lower()


def test_item_sheet_never_applies_to_video():
    """Sheet chỉ có nghĩa với node ẢNH sản phẩm; video không bao giờ là sheet."""
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    assert not agent.is_item_task(
        NodePromptTask(node_id="n", node_type="video", upstream_media_urls=[],
                       is_item=True)
    )
    assert not agent.is_item_task(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                       is_item=False)
    )
    assert agent.is_item_task(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                       is_item=True)
    )
    # Kiểu cũ: gắn cứng `item_id` của script vẫn phải ra sheet.
    assert agent.is_item_task(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                       item_id="item_1")
    )


def test_coordinate_sheet_instruction_forbids_typeless_flat_lay():
    """Sheet mà agent lại dùng một flat-lay không chữ thì ra ảnh sai hẳn mục tiêu.

    Instruction phải chỉ §3.1, bắt buộc typography, và dặn BỎ các cụm negative của ảnh
    plate (`no text`, `no collage`…) — chúng xoá đúng thứ sheet cần."""
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    skill = agent.skill_mgr.get_skill("lookbook-item-cutout-prompter")
    out = agent.format_agent_instruction(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                       is_item=True, item_name="Set Y2K"),
        skill, [],
    )
    assert "COORDINATE SHEET" in out
    assert "§3.1" in out
    assert "Negative phải BỎ" in out
    assert "no text" in out and "no collage" in out
    assert "3 ô `DETAIL`" in out
    assert "COLOR PALETTE" in out
    assert "first frame" in out


def test_coordinate_sheet_instruction_embeds_31_skeleton_at_the_end():
    """Nhắc §3.1 ở giữa instruction là chưa đủ — agent vẫn trả về flat-lay không chữ.

    Khối `ĐỊNH DẠNG ĐẦU RA` (thứ agent đọc cuối) phải nêu đúng câu mở đầu của §3.1 và
    đủ 6 tên khối, để agent không còn đường lùi về ảnh không typography.
    """
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    skill = agent.skill_mgr.get_skill("lookbook-item-cutout-prompter")
    out = agent.format_agent_instruction(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                       is_item=True, item_name="Set Y2K"),
        skill, [],
    )
    _, _, tail = out.partition("--- ĐỊNH DẠNG ĐẦU RA ---")
    assert tail, "khối định dạng đầu ra bị mất"
    for marker in ("LAYOUT", "OUTFIT", "FIDELITY LOCKS", "DO NOT ADD",
                   "TYPE & LIGHT", "COLOR PALETTE", "Negative"):
        assert marker in tail, marker
    # Câu mở đầu lấy từ chính §3.1 của skill, không phải bản chép tay.
    assert "Editorial fashion coordinate sheet" in tail
    assert "ghost-mannequin" in tail
    assert "flat-lay không chữ" in tail
    # Khung đầy đủ 3.5K không được dán lại: một lượt gọi thật đã vượt trần 75s.
    assert len(tail) < 2500


def test_coordinate_sheet_sections_flag_typeless_flat_lay():
    """Prompt flat-lay không chữ ⇒ phải bị nhận là thiếu khối."""
    from src.Workflows.prompt_agent import coordinate_sheet_sections_missing

    plate = (
        "Flat-lay product arrangement of a complete coordinated set: a white keyhole "
        "shirt, and grey-blue wide-leg jeans.\n\n"
        "Negative: no person, no model, no text, no collage, no grid, no multiple items."
    )
    missing = coordinate_sheet_sections_missing(plate)
    assert "LAYOUT" in missing
    assert "COLOR PALETTE" in missing
    assert "FIDELITY LOCKS" in missing

    sheet = (
        "LAYOUT\n- Top left: title\nOUTFIT\nOverall: ...\n"
        "FIDELITY LOCKS: keep the keyhole open.\nDO NOT ADD: belt.\n"
        "TYPE & LIGHT\nTwo typefaces.\nCOLOR PALETTE\nNegative: no person."
    )
    assert coordinate_sheet_sections_missing(sheet) == []


class _StubRunner:
    """Runner giả: trả lần lượt các output đã chuẩn bị và ghi lại instruction."""

    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)
        self.instructions: list[str] = []
        self.config = LocalAgentConfig(preferred_agent="agy", timeout_s=75)

    async def run_prompt_instruction(self, instruction, agent=None, model=None, timeout_s=None):
        self.instructions.append(instruction)
        return self.outputs.pop(0)


_SHEET_PROMPT = (
    "LAYOUT\n- Top left: title\nOUTFIT\nOverall: ...\n"
    "FIDELITY LOCKS: keep the keyhole open.\nDO NOT ADD: belt.\n"
    "TYPE & LIGHT\nTwo typefaces.\nCOLOR PALETTE\nNegative: no person."
)
_TYPELESS_PROMPT = (
    "Flat-lay product arrangement of a complete coordinated set: shirt and jeans.\n\n"
    "Negative: no person, no text, no collage, no grid."
)


def test_coordinate_sheet_retries_once_when_agent_returns_typeless_flat_lay():
    """Agent trả flat-lay không chữ ⇒ chạy lại một lần với cảnh báo, không trả prompt sai cho UI."""
    import asyncio

    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    agent.runner = _StubRunner([_TYPELESS_PROMPT, _SHEET_PROMPT])
    res = asyncio.run(agent.generate_prompt_for_node(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                       is_item=True, item_name="Set Y2K")
    ))
    assert res.prompt == _SHEET_PROMPT
    assert len(agent.runner.instructions) == 2
    retry = agent.runner.instructions[1]
    assert "CẢNH BÁO" in retry
    assert retry.index("CẢNH BÁO") < retry.index("--- ĐỊNH DẠNG ĐẦU RA ---")


def test_plain_image_node_never_retries():
    """Node ảnh không phải bảng phối không được sinh thêm lần gọi: retry là của sheet."""
    import asyncio

    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    agent.runner = _StubRunner([_TYPELESS_PROMPT])
    res = asyncio.run(agent.generate_prompt_for_node(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[])
    ))
    assert res.prompt == _TYPELESS_PROMPT
    assert len(agent.runner.instructions) == 1


def test_sheet_instruction_never_goes_inline():
    """`agy` treo vô hạn khi nhận instruction sheet ~21K qua `-p` (>200s, không stdout).

    Cùng nội dung ghi ra `out/_agent_tasks/*.md` thì trả lời trong ~24s. Ngưỡng inline
    phải thấp hơn mọi instruction thật, nếu không nút AI Prompt treo tới hết timeout và
    người dùng chỉ thấy prompt cũ.
    """
    from src.Workflows.local_agent_runner import MAX_INLINE_INSTRUCTION, _build_print_arg
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    skill = agent.skill_mgr.get_skill("lookbook-item-cutout-prompter")
    ins = agent.format_agent_instruction(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                       is_item=True, item_name="Set Y2K"),
        skill, [],
    )
    assert len(ins) > MAX_INLINE_INSTRUCTION, (
        f"instruction {len(ins)} ký tự vẫn lọt ngưỡng inline {MAX_INLINE_INSTRUCTION}"
    )
    arg = _build_print_arg(ins, "agy")
    assert len(arg) < 1000, f"arg vẫn quá dài: {len(arg)}"
    assert "out/_agent_tasks/" in arg


def test_item_node_not_reminded_it_is_a_plate():
    """Node ảnh sản phẩm KHÔNG phải plate — nhắc 'người mẫu toàn thân' sẽ kéo model vẽ người."""
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    skill = agent.skill_mgr.get_skill("lookbook-item-cutout-prompter")
    out = agent.format_agent_instruction(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                       is_item=True, item_name="Set Donna"),
        skill, [],
    )
    assert "plate nền" not in out


def test_item_node_image_roles_are_sheet_roles():
    """Hai ảnh Shopee cho một bộ phối không được gán vai MODEL/GARMENT của try-on.

    Vai đó bảo agent giữ mặt và dáng của ảnh người mẫu — tức là vẽ người, đúng thứ sheet cấm.
    Mọi ảnh upstream ở chế độ sheet đều là reference của cùng một bộ đồ.
    """
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    for count in (1, 2, 3):
        lines = agent._image_role_lines(
            NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                           is_item=True, item_name="Set Y2K"),
            [f"out/uploads/ref_{i}.jpg" for i in range(count)],
        )
        joined = "\n".join(lines)
        assert "COORDINATE SHEET" in joined, count
        assert "= MODEL" not in joined, count
        assert "CÙNG MỘT bộ đồ" in joined, count


def test_plain_image_node_keeps_tryon_image_roles():
    """Ảnh try-on thường vẫn phải nhận vai MODEL / GARMENT — đừng sửa nhầm sang sheet."""
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    joined = "\n".join(
        agent._image_role_lines(
            NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[]),
            ["out/uploads/model.jpg", "out/uploads/garment.jpg"],
        )
    )
    assert "ảnh thứ 1 = MODEL" in joined and "ảnh thứ 2 = GARMENT" in joined


def test_api_accepts_sheet_fields(client: TestClient):
    """Route phải nhận `is_item`/`item_name`; thiếu là UI không gửi được bảng phối."""
    from src.WebUI.app import GenerateNodePromptBody

    body = GenerateNodePromptBody(node_id="n", is_item=True, item_name="Set Y2K")
    assert body.is_item is True
    assert body.item_name == "Set Y2K"
    empty = GenerateNodePromptBody(node_id="n")
    assert empty.is_item is False and empty.item_name is None


# -- plate mode: skill plate cũ đã gộp vào try-on ----------------------------- #


def test_legacy_plate_skill_id_maps_to_tryon():
    """Project lưu trên đĩa và template canvas cũ vẫn ghi `lookbook-model-only-prompter`.
    Không map thì skill không tồn tại ⇒ rơi về nhánh mặc định và mất chế độ plate."""
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    task = NodePromptTask(
        node_id="n", node_type="image", upstream_media_urls=[],
        skill_id="lookbook-model-only-prompter",
    )
    skill = agent.select_skill(task)
    assert skill.id == "try-on-image-prompter"
    assert task.plate_mode is True


def test_plate_hint_enables_plate_mode():
    """Node plate mới ghi `agentSkillId: try-on-image-prompter` + hint; chỉ dựa vào skill_id
    thì không biết đây là plate hay try-on thường."""
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    task = NodePromptTask(
        node_id="n", node_type="image", upstream_media_urls=[],
        custom_hint="plate first frame",
    )
    assert agent.select_skill(task).id == "try-on-image-prompter"
    assert task.plate_mode is True


def test_plain_tryon_does_not_enter_plate_mode():
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    task = NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[])
    assert agent.select_skill(task).id == "try-on-image-prompter"
    assert task.plate_mode is False


def test_plate_mode_instruction_warns_against_second_image():
    """Agent phải được nói rõ là chỉ có một ảnh, nếu không nó vẫn viết `Image 2`."""
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    task = NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                          plate_mode=True)
    skill = agent.skill_mgr.get_skill("try-on-image-prompter")
    out = agent.format_agent_instruction(task, skill, [])
    assert "PLATE" in out
    assert "Image 2" in out  # câu cấm nhắc tới nó
    assert "2.5" in out
