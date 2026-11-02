"""`/api/node/options` phải phơi danh sách clip để node video có `clip_id` mà chọn.

Bối cảnh: `CanvasDrawer` / `CanvasPanel` gọi `/api/agent/generate-node-prompt` mà không gửi `clip_id`.
Backend đã nhận field đó từ lâu (`GenerateNodePromptBody`), nhưng FE không có nguồn nào để biết có
clip nào — nên cả hai node video rơi vào context rỗng và sinh ra cùng một prompt.

Hợp đồng ở đây là đầu vào của ô chọn: id, role, duration, và cờ "có nhịp" để UI cảnh báo khi thiếu.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.Workflows.media_service import node_options

ROOT = Path(__file__).resolve().parents[1]


def test_node_options_exposes_script_clips():
    opts = node_options()
    script = opts.get("script")
    assert script is not None, "/api/node/options phải có key `script`"
    assert script["path"] == "configs/lookbook_script.json"
    assert script["slug"]
    assert script["duration_s"] > 0
    assert script["clips"], "phải có ít nhất một clip"


def test_every_clip_carries_what_the_selector_needs():
    """Ô chọn hiển thị `{id} · {role} · {duration}s`, nên thiếu trường nào là UI hiện rỗng."""
    opts = node_options()
    for clip in opts["script"]["clips"]:
        assert clip["id"]
        assert clip["role"] in ("hook", "showcase", "detail")
        assert clip["duration_s"] > 0
        assert "has_beats" in clip
        assert "chain_from" in clip


def test_clip_ids_match_the_script_file():
    """Nguồn sự thật là script; options chỉ là bản chiếu. Lệch nhau là node gắn clip không tồn tại."""
    script_raw = json.loads((ROOT / "configs" / "lookbook_script.json").read_text(encoding="utf-8"))
    expected = [c["id"] for c in script_raw["clips"]]
    opts = node_options()
    assert [c["id"] for c in opts["script"]["clips"]] == expected


def test_hook_clip_is_marked_as_having_beats():
    """UI dựa vào `has_beats` để hứa "có nhịp"; script mẫu phải giữ đúng lời hứa đó."""
    opts = node_options()
    hook = next(c for c in opts["script"]["clips"] if c["role"] == "hook")
    assert hook["has_beats"] is True
    assert hook["goal"], "clip hook phải có goal để ô chọn hiện được mục tiêu"


def test_node_options_survives_missing_script(monkeypatch):
    """Script hỏng/không có không được làm sập endpoint dựng UI."""
    import src.Workflows.script_contract as sc

    monkeypatch.setattr(sc, "load_default_script", lambda: None)
    opts = node_options()
    # Không có script thì vẫn trả cấu trúc hợp lệ, chỉ rỗng.
    assert opts["script"]["path"] is None
    assert opts["script"]["clips"] == []
    # Phần còn lại vẫn nguyên.
    assert opts["limits"]["max_prompt_chars"] > 0
    assert opts["video"]["supports_starting_frame"] is True
