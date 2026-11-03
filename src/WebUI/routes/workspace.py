"""Workspace projects (local canvas groups, not Flow UUIDs) + one-time legacy migration."""

from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..asset_scan import migration_asset_entries, scan_output_assets, scan_uploaded_assets
from ..context import AppContext
from ..workspace import (
    DEFAULT_PROJECT_NAME,
    WorkspaceStore,
    normalize_canvas_state,
)

class WorkspaceCanvasBody(BaseModel):
    """Serialized canvas graph as stored on a workspace project."""

    viewport: dict = Field(default_factory=dict)
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    groups: list[dict] = Field(default_factory=list)


class CreateWorkspaceProjectBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    canvas_state: Optional[WorkspaceCanvasBody] = Field(default=None, alias="canvasState")


class UpdateWorkspaceProjectBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = None
    thumbnail_url: Optional[str] = Field(default=None, alias="thumbnailUrl")
    canvas_state: Optional[WorkspaceCanvasBody] = Field(default=None, alias="canvasState")


class DuplicateWorkspaceProjectBody(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)


class SetThumbnailBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    thumbnail_url: Optional[str] = Field(default=None, alias="thumbnailUrl")


class MigrateWorkspaceBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = DEFAULT_PROJECT_NAME
    canvas_state: Optional[WorkspaceCanvasBody] = Field(default=None, alias="canvasState")
    pinned_ids: list[str] = Field(default_factory=list, alias="pinnedIds")


def _asset_sort_ts(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value).timestamp()
        except Exception:
            pass
    return 0.0


def _workspace_projects_payload(
    workspace: WorkspaceStore,
    uploads: list[dict],
    outputs: list[dict],
) -> list[dict]:
    """Serialize projects plus derived node/asset counts and auto thumbnails."""

    counts: dict[str, int] = {}
    latest_output: dict[str, tuple[float, str]] = {}
    latest_upload: dict[str, tuple[float, str]] = {}

    for item in outputs:
        pid = item.get("projectId")
        if not pid:
            continue
        counts[pid] = counts.get(pid, 0) + 1
        url = item.get("thumbnail_url") or item.get("url")
        if not url:
            continue
        ts = _asset_sort_ts(item.get("created_ts"))
        if pid not in latest_output or ts >= latest_output[pid][0]:
            latest_output[pid] = (ts, url)

    for item in uploads:
        pid = item.get("projectId")
        if not pid:
            continue
        counts[pid] = counts.get(pid, 0) + 1
        url = item.get("thumbnail_url") or item.get("url")
        if not url:
            continue
        ts = _asset_sort_ts(item.get("created_ts"))
        if pid not in latest_upload or ts >= latest_upload[pid][0]:
            latest_upload[pid] = (ts, url)

    payload: list[dict] = []
    for project in workspace.list():
        data = project.model_dump(by_alias=True)
        data["nodeCount"] = len(data.get("canvasState", {}).get("nodes", []))
        data["assetCount"] = counts.get(project.id, 0)
        # A user-chosen preview always wins over the auto "latest media" pick.
        if not project.thumbnail_manual:
            generated = latest_output.get(project.id)
            uploaded = latest_upload.get(project.id)
            data["thumbnailUrl"] = (generated or uploaded or (0.0, None))[1]
        payload.append(data)
    return payload


