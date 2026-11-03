"""Auto try-on pipeline: start job, run listing, run file serving."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..context import AppContext
from ..settings import DEFAULT_OUT

class AutoTryOnBody(BaseModel):
    first_frame_path: Optional[str] = None
    garment_path: Optional[str] = None
    transfer_image: Optional[str] = None
    extra_images: Optional[list[str]] = None
    shopee_url: Optional[str] = None
    product_dir: Optional[str] = None
    model_path: Optional[str] = "assets/nabi_model.png"
    project_id: Optional[str] = None
    dry_run: bool = False
    auto_stitch: bool = True
    image_prompt: Optional[str] = None
    video_prompt_1: Optional[str] = None
    video_prompt_2: Optional[str] = None
    aspect_ratio: str = "9:16"
    remove_watermark: bool = True
    single_video: bool = False
    resume_run_id: Optional[str] = None
    start_from_step: Optional[int] = None
    confirm: bool = False


def build_router(ctx: AppContext) -> APIRouter:
    manager = ctx.manager
    out_dir = ctx.out_dir
    router = APIRouter()

    @router.post("/api/tryon/start")
    def api_tryon_start(body: AutoTryOnBody):
        if (
            not body.first_frame_path
            and not body.garment_path
            and not body.transfer_image
            and not body.shopee_url
            and not body.product_dir
            and not body.resume_run_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Cần cung cấp first_frame_path hoặc resume_run_id hoặc garment_path/transfer_image/product_dir/shopee_url",
            )
        if not body.dry_run and not body.confirm:
            raise HTTPException(status_code=400, detail="Chạy thật cần confirm=true.")
        job = manager.submit("auto_tryon", body.model_dump())
        return {"job_id": job.id}

    @router.get("/api/tryon/files/{run_id}/{filename:path}")
    def api_tryon_file(run_id: str, filename: str):
        aff_dir = (out_dir or DEFAULT_OUT).parent / "affiliate_runs"
        base = aff_dir.resolve()
        target = (base / run_id / filename).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            raise HTTPException(status_code=404, detail="Không tìm thấy file")
        media_type = None
        lower = filename.lower()
        if lower.endswith(".mp4"):
            media_type = "video/mp4"
        elif lower.endswith(".png"):
            media_type = "image/png"
        elif lower.endswith(".jpg") or lower.endswith(".jpeg"):
            media_type = "image/jpeg"
        elif lower.endswith(".webp"):
            media_type = "image/webp"
        elif lower.endswith(".json"):
            media_type = "application/json"
        elif lower.endswith(".txt"):
            media_type = "text/plain; charset=utf-8"
        return FileResponse(target, media_type=media_type)

    @router.get("/api/tryon/runs")
    def api_tryon_runs():
        aff_dir = (out_dir or DEFAULT_OUT).parent / "affiliate_runs"
        runs = []
        if aff_dir.exists():
            for d in sorted(aff_dir.iterdir(), reverse=True):
                if not d.is_dir():
                    continue
                mf = d / "manifest.json"
                if mf.exists():
                    try:
                        data = json.loads(mf.read_text(encoding="utf-8"))
                        rid = data.get("run_id") or d.name
                        data["run_id"] = rid
                        ff_name = Path(data.get("first_frame_path") or "").name or "first_frame.png"
                        if (d / ff_name).is_file():
                            data["first_frame_url"] = f"/api/tryon/files/{rid}/{ff_name}"
                        v1_name = Path(data.get("video_1_path") or "").name or "video_1.mp4"
                        if (d / v1_name).is_file():
                            data["video_1_url"] = f"/api/tryon/files/{rid}/{v1_name}"
                        lf_name = Path(data.get("last_frame_path") or "").name or "last_frame_video_1.png"
                        if (d / lf_name).is_file():
                            data["last_frame_url"] = f"/api/tryon/files/{rid}/{lf_name}"
                        v2_name = Path(data.get("video_2_path") or "").name or "video_2.mp4"
                        if (d / v2_name).is_file():
                            data["video_2_url"] = f"/api/tryon/files/{rid}/{v2_name}"
                        fv_name = Path(data.get("final_video_path") or "").name or "final_tryon_video_16s.mp4"
                        if (d / fv_name).is_file():
                            data["final_video_url"] = f"/api/tryon/files/{rid}/{fv_name}"
                        runs.append(data)
                    except Exception:
                        pass
        return {"runs": runs}

    return router
