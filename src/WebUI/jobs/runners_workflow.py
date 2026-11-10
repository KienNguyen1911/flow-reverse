"""Workflow-driven jobs: the ``delivery_build`` export."""

from __future__ import annotations

from .model import Job


class WorkflowJobsMixin:
    """Mixed into :class:`~src.WebUI.jobs.manager.JobManager`; uses its out_root/helpers."""

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
                model=str(raw.get("model") or "macaron_cookie_i2v_8s"),
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