def build_router(ctx: AppContext) -> APIRouter:
    out_dir = ctx.out_dir
    out_root = ctx.out_root
    manager = ctx.manager
    workspace = ctx.workspace
    asset_meta = ctx.asset_meta
    router = APIRouter()

    @router.get("/api/workspace/projects")
    def api_workspace_projects():
        uploads = scan_uploaded_assets(out_dir, asset_meta)
        outputs = scan_output_assets(out_root, node_out=manager.node_out, asset_meta=asset_meta)
        return {
            "projects": _workspace_projects_payload(workspace, uploads, outputs),
            "legacyMigrated": workspace.legacy_migrated,
        }

    @router.get("/api/workspace/projects/{pid}")
    def api_workspace_project(pid: str):
        project = workspace.get(pid)
        if project is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy project")
        return {"project": project.model_dump(by_alias=True)}

    @router.post("/api/workspace/projects")
    def api_workspace_create(body: CreateWorkspaceProjectBody):
        canvas = normalize_canvas_state(
            body.canvas_state.model_dump() if body.canvas_state is not None else None
        )
        project = workspace.create(body.name, body.description, canvas)
        return {"ok": True, "project": project.model_dump(by_alias=True)}

    @router.patch("/api/workspace/projects/{pid}")
    def api_workspace_update(pid: str, body: UpdateWorkspaceProjectBody):
        if workspace.get(pid) is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy project")
        patch = body.model_dump(exclude_unset=True)
        canvas = patch.pop("canvas_state", None)
        if canvas is not None:
            canvas = normalize_canvas_state(canvas)
        project = workspace.update(
            pid,
            name=patch.get("name"),
            description=patch.get("description"),
            thumbnail_url=patch.get("thumbnail_url"),
            canvas_state=canvas,
        )
        return {"ok": True, "project": project.model_dump(by_alias=True) if project else None}

    @router.put("/api/workspace/projects/{pid}/canvas")
    @router.post("/api/workspace/projects/{pid}/canvas")
    def api_workspace_save_canvas(pid: str, body: WorkspaceCanvasBody):
        if workspace.get(pid) is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy project")
        project = workspace.save_canvas(pid, normalize_canvas_state(body.model_dump()))
        return {
            "ok": True,
            "projectId": pid,
            "updatedAt": project.updated_at if project else None,
        }

    @router.delete("/api/workspace/projects/{pid}")
    def api_workspace_delete(pid: str):
        if workspace.get(pid) is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy project")
        if workspace.count() <= 1:
            raise HTTPException(status_code=400, detail="Không thể xóa project cuối cùng.")
        workspace.delete(pid)
        asset_meta.clear_project(pid)
        return {"ok": True, "removed": pid}

    @router.post("/api/workspace/projects/{pid}/duplicate")
    def api_workspace_duplicate(pid: str, body: Optional[DuplicateWorkspaceProjectBody] = None):
        project = workspace.duplicate(pid, body.name if body else None)
        if project is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy project")
        return {"ok": True, "project": project.model_dump(by_alias=True)}

    @router.put("/api/workspace/projects/{pid}/thumbnail")
    def api_workspace_set_thumbnail(pid: str, body: SetThumbnailBody):
        """Pin a specific image as the project preview (empty url = automatic)."""
        if workspace.get(pid) is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy project")
        url = (body.thumbnail_url or "").strip() or None
        project = workspace.set_thumbnail(pid, url, manual=bool(url))
        if project is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy project")
        return {
            "ok": True,
            "project": project.model_dump(by_alias=True),
            "thumbnailUrl": project.thumbnail_url,
            "thumbnailManual": project.thumbnail_manual,
        }

    @router.post("/api/workspace/migrate")
    def api_workspace_migrate(body: MigrateWorkspaceBody):
        raw_canvas = body.canvas_state.model_dump() if body.canvas_state is not None else None
        canvas = normalize_canvas_state(raw_canvas) if raw_canvas is not None else None
        # Only the very first import may seed a canvas from browser state.
        allow_canvas = canvas is not None and not workspace.legacy_migrated
        created = False
        projects = workspace.list()
        target = next((p for p in projects if p.name == DEFAULT_PROJECT_NAME), None)
        if target is None:
            target = projects[0] if projects else None
        if target is None:
            target = workspace.create(body.name or DEFAULT_PROJECT_NAME, canvas_state=canvas if allow_canvas else None)
            created = True
        elif allow_canvas and not target.canvas_state.get("nodes"):
            target = workspace.save_canvas(target.id, canvas) or target

        for asset_id in body.pinned_ids:
            if not asset_id:
                continue
            key = asset_id if ":" in asset_id else f"upload:{asset_id}"
            asset_meta.set_pin(key, True)

        workspace.mark_legacy_migrated()
        claimed = asset_meta.claim_unassigned(
            migration_asset_entries(out_dir, out_root, manager.node_out, asset_meta),
            target.id,
        )
        return {
            "ok": True,
            "created": created,
            "canvasImported": allow_canvas,
            "claimed": claimed,
            "project": target.model_dump(by_alias=True),
        }

    return router
