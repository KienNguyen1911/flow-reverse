"""Gallery listing, generated-run files, and reference/upload storage."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..asset_scan import scan_gallery
from ..context import AppContext
from ..settings import ROOT

def build_router(ctx: AppContext) -> APIRouter:
    out_root = ctx.out_root
    asset_root = ctx.asset_root
    asset_meta = ctx.asset_meta
    router = APIRouter()

    @router.get("/api/gallery")
    def api_gallery():
        return {"runs": scan_gallery(out_root, asset_meta)}

    @router.get("/api/files/{run}/{name}")
    def api_file(run: str, name: str):
        base = out_root.resolve()
        p = (base / run / name)
        try:
            rp = p.resolve()
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="đường dẫn không hợp lệ")
        if not str(rp).startswith(str(base)) or not rp.is_file():
            raise HTTPException(status_code=404, detail="không tìm thấy file")
        return FileResponse(rp)

    @router.post("/api/upload_reference")
    async def api_upload_reference(
        file: UploadFile = File(...),
        project_id: Optional[str] = Form(None),
    ):
        if not file.filename:
            raise HTTPException(status_code=400, detail="Không có file")
        ref_dir = asset_root / "references"
        ref_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{int(time.time()*1000)}_{Path(file.filename).name}"
        dest_path = ref_dir / safe_name
        content = await file.read()
        dest_path.write_bytes(content)
        if project_id:
            asset_meta.bind(f"upload:{safe_name}", project_id, "upload")
        try:
            rel_path = str(dest_path.relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            rel_path = str(dest_path).replace("\\", "/")
        return {
            "ok": True,
            "path": rel_path,
            "filename": safe_name,
            "url": f"/api/references/{safe_name}",
            "size": len(content),
            "projectId": project_id,
        }

    @router.get("/api/references/{name}")
    def api_get_reference(name: str):
        ref_file = asset_root / "references" / name
        if not ref_file.is_file():
            raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")
        return FileResponse(ref_file)

    @router.post("/api/upload")
    async def api_upload(
        file: UploadFile = File(...),
        project_id: Optional[str] = Form(None),
    ):
        if not file.filename:
            raise HTTPException(status_code=400, detail="Không có file")
        raw_name = Path(file.filename).name
        stem = Path(raw_name).stem
        ext = Path(raw_name).suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
            raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file ảnh (.png, .jpg, .jpeg, .webp)")

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="File ảnh rỗng")
        MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=400, detail="Dung lượng ảnh vượt quá giới hạn 50MB")

        clean_stem = re.sub(r"[^a-zA-Z0-9_\u0080-\uffff-]", "_", stem)
        if not clean_stem:
            clean_stem = "upload"
        safe_name = f"{int(time.time()*1000)}_{clean_stem}{ext}"

        upload_dir = asset_root / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest_path = upload_dir / safe_name
        dest_path.write_bytes(content)
        if project_id:
            asset_meta.bind(f"upload:{safe_name}", project_id, "upload")

        try:
            rel_path = str(dest_path.relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            rel_path = str(dest_path).replace("\\", "/")

        return {
            "ok": True,
            "path": rel_path,
            "filename": safe_name,
            "url": f"/api/uploads/{safe_name}",
            "size": len(content),
            "projectId": project_id,
        }

    @router.get("/api/uploads/{name:path}")
    def api_get_upload(name: str):
        upload_dir = asset_root / "uploads"
        base = upload_dir.resolve()
        p = (base / name).resolve()
        if not p.is_relative_to(base) or not p.is_file():
            raise HTTPException(status_code=404, detail="Không tìm thấy file upload")
        return FileResponse(p)

    return router
