import { ListChecks, Lightning, Users } from "@phosphor-icons/react";
import { JOB_POLL_MS, TERMINAL_STATES } from "../../jobLifecycle";
import { BASE } from "./base";
import { StartIntro } from "./quickstart";
import type { Group } from "./types";

// --------------------------------------------------------------------------- //

export const GROUPS: Group[] = [
  {
    key: "start",
    label: "Bắt đầu",
    icon: <Lightning size={14} />,
    extra: <StartIntro />,
    endpoints: [
      {
        method: "GET",
        path: "/api/status",
        title: "Sức khỏe bridge",
        desc: "Kiểm tra kết nối CDP tới CloakBrowser, tab Flow đang mở, độ sâu hàng đợi job và snapshot circuit breaker. Không đánh thức trình duyệt nào.",
        tryIt: true,
        curl: `curl -s ${BASE}/api/status`,
        res: `{
  "cdp_url": "http://127.0.0.1:4022",
  "cdp_ok": true,
  "browser": "Chrome/131",
  "flow_tab_url": "https://labs.google/fx/tools/image-fx",
  "flow_project_id": null,
  "page_targets": 4,
  "cooldown_until_ms": 0,
  "queue_depth": 0,
  "current_job_id": null,
  "breaker": {
    "cooldown_remaining_s": 0,
    "cooldown_reason": null,
    "total_accepted": 12,
    "total_rejected": 1,
    "consecutive_anti_abuse": 0
  }
}`,
      },
    ],
  },
  {
    key: "jobs",
    label: "Jobs & Ảnh",
    icon: <ListChecks size={14} />,
    endpoints: [
      {
        method: "GET",
        path: "/api/jobs?limit=30",
        title: "Danh sách job",
        desc: "Liệt kê các job gần nhất, không kèm events để giữ payload nhẹ.",
        tryIt: true,
        curl: `curl -s "${BASE}/api/jobs?limit=30"`,
        res: `{
  "jobs": [
    {
      "id": "j_20261019_170230_cd34ef",
      "kind": "node_image",
      "state": "succeeded",
      "created_ms": 1760862000123,
      "event_count": 42,
      "result": { "status": "ok", "run_id": "20261019_170230_a1b2c3", "file_url": "/api/node/files/20261019_170230_a1b2c3/image.jpg" }
    }
  ]
}`,
      },
      {
        method: "GET",
        path: "/api/jobs/{jid}",
        title: "Chi tiết 1 job (poll)",
        desc: "Chi tiết một job kèm toàn bộ events. Đây là endpoint poll cho mọi thao tác bất đồng bộ.",
        notes: [
          `state nhận các giá trị: queued, running, ${TERMINAL_STATES.join(", ")}.`,
          `Frontend poll mỗi ${JOB_POLL_MS}ms, script bên ngoài nên poll cách 1 đến 2 giây.`,
          "events là mảng {i, ts_ms, kind, message, data}, dùng làm nhật ký hiển thị.",
          "404 nếu job không tồn tại.",
        ],
        curl: `curl -s ${BASE}/api/jobs/j_20261019_170230_cd34ef`,
        res: `{
  "id": "j_20261019_170230_cd34ef",
  "kind": "generate",
  "params": { "project_id": "3f9a2c1b7e", "prompt": "Bình minh hy vọng", "aspect": 3 },
  "state": "succeeded",
  "created_ms": 1760862000123,
  "started_ms": 1760862000400,
  "finished_ms": 1760862041600,
  "result": { "status": "ok", "image_url": "/api/files/run_20261019_151012_8f3a/image_001.jpg", "seed_echo": 1647032552 },
  "error": null,
  "event_count": 6,
  "events": [
    { "i": 0, "ts_ms": 1760862000400, "kind": "info", "message": "mở tab Flow", "data": {} }
  ]
}`,
      },
      {
        method: "POST",
        path: "/api/jobs/{jid}/cancel",
        title: "Dừng job đang chạy",
        desc: "Đánh dấu job cần dừng. Các bước đang chờ (retry backoff của node Ảnh/Video) hủy ngay trong ~250ms, không phải chờ hết thời gian đếm ngược.",
        notes: [
          "Dùng khi node đang ở trạng thái [Retry 1/2] hoặc [Retry 2/2] và bạn muốn dừng luồng.",
          "Job đã kết thúc (succeeded/failed/rejected) thì chỉ trả về trạng thái hiện tại, không lỗi.",
          "Node đang chờ sẽ kết thúc với state=failed và error nêu rõ 'đã dừng theo yêu cầu'.",
        ],
        tryIt: true,
        curl: `curl -s -X POST ${BASE}/api/jobs/j_20261019_170230_cd34ef/cancel`,
        res: `{
  "ok": true,
  "state": "running",
  "cancelled": true
}`,
      },
      {
        method: "GET",
        path: "/api/gallery",
        title: "Lịch sử ảnh đã tạo",
        desc: "Đọc meta.json của mọi run trong out/playground, mới nhất đứng đầu. Đây là nguồn dữ liệu cho tab Thư viện.",
        tryIt: true,
        curl: `curl -s ${BASE}/api/gallery`,
        res: `{
  "runs": [
    {
      "run": "run_20261019_151012_8f3a",
      "file": "image_001.jpg",
      "url": "/api/files/run_20261019_151012_8f3a/image_001.jpg",
      "prompt": "Bình minh hy vọng, nhìn từ phía sau",
      "seed": 1647032552,
      "resolution": [1376, 768],
      "created_ts": "2026-10-19T15:10:42.318",
      "elapsed_s": 41.2,
      "status": "ok"
    }
  ]
}`,
      },
      {
        method: "GET",
        path: "/api/files/{run}/{name}",
        title: "Tải file ảnh của run",
        desc: "Trả file ảnh gốc. Server ép đường dẫn nằm trong out/playground nên không đọc ra ngoài được.",
        curl: `curl -s -o image.jpg ${BASE}/api/files/run_20261019_151012_8f3a/image_001.jpg`,
      },
      {
        method: "POST",
        path: "/api/upload_reference",
        title: "Upload ảnh tham chiếu i2i",
        desc: "Nhận ảnh tham chiếu dạng multipart/form-data, lưu vào out/references/. Dùng làm node ref hoặc đính vào node ảnh.",
        notes: ["Thân request là multipart với field file, không phải JSON."],
        curl: `curl -s -X POST ${BASE}/api/upload_reference -F "file=@./shot_001.jpg"`,
        res: `{
  "ok": true,
  "path": "out/references/1760862000123_shot_001.jpg",
  "filename": "1760862000123_shot_001.jpg",
  "url": "/api/references/1760862000123_shot_001.jpg",
  "size": 483921
}`,
      },
      {
        method: "GET",
        path: "/api/references/{name}",
        title: "Xem ảnh tham chiếu",
        desc: "Phục vụ lại ảnh đã upload, dùng để xem trước trong UI trước khi gắn vào node.",
        curl: `curl -s -o ref.jpg ${BASE}/api/references/1760862000123_shot_001.jpg`,
      },
    ],
  },
  {
    key: "pool",
    label: "Pool & Tài khoản",
    icon: <Users size={14} />,
    endpoints: [
      {
        method: "GET",
        path: "/api/pool",
        title: "Snapshot toàn bộ pool",
        desc: "Số account, working set hiện tại và trạng thái từng account. Không đánh thức trình duyệt nào.",
        tryIt: true,
        curl: `curl -s ${BASE}/api/pool`,
        res: `{
  "n_total": 2,
  "n_available": 2,
  "target_jobs_per_account": 25,
  "max_active_browsers": 4,
  "working_set": ["flow_main"],
  "accounts": [
    {
      "id": "flow_main",
      "profile_id": "flow_main",
      "cdp_port": 4022,
      "enabled": true,
      "running": true,
      "status": "ready",
      "role": "active",
      "cooldown_remaining_s": 0,
      "total_completed": 12,
      "total_rejected": 1
    }
  ],
  "reference_cache": { "accounts": 2, "entries": 12 }
}`,
      },
      {
        method: "POST",
        path: "/api/pool/config",
        title: "Cấu hình tải pool",
        desc: "Lưu hai nút điều tải của pool, có hiệu lực ngay cho job kế tiếp.",
        notes: [
          "target_jobs_per_account trong 1..500, mặc định 25 ảnh mỗi account.",
          "max_active_browsers trong 1..16, mặc định 4, mỗi CloakBrowser tốn khoảng 500MB RAM.",
        ],
        body: `{
  "target_jobs_per_account": 25,
  "max_active_browsers": 4
}`,
        curl: `curl -s -X POST ${BASE}/api/pool/config \\
  -H "content-type: application/json" \\
  -d '{"target_jobs_per_account":25,"max_active_browsers":4}'`,
        res: `{
  "ok": true,
  "target_jobs_per_account": 25,
  "max_active_browsers": 4
}`,
      },
      {
        method: "POST",
        path: "/api/pool/accounts",
        title: "Thêm account",
        desc: "Thêm một account vào pool, mặc định tự tạo thư mục profile trong browser_vault với seed ngẫu nhiên 8 số.",
        notes: [
          "id và profile_id chỉ dùng chữ, số và gạch nối, không nhận _template.",
          "Bỏ trống cdp_port thì server tự chọn cổng trống thấp nhất.",
          "Đặt create_profile = false nếu profile đã tồn tại.",
        ],
        body: `{
  "id": "acc_02",
  "cdp_port": 4023,
  "enabled": true,
  "note": "Acc dự phòng",
  "create_profile": true
}`,
        curl: `curl -s -X POST ${BASE}/api/pool/accounts \\
  -H "content-type: application/json" \\
  -d '{"id":"acc_02","cdp_port":4023,"enabled":true,"note":"Acc dự phòng"}'`,
        res: `{
  "ok": true,
  "account": {
    "id": "acc_02",
    "profile_id": "acc_02",
    "cdp_port": 4023,
    "enabled": true,
    "note": "Acc dự phòng"
  }
}`,
      },
      {
        method: "PATCH",
        path: "/api/pool/accounts/{aid}",
        title: "Sửa account",
        desc: "Cập nhật một phần thông tin account: bật tắt, ghi chú hoặc đổi cổng CDP.",
        body: `{
  "enabled": false,
  "note": "Tạm nghỉ",
  "cdp_port": 4025
}`,
        curl: `curl -s -X PATCH ${BASE}/api/pool/accounts/acc_02 \\
  -H "content-type: application/json" \\
  -d '{"enabled":false,"note":"Tạm nghỉ"}'`,
        res: `{
  "ok": true,
  "account": {
    "id": "acc_02",
    "profile_id": "acc_02",
    "cdp_port": 4023,
    "enabled": false,
    "note": "Tạm nghỉ"
  }
}`,
      },
      {
        method: "DELETE",
        path: "/api/pool/accounts/{aid}",
        title: "Xóa account",
        desc: "Gỡ account khỏi pool, luôn đóng trình duyệt của account đó trước khi xóa.",
        notes: [
          "Tham số query delete_vault = true sẽ xóa luôn thư mục browser_vault của profile, không thể hoàn tác.",
          "404 nếu account không tồn tại.",
        ],
        curl: `curl -s -X DELETE "${BASE}/api/pool/accounts/acc_02?delete_vault=false"`,
        res: `{
  "ok": true,
  "removed": "acc_02"
}`,
      },
      {
        method: "GET",
        path: "/api/pool/accounts/{aid}/detail",
        title: "Chi tiết 1 account",
        desc: "Dò trạng thái live: CDP còn sống không, tab Flow đang mở ở project nào, số liệu hoàn tất và từ chối.",
        curl: `curl -s ${BASE}/api/pool/accounts/flow_main/detail`,
        res: `{
  "account": {
    "id": "flow_main",
    "profile_id": "flow_main",
    "cdp_port": 4022,
    "cdp_url": "http://127.0.0.1:4022",
    "enabled": true,
    "running": true,
    "managed": true,
    "status": "ready",
    "total_completed": 12,
    "total_rejected": 1,
    "total_failed": 0
  },
  "flow": {
    "cdp_ok": true,
    "flow_tab_url": "https://labs.google/fx/tools/image-fx",
    "flow_project_id": "3f9a2c1b7e",
    "browser": "Chrome/131"
  }
}`,
      },
      {
        method: "POST",
        path: "/api/pool/accounts/{aid}/wake",
        title: "Đánh thức / ngủ / reset",
        desc: "wake đánh thức trình duyệt và đưa vào working set, hibernate đóng để giải phóng RAM, reset xóa cooldown và lỗi cuối.",
        notes: [
          "Chỉ đổi segment cuối: /wake, /hibernate hoặc /reset.",
          "wake trả errors rỗng khi mọi thứ tốt; reset luôn trả ok = true.",
        ],
        curl: `curl -s -X POST ${BASE}/api/pool/accounts/flow_main/wake \\
  -H "content-type: application/json" \\
  -d '{}'`,
        res: `{
  "ok": true,
  "errors": []
}`,
      },
      {
        method: "GET",
        path: "/api/pool/next_port",
        title: "Cổng CDP tiếp theo",
        desc: "Cổng CDP thấp nhất chưa account nào dùng, dành cho thêm account thủ công.",
        tryIt: true,
        curl: `curl -s ${BASE}/api/pool/next_port`,
        res: `{
  "next_port": 4024
}`,
      },
      {
        method: "GET",
        path: "/api/circuit/clear",
        title: "Xóa cooldown breaker",
        desc: "Xóa thời gian chờ anti-abuse. Không truyền tham số thì reset toàn bộ pool.",
        notes: [
          "Thao tác có tác động thật: dùng khi bạn chắc chắn cooldown đã hết nguyên nhân.",
          "Dùng GET vì là reset idempotent, không chứa bí mật.",
          "Giới hạn theo một account bằng ?account=flow_main.",
        ],
        curl: `curl -s "${BASE}/api/circuit/clear?account=flow_main"`,
        res: `{
  "ok": true,
  "accounts": ["flow_main"]
}`,
      },
    ],
  },
];

export const TOTAL_EPS = GROUPS.reduce((n, g) => n + g.endpoints.length, 0);
