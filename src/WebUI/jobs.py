"""Job manager for the Flow Bench playground (N-account pool edition).

One dispatcher thread runs jobs; each job acquires account(s) from the
:class:`~src.Workflows.account_pool.AccountPoolManager`:

  * single jobs  → 1 account (wear-leveled, browser woken on demand);
  * ``batch_generate`` → N_alloc accounts in parallel (plan §1.1), one worker
    thread per account, hot-spare auto-promotion on 429/401/403/cooldown, and
    NLE-ready output copying (plan Phần 3).

Job kinds:
  generate        ogiZ0b  (~1 credit if accepted; requires confirm at the API)
  dry_run         capture + build only, never fires (0 credit)
  batch_generate  J items (t2i/i2i) across the allocated working set
  create_project  jHPbke  (0 credit; creates a REAL project in the account)
  list_projects   UpteDb  (0 credit read)

Batch item format (``params["items"]``, or a storyboard JSON via
``params["storyboard_path"]`` — see ``configs/storyboard_100.json``):

  {"prompt": "...", "seed": 123?, "mode": "t2i"|"i2i"?,
   "reference_image_path": "out/...png"?, "depends_on_shot_id": "..."?,
   "id": "scene_001_shot_001"?, "filename": "scene_001_shot_001_i2i.png"?}
"""

from __future__ import annotations

import json
import queue
import re
import shutil
import threading
import time
import traceback
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..Bridge.flow_bridge import jitter
from ..Workflows.account_pool import (
    AccountPoolManager,
    ActiveAccount,
    PoolUnavailableError,
    sha256_file,
)
from ..Workflows.flow_client import CircuitOpenError, FlowClient
from ..Workflows.flow_models import ProjectInfo, ReferenceTemplate, parse_project_ref

ROOT = Path(__file__).resolve().parents[2]
TERMINAL_STATES = {"succeeded", "failed", "rejected"}
MAX_BATCH_ITEMS = 300


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

    def title_of(self, pid: str) -> Optional[str]:
        with self._lock:
            for p in self.projects:
                if p.id == pid:
                    return p.title
        return None


# --------------------------------------------------------------------------- #
# Batch plumbing
# --------------------------------------------------------------------------- #


@dataclass
class BatchItem:
    idx: int
    prompt: str
    mode: str = "t2i"                     # t2i | i2i
    seed: Optional[int] = None
    reference_image_path: Optional[str] = None
    depends_on_shot_id: Optional[str] = None
    shot_id: Optional[str] = None
    filename: Optional[str] = None
    status: str = "pending"               # pending | running | ok | dry_run | rejected | failed | skipped
    account_id: Optional[str] = None
    attempts: int = 0
    result: Optional[dict] = None
    error: Optional[str] = None
    output_path: Optional[str] = None
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "idx": self.idx,
            "shot_id": self.shot_id,
            "prompt": self.prompt,
            "mode": self.mode,
            "status": self.status,
            "account_id": self.account_id,
            "attempts": self.attempts,
            "error": self.error,
            "output_path": self.output_path,
            "result": self.result,
        }


def plan_dependency_waves(items: list[BatchItem]) -> list[list[BatchItem]]:
    """Topological waves from ``depends_on_shot_id`` (plan Phần 2/3).

    Items whose dependency is unknown are marked ``skipped``. Cycles are
    detected defensively and also skipped.
    """
    by_shot: dict[str, BatchItem] = {}
    for it in items:
        if it.shot_id:
            by_shot[it.shot_id] = it

    pending: list[BatchItem] = []
    for it in items:
        if it.depends_on_shot_id and it.depends_on_shot_id not in by_shot:
            it.status = "skipped"
            it.error = f"không thấy shot phụ thuộc {it.depends_on_shot_id!r}"
        else:
            pending.append(it)

    placed_shots: set[str] = set()
    waves: list[list[BatchItem]] = []
    guard = 0
    while pending and guard < 60:
        guard += 1
        wave: list[BatchItem] = []
        rest: list[BatchItem] = []
        for it in pending:
            if not it.depends_on_shot_id or it.depends_on_shot_id in placed_shots:
                wave.append(it)
            else:
                dep = by_shot.get(it.depends_on_shot_id)
                if dep is not None and dep.status == "skipped":
                    it.status = "skipped"
                    it.error = f"shot phụ thuộc {it.depends_on_shot_id!r} không chạy được"
                else:
                    rest.append(it)
        if not wave:
            for it in rest:
                it.status = "skipped"
                it.error = "phụ thuộc vòng — không giải được thứ tự chạy"
            break
        waves.append(wave)
        for it in wave:
            if it.shot_id:
                placed_shots.add(it.shot_id)
        pending = rest
    return waves


