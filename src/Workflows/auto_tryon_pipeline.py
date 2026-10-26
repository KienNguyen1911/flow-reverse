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
from dataclasses import asdict, dataclass
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
    ) -> TryOnPipelineResult:
        """Run the automated try-on video pipeline (or direct video-chain from first frame)."""
        t0 = time.time()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"tryon_{ts}"
        run_dir = self.out_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------------- #
        # Shortcut Branch: Direct Video-Chain when First Frame is provided
        # ------------------------------------------------------------------- #
        is_direct_first_frame = bool(first_frame_path)
        if is_direct_first_frame:
            ff_p = Path(first_frame_path).resolve()
            if not ff_p.is_file() and not dry_run:
                raise FileNotFoundError(f"Không tìm thấy ảnh First Frame: {ff_p}")
            self._log("step", f"=== Khởi động Video Chain Pipeline ({run_id}) ===", {"dry_run": dry_run})
            self._log("info", f"Sử dụng First Frame Image trực tiếp: {ff_p.name}")

            dest_ff = run_dir / "first_frame.png"
            if ff_p != dest_ff:
                shutil.copy(ff_p, dest_ff)
            first_frame_path = dest_ff

            product_title = ff_p.stem
            v_prompt_1 = override_video_prompt_1 or "A cinematic natural fashion video, 8 seconds"
            v_prompt_2 = override_video_prompt_2 or "A cinematic seamless continuation video, 8 seconds"
            image_prompt = override_image_prompt or ""
            all_product_images = [first_frame_path]
            garment_p = first_frame_path
            model_p = first_frame_path
            resolved_proj_id = project_id
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

                # Optional extra product images from directory if provided
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

            # Include explicit extra_images if passed
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

            # Resolve Flow project ID dynamically if not specified
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
                )
                if gen_res.status != "ok" or not gen_res.image or not gen_res.image.file_path:
                    raise RuntimeError(f"Tạo First Frame trên Flow thất bại: {gen_res.reason} ({gen_res.hint})")
                shutil.copy(gen_res.image.file_path, first_frame_path)
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
        # Step 5: Google Flow -> Video 1 (8s)
        # ------------------------------------------------------------------- #
        step_1_lbl = "BƯỚC 1/4" if is_direct_first_frame else "BƯỚC 5"
        self._log("step", f"{step_1_lbl}: Tạo Video 1 (8s) từ First Frame + Video Prompt 1...")
        video_1_path = run_dir / "video_1.mp4"

        if dry_run:
            self._log("info", "[DRY-RUN] Giả lập tạo Video 1...")
            self._generate_dummy_video(video_1_path, duration_s=2)
        else:
            try:
                self.flow_video.generate_video_flow(
                    frame_path=first_frame_path,
                    prompt_text=v_prompt_1,
                    dest_path=video_1_path,
                    duration_s=8,
                    timeout_s=300.0,
                    project_id=resolved_proj_id,
                    aspect_ratio=aspect_ratio,
                )
            except Exception as e:
                self._log(
                    "warn",
                    f"generate_video_flow Video 1 gặp sự cố ({e}), đang tự động làm mềm Prompt (lọc từ nhạy cảm chính sách) và thử lại lần 2...",
                )
                time.sleep(2.0)
                self.flow_video.generate_video_flow(
                    frame_path=first_frame_path,
                    prompt_text=v_prompt_1,
                    dest_path=video_1_path,
                    duration_s=8,
                    timeout_s=300.0,
                    project_id=resolved_proj_id,
                    aspect_ratio=aspect_ratio,
                    aggressive_sanitize=True,
                )

        # ------------------------------------------------------------------- #
        # Step 6: Extract Last Frame from Video 1
        # ------------------------------------------------------------------- #
        step_2_lbl = "BƯỚC 2/4" if is_direct_first_frame else "BƯỚC 6"
        self._log("step", f"{step_2_lbl}: Trích xuất chính xác Last Frame từ Video 1...")
        last_frame_path = run_dir / "last_frame_video_1.png"
        extract_last_video_frame(video_1_path, last_frame_path, log=self._bridge_log)

        # ------------------------------------------------------------------- #
        # Step 7: Google Flow -> Video 2 (8s) using Last Frame as First Frame
        # ------------------------------------------------------------------- #
        step_3_lbl = "BƯỚC 3/4" if is_direct_first_frame else "BƯỚC 7"
        self._log("step", f"{step_3_lbl}: Tạo Video 2 (8s) từ Last Frame + Video Prompt 2...")
        video_2_path = run_dir / "video_2.mp4"

        if dry_run:
            self._log("info", "[DRY-RUN] Giả lập tạo Video 2...")
            self._generate_dummy_video(video_2_path, duration_s=2)
        else:
            try:
                self.flow_video.generate_video_flow(
                    frame_path=last_frame_path,
                    prompt_text=v_prompt_2,
                    dest_path=video_2_path,
                    duration_s=8,
                    timeout_s=300.0,
                    project_id=resolved_proj_id,
                    aspect_ratio=aspect_ratio,
                )
            except Exception as e:
                self._log(
                    "warn",
                    f"generate_video_flow Video 2 gặp sự cố ({e}), đang tự động làm mềm Prompt (lọc từ nhạy cảm chính sách) và thử lại lần 2...",
                )
                time.sleep(2.0)
                self.flow_video.generate_video_flow(
                    frame_path=last_frame_path,
                    prompt_text=v_prompt_2,
                    dest_path=video_2_path,
                    duration_s=8,
                    timeout_s=300.0,
                    project_id=resolved_proj_id,
                    aspect_ratio=aspect_ratio,
                    aggressive_sanitize=True,
                )

        # ------------------------------------------------------------------- #
        # Step 8: Automatic 16s Video Stitching
        # ------------------------------------------------------------------- #
        final_video_path: Optional[Path] = None
        if auto_stitch:
            step_4_lbl = "BƯỚC 4/4" if is_direct_first_frame else "BƯỚC 8"
            self._log("step", f"{step_4_lbl}: Nối Video 1 + Video 2 thành Video 16s hoàn chỉnh...")
            final_video_path = run_dir / "final_tryon_video_16s.mp4"
            concatenate_two_videos(video_1_path, video_2_path, final_video_path, log=self._bridge_log)

        elapsed = round(time.time() - t0, 2)
        self._log("info", f"=== HOÀN TẤT AUTO TRY-ON ({elapsed}s) ===")

        res = TryOnPipelineResult(
            run_id=run_id,
            status="succeeded",
            product_title=product_title,
            dest_dir=str(run_dir.resolve()),
            shopee_images=[str(p) for p in all_product_images],
            model_image_path=str(model_p),
            garment_image_path=str(garment_p) if garment_p else "",
            image_prompt=image_prompt,
            first_frame_path=str(first_frame_path) if first_frame_path.exists() else None,
            video_prompt_1=v_prompt_1,
            video_prompt_2=v_prompt_2,
            video_1_path=str(video_1_path) if video_1_path.exists() else None,
            last_frame_path=str(last_frame_path) if last_frame_path.exists() else None,
            video_2_path=str(video_2_path) if video_2_path.exists() else None,
            final_video_path=str(final_video_path) if final_video_path and final_video_path.exists() else None,
            elapsed_s=elapsed,
            dry_run=dry_run,
        )

        (run_dir / "manifest.json").write_text(
            json.dumps(asdict(res), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return res

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
