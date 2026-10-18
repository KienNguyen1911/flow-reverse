"""Job manager for the Flow Bench playground.

One background worker thread runs jobs strictly sequentially (single browser
tab => no parallel generations). Bridge events stream into each job's event
list; the API polls job state (simple + robust, no SSE).

Job kinds:
  generate       ogiZ0b  (~1 credit if accepted; requires confirm at the API)
  dry_run        capture + build only, never fires (0 credit)
  create_project jHPbke  (0 credit; creates a REAL project in the account)
  list_projects  UpteDb  (0 credit read)
"""

from __future__ import annotations

import json
import queue
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..Bridge.flow_bridge import jitter
from ..Workflows.flow_client import CircuitOpenError, FlowClient
from ..Workflows.flow_models import ProjectInfo

TERMINAL_STATES = {"succeeded", "failed", "rejected"}


@dataclass
class JobEvent:
    ts_ms: int
    kind: str
    message: str
    data: dict = field(default_factory=dict)


class Job:
    def __init__(self, kind: str, params: dict):
        self.id = "j_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        self.kind = kind
        self.params = params
        self.state = "queued"          # queued | running | succeeded | failed | rejected
        self.events: list[JobEvent] = []
        self.result: Optional[dict] = None
        self.error: Optional[str] = None
        self.created_ms = int(time.time() * 1000)
        self.started_ms: Optional[int] = None
        self.finished_ms: Optional[int] = None
        self._lock = threading.Lock()

    def add_event(self, kind: str, message: str, data: Optional[dict] = None) -> None:
        with self._lock:
            self.events.append(JobEvent(ts_ms=int(time.time() * 1000), kind=kind, message=message, data=data or {}))
            if len(self.events) > 800:
                del self.events[:100]

    def set_state(self, state: str) -> None:
        with self._lock:
            self.state = state

    def to_dict(self, with_events: bool = True) -> dict:
        with self._lock:
            d = {
                "id": self.id,
                "kind": self.kind,
                "params": self.params,
                "state": self.state,
                "created_ms": self.created_ms,
                "started_ms": self.started_ms,
                "finished_ms": self.finished_ms,
                "result": self.result,
                "error": self.error,
                "event_count": len(self.events),
            }
            if with_events:
                d["events"] = [
                    {"i": i, "ts_ms": e.ts_ms, "kind": e.kind, "message": e.message, "data": e.data}
                    for i, e in enumerate(self.events)
                ]
            return d


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


class JobManager:
    def __init__(self, client: FlowClient, store: ProjectsStore):
        self.client = client
        self.store = store
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.RLock()
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._worker = threading.Thread(target=self._run_forever, name="flow-job-worker", daemon=True)
        self._worker.start()
        self._current_id: Optional[str] = None

    # -- API ---------------------------------------------------------------- #

    def submit(self, kind: str, params: dict) -> Job:
        job = Job(kind=kind, params=params)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            while len(self._order) > 80:
                old = self._order.pop(0)
                if old != self._current_id:
                    self._jobs.pop(old, None)
        self._queue.put(job.id)
        return job

    def get(self, jid: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(jid)

    def list(self, limit: int = 30) -> list[Job]:
        with self._lock:
            return [self._jobs[i] for i in reversed(self._order[-limit:]) if i in self._jobs]

    def queue_depth(self) -> int:
        return self._queue.qsize()

    def current_id(self) -> Optional[str]:
        return self._current_id

    # -- worker --------------------------------------------------------------- #

    def _run_forever(self) -> None:
        while True:
            jid = self._queue.get()
            job = self.get(jid)
            if job is None:
                continue
            self._current_id = jid
            job.started_ms = int(time.time() * 1000)
            job.set_state("running")
            try:
                self._dispatch(job)
            except CircuitOpenError as e:
                job.set_state("failed")
                job.error = str(e)
                job.add_event("error", f"circuit breaker đang mở: {e}")
            except Exception as e:  # noqa: BLE001
                job.set_state("failed")
                job.error = f"{type(e).__name__}: {e}"
                job.add_event("error", f"lỗi: {type(e).__name__}: {e}")
                job.add_event("debug", traceback.format_exc()[-900:])
            finally:
                job.finished_ms = int(time.time() * 1000)
                if job.state == "running":
                    job.set_state("failed")
                self._current_id = None
                if self.queue_depth() > 0:
                    time.sleep(jitter(6.0, 2.0, 2.0))

    def _dispatch(self, job: Job) -> None:
        kind = job.kind
        params = job.params
        ev = job.add_event

        if kind in ("generate", "dry_run"):
            res = self.client.generate_image(
                params["project_id"],
                params["prompt"],
                aspect=int(params.get("aspect") or 3),
                seed=params.get("seed"),
                dry_run=(kind == "dry_run"),
                on_event=ev,
            )
            res_dict = res.model_dump()
            if res.image and res.image.file_path:
                run_name = Path(res.run_dir or "").name
                fname = Path(res.image.file_path).name
                res_dict["image_url"] = f"/api/files/{run_name}/{fname}"
            job.result = res_dict
            if res.status in ("ok", "ok_no_download", "dry_run"):
                job.set_state("succeeded")
                if kind == "generate":
                    self.store.touch(params["project_id"])
            elif res.status == "rejected":
                job.set_state("rejected")
            else:
                job.set_state("failed")
            return

        if kind == "list_projects":
            projects = self.client.list_projects(on_event=ev)
            self.store.merge_listed(projects)
            job.result = {"count": len(projects), "projects": [p.model_dump() for p in projects]}
            job.set_state("succeeded")
            return

        if kind == "create_project":
            p = self.client.create_project(str(params.get("title") or ""), on_event=ev)
            self.store.upsert(p)
            job.result = p.model_dump()
            job.set_state("succeeded")
            return

        raise ValueError(f"unknown job kind: {kind}")