def prepare_batch_items(params: dict) -> list[BatchItem]:
    """Validate + normalize ``params["items"]`` or a storyboard JSON file."""
    raw = params.get("items") or []
    sb_path = params.get("storyboard_path")
    if sb_path:
        p = Path(str(sb_path))
        if not p.is_absolute():
            p = ROOT / p
        data = json.loads(p.read_text(encoding="utf-8"))
        raw = data.get("shots") if isinstance(data, dict) else data
    if not isinstance(raw, list) or not raw:
        raise ValueError("Batch rỗng: cần 'items' hoặc 'storyboard_path' có ít nhất 1 shot.")

    items: list[BatchItem] = []
    for i, r in enumerate(raw):
        if not isinstance(r, dict):
            raise ValueError(f"item #{i + 1}: phải là object JSON")
        prompt = str(r.get("prompt") or "").strip()
        if not prompt:
            raise ValueError(f"item #{i + 1}: prompt rỗng")
        ref = r.get("reference_image_path") or None
        dep = r.get("depends_on_shot_id") or None
        mode = str(r.get("mode") or "").strip().lower()
        if mode not in ("t2i", "i2i"):
            mode = "i2i" if (ref or dep) else "t2i"
        if mode == "i2i" and not (ref or dep):
            raise ValueError(f"item #{i + 1}: mode i2i nhưng thiếu reference_image_path/depends_on_shot_id")
        seed = r.get("seed")
        items.append(BatchItem(
            idx=i,
            prompt=prompt,
            mode=mode,
            seed=int(seed) if seed not in (None, "") else None,
            reference_image_path=str(ref) if ref else None,
            depends_on_shot_id=str(dep) if dep else None,
            shot_id=(str(r.get("id")) if r.get("id") else None),
            filename=(str(r.get("filename")) if r.get("filename") else None),
            raw={"reference_image_path": str(ref) if ref else None},
        ))
    return items


