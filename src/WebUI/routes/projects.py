"""Flow project registry (list/add/remove) + refresh/create jobs."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...Workflows.flow_models import parse_project_ref
from ..context import AppContext

class CreateProjectBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    confirm: bool = False


class AddProjectBody(BaseModel):
    ref: str
    title: Optional[str] = None


def build_router(ctx: AppContext) -> APIRouter:
    store = ctx.store
    manager = ctx.manager
    router = APIRouter()

    @router.get("/api/projects")
    def api_projects():
        return {"projects": [p.model_dump() for p in store.list()]}

    @router.post("/api/projects")
    def api_add_project(body: AddProjectBody):
        try:
            pid = parse_project_ref(body.ref)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        store.upsert_project(pid, body.title)
        return {"ok": True, "id": pid}

    @router.delete("/api/projects/{pid}")
    def api_rm_project(pid: str):
        ok = store.remove(pid.lower())
        return {"ok": ok}

    @router.post("/api/projects/refresh")
    def api_refresh_projects():
        job = manager.submit("list_projects", {})
        return {"job_id": job.id}

    @router.post("/api/projects/create")
    def api_create_project(body: CreateProjectBody):
        if not body.confirm:
            raise HTTPException(status_code=400,
                                detail="Cần confirm=true. Thao tác này tạo dự án THẬT trong tài khoản Google (0 credit).")
        job = manager.submit("create_project", {"title": body.title})
        return {"job_id": job.id}

    return router
