"""JSON registry of Flow projects shown in the playground."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

from ...Workflows.flow_models import ProjectInfo


class ProjectsStore:
    """Small JSON registry of projects shown in the playground (out/playground_projects.json)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.projects: list[ProjectInfo] = []
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.projects = [ProjectInfo(**p) for p in raw.get("projects", []) if isinstance(p, dict) and p.get("id")]
        except Exception:  # noqa: BLE001
            self.projects = []

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"projects": [p.model_dump() for p in self.projects]}, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            pass

    def list(self) -> list[ProjectInfo]:
        with self._lock:
            return sorted(self.projects, key=lambda p: (p.last_used_ts or 0), reverse=True)

    def upsert(self, p: ProjectInfo) -> None:
        with self._lock:
            for i, old in enumerate(self.projects):
                if old.id == p.id:
                    merged = old.model_copy(update={
                        "title": p.title or old.title,
                        "source": p.source if p.source != "manual" else old.source,
                        "last_used_ts": max(p.last_used_ts or 0, old.last_used_ts or 0) or None,
                    })
                    self.projects[i] = merged
                    self._save()
                    return
            self.projects.append(p)
            self._save()

    def upsert_project(self, pid: str, title: Optional[str] = None) -> None:
        """Upsert by raw id (manual add from the UI)."""
        self.upsert(ProjectInfo(id=pid.lower(), title=(title or None), source="manual"))

    def merge_listed(self, listed: list[ProjectInfo]) -> None:
        with self._lock:
            ids = {p.id for p in self.projects}
            for p in listed:
                if p.id in ids:
                    self.upsert(p)
                else:
                    self.projects.append(p)
            self._save()

    def remove(self, pid: str) -> bool:
        with self._lock:
            before = len(self.projects)
            self.projects = [p for p in self.projects if p.id != pid]
            if len(self.projects) != before:
                self._save()
                return True
            return False

    def touch(self, pid: str) -> None:
        with self._lock:
            for p in self.projects:
                if p.id == pid:
                    p.last_used_ts = int(time.time() * 1000)
                    self._save()
                    return

    def title_of(self, pid: str) -> Optional[str]:
        with self._lock:
            for p in self.projects:
                if p.id == pid:
                    return p.title
        return None
