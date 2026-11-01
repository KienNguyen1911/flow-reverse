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
        projects_file=base / "projects.json",
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
    assert "lookbook-thumbnail-prompter" in ids

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


# -- item_scope: chọn món nào lên ảnh sản phẩm ------------------------------- #


def _agent_with_skills():
    from src.Workflows.prompt_agent import PromptAgent

    agent = PromptAgent.__new__(PromptAgent)  # không cần runner cho phần format
    agent.skill_mgr = get_skill_manager()
    return agent


def test_item_scope_reaches_agent_instruction():
    """Không có phạm vi thì agent không biết cắt món nào — model tự chọn, luôn ra chiếc áo."""
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    skill = agent.skill_mgr.get_skill("lookbook-item-cutout-prompter")
    assert skill is not None

    for scope, needle in (
        ("top", "chỉ ÁO"),
        ("bottom", "chỉ QUẦN / VÁY"),
        ("full_set", "CẢ BỘ"),
    ):
        out = agent.format_agent_instruction(
            NodePromptTask(
                node_id="n",
                node_type="image",
                upstream_media_urls=[],
                is_item=True,
                item_name="Set Donna",
                item_scope=scope,
            ),
            skill,
            [],
        )
        assert needle in out, scope
        assert "Phạm vi cần tách" in out, scope


def test_item_scope_excludes_other_piece():
    """Mỗi phạm vi phải nói rõ món KHÔNG được xuất hiện, nếu không model vẫn vẽ cả bộ."""
    from src.Workflows.prompt_agent import ITEM_SCOPES

    assert "skirt" in ITEM_SCOPES["top"]["exclude"].lower()
    assert "shirt" in ITEM_SCOPES["bottom"]["exclude"].lower()
    assert "full_set" in ITEM_SCOPES


def test_item_scope_ignored_for_video_and_plain_images():
    """Phạm vi chỉ có nghĩa với node ẢNH sản phẩm; video/non-item không được đổi hành vi."""
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    assert agent.resolve_item_scope(
        NodePromptTask(node_id="n", node_type="video", upstream_media_urls=[],
                       is_item=True, item_scope="top")
    ) is None
    assert agent.resolve_item_scope(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                       is_item=False, item_scope="top")
    ) is None
    # Dữ liệu cũ / gõ tay sai ⇒ bỏ qua, giữ hành vi cũ.
    assert agent.resolve_item_scope(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                       is_item=True, item_scope="left_sleeve")
    ) is None
    assert agent.resolve_item_scope(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                       is_item=True, item_scope="full_set")
    ) is not None


def test_item_node_not_reminded_it_is_a_plate():
    """Node ảnh sản phẩm KHÔNG phải plate — nhắc 'người mẫu toàn thân' sẽ kéo model vẽ người."""
    from src.Workflows.prompt_agent import NodePromptTask

    agent = _agent_with_skills()
    skill = agent.skill_mgr.get_skill("lookbook-item-cutout-prompter")
    out = agent.format_agent_instruction(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[],
                       is_item=True, item_name="Set Donna", item_scope="top"),
        skill, [],
    )
    assert "plate nền" not in out


def test_api_accepts_item_scope(client: TestClient):
    """Route phải nhận `item_scope`; sai chính tả là 422 và UI không gửi được phạm vi."""
    from src.WebUI.app import GenerateNodePromptBody

    body = GenerateNodePromptBody(node_id="n", is_item=True, item_scope="bottom")
    assert body.item_scope == "bottom"
    assert GenerateNodePromptBody(node_id="n").item_scope is None


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
