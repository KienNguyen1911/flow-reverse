"""Flow Bench — FastAPI backend for the image-generation playground.

Run:  python -m src.WebUI.app  [--port 8787] [--cdp-url http://127.0.0.1:9222] [--open]

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
import webbrowser
import time
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..Workflows.account_pool import AccountPoolManager
from ..Workflows.flow_client import DEFAULT_CDP_URL
from ..Workflows.flow_models import parse_project_ref
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
    prompt: str = Field(min_length=1, max_length=2000)
    aspect: int = 3
    seed: Optional[int] = None
    dry_run: bool = False
    confirm: bool = False


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
    confirm: bool = False
    dest_dir: Optional[str] = None


class PoolConfigBody(BaseModel):
    target_jobs_per_account: Optional[int] = None
    max_active_browsers: Optional[int] = None


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
            "dest_dir": body.dest_dir,
        })
        return {"job_id": job.id}

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
    ap.add_argument("--port", type=int, default=8787)
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
