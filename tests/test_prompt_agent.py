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
    assert "lookbook-image-prompter" in ids

    # Check policy clause extraction
    tryon = mgr.get_skill("try-on-image-prompter")
    assert tryon is not None
    assert "fictional" in tryon.policy_clause.lower()


def test_extract_clean_prompt_codeblock():
    raw = """
Here is your prompt:
```markdown
[POLICY COMPLIANCE]: Fictional character.
A young woman in a beige knit cardigan, soft lighting, 8k.
```
Hope this helps!
"""
    cleaned = extract_clean_prompt_from_agent_output(raw)
    assert "[POLICY COMPLIANCE]" in cleaned
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
