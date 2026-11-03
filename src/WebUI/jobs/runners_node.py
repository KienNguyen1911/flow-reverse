"""Canvas node jobs: ``node_image``, ``node_video``, ``node_last_frame`` (via MediaService)."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from ...Workflows.account_pool import ActiveAccount
from ...Workflows.media_service import MediaService
from ...Workflows.node_retry import RetryAborted, run_with_retry
from .model import Job


class NodeJobsMixin:
    """Mixed into :class:`~src.WebUI.jobs.manager.JobManager`; uses its pool/node_out/helpers."""

    def _save_project_item(self, job: Job, file_path: str, result: dict) -> None:
        """Chép ảnh vừa sinh vào `out/items/<project_id>/` theo tên người dùng đặt.

        Best-effort: thư viện hỏng không được biến một job đã thành công thành thất bại.
        Đường dẫn file thư viện được ghi thêm vào `result["item_file"]` để UI hiện ra.
        """
        from ...Workflows.item_library import save_item

        try:
            saved = save_item(
                file_path,
                project_id=job.params.get("workspace_project_id"),
                name=job.params.get("item_name") or job.params.get("node_id"),
            )
        except Exception:  # noqa: BLE001 - never fail a succeeded job
            saved = None
        if saved is not None:
            result["item_file"] = str(saved)
            result["item_name"] = saved.stem

    # -- node media (canvas) ------------------------------------------------------ #

    def _node_service(self, account: ActiveAccount, job: Job) -> MediaService:
        aid = account.config.id
        return MediaService(
            cdp_url=account.cdp_url,
            out_dir=self.node_out,
            account_id=aid,
            registry=self.pool.registry,
            log=lambda kind, msg: job.add_event(kind, f"[{aid}] {msg}"),
        )

    def _run_node_image(self, job: Job) -> None:
        params = job.params
        account, _client = self._acquire_and_client(job)
        aid = account.config.id
        svc = self._node_service(account, job)
        try:
            res = run_with_retry(
                lambda: svc.generate_image(
                    prompt=params["prompt"],
                    aspect_ratio=params.get("aspect_ratio"),
                    aspect=params.get("aspect"),
                    seed=params.get("seed"),
                    model=params.get("model"),
                    count=params.get("count") or 1,
                    agent_mode=bool(params.get("agent_mode")),
                    reference_image=params.get("reference_image_path"),
                    reference_images=params.get("reference_image_paths"),
                    project_id=params.get("project_id"),
                    dry_run=bool(params.get("dry_run")),
                    remove_watermark=bool(params.get("remove_watermark", True)),
                    on_event=job.add_event,
                ),
                kind="image",
                log=job.add_event,
                abort=job.cancel_event,
            )
        except RetryAborted:
            self.pool.report_item_result(aid, "cancelled", error="người dùng dừng job")
            job.set_state("failed")
            job.error = "Đã dừng node tạo ảnh theo yêu cầu (hủy trong lúc chờ retry)."
            return
        except Exception as exc:
            self.pool.report_item_result(aid, "failed", error=f"{type(exc).__name__}: {exc}")
            raise
        self.pool.report_item_result(
            aid,
            res.status,
            error=None if res.status in ("ok", "ok_no_download", "dry_run") else (res.reason or res.hint),
        )
        d = res.to_dict()
        d["account_id"] = aid
        if res.file_path:
            d["file_url"] = f"/api/node/files/{res.run_id}/{Path(res.file_path).name}"
        job.result = d
        if res.status in ("ok", "ok_no_download", "dry_run"):
            job.set_state("succeeded")
            if res.run_id:
                self._bind_workspace_asset(job, f"output:{res.run_id}")
            # Node ảnh đánh dấu `is_item` ⇒ chép kết quả vào thư viện món đồ của project.
            # Không phụ thuộc script: người bán có nhiều món và dùng lại ảnh cho nhiều bộ.
            if params.get("is_item") and res.file_path:
                self._save_project_item(job, res.file_path, d)
        elif res.status == "rejected":
            job.set_state("rejected")
        else:
            job.set_state("failed")

    def _run_node_video(self, job: Job) -> None:
        params = job.params
        account, _client = self._acquire_and_client(job)
        aid = account.config.id
        svc = self._node_service(account, job)
        try:
            res = run_with_retry(
                lambda: svc.generate_video(
                    prompt=params["prompt"],
                    frame_path=params.get("frame_path"),
                    aspect_ratio=params.get("aspect_ratio") or "9:16",
                    seed=params.get("seed"),
                    resolution=params.get("resolution") or "1080p",
                    duration_s=params.get("duration_s") or 8,
                    project_id=params.get("project_id"),
                    dry_run=bool(params.get("dry_run")),
                    remove_watermark=bool(params.get("remove_watermark", True)),
                    auto_image=bool(params.get("auto_image", True)),
                    image_prompt=params.get("image_prompt"),
                    image_aspect_ratio=params.get("image_aspect_ratio") or "16:9",
                    model=params.get("model"),
                    sub_mode=params.get("sub_mode") or "frames",
                    count=params.get("count") or 1,
                    agent_mode=bool(params.get("agent_mode")),
                    on_event=job.add_event,
                ),
                kind="video",
                log=job.add_event,
                abort=job.cancel_event,
            )
        except RetryAborted:
            self.pool.report_item_result(aid, "cancelled", error="người dùng dừng job")
            job.set_state("failed")
            job.error = "Đã dừng node tạo video theo yêu cầu (hủy trong lúc chờ retry)."
            return
        except Exception as exc:
            self.pool.report_item_result(aid, "failed", error=f"{type(exc).__name__}: {exc}")
            raise
        self.pool.report_item_result(aid, "ok" if res.status == "ok" else "dry_run")
        d = res.to_dict()
        d["account_id"] = aid
        if res.video_path:
            d["video_url"] = f"/api/node/files/{res.run_id}/{Path(res.video_path).name}"
        if res.frame_path:
            d["frame_url"] = f"/api/node/files/{res.run_id}/{Path(res.frame_path).name}"
        job.result = d
        job.set_state("succeeded")
        if res.run_id and res.status == "ok":
            self._bind_workspace_asset(job, f"output:{res.run_id}")

    def _run_node_last_frame(self, job: Job) -> None:
        params = job.params
        ev = job.add_event
        v_path = Path(params["video_path"])
        if not v_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy file video: {v_path}")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_name = f"{ts}_last_frame_{v_path.stem[:30]}"
        run_dir = self.node_out / run_name
        run_dir.mkdir(parents=True, exist_ok=True)
        out_frame = run_dir / "last_frame.png"

        ev("step", f"Trích xuất frame cuối từ {v_path.name}...")
        t0 = time.time()
        from ...Bridge.flow_video_bridge import extract_last_video_frame
        from ...Workflows.watermark_remover import remove_image_watermark

        extract_last_video_frame(v_path, out_frame, log=lambda k, m: ev(k, m))
        if not out_frame.is_file() or out_frame.stat().st_size < 100:
            raise RuntimeError("Trích xuất frame cuối thất bại (file đầu ra rỗng hoặc không tồn tại).")

        if params.get("remove_watermark", True):
            try:
                remove_image_watermark(out_frame, prefer_family="video", log=lambda k, m: ev(k, m))
            except Exception as wm_exc:
                ev("warn", f"Xóa watermark frame cuối bỏ qua: {wm_exc}")

        elapsed = round(time.time() - t0, 2)
        ev("done", f"Trích xuất frame cuối hoàn tất ({elapsed}s) → {out_frame.name}")

        res = {
            "status": "ok",
            "run_id": run_name,
            "run_dir": str(run_dir),
            "file_path": str(out_frame),
            "file_url": f"/api/node/files/{run_name}/{out_frame.name}",
            "file_bytes": out_frame.stat().st_size,
            "source_video": str(v_path),
            "elapsed_s": elapsed,
        }
        job.result = res
        job.set_state("succeeded")
        self._bind_workspace_asset(job, f"output:{run_name}")
