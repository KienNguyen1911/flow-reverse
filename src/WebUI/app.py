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
never launches all profiles at startup (see src/Workflows/account_pool.py).
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import webbrowser
import time
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from ..Workflows.account_pool import AccountPoolManager, proxy_label
from ..Workflows.flow_client import DEFAULT_CDP_URL
from ..Workflows.flow_models import parse_project_ref
from ..Workflows.limits import load_limits
from ..Workflows.local_agent_runner import (
    LocalAgentConfig,
    get_agent_runner,
    load_agent_config,
    save_agent_config,
)
from ..Workflows.delivery import (
    DEFAULT_DELIVERY_ROOT,
    DeliveryError,
    RunRef,
    build_delivery,
    list_deliveries,
)
from ..Workflows.media_probe import probe_video
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
from ..Workflows.flow_catalog import (
    VIDEO_SUB_MODES,
    CatalogError,
    capture_resolution,
    image_model_key,
    normalize_count,
    resolve_image_model,
    resolve_video_model,
    video_model_key,
)
from ..Workflows.prompt_agent import NodePromptTask, get_prompt_agent
from ..Workflows.script_contract import ScriptError, load_script
from ..Workflows.skill_manager import get_skill_manager
from .jobs import JobManager, ProjectsStore
from .workspace import (
    DEFAULT_PROJECT_NAME,
    AssetMetaStore,
    WorkspaceStore,
    empty_canvas_state,
    normalize_canvas_state,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "out" / "playground"
DEFAULT_PROJECTS_FILE = ROOT / "out" / "playground_projects.json"
DEFAULT_WEB_DIST = ROOT / "web" / "dist"

# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #

#: Độ dài prompt tối đa — resolve một lần lúc import từ ``Workflows/limits.py``
#: (env / configs/limits.json). Restart server sau khi đổi giá trị.
MAX_PROMPT_CHARS = load_limits().max_prompt_chars


class GenerateBody(BaseModel):
    project_id: str
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    aspect: int = 3
    seed: Optional[int] = None
    dry_run: bool = False
    remove_watermark: bool = True
    confirm: bool = False
    workspace_project_id: Optional[str] = None


class NodeImageBody(BaseModel):
    """One canvas image node: prompt + ratio + optional attached reference image(s)."""

    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    aspect_ratio: Optional[str] = None      # one of the 5 captured ratios (see /api/node/options)
    aspect: Optional[int] = None            # raw enum escape hatch (wins over aspect_ratio)
    seed: Optional[int] = None
    #: Composer model id or label (`nano_banana_pro` / `Nano Banana Pro`).
    #: See `src/Workflows/flow_catalog.py` — never guess a key.
    model: Optional[str] = None
    #: Batch size, mirroring the composer's x1..x4.
    count: int = 1
    #: When true the Flow composer is in "Tác nhân" (Agent) mode: it hides every
    #: model/aspect/count control, so user values are not applied.
    agent_mode: bool = False
    reference_image_path: Optional[str] = None   # path or /api/uploads|references|assets URL
    reference_image_paths: Optional[list[str]] = None
    project_id: Optional[str] = None
    workspace_project_id: Optional[str] = None
    #: Đánh dấu ảnh này là **ảnh sản phẩm** ⇒ chép vào `out/items/<project_id>/` sau khi
    #: sinh xong. Độc lập với kịch bản: người bán có nhiều món, dùng lại cho nhiều bộ phim.
    is_item: bool = False
    #: Tên món để đặt tên file trong thư viện (`Áo Kiểu Nữ Donna` → `ao_kieu_nu_donna.png`).
    item_name: Optional[str] = None
    dry_run: bool = False
    remove_watermark: bool = True
    confirm: bool = False


class NodeVideoBody(BaseModel):
    """One canvas video node: prompt + sub-mode + model + aspect/resolution/duration/count.

    Mirrors the Flow composer: sub-mode "Khung hình" (image→video, needs a frame) or
    "Thành phần" (text→video, no frame). Model choice decides whether resolution and
    duration are selectable at all (Veo fixes both).
    """

    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    aspect_ratio: str = "9:16"
    #: ``frames`` = Khung hình (image→video) | ``ingredients`` = Thành phần (text→video).
    sub_mode: str = "frames"
    #: Composer model id or label (`omni_1_1_flash` / `Omni 1.1 Flash`).
    model: Optional[str] = None
    #: Batch size, mirroring the composer's x1..x4.
    count: int = 1
    #: When true the Flow composer is in "Tác nhân" (Agent) mode: it hides every
    #: model/aspect/resolution/duration/count control, so user values are not applied.
    agent_mode: bool = False
    frame_path: Optional[str] = None        # attached image (path or /api/... URL)
    image_prompt: Optional[str] = None      # used only when auto_image generates the frame
    image_aspect_ratio: str = "16:9"        # frame image ratio
    auto_image: bool = True
    seed: Optional[int] = None
    resolution: str = "1080p"
    duration_s: int = 8
    project_id: Optional[str] = None
    workspace_project_id: Optional[str] = None
    dry_run: bool = False
    remove_watermark: bool = True
    confirm: bool = False


class NodeLastFrameBody(BaseModel):
    """Extract last frame of a video for chaining to next video/image node (0 credit)."""

    video_path: str
    remove_watermark: bool = True
    workspace_project_id: Optional[str] = None


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


class PinAssetBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = None
    key: Optional[str] = None
    kind: str = "upload"
    is_pinned: bool = Field(default=True, alias="isPinned")


class CreateProjectBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    confirm: bool = False


class AddProjectBody(BaseModel):
    ref: str
    title: Optional[str] = None


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
    #: Ngữ cảnh kịch bản — cho phép UI chỉ định clip/món đồ thay vì đoán.
    clip_id: Optional[str] = None
    clip_role: Optional[str] = None
    item_id: Optional[str] = None
    #: Node ảnh tick "đây là ảnh sản phẩm" ⇒ dùng skill cutout + tên món làm ngữ cảnh.
    is_item: bool = False
    item_name: Optional[str] = None
    #: Phạm vi tách món: `"top"` | `"bottom"` | `"full_set"`. Chỉ có nghĩa khi `is_item`.
    item_scope: Optional[str] = None
    script_path: Optional[str] = None


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


class TestAgentBody(BaseModel):
    agent: Optional[str] = None


class AddAccountBody(BaseModel):
    id: str
    profile_id: Optional[str] = None
    cdp_port: Optional[int] = None
    enabled: bool = True
    note: Optional[str] = None
    create_profile: bool = True
    proxy: Optional[str] = None          # "" / null ⇒ direct IP
    proxy_bypass: Optional[str] = None


class UpdateAccountBody(BaseModel):
    enabled: Optional[bool] = None
    note: Optional[str] = None
    cdp_port: Optional[int] = None
    proxy: Optional[str] = None
    proxy_bypass: Optional[str] = None
    clear_proxy: bool = False


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


def scan_gallery(out_root: Path, asset_meta: Optional[AssetMetaStore] = None) -> list[dict]:
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
        asset_key = f"gallery:{d.name}"
        am = asset_meta.get(asset_key) if asset_meta else {}
        runs.append({
            "run": d.name,
            "file": fp.name,
            "url": f"/api/files/{d.name}/{fp.name}",
            "prompt": meta.get("prompt"),
            "title": meta.get("title"),
            "project_id": meta.get("project_id"),
            "workspace_project_id": am.get("projectId"),
            "is_pinned": bool(am.get("isPinned")),
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




def scan_uploaded_assets(
    out_dir: Optional[Path] = None,
    asset_meta: Optional[AssetMetaStore] = None,
) -> list[dict]:
    items: list[dict] = []
    root_out = (out_dir.parent if out_dir else (ROOT / "out"))
    for folder_name, api_prefix in [("uploads", "/api/uploads"), ("references", "/api/references")]:
        d = root_out / folder_name
        if not d.exists():
            continue
        for f in d.iterdir():
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".webm"}:
                continue
            cat = "video" if ext in {".mp4", ".mov", ".webm"} else "image"
            stat = f.stat()
            ts = stat.st_mtime
            m = re.match(r"^(\d{12,14})_", f.name)
            if m:
                try:
                    ts = int(m.group(1)) / 1000.0
                except Exception:
                    pass
            asset_key = f"upload:{f.name}"
            am = asset_meta.get(asset_key) if asset_meta else {}
            items.append({
                "id": f.name,
                "key": asset_key,
                "name": f.name,
                "url": f"{api_prefix}/{f.name}",
                "category": cat,
                "created_ts": ts,
                "size_bytes": stat.st_size,
                "projectId": am.get("projectId"),
                "isPinned": bool(am.get("isPinned")),
            })
    items.sort(key=lambda x: x["created_ts"], reverse=True)
    return items


def scan_output_assets(
    out_root: Path,
    node_out: Optional[Path] = None,
    asset_meta: Optional[AssetMetaStore] = None,
) -> list[dict]:
    items: list[dict] = []
    seen_urls: set[str] = set()

    def meta_for(key: str) -> dict:
        return asset_meta.get(key) if asset_meta else {}

    def add_project_fields(item: dict, key: str) -> dict:
        am = meta_for(key)
        item["key"] = key
        item["projectId"] = am.get("projectId")
        item["isPinned"] = bool(am.get("isPinned"))
        return item

    # 1. Canvas nodes outputs (out/nodes)
    n_dir = node_out if node_out and node_out.exists() else (out_root.parent / "nodes" if out_root.name == "playground" else out_root / "nodes")
    if n_dir.exists():
        for d in n_dir.iterdir():
            if not d.is_dir() or d.name.startswith("_"):
                continue
            # Videos in node
            for v in d.glob("*.mp4"):
                manifest_file = d / "manifest.json"
                meta = {}
                if manifest_file.exists():
                    try:
                        meta = json.loads(manifest_file.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                thumb = d / "starting_frame.jpg"
                thumb_url = f"/api/node/files/{d.name}/{thumb.name}" if thumb.exists() else None
                url = f"/api/node/files/{d.name}/{v.name}"
                seen_urls.add(url)
                # Manifest cũ chỉ có `duration_s` = tham số yêu cầu (8). Ưu tiên số đo
                # thật; nếu manifest chưa có (bản cũ) thì đo ngay tại đây.
                measured = None
                if meta.get("measured_duration_s") is None or meta.get("measured_fps") is None:
                    measured = probe_video(v)
                m_dur = meta.get("measured_duration_s")
                if m_dur is None and measured is not None:
                    m_dur = measured.duration_s
                m_fps = meta.get("measured_fps")
                if m_fps is None and measured is not None:
                    m_fps = measured.fps
                m_w = meta.get("measured_width") or (measured.width if measured else None)
                m_h = meta.get("measured_height") or (measured.height if measured else None)
                items.append(add_project_fields({
                    "id": f"node_{d.name}_{v.name}",
                    "run_id": d.name,
                    "name": v.name,
                    "category": "video",
                    "url": url,
                    "thumbnail_url": thumb_url,
                    "prompt": meta.get("prompt") or "",
                    "created_ts": meta.get("created_ts") or v.stat().st_mtime,
                    "duration_s": m_dur or meta.get("duration_s") or 8,
                    "fps": m_fps,
                    "width": m_w,
                    "height": m_h,
                    "has_audio": meta.get("has_audio"),
                    "resolution": (
                        f"{m_w}x{m_h}" if m_w and m_h
                        else meta.get("resolution") or "1080p"
                    ),
                    "aspect_ratio": meta.get("aspect_ratio") or "9:16",
                    "size_bytes": v.stat().st_size,
                    "source": "canvas_video_node",
                }, f"output:{d.name}"))
            # Images in node
            for img in d.glob("*.*"):
                if img.suffix.lower() in {".jpg", ".png", ".jpeg", ".webp"} and img.name != "starting_frame.jpg":
                    meta_file = d / "meta.json"
                    meta = {}
                    if meta_file.exists():
                        try:
                            meta = json.loads(meta_file.read_text(encoding="utf-8"))
                        except Exception:
                            pass
                    url = f"/api/node/files/{d.name}/{img.name}"
                    seen_urls.add(url)
                    items.append(add_project_fields({
                        "id": f"node_{d.name}_{img.name}",
                        "run_id": d.name,
                        "name": img.name,
                        "category": "image",
                        "url": url,
                        "thumbnail_url": url,
                        "prompt": meta.get("prompt") or "",
                        "created_ts": meta.get("created_ts") or img.stat().st_mtime,
                        "seed": meta.get("seed") or meta.get("seed_echo"),
                        "resolution": meta.get("resolution"),
                        "aspect_ratio": str(meta.get("aspect", "")),
                        "size_bytes": img.stat().st_size,
                        "source": "canvas_image_node",
                    }, f"output:{d.name}"))

    # 2. Affiliate / Try-on runs (out/affiliate_runs)
    aff_dir = (out_root.parent / "affiliate_runs" if out_root.name == "playground" else out_root / "affiliate_runs")
    if aff_dir.exists():
        for d in aff_dir.iterdir():
            if not d.is_dir() or d.name.startswith("_"):
                continue
            manifest_file = d / "manifest.json"
            meta = {}
            if manifest_file.exists():
                try:
                    meta = json.loads(manifest_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            for v in d.glob("*.mp4"):
                if v.stat().st_size < 10000:
                    continue
                thumb = d / "first_frame.jpg"
                if not thumb.exists():
                    thumb = d / "model.jpg"
                thumb_url = f"/api/tryon/files/{d.name}/{thumb.name}" if thumb.exists() else None
                url = f"/api/tryon/files/{d.name}/{v.name}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                items.append(add_project_fields({
                    "id": f"tryon_{d.name}_{v.name}",
                    "run_id": d.name,
                    "name": f"{d.name} - {v.name}",
                    "category": "video",
                    "url": url,
                    "thumbnail_url": thumb_url,
                    "prompt": meta.get("image_prompt") or meta.get("video_prompt_1") or "",
                    "created_ts": meta.get("created_ts") or v.stat().st_mtime,
                    "duration_s": 16 if "16s" in v.name else 8,
                    "resolution": "1080p",
                    "size_bytes": v.stat().st_size,
                    "source": "tryon",
                }, f"output:{d.name}"))

    # 3. Top-level runs (Playground / scan_gallery)
    gallery_runs = scan_gallery(out_root, asset_meta)
    for run in gallery_runs:
        url = run.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        items.append(add_project_fields({
            "id": f"gallery_{run.get('run')}_{run.get('file')}",
            "run_id": run.get("run"),
            "name": run.get("file") or run.get("run"),
            "category": "image",
            "url": url,
            "thumbnail_url": url,
            "prompt": run.get("prompt") or run.get("title") or "",
            "created_ts": run.get("created_ts") or 0,
            "seed": run.get("seed_echo") or run.get("seed"),
            "resolution": run.get("resolution"),
            "size_bytes": run.get("file_bytes"),
            "source": "playground",
        }, f"gallery:{run.get('run')}"))

    def get_sort_key(it):
        t = it.get("created_ts")
        if isinstance(t, (int, float)):
            return float(t)
        if isinstance(t, str):
            try:
                return datetime.datetime.fromisoformat(t).timestamp()
            except Exception:
                pass
        return 0.0

    items.sort(key=get_sort_key, reverse=True)
    return items


# --------------------------------------------------------------------------- #
# Workspace asset helpers
# --------------------------------------------------------------------------- #


def _asset_sort_ts(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value).timestamp()
        except Exception:
            pass
    return 0.0


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


def _migration_asset_entries(
    out_dir: Optional[Path],
    out_root: Path,
    node_out: Path,
    asset_meta: AssetMetaStore,
) -> list[tuple[str, str]]:
    """Every asset key discovered on disk (deduplicated) for one-time claiming."""
    entries: dict[str, str] = {}
    for item in scan_uploaded_assets(out_dir, asset_meta):
        key = item.get("key")
        if key:
            entries[key] = "upload"
    for item in scan_output_assets(out_root, node_out=node_out, asset_meta=asset_meta):
        key = item.get("key")
        if key:
            entries[key] = "output"
    for run in scan_gallery(out_root, asset_meta):
        entries[f"gallery:{run['run']}"] = "gallery"
    return list(entries.items())



def create_app(cdp_url: str = DEFAULT_CDP_URL, out_dir: Optional[Path] = None,
               projects_file: Optional[Path] = None, web_dist: Optional[Path] = None,
               pool_config: Optional[Path] = None, pool_state: Optional[Path] = None,
               workspace_file: Optional[Path] = None,
               asset_meta_file: Optional[Path] = None,
               delivery_root: Optional[Path] = None) -> FastAPI:
    out_root = Path(out_dir) if out_dir else DEFAULT_OUT
    asset_root = out_root.parent if out_dir else (ROOT / "out")
    store = ProjectsStore(Path(projects_file) if projects_file else DEFAULT_PROJECTS_FILE)
    workspace = WorkspaceStore(
        Path(workspace_file) if workspace_file else (out_root.parent / "flowbench_workspace.json")
    )
    asset_meta = AssetMetaStore(
        Path(asset_meta_file) if asset_meta_file else (out_root.parent / "flowbench_asset_meta.json")
    )
    pool = AccountPoolManager(
        config_path=Path(pool_config) if pool_config else None,
        state_path=Path(pool_state) if pool_state else None,
        out_root=out_root,
        default_cdp_url=cdp_url,
    )
    manager = JobManager(pool=pool, store=store, out_root=out_root)
    manager.asset_meta = asset_meta

    # One-time migration: with no workspace project, create the default one and
    # claim every pre-existing asset so no upload/output is lost.
    if workspace.count() == 0:
        default_project = workspace.create(DEFAULT_PROJECT_NAME)
        asset_meta.claim_unassigned(
            _migration_asset_entries(out_dir, out_root, manager.node_out, asset_meta),
            default_project.id,
        )
    else:
        # An existing store means the one-time browser import already happened;
        # never re-import stale client canvas data over server-side truth.
        workspace.mark_legacy_migrated()

    app = FastAPI(title="Flow Bench", version="0.2.0")
    app.state.pool = pool
    app.state.manager = manager
    app.state.store = store
    app.state.out_root = out_root
    app.state.workspace = workspace
    app.state.asset_meta = asset_meta

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
                proxy=body.proxy,
                proxy_bypass=body.proxy_bypass,
            )
            return {
                "ok": True,
                "account": {
                    "id": acc.id,
                    "profile_id": acc.profile_id,
                    "cdp_port": acc.cdp_port,
                    "enabled": acc.enabled,
                    "note": acc.note,
                    "proxy": proxy_label(acc.proxy),
                    "has_proxy": bool(acc.proxy),
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
                proxy=body.proxy,
                proxy_bypass=body.proxy_bypass,
                clear_proxy=body.clear_proxy,
            )
            return {
                "ok": True,
                "account": {
                    "id": acc.id,
                    "profile_id": acc.profile_id,
                    "cdp_port": acc.cdp_port,
                    "enabled": acc.enabled,
                    "note": acc.note,
                    "proxy": proxy_label(acc.proxy),
                    "has_proxy": bool(acc.proxy),
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

    # -- workspace projects (local canvas groups, not Flow UUIDs) -------------- #

    @app.get("/api/workspace/projects")
    def api_workspace_projects():
        uploads = scan_uploaded_assets(out_dir, asset_meta)
        outputs = scan_output_assets(out_root, node_out=manager.node_out, asset_meta=asset_meta)
        return {
            "projects": _workspace_projects_payload(workspace, uploads, outputs),
            "legacyMigrated": workspace.legacy_migrated,
        }

    @app.get("/api/workspace/projects/{pid}")
    def api_workspace_project(pid: str):
        project = workspace.get(pid)
        if project is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy project")
        return {"project": project.model_dump(by_alias=True)}

    @app.post("/api/workspace/projects")
    def api_workspace_create(body: CreateWorkspaceProjectBody):
        canvas = normalize_canvas_state(
            body.canvas_state.model_dump() if body.canvas_state is not None else None
        )
        project = workspace.create(body.name, body.description, canvas)
        return {"ok": True, "project": project.model_dump(by_alias=True)}

    @app.patch("/api/workspace/projects/{pid}")
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

    @app.put("/api/workspace/projects/{pid}/canvas")
    @app.post("/api/workspace/projects/{pid}/canvas")
    def api_workspace_save_canvas(pid: str, body: WorkspaceCanvasBody):
        if workspace.get(pid) is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy project")
        project = workspace.save_canvas(pid, normalize_canvas_state(body.model_dump()))
        return {
            "ok": True,
            "projectId": pid,
            "updatedAt": project.updated_at if project else None,
        }

    @app.delete("/api/workspace/projects/{pid}")
    def api_workspace_delete(pid: str):
        if workspace.get(pid) is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy project")
        if workspace.count() <= 1:
            raise HTTPException(status_code=400, detail="Không thể xóa project cuối cùng.")
        workspace.delete(pid)
        asset_meta.clear_project(pid)
        return {"ok": True, "removed": pid}

    @app.post("/api/workspace/projects/{pid}/duplicate")
    def api_workspace_duplicate(pid: str, body: Optional[DuplicateWorkspaceProjectBody] = None):
        project = workspace.duplicate(pid, body.name if body else None)
        if project is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy project")
        return {"ok": True, "project": project.model_dump(by_alias=True)}

    @app.put("/api/workspace/projects/{pid}/thumbnail")
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

    @app.post("/api/workspace/migrate")
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
            _migration_asset_entries(out_dir, out_root, manager.node_out, asset_meta),
            target.id,
        )
        return {
            "ok": True,
            "created": created,
            "canvasImported": allow_canvas,
            "claimed": claimed,
            "project": target.model_dump(by_alias=True),
        }

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
            "workspace_project_id": body.workspace_project_id,
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
            "workspace_project_id": body.workspace_project_id,
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
            model_info = resolve_image_model(body.model)
            count = normalize_count(body.count)
        except (AspectNotVerifiedError, UnsupportedOptionError, CatalogError, ValueError) as e:
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
            "model": model_info.id,
            "count": count,
            "agent_mode": body.agent_mode,
            "reference_image_path": all_refs[0] if all_refs else None,
            "reference_image_paths": all_refs if all_refs else None,
            "project_id": body.project_id,
            "workspace_project_id": body.workspace_project_id,
            "is_item": body.is_item,
            "item_name": body.item_name,
            "dry_run": body.dry_run,
            "remove_watermark": body.remove_watermark,
        })
        return {
            "job_id": job.id, "kind": "image", "aspect_ratio": ratio, "aspect": enum,
            "model": model_info.id, "model_label": model_info.label,
            "model_key": image_model_key(model_info), "count": count,
        }

    @app.post("/api/node/video")
    def api_node_video(body: NodeVideoBody):
        try:
            ratio = normalize_video_ratio(body.aspect_ratio)
            model_info = resolve_video_model(body.model)
            resolution = normalize_video_resolution(body.resolution, model=model_info.id)
            duration = validate_video_duration(body.duration_s, model=model_info.id)
            sub_mode = str(body.sub_mode or "frames").strip().lower()
            if sub_mode not in VIDEO_SUB_MODES:
                raise UnsupportedOptionError(
                    f"Sub-mode video {body.sub_mode!r} không hợp lệ. Chọn: {', '.join(VIDEO_SUB_MODES)}."
                )
            count = normalize_count(body.count)
            model_key = video_model_key(
                model_info, sub_mode=sub_mode, duration_s=duration,
                resolution=capture_resolution(model_info, resolution), aspect_ratio=ratio,
            )
            image_ratio, _image_enum = resolve_image_aspect(body.image_aspect_ratio)
        except (AspectNotVerifiedError, UnsupportedOptionError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        if sub_mode == "frames" and not body.frame_path and not body.auto_image:
            raise HTTPException(
                status_code=400,
                detail="Sub-mode 'Khung hình' (image→video) cần ảnh đính kèm (frame_path) hoặc "
                       "bật auto_image=true để tạo ảnh khung hình trước. Dùng sub_mode='ingredients' "
                       "nếu chỉ muốn text→video từ câu lệnh.",
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
            "model": model_info.id,
            "sub_mode": sub_mode,
            "count": count,
            "agent_mode": body.agent_mode,
            "project_id": body.project_id,
            "workspace_project_id": body.workspace_project_id,
            "dry_run": body.dry_run,
            "remove_watermark": body.remove_watermark,
        })
        frame_source = (
            "none" if sub_mode == "ingredients"
            else ("provided" if body.frame_path else "generated")
        )
        return {
            "job_id": job.id, "kind": "video", "aspect_ratio": ratio,
            "resolution": resolution, "duration_s": duration,
            "model": model_info.id, "model_label": model_info.label,
            "model_key": model_key, "sub_mode": sub_mode, "count": count,
            "frame_source": frame_source,
        }

    @app.post("/api/node/last_frame")
    def api_node_last_frame(body: NodeLastFrameBody):
        resolved = resolve_input_path(body.video_path)
        if not resolved.is_file():
            raise HTTPException(status_code=400, detail=f"Không tìm thấy file video: {body.video_path}")
        job = manager.submit("node_last_frame", {
            "video_path": str(resolved),
            "remove_watermark": body.remove_watermark,
            "workspace_project_id": body.workspace_project_id,
        })
        return {"job_id": job.id, "kind": "last_frame"}

    @app.get("/api/node/files/{file_path:path}")
    def api_node_file(file_path: str):
        base = manager.node_out.resolve()
        p = (base / file_path).resolve()
        if not p.is_relative_to(base) or not p.is_file():
            raise HTTPException(status_code=404, detail="không tìm thấy file node")
        return FileResponse(p)

    # -- deliveries (bộ nguyên liệu dựng phim cho HyperFrames desktop) ------------ #

    def _delivery_root() -> Path:
        return Path(delivery_root) if delivery_root else DEFAULT_DELIVERY_ROOT

    @app.get("/api/items/library")
    def api_item_library(project_id: Optional[str] = None):
        """Thư viện ảnh sản phẩm của một project: `out/items/<project_id>/`.

        Không phụ thuộc kịch bản — mỗi lần node ảnh có cờ `is_item` sinh xong, file được
        chép vào đây theo tên món. Người bán xem lại toàn bộ món đã có, dùng cho nhiều bộ.
        """
        from ..Workflows.item_library import item_dir, list_items

        return {
            "project_id": project_id,
            "dir": str(item_dir(project_id)),
            "items": list_items(project_id),
        }

    @app.post("/api/deliveries")
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

    @app.get("/api/deliveries")
    def api_list_deliveries():
        return {"deliveries": list_deliveries(_delivery_root())}

    @app.get("/api/deliveries/{slug}/{file_path:path}")
    def api_delivery_file(slug: str, file_path: str):
        base = (_delivery_root() / slug).resolve()
        p = (base / file_path).resolve()
        if not p.is_relative_to(base) or not p.is_file():
            raise HTTPException(status_code=404, detail="không tìm thấy file trong bộ dựng phim")
        return FileResponse(p)

    @app.get("/api/deliveries/{slug}")
    def api_delivery_detail(slug: str):
        manifest = _delivery_root() / slug / "delivery.json"
        if not manifest.is_file():
            raise HTTPException(status_code=404, detail="không tìm thấy bộ dựng phim")
        try:
            return json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise HTTPException(status_code=500, detail=f"delivery.json hỏng: {exc}")

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

    @app.post("/api/jobs/{jid}/cancel")
    def api_cancel_job(jid: str):
        """Stop a running job; interruptible waits (retry backoff) abort at once."""
        job = manager.get(jid)
        if job is None:
            raise HTTPException(status_code=404, detail="job không tồn tại")
        if job.state in ("succeeded", "failed", "rejected"):
            return {"ok": True, "state": job.state, "note": "job đã kết thúc"}
        job.cancel()
        return {"ok": True, "state": job.state, "cancelled": True}

    # -- gallery ----------------------------------------------------------------- #

    @app.get("/api/gallery")
    def api_gallery():
        return {"runs": scan_gallery(out_root, asset_meta)}

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

    @app.get("/api/references/{name}")
    def api_get_reference(name: str):
        ref_file = asset_root / "references" / name
        if not ref_file.is_file():
            raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")
        return FileResponse(ref_file)

    @app.post("/api/upload")
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

    @app.get("/api/uploads/{name:path}")
    def api_get_upload(name: str):
        upload_dir = asset_root / "uploads"
        base = upload_dir.resolve()
        p = (base / name).resolve()
        if not p.is_relative_to(base) or not p.is_file():
            raise HTTPException(status_code=404, detail="Không tìm thấy file upload")
        return FileResponse(p)

    # -- asset drawer ------------------------------------------------------------- #

    @app.get("/api/assets/uploaded")
    def api_get_uploaded_assets(
        project_id: Optional[str] = None,
        scope: str = "all",
    ):
        items = scan_uploaded_assets(out_dir, asset_meta)
        items = _filter_assets(_enrich_assets(items, workspace), project_id, scope)
        return {"items": items}

    @app.delete("/api/assets/uploaded/{name:path}")
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

    @app.post("/api/assets/pin")
    def api_pin_asset(body: PinAssetBody):
        key = (body.key or "").strip()
        if not key and body.id:
            key = f"{body.kind}:{body.id}"
        if not key:
            raise HTTPException(status_code=400, detail="Cần 'key' hoặc 'id'.")
        pinned = asset_meta.set_pin(key, body.is_pinned, kind=body.kind or "upload")
        return {"ok": True, "key": key, "isPinned": pinned}

    @app.get("/api/assets/output")
    def api_get_output_assets(
        project_id: Optional[str] = None,
        scope: str = "all",
    ):
        items = scan_output_assets(out_root, node_out=manager.node_out, asset_meta=asset_meta)
        items = _filter_assets(_enrich_assets(items, workspace), project_id, scope)
        return {"items": items}

    @app.get("/api/assets/outputs")
    def api_get_outputs_assets_alias(
        project_id: Optional[str] = None,
        scope: str = "all",
    ):
        items = scan_output_assets(out_root, node_out=manager.node_out, asset_meta=asset_meta)
        items = _filter_assets(_enrich_assets(items, workspace), project_id, scope)
        return {"items": items}


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
            clip_id=body.clip_id,
            clip_role=body.clip_role,
            item_id=body.item_id,
            is_item=body.is_item,
            item_name=body.item_name,
            item_scope=body.item_scope,
            script_path=body.script_path,
        )
        try:
            res = await agent.generate_prompt_for_node(task)
            # Lint không chặn — trả về để UI hiện cảnh báo trước khi tốn credit.
            try:
                from ..Workflows.prompt_lint import lint_prompt as _lint
                lint = _lint(res.prompt, body.node_type).to_dict()
            except Exception:  # noqa: BLE001 - lint hỏng không được chặn việc sinh prompt
                lint = None
            return {"ok": True, **res.to_dict(), "lint": lint}
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
