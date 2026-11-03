"""Job queue + dispatcher for the Flow Bench playground (N-account pool edition).

One dispatcher thread runs jobs; each job acquires account(s) from the
:class:`~src.Workflows.account_pool.AccountPoolManager`. The per-kind runners live
in sibling modules and are mixed into :class:`JobManager`:

  * :mod:`.runners_single`   generate / dry_run / list_projects / create_project
  * :mod:`.batch`            batch_generate (N_alloc accounts in parallel)
  * :mod:`.runners_node`     node_image / node_video / node_last_frame
  * :mod:`.runners_workflow` auto_tryon / delivery_build

Job kinds:
  generate        ogiZ0b  (~1 credit if accepted; requires confirm at the API)
  dry_run         capture + build only, never fires (0 credit)
  batch_generate  J items (t2i/i2i) across the allocated working set
  create_project  jHPbke  (0 credit; creates a REAL project in the account)
  list_projects   UpteDb  (0 credit read)
  node_image      one canvas image node (MediaService, optional i2i attachment)
  node_video      one canvas video node (MediaService, i2v or image→video chain)
"""

from __future__ import annotations

import queue
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

from ...Bridge.flow_bridge import jitter
from ...Workflows.account_pool import AccountPoolManager, ActiveAccount, PoolUnavailableError
from ...Workflows.flow_client import CircuitOpenError, FlowClient
from ...Workflows.node_retry import NodeExecutionError, RetryAborted
from .batch import BatchRunner
from .model import Job
from .projects_store import ProjectsStore
from .runners_node import NodeJobsMixin
from .runners_single import SingleJobsMixin
from .runners_workflow import WorkflowJobsMixin


class JobManager(SingleJobsMixin, NodeJobsMixin, WorkflowJobsMixin):
    def __init__(self, pool: AccountPoolManager, store: ProjectsStore, out_root: Path):
        self.pool = pool
        self.store = store
        self.out_root = Path(out_root)
        self.node_out = self.out_root.parent / "nodes"
        self.asset_meta = None  # injected by create_app (AssetMetaStore)
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.RLock()
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._worker = threading.Thread(target=self._run_forever, name="flow-job-worker", daemon=True)
        self._worker.start()
        self._current_id: Optional[str] = None
        self._account_projects: dict[str, str] = {}

    # -- workspace asset ownership ------------------------------------------- #

    def _bind_workspace_asset(self, job: Job, key: str, kind: str = "output") -> None:
        """Remember which workspace project produced *key* (best effort)."""
        workspace_id = job.params.get("workspace_project_id")
        store = getattr(self, "asset_meta", None)
        if not workspace_id or not key or store is None:
            return
        try:
            store.bind(key, str(workspace_id), kind)
        except Exception:  # noqa: BLE001 - metadata must never fail a job
            pass

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
            except PoolUnavailableError as e:
                job.set_state("failed")
                job.error = str(e)
                job.add_event("error", str(e))
            except NodeExecutionError as e:
                # Anti-abuse retries exhausted: this is the final EXECUTION_ERROR.
                job.set_state("failed")
                job.error = f"[{e.code}] {e}"
                job.add_event("error", f"[{e.code}] {e}", {
                    "code": e.code,
                    "attempts": e.attempts,
                    "reason": e.reason,
                })
            except RetryAborted as e:
                job.set_state("failed")
                job.error = str(e)
                job.add_event("warn", str(e), {"code": e.code, "cancelled": True})
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
        if kind in ("generate", "dry_run"):
            self._run_single(job, dry_run=(kind == "dry_run"))
            return
        if kind == "batch_generate":
            BatchRunner(self, job).run()
            return
        if kind == "list_projects":
            self._run_project_op(job)
            return
        if kind == "create_project":
            self._run_project_op(job)
            return
        if kind == "auto_tryon":
            self._run_auto_tryon(job)
            return
        if kind == "node_image":
            self._run_node_image(job)
            return
        if kind == "node_video":
            self._run_node_video(job)
            return
        if kind == "node_last_frame":
            self._run_node_last_frame(job)
            return
        if kind == "delivery_build":
            self._run_delivery_build(job)
            return
        raise ValueError(f"unknown job kind: {kind}")

    def _acquire_and_client(self, job: Job) -> tuple[ActiveAccount, FlowClient]:
        account = self.pool.acquire_single()
        job.add_event("info", f"account cấp phát: {account.config.id} ({account.cdp_url})")
        return account, self.pool.client_for(account.config.id)
