"""Single-account Flow jobs: ``generate`` / ``dry_run`` and project list/create."""

from __future__ import annotations

from pathlib import Path

from ..settings import ROOT
from .model import Job


class SingleJobsMixin:
    """Mixed into :class:`~src.WebUI.jobs.manager.JobManager`; uses its pool/store/helpers."""

    def _run_single(self, job: Job, dry_run: bool) -> None:
        params = job.params
        ev = job.add_event
        account, client = self._acquire_and_client(job)
        aid = account.config.id
        target_pid = params.get("project_id")
        cached_pid = self._account_projects.get(aid)
        if cached_pid:
            target_pid = cached_pid
        elif not target_pid or aid not in self._account_projects:
            try:
                listed = client.list_projects()
                if listed:
                    pids = {p.id for p in listed}
                    if target_pid and target_pid in pids:
                        self._account_projects[aid] = target_pid
                    else:
                        target_pid = listed[0].id
                        self._account_projects[aid] = target_pid
                        ev("info", f"[{aid}] tự động dùng dự án của account: {listed[0].title or target_pid[:8]} ({target_pid[:8]}…)")
                else:
                    p = client.create_project("Automated Pipeline", on_event=ev)
                    target_pid = p.id
                    self._account_projects[aid] = target_pid
                    ev("info", f"[{aid}] tự động tạo dự án mới: {p.title} ({target_pid[:8]}…)")
            except Exception as e:
                ev("warn", f"[{aid}] không dò được dự án trên account: {e}")

        ref_paths_raw = params.get("reference_image_paths") or []
        ref_path = params.get("reference_image_path")
        resolved_files: list[Path] = []
        if ref_paths_raw and isinstance(ref_paths_raw, list):
            for rp in ref_paths_raw:
                if rp:
                    rf = resolve_input_path(rp)
                    if rf.is_file() and rf not in resolved_files:
                        resolved_files.append(rf)
        if ref_path:
            rf = resolve_input_path(ref_path)
            if not rf.is_file():
                p = Path(ref_path)
                candidate_paths = [
                    p,
                    ROOT / p,
                    ROOT / "out" / "references" / p.name,
                    ROOT / "out" / "uploads" / p.name,
                ]
                for cand in candidate_paths:
                    if cand.is_file():
                        rf = cand.resolve()
                        break
            if rf.is_file() and rf not in resolved_files:
                resolved_files.insert(0, rf)

        try:
            res = client.generate_image(
                target_pid,
                params["prompt"],
                aspect=int(params.get("aspect") or 3),
                aspect_ratio=params.get("aspect_ratio"),
                seed=params.get("seed"),
                dry_run=dry_run,
                remove_watermark=bool(params.get("remove_watermark", True)),
                reference_path=resolved_files[0] if resolved_files else None,
                reference_paths=resolved_files if resolved_files else None,
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
            if res.run_dir:
                self._bind_workspace_asset(job, f"gallery:{Path(res.run_dir).name}", kind="gallery")
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
