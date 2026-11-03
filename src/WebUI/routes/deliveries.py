"""Deliveries (HyperFrames desktop material kits) + the per-project item library."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ...Workflows.delivery import DEFAULT_DELIVERY_ROOT, list_deliveries
from ...Workflows.script_contract import ScriptError, load_script
from ..context import AppContext

class DeliveryBuildBody(BaseModel):
    """Dựng thư mục nguyên liệu cho HyperFrames desktop từ một lookbook script."""

    script_path: Optional[str] = None
    script: Optional[dict] = None
    run_refs: list[dict] = Field(default_factory=list)
    #: Ảnh sản phẩm sinh từ node ảnh Flow: `{name, item_id?, run_id|run_dir|file_path}`.
    #: Có `item_id` khớp `items[]` của script thì dùng đúng tên script khai; chỉ có `name`
    #: thì đặt tên theo slug của tên món. Mỗi món một ảnh.
    item_refs: list[dict] = Field(default_factory=list)
    #: Thư mục đích. Mặc định `out/deliveries`.
    dest_dir: Optional[str] = None
    overwrite: bool = False


def build_router(ctx: AppContext) -> APIRouter:
    manager = ctx.manager
    delivery_root = ctx.delivery_root
    router = APIRouter()

    def _delivery_root() -> Path:
        return Path(delivery_root) if delivery_root else DEFAULT_DELIVERY_ROOT

    @router.get("/api/items/library")
    def api_item_library(project_id: Optional[str] = None):
        """Thư viện ảnh sản phẩm của một project: `out/items/<project_id>/`.

        Không phụ thuộc kịch bản — mỗi lần node ảnh có cờ `is_item` sinh xong, file được
        chép vào đây theo tên món. Người bán xem lại toàn bộ món đã có, dùng cho nhiều bộ.
        """
        from ...Workflows.item_library import item_dir, list_items

        return {
            "project_id": project_id,
            "dir": str(item_dir(project_id)),
            "items": list_items(project_id),
        }

    @router.post("/api/deliveries")
    def api_create_delivery(body: DeliveryBuildBody):
        """Dựng (hoặc dựng lại) thư mục nguyên liệu. Không gọi Flow → không tốn credit."""
        params: dict = {
            "run_refs": body.run_refs,
            "item_refs": body.item_refs,
            "overwrite": body.overwrite,
        }
        if body.script_path:
            params["script_path"] = body.script_path
        elif body.script:
            params["script"] = body.script
        else:
            raise HTTPException(
                status_code=400,
                detail="cần `script_path` hoặc `script` (object) để biết dựng bộ nào",
            )

        # Validate sớm để trả lỗi 400 thay vì để job chết ở nền.
        try:
            script = load_script(body.script_path or body.script or "")
        except ScriptError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if body.dest_dir:
            params["dest_dir"] = body.dest_dir
        elif delivery_root:
            params["dest_dir"] = str(delivery_root)

        job = manager.submit("delivery_build", params)
        return {
            "job_id": job.id,
            "kind": "delivery_build",
            "slug": script.slug,
            "dest_dir": str((Path(params["dest_dir"]) if params.get("dest_dir") else _delivery_root()) / script.slug),
        }

    @router.get("/api/deliveries")
    def api_list_deliveries():
        return {"deliveries": list_deliveries(_delivery_root())}

    @router.get("/api/deliveries/{slug}/{file_path:path}")
    def api_delivery_file(slug: str, file_path: str):
        base = (_delivery_root() / slug).resolve()
        p = (base / file_path).resolve()
        if not p.is_relative_to(base) or not p.is_file():
            raise HTTPException(status_code=404, detail="không tìm thấy file trong bộ dựng phim")
        return FileResponse(p)

    @router.get("/api/deliveries/{slug}")
    def api_delivery_detail(slug: str):
        manifest = _delivery_root() / slug / "delivery.json"
        if not manifest.is_file():
            raise HTTPException(status_code=404, detail="không tìm thấy bộ dựng phim")
        try:
            return json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise HTTPException(status_code=500, detail=f"delivery.json hỏng: {exc}")

    return router
