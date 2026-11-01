"""Contract cho thu vien pose: JSON phai parse duoc, khong chua vocabulary bi lint chan,
va moi prompt ghep tu JSON phai qua `lint_image_prompt` khong canh bao.

Chay:  python tests/test_pose_library.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.Workflows.prompt_lint import HEIGHT_BLOCK_RE, lint_image_prompt

ROOT = Path(__file__).resolve().parents[1]
POSES_DIR = ROOT / "prompt-skills" / "poses"
ASSETS = POSES_DIR / "pose_assets.json"
SKILL = ROOT / "prompt-skills" / "poses_reference.md"

#: Tiêu cự bị `IMAGE_PERSPECTIVE_ERRORS` bắt khi đứng cạnh `lens`.
BANNED_LENS = ("35mm", "24mm", "28mm", "70mm")

#: Cụm bị `IMAGE_LEG_POSE_ERRORS` bắt — làm hai chân dính thành một khối.
BANNED_LEG_PHRASES = (
    "feet shoulder-width apart",
    "shoulder-width apart",
    "legs together",
    "legs touching",
    "feet together",
    "heels together",
    "crossed legs",
    "legs merging",
)


def _assets() -> dict:
    return json.loads(ASSETS.read_text(encoding="utf-8"))


def _poses() -> list[dict]:
    return _assets()["poses"]


def _walk_strings(node, path: str = ""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk_strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk_strings(value, f"{path}[{index}]")
    elif isinstance(node, str):
        yield path, node


def _compose(pose: dict) -> str:
    """Dựng prompt giống hệt cách skill §3 mô tả: macro + pose + setting + negative."""
    lock = _assets()["consistency_lock"]
    return "\n".join(
        [
            lock["height_anchor"],
            pose["prompt_core"],
            lock["setting_lock"] + ".",
            "Negative: " + lock["negative"] + ".",
        ]
    )


def test_assets_file_is_valid_json_with_expected_shape():
    data = _assets()
    assert data["schema_version"] == 2
    assert len(data["poses"]) == 16
    for key in ("height_anchor", "setting_lock", "negative", "why_50mm"):
        assert data["consistency_lock"][key].strip(), key


def test_every_pose_has_unique_id_and_source_file():
    ids = [p["id"] for p in _poses()]
    assert len(ids) == len(set(ids))

    for pose in _poses():
        assert pose["id"].startswith("pose_")
        assert (POSES_DIR / pose["source_file"]).is_file(), pose["source_file"]


def test_pose_prompt_core_carries_no_focal_length():
    """Schema v1 nhét `shot on 35mm` vào cuối prompt_core ⇒ mỗi ảnh trong bộ một tiêu cự.

    Đây chính là nguyên nhân người mẫu đọc ra cao thấp khác nhau giữa 8 ảnh.
    """
    for pose in _poses():
        core = pose["prompt_core"]
        assert not re.search(r"\b\d{2}\s?mm\b", core), (
            f"{pose['id']}: prompt_core chứa tiêu cự {core!r} — tiêu cự thuộc về consistency_lock"
        )
        # Chỉ chặn ngôn ngữ *đặt máy*. "off-camera" là hướng nhìn hợp lệ, không phải góc máy.
        for phrase in ("eye-level", "high angle", "low angle", "camera positioned", "camera at", "shot on"):
            assert phrase not in core.lower(), (
                f"{pose['id']}: prompt_core chứa ngôn ngữ đặt máy ({phrase!r})"
            )


def test_pose_assets_avoid_lint_banned_vocabulary():
    """Lớp dữ liệu pose không được chứa cụm bị lint chặn, và tiêu cự chỉ sống trong macro.

    Macro (`height_anchor`) *được phép* chứa `50mm` — đó chính là chỗ khoá tiêu cự.
    """

    lock = _assets()["consistency_lock"]
    allowed = {
        ".consistency_lock.height_anchor",
        ".consistency_lock.why_50mm",
        ".consistency_lock.macro_note",
    }

    for path, text in _walk_strings(_assets()):
        lowered = text.lower()
        for bad in BANNED_LEG_PHRASES:
            assert bad not in lowered, f"{path} chứa cụm bị lint chặn: {bad!r}"
        if not re.search(r"\b\d{2}\s?mm\b", lowered):
            continue
        if path in allowed or "validated_batches" in path or "source_focal_length" in path:
            continue
        assert False, f"{path} chứa tiêu cự ngoài vùng cho phép: {text[:80]!r}"

    assert "50mm" in lock["height_anchor"].lower()


def test_consistency_lock_is_a_recognised_height_block():
    """Linter phải nhận header của macro, nếu không mọi prompt ghép ra đều bị warn."""

    assert HEIGHT_BLOCK_RE.search(_assets()["consistency_lock"]["height_anchor"])


def test_height_lock_pins_an_absolute_reference():
    macro = _assets()["consistency_lock"]["height_anchor"].lower()
    assert "168 cm" in macro, "thiếu mốc chiều cao tuyệt đối"
    assert "seven-and-a-half head-to-body ratio" in macro
    assert "76 percent of the frame height" in macro
    assert "50mm" in macro.lower()


def test_every_composed_prompt_passes_image_lint():
    """Ghép macro + pose + setting phải sạch cảnh báo — nếu không, skill tự dạy điều linter báo lỗi."""
    problems = {}
    for pose in _poses():
        result = lint_image_prompt(_compose(pose))
        codes = [w.code for w in result.warnings]
        if codes:
            problems[pose["id"]] = codes
    assert not problems, problems


def test_validated_batch_has_eight_batch_safe_poses():
    batch = _assets()["validated_batches"][0]
    assert len(batch["poses"]) == 8
    assert batch["result"] == "ok"

    by_id = {p["id"]: p for p in _poses()}
    for pose_id in batch["poses"]:
        assert pose_id in by_id, pose_id
        assert by_id[pose_id]["batch_safe"] is True, pose_id


def test_power_stance_is_flagged_unsafe_for_batches():
    """pose_12 vuông góc tuyệt đối ⇒ đọc ra 'cứng' khi đặt cạnh pose ba phần tư."""

    power = next(p for p in _poses() if p["id"] == "pose_12_halter_cargo_power_stance")
    assert power["batch_safe"] is False
    assert power.get("batch_note"), "phải ghi lý do để không ai vô tình thêm lại vào bộ"


def test_skill_documents_the_lock_and_the_rejected_pose():
    text = SKILL.read_text(encoding="utf-8")
    assert "[HEIGHT & PROPORTION OPTIMIZATION]" in text
    assert "consistency_lock" in text
    assert "168 cm" in text
    assert "pose_12" in text
    assert "76" in text and "50mm" in text


def test_skill_states_why_focal_differs_from_tryon():
    """Nếu không ghi lý do, lần sau ai đó sẽ 'đồng bộ' 50mm về 70mm và làm hỏng bộ."""

    text = SKILL.read_text(encoding="utf-8").lower()
    assert "70mm" in text, "phải nêu bản try-on dùng 70mm để so sánh"
    assert "50mm" in text
    assert "82-85" in text or "82–85" in text, "phải nêu occupancy của bản try-on"


@pytest.mark.parametrize("pose_id", [p["id"] for p in json.loads(ASSETS.read_text(encoding="utf-8"))["poses"]])
def test_pose_prompt_core_is_substantive(pose_id: str):
    pose = next(p for p in _poses() if p["id"] == pose_id)
    words = len(pose["prompt_core"].split())
    assert words >= 40, f"{pose_id}: prompt_core quá ngắn ({words} từ) để giữ được dáng"
