# Flow Bench — Playground tạo ảnh Google Flow

> UI web local để chạy **bridge mode** (đã kiểm chứng ở Phase 4): điều khiển CloakBrowser
> qua CDP, "mượn" token reCAPTCHA do chính app Flow mint, rồi fire request do ta dựng.
> Backend: `src/WebUI/` (FastAPI). Frontend: `web/` (React 19 + Vite + Tailwind v4).
> Không dùng browser-use / browser-harness trong vòng lặp vận hành.

---

## 1. Quy tắc credit (quan trọng nhất)

| Thao tác | Credit |
| :--- | :--- |
| `status`, `pool`, `node/options` | **0** |
| `Dry-run` node (nav → type → click → capture → build, không fire) | **0** |
| Node ảnh / video chạy thật, được Google nhận | **~1 credit mỗi node** |
| Node ảnh / video bị Google từ chối | **0 credit** |

- Mọi real run **bắt buộc** qua dialog xác nhận trên canvas (xem §4.3).
- Breaker đang mở (cooldown sau lỗi phiên/anti-busy) → job trả lỗi ngay, không fire.
- Job `node_*` là đơn vị tính credit: **số node chạy thật = số lần tiêu credit tối đa**.

---

## 2. Chuẩn bị (mỗi phiên)

1. **Profile trong `browser_vault/` đã đăng nhập Google** (mặc định `flow_main`). Server (pool) **tự đánh
   thức browser khi có job** — không cần mở tay; PID do pool quản lý ghi vào `out/pids/<profile>.pid`.
   Muốn mở trước thủ công vẫn được:

   ```bash
   python src/BrowserHost/launch_profile.py --profile flow_main --wait
   ```

2. Tab Flow sẽ được job tự điều hướng, không cần mở sẵn. Nếu đang mở tab khác trong browser,
   job vẫn tự tìm/tạo tab `flow.google.com`.
3. Python deps (fastapi, uvicorn, playwright, pydantic) + Chromium của Playwright.

> Lưu ý: trong lúc job chạy, **không thao tác** vào tab Flow của CloakBrowser (job đang type/click).
> Hết job, trang project được reload sạch, dùng lại bình thường.

---

## 3. Khởi động server

```bash
python -m src.WebUI.app              # http://127.0.0.1:4000
python -m src.WebUI.app --open       # mở UI luôn bằng browser mặc định
# flags khác: --host, --port, --cdp-url (bind account đầu tiên), --out
```

Nếu UI báo "UI chưa build" → build frontend:

```bash
cd web && npm install && npm run build   # trên Windows dùng cmd: npm ...
```

(Server serve static từ `web/dist`; sửa frontend thì build lại, không cần restart server.)

---

## 4. Sử dụng UI

UI chỉ có **một màn hình: bảng canvas**. Không còn tab "Tạo ảnh", "Tạo video", "Video Thử Đồ",
"Thư viện" hay "Hướng dẫn" — những thứ đó đã được chuyển thành node + Settings modal.

### 4.1 Khung màn hình

| Vùng | Nội dung |
| :--- | :--- |
| **TopBar** | Logo · chọn/quản lý Project · **Kho Assets** (phím `A`) · **Mẫu Workflow** · Chạy Workflow · chip Pool · nút Settings |
| **Canvas** (toàn màn hình) | 4 loại node: `ref` (ảnh tham chiếu), `image`, `video`, `last_frame`. Kéo thả, nối nguồn, nhóm (group) là đơn vị chạy độc lập |
| **Kho Assets** (drawer trái) | Ảnh đã tải lên / kết quả đã sinh của project, ghim, kéo vào canvas |
| **Settings modal** | 5 tab: Thư viện · Tài khoản (pool) · AI Agent · Hướng dẫn · Docs API |

### 4.2 Project

Hai khái niệm project song song — đừng lẫn:

- **Workspace project** (local): nhóm canvas + viewport + quyền sở hữu asset. Quản lý qua nút Project trên
  TopBar (`ProjectManagerModal`): tạo / đổi tên / nhân bản / xoá / đặt thumbnail. Canvas tự lưu (autosave).
