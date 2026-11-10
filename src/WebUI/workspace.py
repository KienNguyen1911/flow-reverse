"""Workspace projects and project-scoped asset metadata for Flow Bench.

Two distinct project concepts coexist in the app:

* **Flow project** (``project_id`` on generation requests) — the Google Flow
  UUID that owns generated media server-side. Mapped per account inside this
  module (``get_flow_project`` / ``set_flow_project``); no separate registry.
* **Workspace project** (this module) — the local UI grouping of a canvas
  graph, its viewport and the assets uploaded/generated while it was active.

Everything is persisted as plain JSON next to ``out/`` so a restart keeps the
canvases and asset ownership.  No database is required.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Optional

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PROJECT_NAME = "Project Mặc định"
DEFAULT_VIEWPORT = {"x": 40.0, "y": 20.0, "zoom": 1.0}
MAX_CANVAS_BYTES = 12 * 1024 * 1024  # safety cap for one serialized canvas


def now_ms() -> int:
    return int(time.time() * 1000)


def empty_canvas_state() -> dict:
    return {
        "viewport": dict(DEFAULT_VIEWPORT),
        "nodes": [],
        "edges": [],
        "groups": [],
    }


def _as_float(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number or number in (float("inf"), float("-inf")):  # NaN / inf
        return fallback
    return number


def normalize_canvas_state(raw: Any) -> dict:
    """Return a JSON-safe canvas state with the documented shape.

    Nodes are intentionally kept as free-form dicts: the canvas owns their
    schema (prompt, seed, ratios, statuses, media URLs, ...) and evolves often.
    Only the containers are validated so a corrupt payload cannot poison the
    whole project file.
    """

    if not isinstance(raw, dict):
        return empty_canvas_state()

    viewport_raw = raw.get("viewport") if isinstance(raw.get("viewport"), dict) else {}
    viewport = {
        "x": _as_float(viewport_raw.get("x"), DEFAULT_VIEWPORT["x"]),
        "y": _as_float(viewport_raw.get("y"), DEFAULT_VIEWPORT["y"]),
        "zoom": _as_float(viewport_raw.get("zoom"), DEFAULT_VIEWPORT["zoom"]),
    }

    nodes = [n for n in raw.get("nodes", []) if isinstance(n, dict)]
    edges = [e for e in raw.get("edges", []) if isinstance(e, dict)]
    groups: list[dict] = []
    for group in raw.get("groups", []) or []:
        if not isinstance(group, dict):
            continue
        node_ids = group.get("nodeIds")
        groups.append(
            {
                **group,
                "nodeIds": [nid for nid in node_ids if isinstance(nid, str)]
                if isinstance(node_ids, list)
                else [],
            }
        )

    state = {
        "viewport": viewport,
        "nodes": nodes,
        "edges": edges,
        "groups": groups,
    }
    try:
        encoded = json.dumps(state, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"canvasState không serialize được: {exc}") from exc
    if len(encoded.encode("utf-8")) > MAX_CANVAS_BYTES:
        raise ValueError("canvasState quá lớn (giới hạn 12MB). Hãy giảm số node/ảnh nhúng.")
    return state


class WorkspaceProject(BaseModel):
    """One local workspace project (canvas + metadata)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str = ""
    thumbnail_url: Optional[str] = Field(default=None, alias="thumbnailUrl")
    created_at: int = Field(default_factory=now_ms, alias="createdAt")
    updated_at: int = Field(default_factory=now_ms, alias="updatedAt")
    canvas_state: dict = Field(default_factory=empty_canvas_state, alias="canvasState")
    thumbnail_manual: bool = Field(default=False, alias="thumbnailManual")
    flow_projects: dict[str, str] = Field(default_factory=dict, alias="flowProjects")


