import { Lightning } from "@phosphor-icons/react";
import { TERMINAL_STATES } from "../../jobLifecycle";
import { BASE } from "./base";
import { CodeBlock } from "./CodeBlock";

// --------------------------------------------------------------------------- //
// Quickstart snippets
// --------------------------------------------------------------------------- //

const CURL_START = `# 1) Tạo ảnh thử (0 credit), phản hồi ngay với job_id
curl -s -X POST ${BASE}/api/generate \\
  -H "content-type: application/json" \\
  -d '{"project_id":"3f9a2c1b7e","prompt":"Bình minh trên vịnh, ống kính 35mm","aspect":3,"dry_run":true}'

# 2) Poll đến khi state là succeeded / failed / rejected
curl -s ${BASE}/api/jobs/j_20261019_170000_ab12cd`;

const PY_START = `import time

import requests

BASE = "${BASE}"


def wait_job(job_id: str, timeout_s: int = 300) -> dict:
    """Poll job cho tới khi kết thúc."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        job = requests.get(f"{BASE}/api/jobs/{job_id}", timeout=10).json()
        if job["state"] in (${TERMINAL_STATES.map((s) => `"${s}"`).join(", ")}):
            return job
        time.sleep(1.5)
    raise TimeoutError(job_id)


# Chạy thật: confirm=True, khoảng 1 credit/ảnh nếu Google không từ chối
r = requests.post(
    f"{BASE}/api/generate",
    json={
        "project_id": "3f9a2c1b7e",
        "prompt": "Bình minh trên vịnh, ống kính 35mm",
        "aspect": 3,
        "seed": 1647032552,
        "dry_run": False,
        "confirm": True,
    },
    timeout=15,
)
job = wait_job(r.json()["job_id"])
print(job["state"], (job.get("result") or {}).get("image_url"))`;

export function StartIntro() {
  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-ctl border border-line2 bg-panel2 p-4">
        <h3 className="mb-2 text-[13px] font-bold text-fg">Quy tắc chung</h3>
        <ul className="list-disc list-inside space-y-1.5 text-[12.5px] leading-relaxed text-dim marker:text-mut">
          <li>
            <strong className="text-fg">Base URL:</strong>{" "}
            <code className="font-mono text-acc">{BASE}</code>, server chỉ nghe trên localhost nên
            không cần header xác thực.
          </li>
          <li>
            <strong className="text-fg">Bất đồng bộ:</strong> endpoint tạo job trả về{" "}
            <code className="font-mono text-acc">job_id</code>, sau đó poll{" "}
            <code className="font-mono text-acc">GET /api/jobs/{"{id}"}</code> đến khi{" "}
            <code className="font-mono text-acc">state</code> là succeeded, failed hoặc rejected.
          </li>
          <li>
            <strong className="text-fg">Xác nhận chi phí:</strong> chạy thật cần{" "}
            <code className="font-mono text-acc">confirm: true</code>;{" "}
            <code className="font-mono text-acc">dry_run: true</code> chạy thử toàn pipeline với 0
            credit.
          </li>
          <li>
            <strong className="text-fg">Lỗi:</strong> HTTP 4xx/5xx kèm thân{" "}
            <code className="font-mono text-acc">{'{"detail": "..."}'}</code>; mã 423 nghĩa là mọi
            account đang cooldown hoặc bị tắt.
          </li>
        </ul>
      </div>

      <CodeBlock label="curl: tạo ảnh thử rồi poll job" code={CURL_START} />
      <CodeBlock label="python: client tối giản" code={PY_START} />
    </div>
  );
}
