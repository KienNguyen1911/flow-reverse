"""Skill Manager — Dynamically discovers and loads prompt skills from prompt-skills/ directory."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / "prompt-skills"


@dataclass
class PromptSkill:
    id: str
    name: str
    description: str
    file_path: str
    raw_content: str
    system_instructions: str

    def to_dict(self) -> dict:
        return asdict(self)


def _extract_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse YAML-like frontmatter between --- fences."""
    frontmatter: dict[str, str] = {}
    content = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if m:
        fm_block = m.group(1)
        content = m.group(2)
        for line in fm_block.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                frontmatter[k.strip().lower()] = v.strip().strip('"').strip("'")
    return frontmatter, content


class SkillManager:
    """Manages prompt skills located in prompt-skills/ directory."""

    def __init__(self, skills_dir: Path = SKILLS_DIR):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, PromptSkill] = {}
        self.reload()

    def reload(self) -> None:
        """Scan skills_dir and load all markdown skill files."""
        self._skills.clear()
        if not self.skills_dir.exists():
            return

        for p in sorted(self.skills_dir.glob("*.md")):
            try:
                raw = p.read_text(encoding="utf-8")
                fm, body = _extract_frontmatter(raw)
                skill_id = p.stem.lower()
                name = fm.get("name", p.stem)
                desc = fm.get("description", "")

                skill = PromptSkill(
                    id=skill_id,
                    name=name,
                    description=desc,
                    file_path=str(p.relative_to(ROOT)).replace("\\", "/"),
                    raw_content=raw,
                    system_instructions=body.strip(),
                )
                self._skills[skill_id] = skill
            except Exception:
                continue

    def list_skills(self) -> list[PromptSkill]:
        return list(self._skills.values())

    def get_skill(self, skill_id: str) -> Optional[PromptSkill]:
        """Look up by exact id or exact display name.

        Không dùng khớp substring: id ngắn như "lookbook" trước đây có thể trả về
        skill đầu tiên khớp một phần, gây chọn nhầm skill.
        """
        if not skill_id:
            return None
        sid = skill_id.lower().strip()
        if sid in self._skills:
            return self._skills[sid]
        for s in self._skills.values():
            if s.name.lower() == sid:
                return s
        return None


# Global instance
_manager: Optional[SkillManager] = None


def get_skill_manager() -> SkillManager:
    global _manager
    if _manager is None:
        _manager = SkillManager()
    return _manager
