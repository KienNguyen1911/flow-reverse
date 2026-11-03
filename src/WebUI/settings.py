"""Import-time settings shared by the Flow Bench backend (routes, jobs, app factory)."""

from __future__ import annotations

from pathlib import Path

from ..Workflows.limits import load_limits

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "out" / "playground"
DEFAULT_PROJECTS_FILE = ROOT / "out" / "playground_projects.json"
DEFAULT_WEB_DIST = ROOT / "web" / "dist"

#: Độ dài prompt tối đa — resolve một lần lúc import từ ``Workflows/limits.py``
#: (env / configs/limits.json). Restart server sau khi đổi giá trị.
MAX_PROMPT_CHARS = load_limits().max_prompt_chars
