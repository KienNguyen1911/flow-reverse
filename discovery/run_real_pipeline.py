import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from src.Workflows.auto_tryon_pipeline import AutoTryOnPipeline

def log_event(kind: str, msg: str, data: dict = None) -> None:
    timestamp = time.strftime("%H:%M:%S")
    extra = f" {data}" if data else ""
    print(f"[{timestamp}] [{kind.upper()}] {msg}{extra}", flush=True)


model_path = Path("out/uploads/1792955358411_main-model.jpg").resolve()
garment_path = Path("out/uploads/1792955345724_1.jpg").resolve()
project_id = "3163e114-3243-4bc3-b34b-b5878fdb6447"
cdp_url = "http://127.0.0.1:4023"

print("=" * 60)
print("=== KHỞI ĐỘNG REAL TEST AUTO TRY-ON PIPELINE ===")
print(f"CDP URL: {cdp_url}")
print(f"Project ID: {project_id}")
print(f"Model Image: {model_path} ({model_path.stat().st_size} bytes)")
print(f"Garment Image: {garment_path} ({garment_path.stat().st_size} bytes)")
print("=" * 60, flush=True)

pipeline = AutoTryOnPipeline(
    cdp_url=cdp_url,
    out_root=Path("out/affiliate_runs"),
    on_event=log_event,
)

t0 = time.time()
try:
    res = pipeline.run(
        model_path=str(model_path),
        garment_path=str(garment_path),
        project_id=project_id,
        dry_run=False,
        auto_stitch=True,
    )
    print("\n" + "=" * 60)
    print(f"=== PIPELINE THỰC THI THÀNH CÔNG ({round(time.time() - t0, 2)}s) ===")
    print("=" * 60)
    print("Run ID:", res.run_id)
    print("Status:", res.status)
    print("Destination Directory:", res.dest_dir)
    print("Image Prompt:", res.image_prompt)
    print("First Frame Path:", res.first_frame_path)
    print("Video Prompt 1:", res.video_prompt_1)
    print("Video 1 Path:", res.video_1_path)
    print("Last Frame Path:", res.last_frame_path)
    print("Video Prompt 2:", res.video_prompt_2)
    print("Video 2 Path:", res.video_2_path)
    print("Final Video (16s) Path:", res.final_video_path)
    print("=" * 60, flush=True)
except Exception as e:
    import traceback
    print("\n" + "!" * 60)
    print(f"=== PIPELINE GẶP LỖI ({round(time.time() - t0, 2)}s) ===")
    print("!" * 60)
    traceback.print_exc()
    sys.exit(1)
