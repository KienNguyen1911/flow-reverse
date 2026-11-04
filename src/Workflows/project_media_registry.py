"""Persistent cache for reference images uploaded to Google Flow projects.

Thread-safe registry mapping `(account_id, project_id, file_sha256)` to
`{media_id, alias_name, sha256, uploaded_at_ms}` stored in
`configs/project_media_cache.json`.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CACHE_FILE = ROOT / "configs" / "project_media_cache.json"


def compute_alias_name(idx: int, sha256: str) -> str:
    """Compute semantic alias name for a reference image by index and SHA256 prefix.

    - Index 0: model_{sha256[:6]}
    - Index 1: garment_{sha256[:6]}
    - Index 2: scene_{sha256[:6]}
    - Index >= 3: ref{idx+1}_{sha256[:6]}
    """
    prefix_map = {
        0: "model",
        1: "garment",
        2: "scene",
    }
    prefix = prefix_map.get(idx, f"ref{idx + 1}")
    clean_hash = (sha256 or "").lower()[:6]
    return f"{prefix}_{clean_hash}"


class ProjectMediaRegistry:
    """Thread-safe persistent registry of uploaded reference images per project."""

    def __init__(self, path: Optional[Path | str] = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_CACHE_FILE
        self._lock = threading.RLock()
        self._entries: dict[str, dict[str, Any]] = {}
        self._load()

    @classmethod
    def _make_key(cls, account_id: str, project_id: str, sha256: str) -> str:
        aid = (account_id or "").strip().lower()
        pid = (project_id or "").strip().lower()
        sha = (sha256 or "").strip().lower()
        return f"{aid}:{pid}:{sha}"

    def _load(self) -> None:
        with self._lock:
            if not self.path.is_file():
                self._entries = {}
                return
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and "entries" in raw and isinstance(raw["entries"], dict):
                    self._entries = raw["entries"]
                elif isinstance(raw, dict):
                    self._entries = raw
                else:
                    self._entries = {}
            except Exception as exc:
                logger.warning("Không đọc được project_media_cache.json (%s), khởi tạo rỗng: %s", self.path, exc)
                self._entries = {}

    def _save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "entries": self._entries,
            }
            tmp = self.path.with_suffix(".tmp")
            try:
                tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                tmp.replace(self.path)
            except Exception as exc:
                logger.error("Ghi project_media_cache.json thất bại: %s", exc)
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass

    def get(self, account_id: str, project_id: str, sha256: str) -> Optional[dict[str, Any]]:
        """Lookup an uploaded image record by account, project and sha256."""
        if not account_id or not project_id or not sha256:
            return None
        k = self._make_key(account_id, project_id, sha256)
        with self._lock:
            val = self._entries.get(k)
            return dict(val) if isinstance(val, dict) else None

    def put(
        self,
        account_id: str,
        project_id: str,
        sha256: str,
        media_id: str,
        alias_name: str,
    ) -> dict[str, Any]:
        """Store or update an uploaded image record."""
        k = self._make_key(account_id, project_id, sha256)
        entry = {
            "account_id": str(account_id).strip(),
            "project_id": str(project_id).strip(),
            "sha256": str(sha256).strip().lower(),
            "media_id": str(media_id).strip(),
            "alias_name": str(alias_name).strip(),
            "uploaded_at_ms": int(time.time() * 1000),
        }
        with self._lock:
            self._entries[k] = entry
            self._save()
        return dict(entry)

    def remove(self, account_id: str, project_id: str, sha256: str) -> Optional[dict[str, Any]]:
        """Remove a single record (e.g. when discovered stale on cloud)."""
        k = self._make_key(account_id, project_id, sha256)
        with self._lock:
            removed = self._entries.pop(k, None)
            if removed is not None:
                self._save()
            return dict(removed) if isinstance(removed, dict) else None

    def clear_project(self, account_id: str, project_id: str) -> int:
        """Clear all entries belonging to a project (e.g. upon 404 recovery)."""
        aid = (account_id or "").strip().lower()
        pid = (project_id or "").strip().lower()
        if not aid or not pid:
            return 0
        target_prefix = f"{aid}:{pid}:"
        with self._lock:
            to_del = [k for k in self._entries if k.startswith(target_prefix)]
            for k in to_del:
                self._entries.pop(k, None)
            if to_del:
                self._save()
            return len(to_del)

    def count_for_project(self, account_id: str, project_id: str) -> int:
        """Count cached items for a given project."""
        aid = (account_id or "").strip().lower()
        pid = (project_id or "").strip().lower()
        target_prefix = f"{aid}:{pid}:"
        with self._lock:
            return sum(1 for k in self._entries if k.startswith(target_prefix))


_GLOBAL_REGISTRY: Optional[ProjectMediaRegistry] = None
_GLOBAL_LOCK = threading.Lock()


def get_project_media_registry(path: Optional[Path | str] = None) -> ProjectMediaRegistry:
    """Return the application singleton ProjectMediaRegistry."""
    global _GLOBAL_REGISTRY
    with _GLOBAL_LOCK:
        if _GLOBAL_REGISTRY is None or path is not None:
            _GLOBAL_REGISTRY = ProjectMediaRegistry(path)
        return _GLOBAL_REGISTRY
