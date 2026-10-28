"""Flow Bench — FastAPI backend for the image-generation playground.

Run:  python -m src.WebUI.app  [--port 4000] [--cdp-url http://127.0.0.1:4022] [--open]

Serves:
  /api/status            bridge/browser/tab status + breaker snapshot (no playwright)
  /api/pool              N-account pool: active working set vs standby (wakes nothing)
  /api/pool/config       tuning: target_jobs_per_account, max_active_browsers
  /api/pool/accounts/{id}/{wake|hibernate|reset}   per-account actions
  /api/projects          registry of projects (GET list, POST add, DELETE remove)
  /api/projects/refresh  job: UpteDb list-projects (0 credit)
  /api/projects/create   job: jHPbke create-project (0 credit, needs confirm)
  /api/generate          job: ogiZ0b generate image (needs confirm unless dry_run)
  /api/batch             job: J images across N_alloc accounts (needs confirm unless dry_run)
  /api/node/options      canvas node options (verified aspect enums, video limits)
  /api/node/image        job: one canvas image node (prompt, ratio, optional attachment)
  /api/node/video        job: one canvas video node (prompt, ratio, attachment or image→video)
  /api/node/files/{p}    generated node media (out/nodes)
  /api/jobs, /api/jobs/{id}
  /api/gallery           past runs (scans out/playground/*/meta.json)
  /api/files/{run}/{name}
  /                      the built playground UI (web/dist)

Browsers are woken on demand by the pool (AccountPoolManager) — the server
never launches all profiles at startup (plan docs/upgrade_plan_n_account_pool.md).
"""

from __future__ import annotations

import argparse
import json
import re
import webbrowser
import time
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..Workflows.account_pool import AccountPoolManager
from ..Workflows.flow_client import DEFAULT_CDP_URL
from ..Workflows.flow_models import parse_project_ref
from ..Workflows.local_agent_runner import (
    LocalAgentConfig,
    get_agent_runner,
    load_agent_config,
    save_agent_config,
)
from ..Workflows.media_service import (
    AspectNotVerifiedError,
    UnsupportedOptionError,
    node_options,
    normalize_video_ratio,
    normalize_video_resolution,
    resolve_image_aspect,
    resolve_input_path,
    validate_video_duration,
)
from ..Workflows.prompt_agent import NodePromptTask, get_prompt_agent
from ..Workflows.skill_manager import get_skill_manager
from .jobs import JobManager, ProjectsStore

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "out" / "playground"
DEFAULT_PROJECTS_FILE = ROOT / "out" / "playground_projects.json"
DEFAULT_WEB_DIST = ROOT / "web" / "dist"

# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #


class GenerateBody(BaseModel):
    project_id: str
    prompt: str = Field(min_length=1, max_length=5000)
    aspect: int = 3
    seed: Optional[int] = None
    dry_run: bool = False
    remove_watermark: bool = True
    confirm: bool = False


class NodeImageBody(BaseModel):
    """One canvas image node: prompt + ratio + optional attached reference image(s)."""

    prompt: str = Field(min_length=1, max_length=5000)
    aspect_ratio: Optional[str] = None      # "16:9" (verified), other ratios need capture
    aspect: Optional[int] = None            # raw enum escape hatch (wins over aspect_ratio)
    seed: Optional[int] = None
    reference_image_path: Optional[str] = None   # path or /api/uploads|references|assets URL
    reference_image_paths: Optional[list[str]] = None
    project_id: Optional[str] = None
    dry_run: bool = False
    remove_watermark: bool = True
    confirm: bool = False


class NodeVideoBody(BaseModel):
    """One canvas video node: prompt + ratio + attached frame (or auto image→video chain)."""

    prompt: str = Field(min_length=1, max_length=5000)
    aspect_ratio: str = "9:16"
    frame_path: Optional[str] = None        # attached image (path or /api/... URL)
    image_prompt: Optional[str] = None      # used only when auto_image generates the frame
    image_aspect_ratio: str = "16:9"        # frame image ratio (only 16:9 verified today)
    auto_image: bool = True
    seed: Optional[int] = None
    resolution: str = "1080p"
    duration_s: int = 8
    project_id: Optional[str] = None
    dry_run: bool = False
    remove_watermark: bool = True
    confirm: bool = False


class NodeLastFrameBody(BaseModel):
    """Extract last frame of a video for chaining to next video/image node (0 credit)."""

    video_path: str
    remove_watermark: bool = True


class CreateProjectBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    confirm: bool = False