- **Flow project** (Google UUID): nơi ảnh/video thực sự được sinh ra. Không cần chọn tay — mỗi workspace
  project được map sang một Flow project riêng theo từng account, và được **tạo tự động** ở lần chạy đầu
  (`MediaService.resolve_project`).

### 4.3 Chạy node & workflow

- **Chạy 1 node**: nút Run trên thân node → dialog xác nhận (credit ước tính) → job `node_image` /
  `node_video` / `node_last_frame`.
- **Chạy Workflow** (TopBar): chạy toàn bộ canvas theo nhóm. Mỗi **group là một đơn vị độc lập** —
  node lỗi chỉ dừng nhóm đó, các nhóm khác vẫn chạy tiếp. Có thể chọn vùng (chọn node) để chỉ chạy các
  nhóm liên quan.
- **Dry-run (0 credit)**: chạy đúng pipeline nhưng chặn request của app để thu capture và dựng body của ta.
  Dùng để kiểm tra prompt/selector trước khi tiêu credit.
- Tiến trình realtime: node đổi màu theo trạng thái, log xem trong drawer phải của node (tab Logs / Error).

### 4.4 Dữ liệu trên canvas

- Node `ref` nhận ảnh upload hoặc kéo từ Kho Assets.
- Node `image` → ra ảnh; node `video` → ra video (có thể nhận ảnh/frame từ node trước làm frame đầu).
- Node `last_frame` → cắt frame cuối của video để nối chuỗi video tiếp theo.
- Thư viện: Settings → **Thư viện** (quét `out/playground/*/meta.json`, chỉ hiện run có file thật).

---

## 5. Pool N tài khoản

- Mỗi profile trong `browser_vault/` là 1 account của pool (`flow_main` + profile khác nếu bạn thêm).
  Tuỳ chọn cấu hình tại `configs/accounts_pool.json` (`target_jobs_per_account`, `max_active_browsers`,
  `port_base`, danh sách `accounts`); không có file / danh sách rỗng → pool tự dò profile trong vault
  (giữ nguyên hành vi setup 1 tài khoản cũ).
- **Browser mở theo nhu cầu (on-demand):** account chỉ được đánh thức khi được cấp cho job; pool ghi PID
  vào `out/pids/<profile>.pid` để chỉ đóng browser *do pool mở* khi hibernate (browser bạn tự mở →
  `not_managed`, pool không đóng).
- **Số account chạy song song:** `N_alloc = min(N_avail, M_RAM, max(1, ⌈J / Q_target⌉))` — J = số job,
  `Q_target` = job/account (mặc định 25), `M_RAM` = trần browser song song (mặc định 4). Sửa trong
  Settings → **Tài khoản** hoặc `POST /api/pool/config`.
- **Hot spare & failover:** account không được cấp ở trạng thái *standby*. Khi account đang chạy dính
  429/401/403 hoặc cooldown, pool tự thăng cấp 1 standby thay thế; job đang dở được trả về hàng đợi
  (tối đa 2 lần thử/job). Breaker/cooldown lưu riêng từng account tại `out/breakers/<account>.json`.
- Chip **Pool** trên TopBar: hover để xem danh sách account (port, đang mở/standby, cooldown).
- CRUD account (thêm/xoá/sửa proxy/port) nằm ở Settings → **Tài khoản**.

---

## 6. Artifact & trạng thái lưu trên đĩa

| Đường dẫn | Nội dung |
| :--- | :--- |
| `out/playground/<ts>_<slug>/meta.json` | metadata run (status, seed, seed_echo, media_id, file, elapsed…) |
| `out/playground/<ts>_<slug>/app_request_body.txt` | body app Flow (capture, bị chặn) |
| `out/playground/<ts>_<slug>/our_request_body.txt` + `our_args.pretty.json` | request của ta (dựng từ builder) |
| `out/playground/<ts>_<slug>/response.txt` | response batchexecute (chỉ có khi real run) |
| `out/playground/<ts>_<slug>/*.jpg` | ảnh đã tải |
| `out/playground_projects.json` | registry Flow project (do `MediaService` tự cập nhật) |
| `out/bridge_state.json` | circuit breaker CLI/legacy (UI pool dùng `out/breakers/`) |
| `out/pool_state.json` | trạng thái pool (role, counters, `last_used_at` từng account) |
| `out/breakers/<account>.json` | circuit breaker riêng từng account |
| `out/pids/<profile>.pid` | PID browser do pool mở (để hibernate an toàn) |
| `configs/reference_media_cache.json` | cache template i2i theo account + sha256 (gitignored) |

