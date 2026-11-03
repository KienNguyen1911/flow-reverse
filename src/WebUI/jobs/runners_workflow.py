"""Workflow-driven jobs: ``auto_tryon`` pipeline and ``delivery_build`` export."""

from __future__ import annotations

from pathlib import Path

from ...Bridge.flow_bridge import DEFAULT_CDP_URL
from .model import Job


class WorkflowJobsMixin:
    """Mixed into :class:`~src.WebUI.jobs.manager.JobManager`; uses its pool/out_root/helpers."""

    # -- delivery (export nguyên liệu cho HyperFrames desktop) --------------------- #

    def _run_delivery_build(self, job: Job) -> None:
        """Gom file đã sinh vào một thư mục tự chứa + manifest.

        Không gọi Flow, không tốn credit: chỉ đọc run đã có, đo bằng ffprobe và copy.
        """
        from ...Workflows.delivery import ItemRef, RunRef, build_delivery
        from ...Workflows.script_contract import ScriptError, load_script

        params = job.params
        ev = job.add_event

        try:
            script = load_script(params.get("script") or params.get("script_path") or "")
        except ScriptError as exc:
            raise RuntimeError(f"script không hợp lệ: {exc}") from exc

        ev("info", f"script: {script.slug} — {len(script.clips)} clip, {len(script.shots)} shot")

        refs: list[RunRef] = []
        for raw in params.get("run_refs") or []:
            if not isinstance(raw, dict) or not raw.get("run_id") and not raw.get("run_dir"):
                continue
            ref = RunRef(
                clip_id=str(raw.get("clip_id") or ""),
                run_id=str(raw.get("run_id") or ""),
                run_dir=str(raw.get("run_dir") or ""),
                take=int(raw.get("take") or 1),
                prompt=str(raw.get("prompt") or ""),
                seed=raw.get("seed"),
                model=str(raw.get("model") or "abra_i2v_8s"),
                policy_retries=int(raw.get("policy_retries") or 0),
                video_path=raw.get("video_path"),
                plate_path=raw.get("plate_path"),
            )
            if not ref.run_dir:
                ref.run_dir = str(self.node_out / ref.run_id)
            refs.append(ref)

        item_refs: list[ItemRef] = []
        for raw in params.get("item_refs") or []:
            if not isinstance(raw, dict):
                continue
            # Chấp nhận 2 kiểu: nối vào `items[]` của script (`item_id`), hoặc chỉ có
            # tên món do người dùng đặt. Không có cả hai thì không biết đặt tên gì.
            name = str(raw.get("name") or "").strip()
            item_id = str(raw.get("item_id") or "").strip() or None
            if not item_id and not name:
                continue
            ref = ItemRef(
                name=name,
                item_id=item_id,
                run_id=str(raw.get("run_id") or ""),
                run_dir=str(raw.get("run_dir") or ""),
                file_path=raw.get("file_path"),
            )
            if not ref.run_dir and ref.run_id:
                ref.run_dir = str(self.node_out / ref.run_id)
            item_refs.append(ref)
        if item_refs:
            ev("info", f"nhận {len(item_refs)} ảnh sản phẩm sinh từ Flow")

        dest_root = params.get("dest_dir") or None
        result = build_delivery(
            script,
            refs,
            dest_root=dest_root,
            overwrite=bool(params.get("overwrite")),
            item_refs=item_refs,
        )

        for m in result.assets_missing:
            ev("warn", f"thiếu: {m}")
        for w in result.warnings:
            ev("warn", w)
        ev("done", f"bộ dựng phim ở {result.dest_dir}")

        job.result = {
            **result.to_dict(),
            "dest_dir": result.dest_dir,
            "file_url_base": f"/api/deliveries/{script.slug}",
        }
        job.set_state("succeeded")

    def _run_auto_tryon(self, job: Job) -> None:
        import importlib
        from dataclasses import asdict
        from ...Bridge import flow_bridge, flow_video_bridge
        from ...Workflows import auto_tryon_pipeline

        importlib.reload(flow_bridge)
        importlib.reload(flow_video_bridge)
        importlib.reload(auto_tryon_pipeline)
        AutoTryOnPipeline = auto_tryon_pipeline.AutoTryOnPipeline

        params = job.params
        ev = job.add_event
        dry_run = bool(params.get("dry_run", False))

        if dry_run:
            aid = "dry_run"
            target_pid = params.get("project_id") or "dry_run_project"
            cdp_url = DEFAULT_CDP_URL
            ev("info", "[dry_run] Chạy giả lập không cần kết nối tài khoản hay browser.")
        else:
            account, client = self._acquire_and_client(job)
            aid = account.config.id
            cdp_url = account.cdp_url

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

        pipeline = AutoTryOnPipeline(
            cdp_url=cdp_url,
            out_root=self.out_root.parent / "affiliate_runs",
            on_event=ev,
        )
        try:
            res = pipeline.run(
                first_frame_path=params.get("first_frame_path"),
                model_path=params.get("model_path") or "assets/nabi_model.png",
                garment_path=params.get("garment_path") or params.get("transfer_image"),
                product_dir=params.get("product_dir"),
                extra_images=params.get("extra_images"),
                shopee_url=params.get("shopee_url"),
                project_id=target_pid,
                dry_run=dry_run,
                auto_stitch=bool(params.get("auto_stitch", True)),
                override_image_prompt=params.get("image_prompt"),
                override_video_prompt_1=params.get("video_prompt_1"),
                override_video_prompt_2=params.get("video_prompt_2"),
                aspect_ratio=params.get("aspect_ratio", "9:16"),
                remove_watermark=bool(params.get("remove_watermark", True)),
                single_video=bool(params.get("single_video", False)),
                resume_run_id=params.get("resume_run_id"),
                start_from_step=params.get("start_from_step"),
            )
            res_dict = asdict(res)
            res_dict["account_id"] = aid
            rid = res.run_id
            if res.first_frame_path and Path(res.first_frame_path).exists():
                res_dict["first_frame_url"] = f"/api/tryon/files/{rid}/{Path(res.first_frame_path).name}"
            if res.video_1_path and Path(res.video_1_path).exists():
                res_dict["video_1_url"] = f"/api/tryon/files/{rid}/{Path(res.video_1_path).name}"
            if res.last_frame_path and Path(res.last_frame_path).exists():
                res_dict["last_frame_url"] = f"/api/tryon/files/{rid}/{Path(res.last_frame_path).name}"
            if res.video_2_path and Path(res.video_2_path).exists():
                res_dict["video_2_url"] = f"/api/tryon/files/{rid}/{Path(res.video_2_path).name}"
            if res.final_video_path and Path(res.final_video_path).exists():
                res_dict["final_video_url"] = f"/api/tryon/files/{rid}/{Path(res.final_video_path).name}"
            job.result = res_dict
            job.set_state("succeeded")
            if not dry_run:
                self.pool.report_item_result(aid, "ok")
        except Exception as exc:
            partial = getattr(exc, "partial_result", None)
            if isinstance(partial, dict):
                partial["account_id"] = aid
                rid = partial.get("run_id") or ""
                if partial.get("first_frame_path") and Path(partial["first_frame_path"]).exists():
                    partial["first_frame_url"] = f"/api/tryon/files/{rid}/{Path(partial['first_frame_path']).name}"
                if partial.get("video_1_path") and Path(partial["video_1_path"]).exists():
                    partial["video_1_url"] = f"/api/tryon/files/{rid}/{Path(partial['video_1_path']).name}"
                if partial.get("last_frame_path") and Path(partial["last_frame_path"]).exists():
                    partial["last_frame_url"] = f"/api/tryon/files/{rid}/{Path(partial['last_frame_path']).name}"
                if partial.get("video_2_path") and Path(partial["video_2_path"]).exists():
                    partial["video_2_url"] = f"/api/tryon/files/{rid}/{Path(partial['video_2_path']).name}"
                job.result = partial
            if not dry_run:
                self.pool.report_item_result(aid, "failed", error=f"{type(exc).__name__}: {exc}")
            raise
