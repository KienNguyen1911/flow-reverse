"""AI Prompt Agent: skills, local agent config/test, node prompt generation."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...Workflows.local_agent_runner import (
    LocalAgentConfig,
    get_agent_runner,
    load_agent_config,
    save_agent_config,
)
from ...Workflows.prompt_agent import NodePromptTask, get_prompt_agent
from ...Workflows.skill_manager import get_skill_manager

class AgentConfigBody(BaseModel):
    preferred_agent: Optional[str] = "agy"
    agy_model: Optional[str] = "gemini-3.8-flash-low"
    pi_model: Optional[str] = "agnes-3.0-flash"
    timeout_s: Optional[float] = 75.0


class GenerateNodePromptBody(BaseModel):
    node_id: str
    node_type: str = "image"
    upstream_media_urls: list[str] = Field(default_factory=list)
    skill_id: Optional[str] = None
    custom_hint: Optional[str] = None
    is_video_continuation: bool = False
    agent: Optional[str] = None
    model: Optional[str] = None
    #: Ngữ cảnh kịch bản — cho phép UI chỉ định clip/món đồ thay vì đoán.
    clip_id: Optional[str] = None
    clip_role: Optional[str] = None
    item_id: Optional[str] = None
    #: Node ảnh tick "đây là ảnh sản phẩm" ⇒ dùng skill cutout + tên món làm ngữ cảnh.
    is_item: bool = False
    item_name: Optional[str] = None
    #: Phạm vi tách món: `"top"` | `"bottom"` | `"full_set"`. Chỉ có nghĩa khi `is_item`.
    item_scope: Optional[str] = None
    script_path: Optional[str] = None


class TestAgentBody(BaseModel):
    agent: Optional[str] = None


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/agent/skills")
    def api_agent_skills():
        mgr = get_skill_manager()
        mgr.reload()
        return {
            "skills": [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "file_path": s.file_path,
                }
                for s in mgr.list_skills()
            ]
        }

    @router.get("/api/agent/config")
    def api_get_agent_config():
        cfg = load_agent_config()
        return cfg.to_dict()

    @router.post("/api/agent/config")
    def api_set_agent_config(body: AgentConfigBody):
        cfg = LocalAgentConfig(
            preferred_agent=body.preferred_agent or "agy",
            agy_model=body.agy_model or "gemini-3.8-flash-low",
            pi_model=body.pi_model or "agnes-3.0-flash",
            timeout_s=body.timeout_s or 75.0,
        )
        save_agent_config(cfg)
        return {"ok": True, "config": cfg.to_dict()}

    @router.post("/api/agent/test")
    async def api_test_agent(body: Optional[TestAgentBody] = None):
        target = body.agent if body else None
        runner = get_agent_runner()
        res = await runner.test_agent(target)
        return res

    @router.post("/api/agent/generate-node-prompt")
    async def api_generate_node_prompt(body: GenerateNodePromptBody):
        agent = get_prompt_agent()
        task = NodePromptTask(
            node_id=body.node_id,
            node_type=body.node_type,
            upstream_media_urls=body.upstream_media_urls,
            skill_id=body.skill_id,
            custom_hint=body.custom_hint,
            is_video_continuation=body.is_video_continuation,
            agent=body.agent,
            model=body.model,
            clip_id=body.clip_id,
            clip_role=body.clip_role,
            item_id=body.item_id,
            is_item=body.is_item,
            item_name=body.item_name,
            item_scope=body.item_scope,
            script_path=body.script_path,
        )
        try:
            res = await agent.generate_prompt_for_node(task)
            # Lint không chặn — trả về để UI hiện cảnh báo trước khi tốn credit.
            try:
                from ...Workflows.prompt_lint import lint_prompt as _lint
                lint = _lint(res.prompt, body.node_type).to_dict()
            except Exception:  # noqa: BLE001 - lint hỏng không được chặn việc sinh prompt
                lint = None
            return {"ok": True, **res.to_dict(), "lint": lint}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi AI Prompt Agent: {e}")

    return router
