"""Auto Try-On Pipeline — Autonomous end-to-end Shopee Affiliate Video Workflow.

Automates the complete 5-stage loop:
1. Shopee Affiliate Ingestion:
   - Extract product images, identify primary garment try-on sample.
2. Gemini Nabi Studio:
   - Upload @nabi model + garment sample -> "@try-on-prompter create image prompt"
   - Output: Image Prompt (1)
3. Google Flow First Frame Image Generation:
   - Generate try-on First Frame image via Flow -> download first_frame.png
4. Gemini Nabi Studio Video Prompts:
   - Upload first_frame.png -> "@try-on-prompter create video prompt"
   - Output: Video Prompt 1 & Video Prompt 2 (8s each)
5. Google Flow Video Chaining & Assembly:
   - Video 1 (8s): First Frame + Video Prompt 1 -> video_1.mp4
   - Extract Last Frame of Video 1 -> last_frame_video_1.png (high-precision FFmpeg)
   - Video 2 (8s): Last Frame + Video Prompt 2 -> video_2.mp4
   - Automatic 16s Stitch: video_1 + video_2 -> final_tryon_video_16s.mp4

Usage:
    # 1. Full auto run from Shopee URL:
    python -m src.Workflows.auto_tryon_pipeline \
        --shopee-url "https://affiliate.shopee.vn/offer/product_offer?..." \
        --model-path "assets/nabi_model.png"

    # 2. Dry-run mode (0 credit, validates all steps, parsers, and local media tools):
    python -m src.Workflows.auto_tryon_pipeline \
        --product-dir "out/sample_product" \
        --model-path "assets/nabi_model.png" \
        --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from ..Bridge.flow_bridge import DEFAULT_CDP_URL, FlowBridge
from ..Bridge.flow_video_bridge import (
    FlowVideoBridge,
    concatenate_two_videos,
    extract_last_video_frame,
)
from ..Bridge.gemini_bridge import (
    NABI_NOTEBOOK_URL,
    GeminiNotebookBridge,
    parse_gemini_image_prompt,
    parse_gemini_video_prompts,
)
from .flow_client import FlowClient
from .flow_models import ProjectInfo
from .shopee_downloader import ShopeeAssetDownloader, ShopeeProductInfo
from .watermark_remover import remove_image_watermark, remove_video_watermark

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = ROOT / "out" / "affiliate_runs"
DEFAULT_ASSETS_DIR = ROOT / "assets"

LogFn = Callable[[str, str, Optional[dict]], None]


@dataclass
class TryOnPipelineResult:
    run_id: str
    status: str
    product_title: str
    dest_dir: str
    shopee_images: list[str]
    model_image_path: str
    garment_image_path: str
    image_prompt: str
    first_frame_path: Optional[str] = None
    video_prompt_1: str = ""
    video_prompt_2: str = ""
    video_1_path: Optional[str] = None
    last_frame_path: Optional[str] = None
    video_2_path: Optional[str] = None
    final_video_path: Optional[str] = None
    elapsed_s: float = 0.0
    dry_run: bool = False
    single_video: bool = False
    aspect_ratio: str = "9:16"
    current_step: int = 0
    failed_step: Optional[int] = None
    failed_step_label: Optional[str] = None
    steps: list[dict] = field(default_factory=list)
    error: Optional[str] = None


class AutoTryOnPipeline:
    """Master orchestrator for autonomous try-on image and video creation."""

    def __init__(
        self,
        cdp_url: str = DEFAULT_CDP_URL,
        out_root: Optional[Path] = None,
        on_event: Optional[LogFn] = None,
    ):
        self.cdp_url = cdp_url
        self.out_root = Path(out_root) if out_root else DEFAULT_OUT_DIR
        self._on_event = on_event or (lambda kind, msg, data: None)
        self.shopee_downloader = ShopeeAssetDownloader(out_dir=self.out_root)
        self.flow_video = FlowVideoBridge(cdp_url=self.cdp_url, log=self._bridge_log)

    def _log(self, kind: str, message: str, data: Optional[dict] = None) -> None:
        self._on_event(kind, message, data or {})
        print(f"[{kind.upper()}] {message}")

    def _bridge_log(self, kind: str, message: str) -> None:
        self._log(kind, message)

    def _resolve_local_path(self, raw: Path | str) -> Path:
        s = str(raw).strip()
        if s.startswith("/api/tryon/files/"):
            rel = s[len("/api/tryon/files/"):].lstrip("/")
            cand = (self.out_root / rel).resolve()
            if cand.exists():
                return cand
        if s.startswith("/api/uploads/"):
            rel = s[len("/api/uploads/"):].lstrip("/")
            cand = (ROOT / "out" / "uploads" / rel).resolve()
            if cand.exists():
                return cand
        if s.startswith("/api/assets/"):
            rel = s[len("/api/assets/"):].lstrip("/")
            cand = (ROOT / "assets" / rel).resolve()
            if cand.exists():
                return cand
        p = Path(s)
        if p.is_file():
            return p.resolve()
        if (ROOT / p).is_file():
            return (ROOT / p).resolve()
        return p.resolve()

    def run(
        self,
        model_path: Optional[Path | str] = None,
        garment_path: Optional[Path | str] = None,
        transfer_image: Optional[Path | str] = None,
        product_dir: Optional[Path | str] = None,
        extra_images: Optional[list[Path | str]] = None,
        shopee_url: Optional[str] = None,
        project_id: Optional[str] = None,
        dry_run: bool = False,
        auto_stitch: bool = True,
        override_image_prompt: Optional[str] = None,
        override_video_prompt_1: Optional[str] = None,
        override_video_prompt_2: Optional[str] = None,
        first_frame_path: Optional[Path | str] = None,
        aspect_ratio: str = "9:16",
        remove_watermark: bool = True,
        single_video: bool = False,
        resume_run_id: Optional[str] = None,
        start_from_step: Optional[int] = None,
    ) -> TryOnPipelineResult:
        """Run the automated try-on video pipeline (or direct video-chain / single 8s video from first frame)."""
        t0 = time.time()

        # Check bound Job (when invoked from JobManager._run_auto_tryon)
        bound_job = getattr(self._on_event, "__self__", None)
        if bound_job is not None and hasattr(bound_job, "params") and isinstance(bound_job.params, dict):
            if not resume_run_id and bound_job.params.get("resume_run_id"):
                resume_run_id = str(bound_job.params.get("resume_run_id")).strip()
            if start_from_step is None and bound_job.params.get("start_from_step") is not None:
                try:
                    start_from_step = int(bound_job.params.get("start_from_step"))
                except Exception:
                    pass

        # Also support encoding "__resume__:<run_id>:<step>" inside override_image_prompt
        if override_image_prompt and str(override_image_prompt).startswith("__resume__:"):
            parts = str(override_image_prompt).split(":")
            if len(parts) >= 2 and parts[1].strip():
                resume_run_id = resume_run_id or parts[1].strip()
            if len(parts) >= 3 and parts[2].strip().isdigit() and start_from_step is None:
                start_from_step = int(parts[2].strip())
            override_image_prompt = None

        # Also auto-detect resume_run_id if first_frame_path points inside an existing affiliate_runs/<run_id>/ directory
        if not resume_run_id and first_frame_path:
            ff_str = str(first_frame_path).replace("\\", "/")
            import re as _re
            m_run = _re.search(r"(?:affiliate_runs|/api/tryon/files)/(tryon_\d{8}_\d{6})/", ff_str)
            if m_run and start_from_step is not None:
                resume_run_id = m_run.group(1)

        prev_manifest: dict = {}
        if resume_run_id and (self.out_root / resume_run_id).is_dir():
            run_id = resume_run_id
            run_dir = self.out_root / run_id
            mf_path = run_dir / "manifest.json"
            if mf_path.is_file():
                try:
                    prev_manifest = json.loads(mf_path.read_text(encoding="utf-8"))
                except Exception:
                    prev_manifest = {}
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_id = f"tryon_{ts}"
            run_dir = self.out_root / run_id
            n = 2
            while run_dir.exists():
                run_id = f"tryon_{ts}_{n}"
                run_dir = self.out_root / run_id
                n += 1
            run_dir.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------------- #
        # Shortcut Branch: Direct Video-Chain / Single Video when First Frame is provided
        # ------------------------------------------------------------------- #
        if not first_frame_path and prev_manifest.get("first_frame_path"):
            first_frame_path = prev_manifest["first_frame_path"]
        is_direct_first_frame = bool(
            first_frame_path or (resume_run_id and (run_dir / "first_frame.png").is_file())
        )
        is_single = bool(single_video or (is_direct_first_frame and not (override_video_prompt_2 or prev_manifest.get("video_prompt_2") or "").strip()))

        if is_single:
            steps_state = [
                {"id": 1, "key": "video_1", "label": "Tạo Video (8s)", "desc": "Upload First Frame & render Video 8s", "status": "pending", "error": None},
                {"id": 2, "key": "postprocess", "label": "Hậu kỳ & Xóa Watermark", "desc": "Làm sạch watermark & xuất MP4", "status": "pending", "error": None},
            ]
        else:
            steps_state = [
                {"id": 1, "key": "video_1", "label": "Tạo Video 1 (8s)", "desc": "Upload First Frame & render Video 1", "status": "pending", "error": None},
                {"id": 2, "key": "last_frame", "label": "Trích xuất Last Frame", "desc": "FFmpeg cắt frame chính xác 100%", "status": "pending", "error": None},
                {"id": 3, "key": "video_2", "label": "Tạo Video 2 (8s)", "desc": "Upload Last Frame & render Video 2", "status": "pending", "error": None},
                {"id": 4, "key": "stitch_16s", "label": "Ghép hoàn chỉnh 16s", "desc": "Nối liền mạch 2 video không giật", "status": "pending", "error": None},
            ]

        video_1_path = run_dir / "video_1.mp4"
        last_frame_path: Optional[Path] = run_dir / "last_frame_video_1.png"
        video_2_path: Optional[Path] = run_dir / "video_2.mp4"
        final_video_path: Optional[Path] = run_dir / ("video_1.mp4" if is_single else "final_tryon_video_16s.mp4")

        product_title = str(prev_manifest.get("product_title") or "Fashion Outfit")
        v_prompt_1 = override_video_prompt_1 or str(prev_manifest.get("video_prompt_1") or "")
        v_prompt_2 = "" if is_single else (override_video_prompt_2 or str(prev_manifest.get("video_prompt_2") or ""))
        image_prompt = override_image_prompt or str(prev_manifest.get("image_prompt") or "")
        all_product_images: list[Path] = []
        garment_p: Optional[Path] = None
        model_p: Path = Path(model_path or "assets/nabi_model.png")
        resolved_proj_id = project_id

        def _build_and_persist(
            status_val: str,
            cur_step: int,
            fail_step: Optional[int] = None,
            fail_label: Optional[str] = None,
            err_msg: Optional[str] = None,
        ) -> TryOnPipelineResult:
            ff_file = run_dir / "first_frame.png"
            v1_file = run_dir / "video_1.mp4"
            lf_file = run_dir / "last_frame_video_1.png"
            v2_file = run_dir / "video_2.mp4"
            fv_file = v1_file if is_single else (run_dir / "final_tryon_video_16s.mp4")

            res_obj = TryOnPipelineResult(
                run_id=run_id,
                status=status_val,
                product_title=product_title,
                dest_dir=str(run_dir.resolve()),
                shopee_images=[str(p) for p in all_product_images],
                model_image_path=str(model_p),
                garment_image_path=str(garment_p) if garment_p else "",
                image_prompt=image_prompt,
                first_frame_path=str(ff_file) if ff_file.is_file() else None,
                video_prompt_1=v_prompt_1,
                video_prompt_2=v_prompt_2,
                video_1_path=str(v1_file) if (v1_file.is_file() and v1_file.stat().st_size > 1000) else None,
                last_frame_path=str(lf_file) if (lf_file.is_file() and lf_file.stat().st_size > 500) else None,
                video_2_path=str(v2_file) if (v2_file.is_file() and v2_file.stat().st_size > 1000) else None,
                final_video_path=str(fv_file) if (fv_file.is_file() and fv_file.stat().st_size > 1000 and status_val == "succeeded") else None,
                elapsed_s=round(time.time() - t0, 2),
                dry_run=dry_run,
                single_video=is_single,
                aspect_ratio=aspect_ratio,
                current_step=cur_step,
                failed_step=fail_step,
                failed_step_label=fail_label,
                steps=[dict(s) for s in steps_state],
                error=err_msg,
            )
            res_dict = asdict(res_obj)
            if res_obj.first_frame_path:
                res_dict["first_frame_url"] = f"/api/tryon/files/{run_id}/{Path(res_obj.first_frame_path).name}"
            if res_obj.video_1_path:
                res_dict["video_1_url"] = f"/api/tryon/files/{run_id}/{Path(res_obj.video_1_path).name}"
            if res_obj.last_frame_path:
                res_dict["last_frame_url"] = f"/api/tryon/files/{run_id}/{Path(res_obj.last_frame_path).name}"
            if res_obj.video_2_path:
                res_dict["video_2_url"] = f"/api/tryon/files/{run_id}/{Path(res_obj.video_2_path).name}"
            if res_obj.final_video_path:
                res_dict["final_video_url"] = f"/api/tryon/files/{run_id}/{Path(res_obj.final_video_path).name}"

            try:
                (run_dir / "manifest.json").write_text(
                    json.dumps(res_dict, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass

            if bound_job is not None:
                try:
                    bound_job.result = res_dict
                except Exception:
                    pass
            return res_obj

        active_step_id = 1
        try:
            if is_direct_first_frame:
                dest_ff = run_dir / "first_frame.png"
                if first_frame_path:
                    ff_p = self._resolve_local_path(first_frame_path)
                else:
                    ff_p = dest_ff
                if not ff_p.is_file() and not dest_ff.is_file() and not dry_run:
                    raise FileNotFoundError(f"Không tìm thấy ảnh First Frame: {ff_p}")
                mode_label = "Single Video 8s Pipeline" if is_single else "Video Chain Pipeline"
                if resume_run_id:
                    self._log(
                        "step",
                        f"=== Tiếp tục {mode_label} ({run_id}) từ Bước {start_from_step or 'tự động'} ===",
                        {"dry_run": dry_run, "single_video": is_single, "resume_run_id": run_id, "start_from_step": start_from_step},
                    )
                else:
                    self._log("step", f"=== Khởi động {mode_label} ({run_id}) ===", {"dry_run": dry_run, "single_video": is_single})

                if ff_p.is_file() and ff_p != dest_ff:
                    self._log("info", f"Sử dụng First Frame Image trực tiếp: {ff_p.name}")
                    shutil.copy(ff_p, dest_ff)
                    if remove_watermark and not dry_run and dest_ff.is_file():
                        remove_image_watermark(dest_ff, log=self._bridge_log)
                elif dest_ff.is_file():
                    self._log("info", f"Sử dụng First Frame đã lưu của run ({dest_ff.name})")

                first_frame_path = dest_ff
                product_title = ff_p.stem if ff_p.stem != "first_frame" else product_title
                v_prompt_1 = v_prompt_1 or "A cinematic natural fashion video, 8 seconds"
                v_prompt_2 = "" if is_single else (v_prompt_2 or "A cinematic seamless continuation video, 8 seconds")
                all_product_images = [first_frame_path]
                garment_p = first_frame_path
                model_p = first_frame_path
            else:
                model_p = Path(model_path or "assets/nabi_model.png").resolve()
                if not model_p.is_file() and not dry_run:
                    raise FileNotFoundError(f"Không tìm thấy ảnh người mẫu Nabi: {model_p}")

                self._log("step", f"=== Khởi động Auto Try-On Pipeline ({run_id}) ===", {"dry_run": dry_run})

                # ------------------------------------------------------------------- #
                # Step 1: Ingest model, chosen transfer model / garment & extra images
                # ------------------------------------------------------------------- #
                self._log("step", "BƯỚC 1: Chuẩn bị ảnh người mẫu và mẫu mặc thử (transfer model)...")
                garment_arg = garment_path or transfer_image
                garment_p = None
                all_product_images = []
                extra_imgs = []
                product_title = "Fashion Outfit"

                if garment_arg:
                    garment_p = Path(garment_arg).resolve()
                    if not garment_p.is_file() and not dry_run:
                        raise FileNotFoundError(f"Không tìm thấy ảnh mẫu mặc thử / transfer model: {garment_p}")
                    all_product_images.append(garment_p)
                    product_title = garment_p.stem

                    if product_dir:
                        pdir = Path(product_dir).resolve()
                        if pdir.is_dir():
                            for f in sorted(pdir.iterdir()):
                                if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                                    if f.resolve() != garment_p:
                                        extra_imgs.append(f)
                                        all_product_images.append(f)

                elif product_dir:
                    product_info = self.shopee_downloader.load_local_images(Path(product_dir))
                    garment_p = product_info.primary_garment_path
                    all_product_images = list(product_info.downloaded_paths)
                    product_title = product_info.title
                    extra_imgs = [p for p in all_product_images if p != garment_p]

                elif shopee_url:
                    product_info = self.shopee_downloader.process_url(
                        shopee_url,
                        dest_subdir=run_id,
                        on_event=self._bridge_log,
                    )
                    garment_p = product_info.primary_garment_path
                    all_product_images = list(product_info.downloaded_paths)
                    product_title = product_info.title
                    extra_imgs = [p for p in all_product_images if p != garment_p]

                else:
                    raise ValueError("Phải cung cấp ít nhất --garment-path (hoặc --transfer-image), hoặc --product-dir, hoặc --shopee-url")

                if extra_images:
                    for ei in extra_images:
                        ep = Path(ei).resolve()
                        if not ep.is_file() and not dry_run:
                            raise FileNotFoundError(f"Không tìm thấy ảnh bổ sung: {ep}")
                        if ep not in all_product_images and (not garment_p or ep != garment_p):
                            extra_imgs.append(ep)
                            all_product_images.append(ep)

                if not garment_p and not dry_run:
                    raise ValueError("Không tìm thấy ảnh mẫu áo/quần mặc thử từ sản phẩm.")

                self._log(
                    "info",
                    f"Đã chuẩn bị ảnh người mẫu: {model_p.name}, mẫu thử: {garment_p.name if garment_p else 'N/A'}, "
                    f"tổng cộng {len(all_product_images)} ảnh sản phẩm/bổ sung.",
                )

                # ------------------------------------------------------------------- #
                # Step 2: Gemini Nabi Studio -> Image Prompt (1)
                # ------------------------------------------------------------------- #
                self._log("step", "BƯỚC 2: Gọi Gemini Nabi Studio tạo Image Prompt (1)...")
                image_prompt = ""

                if override_image_prompt:
                    image_prompt = override_image_prompt
                    self._log("info", f"Dùng prompt ảnh chỉ định sẵn: '{image_prompt[:100]}...'")
                elif dry_run:
                    image_prompt = (
                        f"Full-body fashion portrait of Nabi model wearing {product_title[:60]}, "
                        f"studio lighting, highly detailed fabric texture, 8k, photorealistic"
                    )
                    self._log("info", f"[DRY-RUN] Sinh prompt ảnh mẫu: '{image_prompt}'")
                else:
                    with GeminiNotebookBridge(cdp_url=self.cdp_url, log=self._bridge_log) as gemini:
                        image_prompt = gemini.generate_image_prompt(
                            model_p,
                            garment_p,
                            extra_images=extra_imgs if extra_imgs else None,
                        )

                (run_dir / "image_prompt.txt").write_text(image_prompt, encoding="utf-8")

                # ------------------------------------------------------------------- #
                # Step 3: Google Flow -> First Frame Image
                # ------------------------------------------------------------------- #
                self._log("step", "BƯỚC 3: Tạo First Frame Image trên Google Flow...")
                first_frame_path = run_dir / "first_frame.png"

                resolved_proj_id = project_id
                if not dry_run and not resolved_proj_id:
                    try:
                        client = FlowClient(cdp_url=self.cdp_url)
                        st = client.status()
                        if st.flow_project_id:
                            resolved_proj_id = st.flow_project_id
                            self._log("info", f"Tự động dùng dự án đang mở trên Flow: {resolved_proj_id}")
                        else:
                            listed = client.list_projects()
                            if listed:
                                resolved_proj_id = listed[0].id
                                self._log("info", f"Tự động dùng dự án có sẵn: {listed[0].title} ({resolved_proj_id[:8]}…)")
                            else:
                                new_p = client.create_project("Affiliate Try-On")
                                resolved_proj_id = new_p.id
                                self._log("info", f"Tự động tạo dự án mới: {new_p.title} ({resolved_proj_id[:8]}…)")
                    except Exception as e:
                        self._log("warn", f"Không thể tự động phát hiện project trên Flow: {e}")

                if dry_run:
                    self._log("info", "[DRY-RUN] Giả lập tạo First Frame Image...")
                    if garment_p and garment_p.is_file():
                        shutil.copy(garment_p, first_frame_path)
                    else:
                        first_frame_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)
                else:
                    client = FlowClient(cdp_url=self.cdp_url)
                    proj_id = resolved_proj_id or "default"
                    flow_image_prompt = image_prompt
                    if "@nabi" not in flow_image_prompt.lower():
                        import re
                        if re.search(r"\bnabi\b", flow_image_prompt, re.IGNORECASE):
                            flow_image_prompt = re.sub(r"\bnabi\b", "@nabi", flow_image_prompt, flags=re.IGNORECASE)
                        else:
                            flow_image_prompt = f"@nabi {flow_image_prompt}".strip()

                    tpl = None
                    if garment_p and garment_p.is_file():
                        try:
                            self._log("step", f"Tải ảnh mẫu thử lên Flow làm reference template: {garment_p.name}")
                            tpl = client.upload_reference_image(
                                proj_id,
                                garment_p,
                                prompt_probe=flow_image_prompt[:60],
                            )
                            self._log("info", f"Upload reference thành công (media≈{tpl.media_id})")
                        except Exception as e:
                            self._log("warn", f"Upload reference không thành công ({e}), tiếp tục với text2image...")
                            tpl = None

                    gen_res = client.generate_image(
                        project_id=proj_id,
                        prompt=flow_image_prompt,
                        reference=tpl,
                        dry_run=False,
                        remove_watermark=remove_watermark,
                    )
                    if gen_res.status != "ok" or not gen_res.image or not gen_res.image.file_path:
                        raise RuntimeError(f"Tạo First Frame trên Flow thất bại: {gen_res.reason} ({gen_res.hint})")
                    shutil.copy(gen_res.image.file_path, first_frame_path)
                    if remove_watermark and first_frame_path.is_file():
                        remove_image_watermark(first_frame_path, prefer_family="image", log=self._bridge_log)
                    self._log("info", f"First Frame đã lưu: {first_frame_path.name}")

                # ------------------------------------------------------------------- #
                # Step 4: Gemini Nabi Studio -> 2 Video Prompts (8s each)
                # ------------------------------------------------------------------- #
                self._log("step", "BƯỚC 4: Gọi Gemini Nabi Studio tạo 2 Video Prompt (8s)...")
                v_prompt_1 = ""
                v_prompt_2 = ""

                if override_video_prompt_1 and override_video_prompt_2:
                    v_prompt_1 = override_video_prompt_1
                    v_prompt_2 = override_video_prompt_2
                    self._log("info", "Dùng video prompts chỉ định sẵn.")
                elif dry_run:
                    v_prompt_1 = (
                        "Nabi stands elegantly, smooth camera slow zoom in, gentle movement showing garment drape, 8 seconds"
                    )
                    v_prompt_2 = (
                        "Nabi turns slightly to showcase side profile and back of the outfit, natural fashion pose, 8 seconds"
                    )
                    self._log("info", f"[DRY-RUN] Sinh video prompt 1: '{v_prompt_1[:80]}...'")
                    self._log("info", f"[DRY-RUN] Sinh video prompt 2: '{v_prompt_2[:80]}...'")
                else:
                    with GeminiNotebookBridge(cdp_url=self.cdp_url, log=self._bridge_log) as gemini:
                        v_prompt_1, v_prompt_2 = gemini.generate_video_prompts(first_frame_path)

                prompts_meta = {
                    "image_prompt": image_prompt,
                    "video_prompt_1": v_prompt_1,
                    "video_prompt_2": v_prompt_2,
                }
                (run_dir / "prompts.json").write_text(json.dumps(prompts_meta, ensure_ascii=False, indent=2), encoding="utf-8")

            # ------------------------------------------------------------------- #
            # Step 5 (UI Step 1): Google Flow -> Video 1 (8s)
            # ------------------------------------------------------------------- #
            active_step_id = 1
            step_1_lbl = "BƯỚC 1/1" if is_single else ("BƯỚC 1/4" if is_direct_first_frame else "BƯỚC 5")
            video_1_path = run_dir / "video_1.mp4"

            skip_v1 = (
                video_1_path.is_file()
                and video_1_path.stat().st_size > 2_000
                and (
                    (resume_run_id and (start_from_step is None or start_from_step > 1))
                    or (start_from_step is not None and start_from_step > 1)
                )
            )
            if skip_v1:
                steps_state[0]["status"] = "succeeded"
                self._log(
                    "info",
                    f"{step_1_lbl}: Đã có sẵn Video 1 ({video_1_path.stat().st_size // 1024} KB) từ bước trước — giữ nguyên, không tạo lại Video 1.",
                )
                _build_and_persist("running", cur_step=1)
            else:
                steps_state[0]["status"] = "running"
                _build_and_persist("running", cur_step=1)
                self._log("step", f"{step_1_lbl}: Tạo Video 1 (8s) từ First Frame + Video Prompt 1...")

                if dry_run:
                    self._log("info", "[DRY-RUN] Giả lập tạo Video 1...")
                    self._generate_dummy_video(video_1_path, duration_s=2)
                else:
                    self.flow_video.generate_video_flow(
                        frame_path=first_frame_path,
                        prompt_text=v_prompt_1,
                        dest_path=video_1_path,
                        duration_s=8,
                        timeout_s=300.0,
                        project_id=resolved_proj_id,
                        aspect_ratio=aspect_ratio,
                        resolution="1080p",
                    )
                    if not is_single and remove_watermark and video_1_path.is_file():
                        self._log("step", "Đang tự động xóa watermark (✦) trên Video 1...")
                        remove_video_watermark(video_1_path, log=self._bridge_log)

                steps_state[0]["status"] = "succeeded"
                _build_and_persist("running", cur_step=1)

            if is_single:
                active_step_id = 2
                steps_state[1]["status"] = "running"
                _build_and_persist("running", cur_step=2)
                if not dry_run and remove_watermark and video_1_path.is_file():
                    self._log("step", "Đang tự động xóa watermark (✦) trên Video 8s...")
                    remove_video_watermark(video_1_path, log=self._bridge_log)
                final_video_path = video_1_path
                steps_state[1]["status"] = "succeeded"
                self._log("info", "Chế độ Tạo 1 Video (8s): Hoàn tất xuất MP4.")
            else:
                # ------------------------------------------------------------------- #
                # Step 6 (UI Step 2): Extract Last Frame from Video 1
                # ------------------------------------------------------------------- #
                active_step_id = 2
                step_2_lbl = "BƯỚC 2/4" if is_direct_first_frame else "BƯỚC 6"
                last_frame_path = run_dir / "last_frame_video_1.png"

                skip_lf = (
                    last_frame_path.is_file()
                    and last_frame_path.stat().st_size > 1_000
                    and (
                        (resume_run_id and (start_from_step is None or start_from_step > 2))
                        or (start_from_step is not None and start_from_step > 2)
                    )
                )
                if skip_lf:
                    steps_state[1]["status"] = "succeeded"
                    self._log(
                        "info",
                        f"{step_2_lbl}: Đã có sẵn Last Frame ({last_frame_path.name}) — giữ nguyên, chuyển sang Bước 3.",
                    )
                    _build_and_persist("running", cur_step=2)
                else:
                    steps_state[1]["status"] = "running"
                    _build_and_persist("running", cur_step=2)
                    self._log("step", f"{step_2_lbl}: Trích xuất chính xác Last Frame từ Video 1...")
                    extract_last_video_frame(video_1_path, last_frame_path, log=self._bridge_log)
                    if remove_watermark and not dry_run and last_frame_path.is_file():
                        remove_image_watermark(last_frame_path, prefer_family="video", log=self._bridge_log)
                    steps_state[1]["status"] = "succeeded"
                    _build_and_persist("running", cur_step=2)

                # ------------------------------------------------------------------- #
                # Step 7 (UI Step 3): Google Flow -> Video 2 (8s) using Last Frame as First Frame
                # ------------------------------------------------------------------- #
                active_step_id = 3
                step_3_lbl = "BƯỚC 3/4" if is_direct_first_frame else "BƯỚC 7"
                video_2_path = run_dir / "video_2.mp4"

                skip_v2 = (
                    video_2_path.is_file()
                    and video_2_path.stat().st_size > 2_000
                    and (
                        (resume_run_id and (start_from_step is None or start_from_step > 3))
                        or (start_from_step is not None and start_from_step > 3)
                    )
                )
                if skip_v2:
                    steps_state[2]["status"] = "succeeded"
                    self._log(
                        "info",
                        f"{step_3_lbl}: Đã có sẵn Video 2 ({video_2_path.stat().st_size // 1024} KB) — giữ nguyên, chuyển sang Bước 4.",
                    )
                    _build_and_persist("running", cur_step=3)
                else:
                    steps_state[2]["status"] = "running"
                    _build_and_persist("running", cur_step=3)
                    self._log("step", f"{step_3_lbl}: Tạo Video 2 (8s) từ Last Frame + Video Prompt 2...")

                    if dry_run:
                        self._log("info", "[DRY-RUN] Giả lập tạo Video 2...")
                        self._generate_dummy_video(video_2_path, duration_s=2)
                    else:
                        self.flow_video.generate_video_flow(
                            frame_path=last_frame_path,
                            prompt_text=v_prompt_2,
                            dest_path=video_2_path,
                            duration_s=8,
                            timeout_s=300.0,
                            project_id=resolved_proj_id,
                            aspect_ratio=aspect_ratio,
                            resolution="1080p",
                        )
                        if remove_watermark and video_2_path.is_file():
                            self._log("step", "Đang tự động xóa watermark (✦) trên Video 2...")
                            remove_video_watermark(video_2_path, log=self._bridge_log)

                    steps_state[2]["status"] = "succeeded"
                    _build_and_persist("running", cur_step=3)

                # ------------------------------------------------------------------- #
                # Step 8 (UI Step 4): Automatic 16s Video Stitching
                # ------------------------------------------------------------------- #
                active_step_id = 4
                steps_state[3]["status"] = "running"
                _build_and_persist("running", cur_step=4)
                if auto_stitch:
                    step_4_lbl = "BƯỚC 4/4" if is_direct_first_frame else "BƯỚC 8"
                    self._log("step", f"{step_4_lbl}: Nối Video 1 + Video 2 thành Video 16s hoàn chỉnh...")
                    final_video_path = run_dir / "final_tryon_video_16s.mp4"
                    concatenate_two_videos(video_1_path, video_2_path, final_video_path, log=self._bridge_log)
                else:
                    final_video_path = video_2_path
                steps_state[3]["status"] = "succeeded"

            elapsed = round(time.time() - t0, 2)
            self._log("info", f"=== HOÀN TẤT {'VIDEO 8S' if is_single else 'AUTO TRY-ON'} ({elapsed}s) ===")
            return _build_and_persist("succeeded", cur_step=len(steps_state))

        except Exception as exc:
            err_str = f"{type(exc).__name__}: {exc}"
            fail_lbl = f"Bước {active_step_id}"
            for st in steps_state:
                if st["id"] == active_step_id:
                    st["status"] = "failed"
                    st["error"] = err_str
                    fail_lbl = st["label"]
                elif st["status"] == "running":
                    st["status"] = "failed"
                    st["error"] = err_str
            self._log(
                "error",
                f"Pipeline dừng tại Bước {active_step_id}/{len(steps_state)} ({fail_lbl}): {err_str}",
                {"failed_step": active_step_id, "failed_step_label": fail_lbl, "run_id": run_id},
            )
            failed_res = _build_and_persist(
                "failed",
                cur_step=active_step_id,
                fail_step=active_step_id,
                fail_label=fail_lbl,
                err_msg=err_str,
            )
            try:
                setattr(exc, "partial_result", asdict(failed_res))
            except Exception:
                pass
            raise

    @staticmethod
    def _generate_dummy_video(dest_path: Path, duration_s: int = 2) -> None:
        """Create a tiny test MP4 for dry-run verification using FFmpeg."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        import subprocess

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s=640x360:d={duration_s}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(dest_path),
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        except Exception:
            dest_path.write_bytes(b"\x00\x00\x00 ftypmp42" + b"\x00" * 1000)