class WorkspaceStore:
    """JSON-backed registry of workspace projects (``out/flowbench_workspace.json``)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.projects: list[WorkspaceProject] = []
        # ``legacy_migrated`` blocks any later re-import of browser localStorage
        # canvas data, so a server-side wipe cannot be undone by a stale client.
        self.meta: dict = {"legacyMigrated": False}
        self._load()

    # -- persistence ------------------------------------------------------- #
    def _load(self) -> None:
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                loaded: list[WorkspaceProject] = []
                for item in raw.get("projects", []):
                    if not isinstance(item, dict) or not item.get("id"):
                        continue
                    project = WorkspaceProject(**item)
                    project.canvas_state = normalize_canvas_state(project.canvas_state)
                    loaded.append(project)
                self.projects = loaded
                if isinstance(raw.get("meta"), dict):
                    self.meta.update(raw["meta"])
        except Exception:  # noqa: BLE001 - a corrupt file must not kill startup
            self.projects = []

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "meta": dict(self.meta),
                "projects": [p.model_dump(by_alias=True) for p in self.projects],
            }
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:  # noqa: BLE001 - best effort, in-memory state stays valid
            pass

    # -- one-time browser migration ---------------------------------------- #
    @property
    def legacy_migrated(self) -> bool:
        with self._lock:
            return bool(self.meta.get("legacyMigrated"))

    def mark_legacy_migrated(self) -> None:
        with self._lock:
            if self.meta.get("legacyMigrated"):
                return
            self.meta["legacyMigrated"] = True
            self._save()

    # -- queries ----------------------------------------------------------- #
    def list(self) -> list[WorkspaceProject]:
        with self._lock:
            return sorted(self.projects, key=lambda p: (p.updated_at, p.created_at), reverse=True)

    def get(self, project_id: str) -> Optional[WorkspaceProject]:
        with self._lock:
            for project in self.projects:
                if project.id == project_id:
                    return project
            return None

    def count(self) -> int:
        with self._lock:
            return len(self.projects)

    def name_of(self, project_id: Optional[str]) -> Optional[str]:
        if not project_id:
            return None
        with self._lock:
            for project in self.projects:
                if project.id == project_id:
                    return project.name
            return None

    def get_flow_project(self, workspace_project_id: str, account_id: str) -> Optional[str]:
        if not workspace_project_id or not account_id:
            return None
        with self._lock:
            for project in self.projects:
                if project.id == workspace_project_id:
                    if getattr(project, "flow_projects", None) is None:
                        project.flow_projects = {}
                    return project.flow_projects.get(account_id)
            return None

    def set_flow_project(self, workspace_project_id: str, account_id: str, flow_project_id: str) -> None:
        if not workspace_project_id or not account_id or not flow_project_id:
            return
        with self._lock:
            for project in self.projects:
                if project.id == workspace_project_id:
                    if getattr(project, "flow_projects", None) is None:
                        project.flow_projects = {}
                    project.flow_projects[account_id] = flow_project_id
                    self._save()
                    return

    def remove_flow_project(self, workspace_project_id: str, account_id: str) -> bool:
        if not workspace_project_id or not account_id:
            return False
        with self._lock:
            for project in self.projects:
                if project.id == workspace_project_id:
                    if getattr(project, "flow_projects", None) is not None and account_id in project.flow_projects:
                        del project.flow_projects[account_id]
                        self._save()
                        return True
                    return False
            return False

    # -- mutations --------------------------------------------------------- #
    def create(
        self,
        name: str,
        description: str = "",
        canvas_state: Optional[dict] = None,
        thumbnail_url: Optional[str] = None,
        thumbnail_manual: bool = False,
    ) -> WorkspaceProject:
        state = normalize_canvas_state(canvas_state if canvas_state is not None else {})
        timestamp = now_ms()
        project = WorkspaceProject(
            id=f"prj_{uuid.uuid4().hex[:12]}",
            name=(name or DEFAULT_PROJECT_NAME).strip()[:120] or DEFAULT_PROJECT_NAME,
            description=(description or "")[:2000],
            thumbnail_url=thumbnail_url,
            thumbnail_manual=bool(thumbnail_manual and thumbnail_url),
            created_at=timestamp,
            updated_at=timestamp,
            canvas_state=state,
        )
        with self._lock:
            self.projects.append(project)
            self._save()
        return project

    def update(
        self,
        project_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        canvas_state: Optional[dict] = None,
        touch: bool = True,
    ) -> Optional[WorkspaceProject]:
        with self._lock:
            for project in self.projects:
                if project.id != project_id:
                    continue
                if name is not None:
                    project.name = name.strip()[:120] or project.name
                if description is not None:
                    project.description = description[:2000]
                if thumbnail_url is not None:
                    project.thumbnail_url = thumbnail_url or None
                if canvas_state is not None:
                    project.canvas_state = normalize_canvas_state(canvas_state)
                if touch:
                    project.updated_at = now_ms()
                self._save()
                return project
        return None

    def save_canvas(self, project_id: str, canvas_state: dict) -> Optional[WorkspaceProject]:
        return self.update(project_id, canvas_state=canvas_state)

    def set_thumbnail(
        self, project_id: str, url: Optional[str], manual: bool = True
    ) -> Optional[WorkspaceProject]:
        """Explicitly set (``manual=True``) or clear the project preview image.

        Unlike :meth:`update`, an empty value here really clears the thumbnail
        and re-enables the automatic "latest generated media" fallback.
        """
        with self._lock:
            for project in self.projects:
                if project.id != project_id:
                    continue
                cleaned = (url or "").strip() or None
                project.thumbnail_url = cleaned
                project.thumbnail_manual = bool(manual and cleaned)
                project.updated_at = now_ms()
                self._save()
                return project
        return None

    def delete(self, project_id: str) -> bool:
        with self._lock:
            before = len(self.projects)
            self.projects = [p for p in self.projects if p.id != project_id]
            if len(self.projects) == before:
                return False
            self._save()
            return True

    def duplicate(self, project_id: str, name: Optional[str] = None) -> Optional[WorkspaceProject]:
        source = self.get(project_id)
        if source is None:
            return None
        return self.create(
            name=name or f"{source.name} (Bản sao)",
            description=source.description,
            canvas_state=source.canvas_state,
            thumbnail_url=source.thumbnail_url,
            thumbnail_manual=source.thumbnail_manual,
        )

class AssetMetaStore:
    """Sidecar metadata for assets: owning workspace project + pinned flag.

    Keys are namespaced strings::

        upload:<filename>     files in out/uploads and out/references
        output:<run_id>       canvas node runs in out/nodes (+ try-on runs)
        gallery:<run_id>      legacy playground runs in out/playground

    Keeping metadata outside the media files means deleting the sidecar never
    deletes user media, and scanning stays cheap.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.assets: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                assets = raw.get("assets", {})
                if isinstance(assets, dict):
                    self.assets = {
                        str(key): value
                        for key, value in assets.items()
                        if isinstance(value, dict)
                    }
        except Exception:  # noqa: BLE001
            self.assets = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"version": 1, "assets": self.assets}
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:  # noqa: BLE001
            pass

    # -- reads ------------------------------------------------------------- #
    def get(self, key: str) -> dict:
        with self._lock:
            meta = self.assets.get(key)
            return dict(meta) if isinstance(meta, dict) else {}

    def project_of(self, key: str) -> Optional[str]:
        value = self.get(key).get("projectId")
        return value if isinstance(value, str) and value else None

    def is_pinned(self, key: str) -> bool:
        return bool(self.get(key).get("isPinned"))

    # -- writes ------------------------------------------------------------ #
    def _ensure(self, key: str, kind: str) -> dict:
        meta = self.assets.get(key)
        if not isinstance(meta, dict):
            meta = {}
            self.assets[key] = meta
        if kind and not meta.get("kind"):
            meta["kind"] = kind
        meta["updatedAt"] = now_ms()
        return meta

    def bind(self, key: str, project_id: Optional[str], kind: str) -> None:
        with self._lock:
            meta = self._ensure(key, kind)
            if project_id:
                meta["projectId"] = project_id
            else:
                meta.pop("projectId", None)
            self._save()

    def set_pin(self, key: str, pinned: bool, kind: str = "") -> bool:
        with self._lock:
            meta = self._ensure(key, kind)
            meta["isPinned"] = bool(pinned)
            self._save()
            return bool(meta["isPinned"])

    def remove(self, key: str) -> None:
        with self._lock:
            if key in self.assets:
                self.assets.pop(key, None)
                self._save()

    def clear_project(self, project_id: str) -> int:
        """Unbind every asset owned by a deleted project (files are kept)."""
        changed = 0
        with self._lock:
            for meta in self.assets.values():
                if isinstance(meta, dict) and meta.get("projectId") == project_id:
                    meta.pop("projectId", None)
                    meta["updatedAt"] = now_ms()
                    changed += 1
            if changed:
                self._save()
        return changed

    def claim_unassigned(self, entries: Iterable[tuple[str, str]], project_id: str) -> int:
        """Attach assets that have never been linked to a workspace project.

        Used for the one-time migration of pre-existing media into the default
        project.  Assets already owned by a project are never moved.
        """
        claimed = 0
        with self._lock:
            for key, kind in entries:
                if not key:
                    continue
                if self.project_of(key):
                    continue
                meta = self._ensure(key, kind)
                meta["projectId"] = project_id
                claimed += 1
            if claimed:
                self._save()
        return claimed


__all__ = [
    "DEFAULT_PROJECT_NAME",
    "DEFAULT_VIEWPORT",
    "MAX_CANVAS_BYTES",
    "WorkspaceProject",
    "WorkspaceStore",
    "AssetMetaStore",
    "empty_canvas_state",
    "normalize_canvas_state",
    "now_ms",
]
