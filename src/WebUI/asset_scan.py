"""Disk scanners behind the gallery and asset-drawer endpoints.

Pure functions over ``out/`` (playground runs, node outputs, try-on runs, uploads):
they return plain dicts shaped for the UI and never touch the network.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Optional

from ..Workflows.media_probe import probe_video
from .settings import ROOT
from .workspace import AssetMetaStore


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


def migration_asset_entries(
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
