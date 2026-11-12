"""Regression: ảnh try-on ra SAI TRANG PHỤC dù 3 ảnh tham chiếu đúng.

Chuỗi lỗi thật (project HAVANA, node ảnh nối model + garment + background):

1. `format_agent_instruction` dài 34.795 ký tự. Windows `CreateProcess` giới hạn
   32.767 ký tự cho cả command line ⇒ `WinError 206`. Nút "Tạo lại Prompt" chết,
   nên không có đường nào sửa ảnh sai.
2. `_script_context_lines` chèn `- Món đồ trong bộ: item_1(DONNA CAMISOLE),
   item_2(SHEER CARDIGAN)` vào **mọi** node ảnh. Agent tin chữ hơn pixel ⇒ viết ra
   bộ Donna dù ảnh garment là áo lệch vai be + váy bong bóng xám.
3. Không có chỗ nào nói ảnh 1/2/3 là gì, nên agent phải đoán vai trò từng ảnh.

Ba test dưới đây khoá đúng ba lỗi đó.
"""

from __future__ import annotations

from pathlib import Path

from src.Workflows.local_agent_runner import MAX_INLINE_INSTRUCTION, ROOT, _build_print_arg
from src.Workflows.prompt_agent import NodePromptTask, PromptAgent


def _agent() -> PromptAgent:
    from src.Workflows.skill_manager import get_skill_manager

    agent = PromptAgent.__new__(PromptAgent)  # không cần runner cho phần format
    agent.skill_mgr = get_skill_manager()
    return agent


# --------------------------------------------------------------------------- #
# 1. Script không được áp danh sách món của nó lên node ảnh của người dùng
# --------------------------------------------------------------------------- #

def test_script_items_not_injected_into_plain_image_node():
    """Node ảnh thường (không phải item) không được thấy tên món của script."""
    agent = _agent()
    skill = agent.skill_mgr.get_skill("try-on-image-prompter")
    out = agent.format_agent_instruction(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=["/api/uploads/a.png"]),
        skill,
        [],
    )
    assert "DONNA" not in out.upper(), "tên món của script rò vào instruction node ảnh"
    assert "SHEER CARDIGAN" not in out.upper()
    assert "Món đồ trong bộ" not in out


def test_script_items_still_reach_item_nodes():
    """Bỏ ngữ cảnh script ở node ảnh thường không được làm mất ngữ cảnh node sản phẩm."""
    agent = _agent()
    skill = agent.skill_mgr.get_skill("lookbook-item-cutout-prompter")
    out = agent.format_agent_instruction(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[], item_id="item_1"),
        skill,
        [],
    )
    assert "DONNA CAMISOLE" in out.upper()


def test_video_nodes_keep_script_context():
    """Video vẫn phải nhận clip/shots từ script — chỉ node ảnh thường bị cắt."""
    agent = _agent()
    skill = agent.skill_mgr.get_skill("lookbook-video-prompter")
    out = agent.format_agent_instruction(
        NodePromptTask(node_id="n", node_type="video", upstream_media_urls=[], clip_id="clip1"),
        skill,
        [],
    )
    assert "KỊCH BẢN PHIM" in out


# --------------------------------------------------------------------------- #
# 2. Vai trò từng ảnh phải được nói rõ, không để agent đoán
# --------------------------------------------------------------------------- #

def test_image_roles_told_explicitly_for_three_images():
    agent = _agent()
    skill = agent.skill_mgr.get_skill("try-on-image-prompter")
    out = agent.format_agent_instruction(
        NodePromptTask(
            node_id="n",
            node_type="image",
            upstream_media_urls=["/a.png", "/b.png", "/c.png"],
        ),
        skill,
        [Path("a.png"), Path("b.png"), Path("c.png")],
    )
    assert "ảnh thứ 1 = MODEL" in out
    assert "ảnh thứ 2 = GARMENT" in out
    assert "ảnh thứ 3 = BACKGROUND" in out
    # Ánh xạ sang token phải nói rõ, nếu không agent tự đặt tên khác.
    assert "`<<model>>`" in out


def test_image_roles_told_explicitly_for_two_images():
    agent = _agent()
    skill = agent.skill_mgr.get_skill("try-on-image-prompter")
    out = agent.format_agent_instruction(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=["/a.png", "/b.png"]),
        skill,
        [Path("a.png"), Path("b.png")],
    )
    assert "ảnh thứ 2 = GARMENT" in out
    # Skill có nhắc `<<background>>` trong template; chỉ phần BỐI CẢNH NODE mới
    # được quyết định vai trò, nên scope assertion vào đó.
    node_ctx = out.split("--- BỐI CẢNH NODE HIỆN TẠI ---")[-1]
    assert "ảnh thứ 3 = BACKGROUND" not in node_ctx


def test_plate_mode_does_not_claim_three_images():
    """Plate chỉ có một ảnh; nhắc ảnh 2/3 là agent tự bịa ra ảnh không tồn tại."""
    agent = _agent()
    skill = agent.skill_mgr.get_skill("try-on-image-prompter")
    out = agent.format_agent_instruction(
        NodePromptTask(
            node_id="n", node_type="image", upstream_media_urls=["/a.png"], plate_mode=True
        ),
        skill,
        [Path("a.png")],
    )
    node_ctx = out.split("--- BỐI CẢNH NODE HIỆN TẠI ---")[-1]
    assert "ảnh thứ 2 = GARMENT" not in node_ctx
    assert "nó đóng cả hai vai" in node_ctx


# --------------------------------------------------------------------------- #
# 3. Instruction dài phải đi qua file, không nhét vào command line
# --------------------------------------------------------------------------- #

def test_long_instruction_routed_via_file_not_cmdline():
    """Skill try-on đã >32.767 ký tự ⇒ nhét vào `-p` là WinError 206."""
    short = "x" * 10
    assert _build_print_arg(short, "agy") == short

    long_ins = "y" * (MAX_INLINE_INSTRUCTION + 1)
    arg = _build_print_arg(long_ins, "agy")
    assert len(arg) < 1000, f"arg vẫn quá dài: {len(arg)}"
    assert "out/_agent_tasks/" in arg

    written = list((ROOT / "out" / "_agent_tasks").glob("task_*_agy.md"))
    assert written, "không ghi file task"
    latest = max(written, key=lambda p: p.stat().st_mtime)
    assert latest.read_text(encoding="utf-8") == long_ins


def test_tryon_instruction_exceeds_cmdline_limit():
    """Nếu skill ngắn lại dưới trần này thì test routing ở trên thành vô nghĩa."""
    agent = _agent()
    skill = agent.skill_mgr.get_skill("try-on-image-prompter")
    ins = agent.format_agent_instruction(
        NodePromptTask(node_id="n", node_type="image", upstream_media_urls=[]),
        skill,
        [],
    )
    assert len(ins) > MAX_INLINE_INSTRUCTION, (
        f"instruction chỉ {len(ins)} ký tự — đường file không còn được kiểm chứng"
    )