# --------------------------------------------------------------------------- #
# CLI entrypoint
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Auto Try-On Video Pipeline (Manual Transfer Model & Workflow)")
    ap.add_argument("--garment-path", "--transfer-image", dest="garment_path", help="Đường dẫn ảnh mẫu mặc thử / transfer model do người dùng chọn")
    ap.add_argument("--model-path", default="assets/nabi_model.png", help="Đường dẫn ảnh người mẫu Nabi (mặc định: assets/nabi_model.png)")
    ap.add_argument("--product-dir", help="Thư mục ảnh sản phẩm bổ sung nếu muốn")
    ap.add_argument("--extra-images", nargs="*", default=[], help="Danh sách các file ảnh sản phẩm bổ sung")
    ap.add_argument("--shopee-url", help="URL sản phẩm hoặc affiliate Shopee (tùy chọn / fallback)")
    ap.add_argument("--project-id", help="UUID project trên Google Flow")
    ap.add_argument("--cdp-url", default=DEFAULT_CDP_URL, help=f"Cổng CDP CloakBrowser (mặc định: {DEFAULT_CDP_URL})")
    ap.add_argument("--dry-run", action="store_true", help="Chạy thử nghiệm (0 credit, test toàn bộ pipeline)")
    ap.add_argument("--no-stitch", action="store_true", help="Không nối video 1 + 2 thành 16s")
    ap.add_argument("--no-remove-watermark", action="store_true", help="Giữ nguyên watermark ngôi sao (✦) trên ảnh và video")
    ap.add_argument("--image-prompt", help="Chỉ định sẵn prompt tạo ảnh")
    ap.add_argument("--video-prompt-1", help="Chỉ định sẵn video prompt 1")
    ap.add_argument("--video-prompt-2", help="Chỉ định sẵn video prompt 2")

    args = ap.parse_args(argv)

    if not args.garment_path and not args.product_dir and not args.shopee_url:
        ap.error("Phải cung cấp ít nhất --garment-path (hoặc --transfer-image), hoặc --product-dir, hoặc --shopee-url")

    pipeline = AutoTryOnPipeline(cdp_url=args.cdp_url)
    res = pipeline.run(
        model_path=args.model_path,
        garment_path=args.garment_path,
        product_dir=args.product_dir,
        extra_images=args.extra_images,
        shopee_url=args.shopee_url,
        project_id=args.project_id,
        dry_run=args.dry_run,
        auto_stitch=not args.no_stitch,
        remove_watermark=not args.no_remove_watermark,
        override_image_prompt=args.image_prompt,
        override_video_prompt_1=args.video_prompt_1,
        override_video_prompt_2=args.video_prompt_2,
    )

    print("\n--- KẾT QUẢ QUY TRÌNH ---")
    print(f"Trạng thái:     {res.status}")
    print(f"Thư mục lưu:    {res.dest_dir}")
    print(f"First Frame:    {res.first_frame_path}")
    print(f"Video 1:        {res.video_1_path}")
    print(f"Last Frame:     {res.last_frame_path}")
    print(f"Video 2:        {res.video_2_path}")
    print(f"Video 16s ghép: {res.final_video_path}")
    print(f"Thời gian:      {res.elapsed_s}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
