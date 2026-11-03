"""Flow Bench — FastAPI backend for the image-generation playground.

Run:  python -m src.WebUI.app  [--port 4000] [--cdp-url http://127.0.0.1:4022] [--open]

This module is the composition root: ``create_app`` builds the shared
:class:`~src.WebUI.context.AppContext`, registers the validation handler, includes
one router per feature area from ``src/WebUI/routes/`` and mounts the built UI.

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
never launches all profiles at startup (see src/Workflows/account_pool.py).
"""

from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ..Workflows.flow_client import DEFAULT_CDP_URL
from .context import build_context
from .routes import (
    agent,
    assets,
    deliveries,
    files,
    generate,
    jobs,
    node,
    pool,
    projects,
    tryon,
    workspace,
)
from .settings import DEFAULT_WEB_DIST

# Re-exported: tests/scripts import request bodies and path constants from here.
from .asset_scan import scan_gallery, scan_output_assets, scan_uploaded_assets  # noqa: F401
from .routes.agent import AgentConfigBody, GenerateNodePromptBody, TestAgentBody  # noqa: F401
from .routes.generate import BatchBody, BatchItemBody, GenerateBody  # noqa: F401
from .routes.node import NodeImageBody, NodeLastFrameBody, NodeVideoBody  # noqa: F401
from .routes.tryon import AutoTryOnBody  # noqa: F401
from .settings import DEFAULT_OUT, DEFAULT_PROJECTS_FILE, MAX_PROMPT_CHARS, ROOT  # noqa: F401


def create_app(cdp_url: str = DEFAULT_CDP_URL, out_dir: Optional[Path] = None,
               projects_file: Optional[Path] = None, web_dist: Optional[Path] = None,
               pool_config: Optional[Path] = None, pool_state: Optional[Path] = None,
               workspace_file: Optional[Path] = None,
               asset_meta_file: Optional[Path] = None,
               delivery_root: Optional[Path] = None) -> FastAPI:
    ctx = build_context(
        cdp_url=cdp_url,
        out_dir=out_dir,
        projects_file=projects_file,
        pool_config=pool_config,
        pool_state=pool_state,
        workspace_file=workspace_file,
        asset_meta_file=asset_meta_file,
        delivery_root=delivery_root,
    )

    app = FastAPI(title="Flow Bench", version="0.2.0")
    app.state.pool = ctx.pool
    app.state.manager = ctx.manager
    app.state.store = ctx.store
    app.state.out_root = ctx.out_root
    app.state.workspace = ctx.workspace
    app.state.asset_meta = ctx.asset_meta

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", []) if x != "body")
            msg = err.get("msg", "Lỗi tham số")
            errors.append(f"{loc}: {msg}" if loc else msg)
        msg_str = "; ".join(errors)
        return JSONResponse(status_code=422, content={"detail": f"Tham số không hợp lệ: {msg_str}"})

    app.include_router(pool.build_router(ctx))
    app.include_router(workspace.build_router(ctx))
    app.include_router(projects.build_router(ctx))
    app.include_router(generate.build_router(ctx))
    app.include_router(node.build_router(ctx))
    app.include_router(deliveries.build_router(ctx))
    app.include_router(jobs.build_router(ctx))
    app.include_router(files.build_router(ctx))
    app.include_router(assets.build_router(ctx))
    app.include_router(tryon.build_router(ctx))
    app.include_router(agent.build_router())

    # -- static UI ------------------------------------------------------------ #
    # Must stay last: the "/" mount is a catch-all.

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
    ap.add_argument(
        "--deliveries",
        default=None,
        help="thư mục chứa bộ nguyên liệu dựng phim (mặc định <out>/deliveries)",
    )
    ap.add_argument("--open", action="store_true", help="mở UI trong browser mặc định")
    args = ap.parse_args(argv)

    app = create_app(
        cdp_url=args.cdp_url,
        out_dir=Path(args.out) if args.out else None,
        delivery_root=Path(args.deliveries) if args.deliveries else None,
    )
    url = f"http://{args.host}:{args.port}"
    print(f"Flow Bench: {url}  (CDP: {args.cdp_url})")
    if args.open:
        webbrowser.open(url)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