Job history chỉ nằm trong RAM; restart server không mất ảnh/artifacts đã tạo.

---

## 7. API (dùng được bằng script)

| Method + path | Ghi chú |
| :--- | :--- |
| `GET /api/status` | health: CDP, browser, tab Flow, breaker |
| `GET /api/pool` | snapshot pool: accounts (port, status, role), N_alloc, cooldown, cache i2i |
| `POST /api/pool/config` `{"target_jobs_per_account": 25, "max_active_browsers": 4}` | sửa Q_target / trần browser song song |
| `GET /api/pool/accounts/{id}/wake` / `.../hibernate` / `.../reset` | đánh thức / hạ nhiệt / reset account |
| `POST /api/node/image` · `POST /api/node/video` · `POST /api/node/last_frame` | **job của canvas** — một node = một lần gọi độc lập |
| `GET /api/node/options` | option thật của composer (tỷ lệ, model, giới hạn) — nguồn chân lý duy nhất |
| `GET /api/jobs` / `GET /api/jobs/{id}` | job list / chi tiết kèm events |
| `GET /api/gallery` | danh sách run có ảnh |
| `GET /api/files/{run}/{file}` | file trong run dir |
| `GET /api/circuit/clear[?account=<id>]` | reset cooldown breaker (mặc định **mọi account**, idempotent) |

Ví dụ chạy một node ảnh bằng script (sau khi tự chịu trách nhiệm credit):

```bash
curl -X POST http://127.0.0.1:4000/api/node/image -H "Content-Type: application/json" \
  -d '{"prompt":"một chú vịt vàng bơi hồ","aspect_ratio":"9:16"}'
# → {"job_id": "j_..."}  → poll GET /api/jobs/{job_id}
```

---

## 8. Lỗi thường gặp

| Hiện tượng | Xử lý |
| :--- | :--- |
| "Browser offline" | CloakBrowser chưa mở / chưa đăng nhập → mục 2 |
| "Chưa thấy tab Flow" | Mở `flow.google.com` trong CloakBrowser hoặc bấm refresh |
| `423` khi chạy thật | Breaker/account pool đang cooldown (chi tiết khi hover chip **Pool**). Chờ hết cooldown — kiểm tra phiên đăng nhập trước khi dùng `/api/circuit/clear` |
| `rejected [3]` | Tham số sai (ví dụ seed ngoài int32) — lỗi của ta, 0 credit, sửa tham số rồi chạy lại |
| `rejected [7]` (UNUSUAL_ACTIVITY) | Anti-abuse; client tự backoff 120 s và retry 1 lần; 3 lần liên tiếp → breaker 30 phút |
| `401/403` | Phiên Google hỏng → đăng nhập lại trong CloakBrowser; breaker 30 phút |
| Job "không tìm thấy ô prompt" | UI Flow đổi cấu trúc → cập nhật selector `div.ProseMirror` / `button.generate-icon-button` trong `src/Bridge/flow_bridge.py` |
| Job i2i báo "không thấy `<input type=file>` trong composer" | UI Flow đổi → chạy `python discovery/probe_i2i_composer.py --fresh --project <uuid>` rồi làm theo `docs/api_specs/flow_image2image.md` §4 |
---

## 9. Ghi chú kỹ thuật

- Bridge **không bao giờ** gọi `browser.close()` — chỉ `playwright.stop()` (disconnect). Browser
  của user giữ nguyên trạng thái.
- Hook fetch (block+capture `ogiZ0b`) chỉ bật trong lúc job chạy và tự disarm; cuối mỗi lần
  generate trang được reload sạch.
- Token reCAPTCHA / `at` / `_reqid` **luôn đọc tươi** từ capture của app, không hard-code.
- Ảnh test UI (QA): `out/ui_shots/` (gitignored).

Xem thêm: `docs/api_specs/flow_transport.md` (bridge mode), `docs/api_specs/flow_create_image.md`,
`docs/api_specs/node_media_api.md` (lớp node của canvas), `src/Workflows/account_pool.py` (N-account pool).
