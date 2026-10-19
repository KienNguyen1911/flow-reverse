"""Test script for running a 40-image cinematic batch.

10 concept shots (characters + environments) + 30 narrative storyboard shots.
Supports both WebUI API mode (with SSE progress stream) and standalone direct runner.

Usage:
    # 1. Chạy thử nghiệm Dry-run (0 credit, test toàn bộ pipeline phân bổ tài khoản):
    python scripts/test_batch_40.py --dry-run

    # 2. Chạy thật 40 ảnh trên pool tài khoản (cần cờ --real và --confirm):
    python scripts/test_batch_40.py --real --confirm

    # 3. Chạy với dự án cụ thể hoặc đổi file storyboard:
    python scripts/test_batch_40.py --file configs/batch_40_storyboard.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_shots(file_path: Path) -> List[Dict[str, Any]]:
    """Loads shots from either .json or .txt format."""
    if not file_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file kịch bản: {file_path}")

    if file_path.suffix.lower() == ".json":
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if "shots" in data:
            return data["shots"]
        elif isinstance(data, list):
            return data
        raise ValueError("File JSON không chứa danh sách 'shots'.")

    # .txt format: 1 prompt per line, skip comments and empty lines
    shots: List[Dict[str, Any]] = []
    lines = file_path.read_text(encoding="utf-8").splitlines()
    idx = 1
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        shots.append({
            "id": f"shot_{idx:03d}",
            "prompt": line,
            "mode": "t2i",
        })
        idx += 1
    return shots


def check_api_server(base_url: str) -> bool:
    """Checks if WebUI API server is alive."""
    try:
        req = urllib.request.Request(f"{base_url}/api/status", headers={"User-Agent": "rev-flow-test"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def run_via_api(
    base_url: str,
    shots: List[Dict[str, Any]],
    project_id: Optional[str],
    dry_run: bool,
    confirm: bool,
    dest_dir: Optional[str] = None,
) -> int:
    """Submits batch to WebUI /api/batch and streams SSE logs."""
    payload: Dict[str, Any] = {
        "aspect": 3,
        "dry_run": dry_run,
        "confirm": confirm,
        "items": shots,
    }
    if project_id:
        payload["project_id"] = project_id
    if dest_dir:
        payload["dest_dir"] = dest_dir

    post_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/batch",
        data=post_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    print(f"\n[+] Đang gửi yêu cầu batch {len(shots)} ảnh tới WebUI server ({base_url})...")
    print(f"    - Chế độ: {'DRY-RUN (0 credit)' if dry_run else 'CHẠY THẬT (tốn credit)'}")
    print(f"    - Dự án: {project_id if project_id else '(Tự động tạo / quản lý theo từng account)'}")

    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(f"[!] Lỗi gửi batch ({e.code}): {err_msg}", file=sys.stderr)
        return 1

    job_id = res_json.get("job_id")
    print(f"[+] Khởi tạo thành công! Job ID: {job_id}")
    print(f"[+] Đang theo dõi tiến trình qua API...\n")

    last_event_idx = 0
    last_done = 0
    total = len(shots)
    start_time = time.time()

    try:
        while True:
            try:
                job_req = urllib.request.Request(
                    f"{base_url}/api/jobs/{job_id}",
                    headers={"User-Agent": "rev-flow-test"},
                )
                with urllib.request.urlopen(job_req, timeout=5.0) as resp:
                    job_data = json.loads(resp.read().decode("utf-8"))
            except Exception:
                time.sleep(0.8)
                continue

            events = job_data.get("events", [])
            while last_event_idx < len(events):
                ev = events[last_event_idx]
                last_event_idx += 1
                msg = ev.get("message", "")
                if msg:
                    print(f"  {msg}", flush=True)

            res = job_data.get("result") or {}
            done = (res.get("ok", 0) + res.get("dry_run", 0) + res.get("failed", 0) + res.get("skipped", 0))
            if done != last_done and total > 0:
                pct = (done / total * 100)
                bar_len = 25
                filled = int(bar_len * done / total)
                bar = "=" * filled + "-" * (bar_len - filled)
                print(f"\r  [{bar}] {done}/{total} ({pct:5.1f}%) | running: {res.get('accounts', [])}", end="", flush=True)
                last_done = done

            state = job_data.get("state")
            if state in ("succeeded", "failed", "canceled"):
                print(f"\n\n[+] Job kết thúc với trạng thái: {state.upper()}", flush=True)
                err = job_data.get("error")
                if err:
                    print(f"[!] Chi tiết: {err}", flush=True)
                break

            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[!] Đã nhận tín hiệu dừng (Ctrl+C). Đang hủy job...")
        cancel_req = urllib.request.Request(
            f"{base_url}/api/jobs/{job_id}/cancel",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(cancel_req, timeout=5.0)
            print("[+] Đã gửi yêu cầu hủy.")
        except Exception as ce:
            print(f"[!] Không thể gửi hủy: {ce}")
        return 1

    elapsed = time.time() - start_time
    print("\n" + "=" * 65)
    print(" BÁO CÁO KẾT QUẢ BATCH 40 ẢNH")
    print("=" * 65)
    print(f"  Tổng số ảnh:        {total}")
    print(f"  Thời gian hoàn tất: {elapsed:.1f}s")
    if last_done > 0:
        print(f"  Tốc độ trung bình:  {elapsed / last_done:.2f}s/ảnh")
    print(f"  Xem chi tiết & ảnh: {base_url}")
    print("=" * 65 + "\n")
    return 0


def run_standalone(
    shots: List[Dict[str, Any]],
    project_id: Optional[str],
    dry_run: bool,
    dest_dir: Optional[str] = None,
) -> int:
    """Runs batch directly using src.Workflows.batch_runner when WebUI is offline."""
    import asyncio
    from src.WebUI.jobs import BatchRunner
    from src.Workflows.account_pool import AccountPool

    print("[*] WebUI server không mở, chuyển sang chạy trực tiếp (Standalone Runner)...")
    pool = AccountPool.from_config()
    print(f"[*] Account pool: {pool.summary()}")

    runner = BatchRunner(
        pool=pool,
        dest_dir=Path(dest_dir) if dest_dir else Path("out/outputs") / f"batch_40_{int(time.time())}",
        dry_run=dry_run,
        project_id=project_id,
    )

    class CLIJob:
        def log(self, msg: str):
            print(f"  {msg}")
        def progress(self, done: int, total: int, cur: str = ""):
            print(f"\r  Tiến độ: {done}/{total} ({cur[:35]}...)", end="", flush=True)

    print(f"[+] Bắt đầu chạy {len(shots)} ảnh (dry_run={dry_run})...")
    res = asyncio.run(runner.run(shots, job_ctx=CLIJob()))
    print(f"\n[+] Kết quả hoàn thành: {res.summary()}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Script kiểm thử chạy Batch 40 ảnh (10 Concept + 30 Storyboard) trên Google Flow"
    )
    parser.add_argument(
        "--file",
        type=str,
        default="configs/batch_40_storyboard.json",
        help="Đường dẫn file kịch bản (.json hoặc .txt). Mặc định: configs/batch_40_storyboard.json",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://127.0.0.1:8787",
        help="Địa chỉ WebUI server API (mặc định: http://127.0.0.1:8787)",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="UUID dự án Flow (để trống để từng account tự tạo hoặc dùng dự án riêng)",
    )
    parser.add_argument(
        "--dest-dir",
        type=str,
        default=None,
        help="Thư mục lưu ảnh tải về (mặc định: out/outputs/batch_YYYYMMDD_HHMMSS)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Chạy chế độ thử nghiệm (0 credit, test điều phối tài khoản & giao thức)",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        default=False,
        help="Chạy thật tạo ảnh trên Google Flow (tiêu tốn credit)",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Xác nhận cho phép trừ credit khi chạy thật (--real)",
    )

    args = parser.parse_args()

    # Safety logic: default to dry-run unless --real is explicitly set
    dry_run = True
    if args.real:
        if not args.confirm:
            print("[!] CẢNH BÁO AN TOÀN: Khi dùng --real, bạn PHẢI truyền thêm cờ --confirm để xác nhận trừ credit.", file=sys.stderr)
            print("    Ví dụ: python scripts/test_batch_40.py --real --confirm", file=sys.stderr)
            return 1
        dry_run = False
    elif not args.dry_run:
        # Default safety: prompt user or default dry_run
        print("[i] Mặc định chạy ở chế độ DRY-RUN (0 credit).")
        print("    Để chạy thật, hãy thêm cờ: --real --confirm\n")
        dry_run = True

    story_path = PROJECT_ROOT / args.file
    try:
        shots = load_shots(story_path)
    except Exception as e:
        print(f"[!] Lỗi đọc file kịch bản: {e}", file=sys.stderr)
        return 1

    print(f"[+] Đã tải {len(shots)} shots từ: {story_path.relative_to(PROJECT_ROOT)}")

    # Check WebUI API
    if check_api_server(args.api_url):
        return run_via_api(
            base_url=args.api_url,
            shots=shots,
            project_id=args.project,
            dry_run=dry_run,
            confirm=args.confirm or dry_run,
            dest_dir=args.dest_dir,
        )
    else:
        return run_standalone(
            shots=shots,
            project_id=args.project,
            dry_run=dry_run,
            dest_dir=args.dest_dir,
        )


if __name__ == "__main__":
    sys.exit(main())
