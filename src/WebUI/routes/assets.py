"""Asset drawer: uploaded/output listings, pinning, delete, static ``assets/`` files."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from ..asset_scan import scan_output_assets, scan_uploaded_assets
from ..context import AppContext
from ..settings import ROOT
from ..workspace import WorkspaceStore

class PinAssetBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = None
    key: Optional[str] = None
    kind: str = "upload"
    is_pinned: bool = Field(default=True, alias="isPinned")


def _enrich_assets(items: list[dict], workspace: WorkspaceStore) -> list[dict]:
    """Attach the human project name so the drawer can badge cross-project assets."""
    for item in items:
        project_id = item.get("projectId")
        item["projectName"] = workspace.name_of(project_id) if project_id else None
    return items


def _filter_assets(items: list[dict], project_id: Optional[str], scope: str) -> list[dict]:
    """Filter assets by project scope. Pinned assets are always kept."""
    if scope != "project" or not project_id:
        return items
    return [
        item
        for item in items
        if item.get("projectId") == project_id or item.get("isPinned")
    ]


def build_router(ctx: AppContext) -> APIRouter:
    out_dir = ctx.out_dir
    out_root = ctx.out_root
    asset_root = ctx.asset_root
    asset_meta = ctx.asset_meta
    manager = ctx.manager
    workspace = ctx.workspace
    router = APIRouter()

    @router.get("/api/assets/uploaded")
    def api_get_uploaded_assets(
        project_id: Optional[str] = None,
        scope: str = "all",
    ):
        items = scan_uploaded_assets(out_dir, asset_meta)
        items = _filter_assets(_enrich_assets(items, workspace), project_id, scope)
        return {"items": items}

    @router.delete("/api/assets/uploaded/{name:path}")
    def api_delete_uploaded_asset(name: str):
        upload_dir = asset_root / "uploads"
        base = upload_dir.resolve()
        p = (base / name).resolve()
        if p.is_relative_to(base) and p.is_file():
            try:
                p.unlink()
                asset_meta.remove(f"upload:{name}")
                return {"ok": True, "removed": name}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        ref_dir = asset_root / "references"
        base_ref = ref_dir.resolve()
        p_ref = (base_ref / name).resolve()
        if p_ref.is_relative_to(base_ref) and p_ref.is_file():
            try:
                p_ref.unlink()
                asset_meta.remove(f"upload:{name}")
                return {"ok": True, "removed": name}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        raise HTTPException(status_code=404, detail="Không tìm thấy file upload")

    @router.post("/api/assets/pin")
    def api_pin_asset(body: PinAssetBody):
        key = (body.key or "").strip()
        if not key and body.id:
            key = f"{body.kind}:{body.id}"
        if not key:
            raise HTTPException(status_code=400, detail="Cần 'key' hoặc 'id'.")
        pinned = asset_meta.set_pin(key, body.is_pinned, kind=body.kind or "upload")
        return {"ok": True, "key": key, "isPinned": pinned}

    @router.get("/api/assets/output")
    def api_get_output_assets(
        project_id: Optional[str] = None,
        scope: str = "all",
    ):
        items = scan_output_assets(out_root, node_out=manager.node_out, asset_meta=asset_meta)
        items = _filter_assets(_enrich_assets(items, workspace), project_id, scope)
        return {"items": items}

    @router.get("/api/assets/outputs")
    def api_get_outputs_assets_alias(
        project_id: Optional[str] = None,
        scope: str = "all",
    ):
        items = scan_output_assets(out_root, node_out=manager.node_out, asset_meta=asset_meta)
        items = _filter_assets(_enrich_assets(items, workspace), project_id, scope)
        return {"items": items}


    @router.get("/api/assets/{name:path}")
    def api_get_asset(name: str):
        base = (ROOT / "assets").resolve()
        p = (base / name).resolve()
        if not p.is_relative_to(base) or not p.is_file():
            raise HTTPException(status_code=404, detail="Không tìm thấy asset")
        return FileResponse(p)

    return router