class AddProjectBody(BaseModel):
    ref: str
    title: Optional[str] = None


class BatchItemBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
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


class PoolConfigBody(BaseModel):
    target_jobs_per_account: Optional[int] = None
    max_active_browsers: Optional[int] = None


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


class TestAgentBody(BaseModel):
    agent: Optional[str] = None


class AddAccountBody(BaseModel):
    id: str
    profile_id: Optional[str] = None
    cdp_port: Optional[int] = None
    enabled: bool = True
    note: Optional[str] = None
    create_profile: bool = True


class UpdateAccountBody(BaseModel):
    enabled: Optional[bool] = None
    note: Optional[str] = None
    cdp_port: Optional[int] = None


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


# --------------------------------------------------------------------------- #
# Gallery scanner
# --------------------------------------------------------------------------- #


def scan_gallery(out_root: Path) -> list[dict]:
    runs: list[dict] = []
    if not out_root.exists():
        return runs
    for d in sorted(out_root.iterdir(), reverse=True):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        mp = d / "meta.json"
        if not mp.exists():
            continue
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        f = meta.get("file")
        if not f:
            continue
        fp = Path(f)
        if not fp.exists() or fp.parent != d:
            continue
        runs.append({
            "run": d.name,
            "file": fp.name,
            "url": f"/api/files/{d.name}/{fp.name}",
            "prompt": meta.get("prompt"),
            "title": meta.get("title"),
            "project_id": meta.get("project_id"),
            "seed": meta.get("seed"),
            "seed_echo": meta.get("seed_echo"),
            "resolution": meta.get("resolution"),
            "media_id": meta.get("media_id"),
            "created_ts": meta.get("created_ts"),
            "elapsed_s": meta.get("elapsed_s"),
            "file_bytes": meta.get("file_bytes"),
            "status": meta.get("status"),
        })
    return runs


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #


def create_app(cdp_url: str = DEFAULT_CDP_URL, out_dir: Optional[Path] = None,
               projects_file: Optional[Path] = None, web_dist: Optional[Path] = None,
               pool_config: Optional[Path] = None, pool_state: Optional[Path] = None) -> FastAPI:
    out_root = Path(out_dir) if out_dir else DEFAULT_OUT
    store = ProjectsStore(Path(projects_file) if projects_file else DEFAULT_PROJECTS_FILE)
    pool = AccountPoolManager(
        config_path=Path(pool_config) if pool_config else None,
        state_path=Path(pool_state) if pool_state else None,
        out_root=out_root,
        default_cdp_url=cdp_url,
    )
    manager = JobManager(pool=pool, store=store, out_root=out_root)

    app = FastAPI(title="Flow Bench", version="0.2.0")
    app.state.pool = pool
    app.state.manager = manager
    app.state.store = store
    app.state.out_root = out_root

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", []) if x != "body")
            msg = err.get("msg", "Lỗi tham số")
            errors.append(f"{loc}: {msg}" if loc else msg)
        msg_str = "; ".join(errors)
        return JSONResponse(status_code=422, content={"detail": f"Tham số không hợp lệ: {msg_str}"})

    # -- status ------------------------------------------------------------- #

    @app.get("/api/status")
    def api_status():
        client = pool.status_client()
        st = client.status()
        snap = client.breaker.snapshot()
        d = st.model_dump()
        d["queue_depth"] = manager.queue_depth()
        d["current_job_id"] = manager.current_id()
        d["breaker"] = {
            "cooldown_remaining_s": snap.get("cooldown_remaining_s"),
            "cooldown_reason": snap.get("cooldown_reason") or None,
            "total_accepted": snap.get("total_accepted"),
            "total_rejected": snap.get("total_rejected"),
            "consecutive_anti_abuse": snap.get("consecutive_anti_abuse"),
        }
        return d

    # -- account pool --------------------------------------------------------- #

    @app.get("/api/pool")
    def api_pool():
        return pool.snapshot()

    @app.post("/api/pool/config")
    def api_pool_config(body: PoolConfigBody):
        try:
            updated = pool.update_config(body.target_jobs_per_account, body.max_active_browsers)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True, **updated}

    @app.post("/api/pool/accounts/{aid}/wake")
    def api_pool_wake(aid: str):
        try:
            return pool.wake_account(aid)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/api/pool/accounts/{aid}/hibernate")
    def api_pool_hibernate(aid: str):
        try:
            return pool.hibernate_account(aid)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/api/pool/accounts/{aid}/reset")
    def api_pool_reset(aid: str):
        try:
            return pool.reset_account(aid)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/pool/next_port")
    def api_pool_next_port():
        return {"next_port": pool.next_suggested_port()}

    @app.post("/api/pool/accounts")
    def api_pool_add_account(body: AddAccountBody):
        try:
            acc = pool.add_account(
                account_id=body.id,
                profile_id=body.profile_id,
                cdp_port=body.cdp_port,
                enabled=body.enabled,
                note=body.note or "",
                create_profile=body.create_profile,
            )
            return {
                "ok": True,
                "account": {
                    "id": acc.id,
                    "profile_id": acc.profile_id,
                    "cdp_port": acc.cdp_port,
                    "enabled": acc.enabled,
                    "note": acc.note,
                },
            }
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.patch("/api/pool/accounts/{aid}")
    def api_pool_update_account(aid: str, body: UpdateAccountBody):
        try:
            acc = pool.update_account(
                account_id=aid,
                enabled=body.enabled,
                note=body.note,
                cdp_port=body.cdp_port,
            )
            return {
                "ok": True,
                "account": {
                    "id": acc.id,
                    "profile_id": acc.profile_id,
                    "cdp_port": acc.cdp_port,
                    "enabled": acc.enabled,
                    "note": acc.note,
                },
            }
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.delete("/api/pool/accounts/{aid}")
    def api_pool_delete_account(aid: str, delete_vault: bool = False):
        try:
            return pool.remove_account(aid, delete_vault=delete_vault)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/pool/accounts/{aid}/detail")
    def api_pool_account_detail(aid: str):
        try:
            return pool.account_detail(aid)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # -- projects ------------------------------------------------------------ #

    @app.get("/api/projects")
    def api_projects():
        return {"projects": [p.model_dump() for p in store.list()]}

    @app.post("/api/projects")
    def api_add_project(body: AddProjectBody):
        try:
            pid = parse_project_ref(body.ref)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        store.upsert_project(pid, body.title)
        return {"ok": True, "id": pid}

    @app.delete("/api/projects/{pid}")
    def api_rm_project(pid: str):
        ok = store.remove(pid.lower())
        return {"ok": ok}

    @app.post("/api/projects/refresh")
    def api_refresh_projects():
        job = manager.submit("list_projects", {})
        return {"job_id": job.id}

    @app.post("/api/projects/create")
    def api_create_project(body: CreateProjectBody):
        if not body.confirm:
            raise HTTPException(status_code=400,
                                detail="Cần confirm=true. Thao tác này tạo dự án THẬT trong tài khoản Google (0 credit).")
        job = manager.submit("create_project", {"title": body.title})
        return {"job_id": job.id}

    # -- generation ------------------------------------------------------------ #

    @app.post("/api/generate")
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
        })
        return {"job_id": job.id}

    # -- batch (N_alloc accounts, plan Task 3) --------------------------------- #

    @app.post("/api/batch")
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
        })
        return {"job_id": job.id}

    # -- canvas nodes (image / video, independent of the try-on pipeline) ------- #

    @app.get("/api/node/options")
    def api_node_options():
        return node_options()

    @app.post("/api/node/image")
    def api_node_image(body: NodeImageBody):
        try:
            ratio, enum = resolve_image_aspect(body.aspect_ratio, body.aspect)
        except (AspectNotVerifiedError, UnsupportedOptionError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        if body.seed is not None and not (1 <= int(body.seed) <= 2147483647):
            raise HTTPException(status_code=400, detail="seed phải nằm trong int32: 1..2147483647")

        # Collect & validate all reference image paths
        all_refs: list[str] = []
        if body.reference_image_paths:
            for rp in body.reference_image_paths:
                if rp and rp not in all_refs:
                    all_refs.append(rp)
        if body.reference_image_path and body.reference_image_path not in all_refs:
            all_refs.insert(0, body.reference_image_path)

        for ref_p in all_refs:
            if not resolve_input_path(ref_p).is_file():
                raise HTTPException(status_code=400, detail=f"Không tìm thấy ảnh đính kèm: {ref_p}")

        if not body.dry_run:
            if not body.confirm:
                raise HTTPException(status_code=400,
                                    detail="Chạy thật cần confirm=true. Mỗi ảnh ~1 credit nếu Google nhận (reject = 0).")
            if not pool.available_accounts():
                raise HTTPException(status_code=423,
                                    detail="Tất cả account đang cooldown/disabled — chờ hết cooldown hoặc reset trong tab Pool.")
        job = manager.submit("node_image", {
            "prompt": body.prompt.strip(),
            "aspect_ratio": ratio,
            "aspect": enum,
            "seed": body.seed,
            "reference_image_path": all_refs[0] if all_refs else None,
            "reference_image_paths": all_refs if all_refs else None,
            "project_id": body.project_id,
            "dry_run": body.dry_run,
            "remove_watermark": body.remove_watermark,
        })
        return {"job_id": job.id, "kind": "image", "aspect_ratio": ratio, "aspect": enum}

    @app.post("/api/node/video")
    def api_node_video(body: NodeVideoBody):
        try:
            ratio = normalize_video_ratio(body.aspect_ratio)
            resolution = normalize_video_resolution(body.resolution)
            duration = validate_video_duration(body.duration_s)
            image_ratio, _image_enum = resolve_image_aspect(body.image_aspect_ratio)
        except (AspectNotVerifiedError, UnsupportedOptionError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not body.frame_path and not body.auto_image:
            raise HTTPException(
                status_code=400,
                detail="Flow chỉ hỗ trợ image-to-video: cần ảnh đính kèm (frame_path) "
                       "hoặc bật auto_image=true để tạo ảnh khung hình trước.",
            )
        if body.frame_path and not resolve_input_path(body.frame_path).is_file():
            raise HTTPException(status_code=400, detail=f"Không tìm thấy ảnh đính kèm: {body.frame_path}")
        if not body.dry_run:
            if not body.confirm:
                raise HTTPException(status_code=400,
                                    detail="Chạy thật cần confirm=true. Mỗi video ~1 credit nếu Google nhận (reject = 0).")
            if not pool.available_accounts():
                raise HTTPException(status_code=423,
                                    detail="Tất cả account đang cooldown/disabled — chờ hết cooldown hoặc reset trong tab Pool.")
        job = manager.submit("node_video", {
            "prompt": body.prompt.strip(),
            "frame_path": body.frame_path,
            "image_prompt": body.image_prompt,
            "image_aspect_ratio": image_ratio,
            "auto_image": body.auto_image,
            "aspect_ratio": ratio,
            "seed": body.seed,
            "resolution": resolution,
            "duration_s": duration,
            "project_id": body.project_id,
            "dry_run": body.dry_run,
            "remove_watermark": body.remove_watermark,
        })
        return {
            "job_id": job.id, "kind": "video", "aspect_ratio": ratio,
            "resolution": resolution, "duration_s": duration, "frame_source": ("provided" if body.frame_path else "generated"),
        }

    @app.post("/api/node/last_frame")
    def api_node_last_frame(body: NodeLastFrameBody):
        resolved = resolve_input_path(body.video_path)
        if not resolved.is_file():
            raise HTTPException(status_code=400, detail=f"Không tìm thấy file video: {body.video_path}")
        job = manager.submit("node_last_frame", {
            "video_path": str(resolved),
            "remove_watermark": body.remove_watermark,
        })
        return {"job_id": job.id, "kind": "last_frame"}

    @app.get("/api/node/files/{file_path:path}")
    def api_node_file(file_path: str):
        base = manager.node_out.resolve()
        p = (base / file_path).resolve()
        if not p.is_relative_to(base) or not p.is_file():
            raise HTTPException(status_code=404, detail="không tìm thấy file node")
        return FileResponse(p)

    # -- jobs ------------------------------------------------------------------ #

    @app.get("/api/jobs")
    def api_jobs(limit: int = 30):
        return {"jobs": [j.to_dict(with_events=False) for j in manager.list(limit=limit)]}

    @app.get("/api/jobs/{jid}")
    def api_job(jid: str):
        job = manager.get(jid)
        if job is None:
            raise HTTPException(status_code=404, detail="job không tồn tại")
        return job.to_dict(with_events=True)

    # -- gallery ----------------------------------------------------------------- #

    @app.get("/api/gallery")
    def api_gallery():
        return {"runs": scan_gallery(out_root)}

    @app.get("/api/files/{run}/{name}")
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

    @app.post("/api/upload_reference")
    async def api_upload_reference(file: UploadFile = File(...)):
        if not file.filename:
            raise HTTPException(status_code=400, detail="Không có file")
        ref_dir = ROOT / "out" / "references"
        ref_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{int(time.time()*1000)}_{Path(file.filename).name}"
        dest_path = ref_dir / safe_name
        content = await file.read()
        dest_path.write_bytes(content)
        rel_path = str(dest_path.relative_to(ROOT)).replace("\\", "/")
        return {
            "ok": True,
            "path": rel_path,
            "filename": safe_name,
            "url": f"/api/references/{safe_name}",
            "size": len(content),
        }

    @app.get("/api/references/{name}")
    def api_get_reference(name: str):
        ref_file = ROOT / "out" / "references" / name
        if not ref_file.is_file():
            raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")
        return FileResponse(ref_file)

    @app.post("/api/upload")
    async def api_upload(file: UploadFile = File(...)):
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

        upload_dir = (out_dir.parent if out_dir else (ROOT / "out")) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest_path = upload_dir / safe_name
        dest_path.write_bytes(content)

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
        }

    @app.get("/api/uploads/{name:path}")
    def api_get_upload(name: str):
        upload_dir = (out_dir.parent if out_dir else (ROOT / "out")) / "uploads"
        base = upload_dir.resolve()
        p = (base / name).resolve()
        if not p.is_relative_to(base) or not p.is_file():
            raise HTTPException(status_code=404, detail="Không tìm thấy file upload")
        return FileResponse(p)

    @app.get("/api/assets/{name:path}")
    def api_get_asset(name: str):
        base = (ROOT / "assets").resolve()
        p = (base / name).resolve()
        if not p.is_relative_to(base) or not p.is_file():
            raise HTTPException(status_code=404, detail="Không tìm thấy asset")
        return FileResponse(p)

    @app.get("/api/circuit/clear")
    def api_clear_circuit(account: Optional[str] = None):  # GET intentionally: idempotent reset, no secrets
        if account:
            try:
                pool.reset_account(account)
            except KeyError as e:
                raise HTTPException(status_code=404, detail=str(e))
            return {"ok": True, "accounts": [account]}
        for a in pool.accounts:
            pool.reset_account(a.id)
        return {"ok": True, "accounts": [a.id for a in pool.accounts]}

    # -- auto try-on ---------------------------------------------------------------- #

    @app.post("/api/tryon/start")
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

    @app.get("/api/tryon/files/{run_id}/{filename:path}")
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

    @app.get("/api/tryon/runs")
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

    # -- AI Prompt Agent ------------------------------------------------------------ #

    @app.get("/api/agent/skills")
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
                    "policy_clause": s.policy_clause,
                }
                for s in mgr.list_skills()
            ]
        }

    @app.get("/api/agent/config")
    def api_get_agent_config():
        cfg = load_agent_config()
        return cfg.to_dict()

    @app.post("/api/agent/config")
    def api_set_agent_config(body: AgentConfigBody):
        cfg = LocalAgentConfig(
            preferred_agent=body.preferred_agent or "agy",
            agy_model=body.agy_model or "gemini-3.8-flash-low",
            pi_model=body.pi_model or "agnes-3.0-flash",
            timeout_s=body.timeout_s or 75.0,
        )
        save_agent_config(cfg)
        return {"ok": True, "config": cfg.to_dict()}

    @app.post("/api/agent/test")
    async def api_test_agent(body: Optional[TestAgentBody] = None):
        target = body.agent if body else None
        runner = get_agent_runner()
        res = await runner.test_agent(target)
        return res

    @app.post("/api/agent/generate-node-prompt")
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
        )
        try:
            res = await agent.generate_prompt_for_node(task)
            return {"ok": True, **res.to_dict()}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi AI Prompt Agent: {e}")

    # -- static UI ------------------------------------------------------------------ #

    dist = Path(web_dist) if web_dist else DEFAULT_WEB_DIST
    if dist.exists() and (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")
    else:
        @app.get("/")
        def no_ui():
            return JSONResponse({
                "ok": True,
                "note": "UI chưa build (web/dist trống). Chạy: cd web && npm install && npm run build",
                "api": ["/api/status", "/api/projects", "/api/generate", "/api/jobs", "/api/gallery"],
            })

    return app


# --------------------------------------------------------------------------- #
# CLI entry
# --------------------------------------------------------------------------- #


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="flow_bench", description="Flow Bench playground server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4000)
    ap.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    ap.add_argument("--out", default=None)
    ap.add_argument("--open", action="store_true", help="mở UI trong browser mặc định")
    args = ap.parse_args(argv)

    app = create_app(cdp_url=args.cdp_url, out_dir=Path(args.out) if args.out else None)
    url = f"http://{args.host}:{args.port}"
    print(f"Flow Bench: {url}  (CDP: {args.cdp_url})")
    if args.open:
        webbrowser.open(url)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
