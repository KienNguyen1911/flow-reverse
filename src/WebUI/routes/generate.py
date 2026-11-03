"""Playground image generation: single ``/api/generate`` and multi-account ``/api/batch``."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...Workflows.flow_models import parse_project_ref
from ..context import AppContext
from ..settings import MAX_PROMPT_CHARS

class GenerateBody(BaseModel):
    project_id: str
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    aspect: int = 3
    seed: Optional[int] = None
    dry_run: bool = False
    remove_watermark: bool = True
    confirm: bool = False
    workspace_project_id: Optional[str] = None


class BatchItemBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    seed: Optional[int] = None
    mode: Optional[str] = None                     # t2i | i2i (auto if omitted)
    reference_image_path: Optional[str] = None
    depends_on_shot_id: Optional[str] = None
    id: Optional[str] = None
    filename: Optional[str] = None


class BatchBody(BaseModel):
    project_id: Optional[str] = None
    items: list[BatchItemBody] = Field(default_factory=list)
    storyboard_path: Optional[str] = None
    aspect: int = 3
    dry_run: bool = False
    remove_watermark: bool = True
    confirm: bool = False
    dest_dir: Optional[str] = None
    workspace_project_id: Optional[str] = None


def build_router(ctx: AppContext) -> APIRouter:
    pool = ctx.pool
    manager = ctx.manager
    router = APIRouter()

    @router.post("/api/generate")
    def api_generate(body: GenerateBody):
        try:
            pid = parse_project_ref(body.project_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if body.seed is not None and not (1 <= int(body.seed) <= 2147483647):
            raise HTTPException(status_code=400, detail="seed phải nằm trong int32: 1..2147483647")
        if not body.dry_run:
            if not body.confirm:
                raise HTTPException(status_code=400,
                                    detail="Chạy thật cần confirm=true. Mỗi ảnh ~1 credit nếu Google nhận (reject = 0).")
            if not pool.available_accounts():
                raise HTTPException(status_code=423,
                                    detail="Tất cả account đang cooldown/disabled — chờ hết cooldown hoặc reset trong tab Pool.")
        kind = "dry_run" if body.dry_run else "generate"
        job = manager.submit(kind, {
            "project_id": pid, "prompt": body.prompt.strip(),
            "aspect": body.aspect, "seed": body.seed,
            "remove_watermark": body.remove_watermark,
            "workspace_project_id": body.workspace_project_id,
        })
        return {"job_id": job.id}

    @router.post("/api/batch")
    def api_batch(body: BatchBody):
        pid = None
        if body.project_id:
            try:
                pid = parse_project_ref(body.project_id)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        items = [i.model_dump(exclude_none=True) for i in body.items]
        if not items and not body.storyboard_path:
            raise HTTPException(status_code=400, detail="Cần 'items' (danh sách shot) hoặc 'storyboard_path'.")
        for i, it in enumerate(items):
            seed = it.get("seed")
            if seed is not None and not (1 <= int(seed) <= 2147483647):
                raise HTTPException(status_code=400, detail=f"items[{i}].seed phải trong int32: 1..2147483647")
        if not body.dry_run:
            if not body.confirm:
                raise HTTPException(status_code=400,
                                    detail="Batch chạy thật cần confirm=true. Mỗi ảnh ~1 credit nếu Google nhận.")
            if not pool.available_accounts():
                raise HTTPException(status_code=423,
                                    detail="Tất cả account đang cooldown/disabled — chờ hết cooldown hoặc reset trong tab Pool.")
        job = manager.submit("batch_generate", {
            "project_id": pid,
            "items": items,
            "storyboard_path": body.storyboard_path,
            "aspect": body.aspect,
            "dry_run": body.dry_run,
            "remove_watermark": body.remove_watermark,
            "dest_dir": body.dest_dir,
            "workspace_project_id": body.workspace_project_id,
        })
        return {"job_id": job.id}

    return router