class BatchRunner:
    """Executes one batch job across the allocated working set."""

    def __init__(self, manager: "JobManager", job: Job):
        self.manager = manager
        self.pool = manager.pool
        self.job = job
        self.params = job.params
        raw_pid = self.params.get("project_id")
        self.project_id = parse_project_ref(str(raw_pid)) if raw_pid else None
        self.dry_run = bool(self.params.get("dry_run"))
        self.aspect = int(self.params.get("aspect") or 3)
        self.item_pause_mean = float(self.params.get("item_pause_s") or 4.0)
        self.items: list[BatchItem] = []
        self.by_shot: dict[str, BatchItem] = {}
        self.working: list[ActiveAccount] = []
        self.cooked: dict[str, threading.Event] = {}
        self.n_alloc = 0
        self._progress_lock = threading.Lock()
        self._dest_dir: Optional[Path] = None

    # -- item preparation ------------------------------------------------------ #

    def _prepare_items(self) -> list[BatchItem]:
        return prepare_batch_items(self.params)

    # -- output naming (plan Phần 3, NLE-ready) -------------------------------- #

    @staticmethod
    def _slug(text: str, max_len: int = 40) -> str:
        s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
        return s[:max_len].strip("_") or "project"

    def _resolve_dest_dir(self) -> Path:
        if self._dest_dir is not None:
            return self._dest_dir
        explicit = self.params.get("dest_dir")
        if explicit:
            p = Path(str(explicit))
            self._dest_dir = p if p.is_absolute() else ROOT / p
        else:
            if self.project_id:
                title = self.manager.store.title_of(self.project_id) or self.project_id[:8]
                self._dest_dir = ROOT / "out" / "outputs" / self._slug(title)
            else:
                self._dest_dir = ROOT / "out" / "outputs" / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return self._dest_dir

    def _export_output(self, it: BatchItem, src_file: str) -> Optional[str]:
        try:
            src = Path(src_file)
            if not src.is_file():
                return None
            dest_dir = self._resolve_dest_dir()
            dest_dir.mkdir(parents=True, exist_ok=True)
            ext = src.suffix or ".jpg"
            base = re.sub(r"[^A-Za-z0-9._-]+", "_", it.filename or f"shot_{it.idx + 1:03d}_{it.mode}")
            if not Path(base).suffix:
                base += ext
            dst = dest_dir / base
            n = 2
            while dst.exists():
                dst = dest_dir / f"{Path(base).stem}_{n}{Path(base).suffix}"
                n += 1
            shutil.copy2(src, dst)
            return str(dst)
        except Exception as exc:  # noqa: BLE001
            self.job.add_event("warn", f"không copy được output shot #{it.idx + 1}: {exc}")
            return None

    # -- progress -------------------------------------------------------------- #

    def _counts(self) -> Counter:
        return Counter(it.status for it in self.items)

    def _snapshot(self, status: str) -> dict:
        c = self._counts()
        return {
            "batch": True,
            "status": status,
            "total": len(self.items),
            "ok": c.get("ok", 0),
            "dry_run": c.get("dry_run", 0),
            "rejected": c.get("rejected", 0),
            "failed": c.get("failed", 0),
            "skipped": c.get("skipped", 0),
            "pending": c.get("pending", 0) + c.get("running", 0),
            "n_alloc": self.n_alloc,
            "accounts": [a.config.id for a in self.working],
            "output_dir": str(self._resolve_dest_dir()),
            "items": [it.to_dict() for it in self.items],
        }

    def _touch_progress(self, status: str = "running") -> None:
        with self._progress_lock:
            self.job.result = self._snapshot(status)

    # -- item execution --------------------------------------------------------- #

    def _ev_for(self, account_id: str):
        def ev(kind: str, message: str, data: Optional[dict] = None) -> None:
            self.job.add_event(kind, f"[{account_id}] {message}", {**(data or {}), "account_id": account_id})
        return ev

    def _resolve_reference_path(self, it: BatchItem) -> str:
        if it.reference_image_path:
            p = Path(it.reference_image_path)
            if not p.is_absolute():
                p = ROOT / p
            if not p.is_file():
                raise ValueError(f"không thấy ảnh tham chiếu: {p}")
            return str(p)
        if it.depends_on_shot_id:
            dep = self.by_shot.get(it.depends_on_shot_id)
            if dep is not None:
                if dep.output_path and Path(dep.output_path).is_file():
                    return dep.output_path
                if self.dry_run and dep.reference_image_path:
                    return dep.reference_image_path
            raise ValueError(f"shot phụ thuộc {it.depends_on_shot_id!r} chưa có output")
        raise ValueError("i2i thiếu reference_image_path/depends_on_shot_id")

    def _project_for_account(self, aid: str, client: FlowClient) -> str:
        with self._progress_lock:
            if not hasattr(self, "_account_projects"):
                self._account_projects: dict[str, str] = {}
            if aid in self._account_projects:
                return self._account_projects[aid]

            if self.project_id:
                self._account_projects[aid] = self.project_id
                return self.project_id

            # Auto-resolve or create project for this account
            self.job.add_event("step", f"[{aid}] tự động dò tìm dự án trên account...", {"account_id": aid})
            try:
                listed = client.list_projects()
                if listed:
                    pid = listed[0].id
                    self.job.add_event("info", f"[{aid}] dùng dự án có sẵn: {listed[0].title or pid[:8]} ({pid[:8]}…)", {"account_id": aid})
                    self._account_projects[aid] = pid
                    return pid
            except Exception as e:
                self.job.add_event("warn", f"[{aid}] list_projects ({e}) — tạo dự án mới...", {"account_id": aid})

            title = f"Batch {datetime.now().strftime('%d/%m %H:%M')}"
            try:
                proj = client.create_project(title)
                self.job.add_event("info", f"[{aid}] tự động tạo dự án mới: '{title}' ({proj.id[:8]}…)", {"account_id": aid})
                self._account_projects[aid] = proj.id
                return proj.id
            except Exception as exc:
                self.job.add_event("error", f"[{aid}] không tạo được dự án tự động: {exc}", {"account_id": aid})
                raise

    def _generate_for_item(self, it: BatchItem, acct: ActiveAccount, client: FlowClient):
        ev = self._ev_for(acct.config.id)
        target_pid = self._project_for_account(acct.config.id, client)
        if it.mode == "i2i":
            ref_path = self._resolve_reference_path(it)
            sha = sha256_file(ref_path)
            cached = self.pool.registry.get(acct.config.id, sha)
            if cached is None:
                self.job.add_event("step",
                    f"[{acct.config.id}] lazy upload ảnh tham chiếu lần đầu ({Path(ref_path).name}) — 0 credit",
                    {"account_id": acct.config.id, "sha256": sha})
                tpl = client.upload_reference_image(target_pid, ref_path, prompt_probe=it.prompt, on_event=ev)
                self.pool.registry.put(acct.config.id, tpl.model_dump())
            else:
                tpl = ReferenceTemplate(**cached)
                self.job.add_event("info",
                    f"[{acct.config.id}] trúng cache tham chiếu sha {sha[:8]}… (media≈{tpl.media_id}) — không upload lại",
                    {"account_id": acct.config.id, "sha256": sha})
            return client.generate_image(
                target_pid, it.prompt,
                aspect=self.aspect, seed=it.seed, dry_run=self.dry_run,
                reference=tpl, on_event=ev,
            )
        return client.generate_image(
            target_pid, it.prompt,
            aspect=self.aspect, seed=it.seed, dry_run=self.dry_run,
            on_event=ev,
        )

    def _apply_result(self, it: BatchItem, acct: ActiveAccount, res) -> None:
        d = res.model_dump()
        if res.status in ("ok", "ok_no_download"):
            it.status = "ok"
            if res.image and res.image.file_path:
                run_name = Path(res.run_dir or "").name
                d["image_url"] = f"/api/files/{run_name}/{Path(res.image.file_path).name}"
                it.output_path = self._export_output(it, res.image.file_path)
        elif res.status == "dry_run":
            it.status = "dry_run"
        elif res.status == "rejected":
            it.status = "rejected"
        else:
            it.status = "failed"
            it.error = res.reason or res.hint or "failed"
        it.account_id = acct.config.id
        it.result = d

    def _requeue(self, it: BatchItem, reason: str, q: "queue.Queue[BatchItem]") -> None:
        it.attempts += 1
        if it.attempts < 2:
            it.status = "pending"
            q.put(it)
            self.job.add_event("retry",
                f"[{it.account_id}] shot #{it.idx + 1} sẽ chạy lại trên account khác ({reason[:160]})",
                {"idx": it.idx, "account_id": it.account_id})
        else:
            it.status = "failed"
            it.error = reason[:400]
            self.job.add_event("error", f"shot #{it.idx + 1} thất bại sau 2 lần thử: {reason[:200]}", {"idx": it.idx})

    def _exec_item(self, it: BatchItem, acct: ActiveAccount, client: FlowClient,
                   q: "queue.Queue[BatchItem]", cooked: threading.Event) -> None:
        aid = acct.config.id
        it.status = "running"
        it.account_id = aid
        self._touch_progress()
        try:
            res = self._generate_for_item(it, acct, client)
        except CircuitOpenError as exc:
            self._requeue(it, f"breaker account {aid}: {exc}", q)
            cooked.set()
            self.pool.report_item_result(aid, "failed", error=str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
            self.job.add_event("warn", f"[{aid}] lỗi shot #{it.idx + 1}: {err[:240]}", {"idx": it.idx, "account_id": aid})
            self._requeue(it, err, q)
            self.pool.report_item_result(aid, "failed", error=err)
            if self.pool.cooldown_remaining_s(aid) > 0:
                self.job.add_event("warn", f"[{aid}] vào cooldown — rút khỏi working set (hot-spare nếu có)", {"account_id": aid})
                cooked.set()
            return

        self.pool.report_item_result(aid, res.status,
                                     error=None if res.status in ("ok", "ok_no_download", "dry_run") else (res.reason or res.hint))
        self._apply_result(it, acct, res)
        # A rejection may have just tripped the breaker (3rd anti-abuse in a row).
        if res.status != "ok" and self.pool.cooldown_remaining_s(aid) > 0:
            self.job.add_event("warn", f"[{aid}] vào cooldown sau kết quả '{res.status}' — rút khỏi working set", {"account_id": aid})
            cooked.set()
        self._touch_progress()

    # -- wave execution ----------------------------------------------------------- #

    def _spawn(self, acct: ActiveAccount, q: "queue.Queue[BatchItem]"):
        cooked = self.cooked[acct.config.id]

        def worker() -> None:
            client = self.pool.client_for(acct.config.id)
            while not cooked.is_set():
                try:
                    it = q.get_nowait()
                except queue.Empty:
                    return
                self._exec_item(it, acct, client, q, cooked)
                if cooked.is_set():
                    return
                time.sleep(max(0.5, jitter(self.item_pause_mean, 1.2)))

        t = threading.Thread(target=worker, name=f"flow-batch-{acct.config.id}", daemon=True)
        t.start()
        return t

    def _run_wave(self, wave: list[BatchItem]) -> None:
        q: "queue.Queue[BatchItem]" = queue.Queue()
        for it in wave:
            q.put(it)

        for a in self.working:
            self.cooked.setdefault(a.config.id, threading.Event())

        threads = [self._spawn(a, q) for a in self.working if not self.cooked[a.config.id].is_set()]

        guard = 0
        while True:
            guard += 1
            if guard > 40:
                self.job.add_event("error", "batch: vượt vòng lặp điều phối — dừng an toàn")
                while not q.empty():
                    it = q.get_nowait()
                    it.status = "failed"
                    it.error = "wave bị dừng"
                return
            for t in threads:
                t.join()
            if q.empty():
                return
            live = [a for a in self.working if not self.cooked[a.config.id].is_set()]
            if live:
                threads = [self._spawn(a, q) for a in live]
                continue
            promoted = self.pool.promote_standby(exclude=[a.config.id for a in self.working])
            if promoted is None:
                self.job.add_event("error", f"hết account dự phòng — {q.qsize()} ảnh trong wave không chạy được")
                while not q.empty():
                    it = q.get_nowait()
                    if it.status in ("pending", "running"):
                        it.status = "failed"
                        it.error = "hết account khả dụng (cooldown toàn bộ / disabled)"
                return
            self.job.add_event("warn",
                f"hot-spare: đưa {promoted.config.id} vào thay thế — còn {q.qsize()} ảnh trong wave",
                {"account_id": promoted.config.id})
            self.working.append(promoted)
            self.cooked[promoted.config.id] = threading.Event()
            threads = [self._spawn(promoted, q)]

    # -- main -------------------------------------------------------------------- #

    def run(self) -> None:
        ev = self.job.add_event
        self.items = self._prepare_items()
        J = len(self.items)
        if J > MAX_BATCH_ITEMS:
            raise ValueError(f"batch quá lớn: {J} > {MAX_BATCH_ITEMS} (chia thành nhiều batch)")

        modes = Counter(it.mode for it in self.items)
        p_tag = (self.project_id[:8] + "…") if self.project_id else "auto-per-account"
        ev("info", f"BATCH: J={J} ảnh (t2i: {modes.get('t2i', 0)}, i2i: {modes.get('i2i', 0)}), project: {p_tag}")

        n_avail = len(self.pool.available_accounts())
        self.n_alloc = self.pool.compute_allocation(J)
        if self.n_alloc <= 0:
            raise PoolUnavailableError("Không có account khả dụng (cooldown/disabled toàn bộ).")
        affinity = self.pool.affinity_shas_for_items([it.raw for it in self.items])
        selected = self.pool.select_working_set(self.n_alloc, affinity_shas=affinity)
        self.working, errors = self.pool.ensure_working_set(selected)
        for e in errors:
            ev("warn", f"account {e['account_id']} không wake được: {e['error'][:220]}")
        self.n_alloc = len(self.working)
        for a in self.working:
            self.cooked[a.config.id] = threading.Event()
        self.pool.set_current_batch(self.job.id, J, self.n_alloc, [a.config.id for a in self.working])
        ev("info",
           f"N_alloc = min(N={len(self.pool.accounts)}, M_RAM={self.pool.max_active_browsers}, "
           f"ceil(J/Q={self.pool.target_jobs_per_account})) = {self.n_alloc} → active: "
           + ", ".join(a.config.id for a in self.working),
           {"n_alloc": self.n_alloc, "accounts": [a.config.id for a in self.working]})
        self._touch_progress()

        try:
            waves = plan_dependency_waves(self.items)
            for it in self.items:
                if it.status == "skipped":
                    ev("warn", f"bỏ qua shot {it.shot_id or ('#' + str(it.idx + 1))}: {it.error}")
            for w, wave in enumerate(waves):
                live: list[BatchItem] = []
                for it in wave:
                    dep = self.by_shot.get(it.depends_on_shot_id or "")
                    if dep is not None and dep.status != "ok":
                        it.status = "skipped"
                        it.error = f"shot phụ thuộc {it.depends_on_shot_id!r} không thành công ({dep.status})"
                        ev("warn", f"bỏ qua shot {it.shot_id or it.idx}: {it.error}")
                    else:
                        live.append(it)
                if not live:
                    continue
                active_workers = [a for a in self.working if not self.cooked.get(a.config.id, threading.Event()).is_set()]
                ev("step", f"wave {w + 1}/{len(waves)}: {len(live)} ảnh trên {len(active_workers)} account")
                self._run_wave(live)
                self._touch_progress()
        finally:
            self.pool.end_batch()

        snap = self._snapshot("done")
        ok = snap["ok"] + snap["dry_run"]
        failed = snap["failed"] + snap["skipped"]
        if ok > 0 and failed == 0:
            final = "ok"
        elif ok > 0:
            final = "partial"
        elif snap["rejected"] > 0 and failed == 0:
            final = "rejected"
        else:
            final = "failed"
        snap["status"] = final
        self.job.result = snap

        if final == "ok":
            self.job.set_state("succeeded")
        elif final == "partial":
            self.job.set_state("failed")
            self.job.error = f"{failed} ảnh không hoàn tất — xem chi tiết trong items"
        elif final == "rejected":
            self.job.set_state("rejected")
        else:
            self.job.set_state("failed")
            self.job.error = "toàn bộ ảnh thất bại — xem nhật ký/items"
        if snap["ok"] > 0 and not self.dry_run:
            self.manager.store.touch(self.project_id)
        ev("done" if final in ("ok", "rejected") else "error",
           f"BATCH kết thúc: {snap['ok']} ok / {snap['dry_run']} dry / {snap['rejected']} bị từ chối / "
           f"{snap['failed']} lỗi / {snap['skipped']} bỏ qua (tổng {snap['total']}) → {self._resolve_dest_dir()}")


# --------------------------------------------------------------------------- #
# JobManager
# --------------------------------------------------------------------------- #


class JobManager:
    def __init__(self, pool: AccountPoolManager, store: ProjectsStore, out_root: Path):
        self.pool = pool
        self.store = store
        self.out_root = Path(out_root)
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
            except PoolUnavailableError as e:
                job.set_state("failed")
                job.error = str(e)
                job.add_event("error", str(e))
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
        raise ValueError(f"unknown job kind: {kind}")

    # -- single-account jobs ---------------------------------------------------- #

    def _acquire_and_client(self, job: Job) -> tuple[ActiveAccount, FlowClient]:
        account = self.pool.acquire_single()
        job.add_event("info", f"account cấp phát: {account.config.id} ({account.cdp_url})")
        return account, self.pool.client_for(account.config.id)

    def _run_single(self, job: Job, dry_run: bool) -> None:
        params = job.params
        ev = job.add_event
        account, client = self._acquire_and_client(job)
        aid = account.config.id
        try:
            res = client.generate_image(
                params["project_id"],
                params["prompt"],
                aspect=int(params.get("aspect") or 3),
                seed=params.get("seed"),
                dry_run=dry_run,
                on_event=ev,
            )
        except Exception as exc:
            self.pool.report_item_result(aid, "failed", error=f"{type(exc).__name__}: {exc}")
            raise
        self.pool.report_item_result(
            aid, res.status,
            error=None if res.status in ("ok", "ok_no_download", "dry_run") else (res.reason or res.hint),
        )
        res_dict = res.model_dump()
        if res.image and res.image.file_path:
            run_name = Path(res.run_dir or "").name
            fname = Path(res.image.file_path).name
            res_dict["image_url"] = f"/api/files/{run_name}/{fname}"
        res_dict["account_id"] = aid
        job.result = res_dict
        if res.status in ("ok", "ok_no_download", "dry_run"):
            job.set_state("succeeded")
            if not dry_run:
                self.store.touch(params["project_id"])
        elif res.status == "rejected":
            job.set_state("rejected")
        else:
            job.set_state("failed")

    def _run_project_op(self, job: Job) -> None:
        params = job.params
        ev = job.add_event
        account, client = self._acquire_and_client(job)
        try:
            if job.kind == "list_projects":
                projects = client.list_projects(on_event=ev)
                self.store.merge_listed(projects)
                job.result = {"count": len(projects), "projects": [p.model_dump() for p in projects]}
                job.set_state("succeeded")
                return
            p = client.create_project(str(params.get("title") or ""), on_event=ev)
            self.store.upsert(p)
            job.result = p.model_dump()
            job.set_state("succeeded")
        except Exception as exc:
            self.pool.report_item_result(account.config.id, "failed", error=f"{type(exc).__name__}: {exc}")
            raise
