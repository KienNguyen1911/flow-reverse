# Flow Bench — Playground tạo ảnh Google Flow

> UI web local để chạy **bridge mode** (đã kiểm chứng ở Phase 4): điều khiển CloakBrowser
> qua CDP, "mượn" token reCAPTCHA do chính app Flow mint, rồi fire request do ta dựng.
> Backend: `src/WebUI/` (FastAPI). Frontend: `web/` (React 19 + Vite + Tailwind v4).
> Không dùng browser-use / browser-harness trong vòng lặp vận hành.

---

## 1. Quy tắc credit (quan trọng nhất)

| Thao tác | Credit |
| :--- | :--- |
| `status`, `refresh projects`, `create project` | **0** |
| `Dry-run` (nav → type → click → capture → build, không fire) | **0** |
| `Tạo ảnh` (fire thật) được Google nhận | **~1 credit** |
| `Tạo ảnh` bị Google từ chối | **0 credit** |
| `Dry-run` batch / capture template i2i (đính ảnh + chặn) | **0 credit** |
| Batch N ảnh (fire thật) | **≤ N credit** — chỉ tính ảnh Google nhận |

- Mọi real run **bắt buộc** qua dialog xác nhận trong UI. API cũng chặn: thiếu `confirm=true`
  thì `/api/generate` trả `400` và không có gì được gửi đi.
- Breaker đang mở (cooldown sau lỗi phiên/anti-busy) → `/api/generate` trả `423`.

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
python -m src.WebUI.app              # http://127.0.0.1:8787
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

### 4.1 Chọn dự án
- Dropdown "Dự án" load từ registry (`out/playground_projects.json`).
- `↻` refresh: gọi UpteDb qua bridge (0 credit) để cập nhật danh sách 6 dự án cloud.
- `+` tạo dự án mới (jHPbke, 0 credit, tạo **thật** trong tài khoản).
- `/><` (link icon) thêm dự án ngoài danh sách bằng UUID hoặc URL project.

### 4.2 Dry-run (0 credit)
Chạy đúng pipeline: nav về trang chủ → mở project → type prompt → click Generate (hook chặn
request của app, 0 credit) → đọc capture → dựng request của ta. Kết quả hiện trong thẻ
"Dry-run thành công" kèm seed + thư mục run. Dùng để kiểm tra trước khi tiêu credit.

### 4.3 Tạo ảnh thật (~1 credit)
1. Nhập prompt → bấm **Tạo ảnh** → dialog xác nhận hiện project/seed/prompt/credit.
2. Bấm **Tạo ảnh** trong dialog → job chạy (~20–40 s): fire request, long-poll, tải ảnh signed URL.
3. Kết quả: thẻ ảnh kèm seed (echo khớp = xác nhận kiểm soát tham số), kích thước, media id,
   nút tải ảnh + "Mở trong Flow". Trang project trong CloakBrowser cũng tự reload để ảnh hiện trên UI Flow.

### 4.4 Nhật ký job
- Job lẻ chạy 1 worker; batch chạy **1 worker thread cho mỗi account được cấp** (log có tiền tố account).
  Log realtime (poll 800 ms): timestamp, kind,
  message; chip trạng thái `Đang chờ / Đang chạy / Hoàn tất / Bị từ chối / Lỗi` + đồng hồ elapsed.
- Cuối job luôn có thẻ kết quả (dry-run / ảnh / reject / lỗi / tạo dự án / refresh).

### 4.5 Gallery
- Quét `out/playground/*/meta.json`; chỉ hiện run có file ảnh thật. Click thẻ để mở ảnh gốc.
- Ảnh phục vụ qua `/api/files/<run>/<file>` (serve local, không phụ thuộc signed URL đã hết hạn).

---

## 5. Pool N tài khoản & Batch

### 5.1 Cơ chế pool
- Mỗi profile trong `browser_vault/` là 1 account của pool (`flow_main` + profile khác nếu bạn thêm).
  Tuỳ chọn cấu hình tại `configs/accounts_pool.json` (`target_jobs_per_account`, `max_active_browsers`,
  `port_base`, danh sách `accounts`); không có file / danh sách rỗng → pool tự dò profile trong vault
  (giữ nguyên hành vi setup 1 tài khoản cũ).
- **Browser mở theo nhu cầu (on-demand):** account chỉ được đánh thức khi được cấp cho job; pool ghi PID
  vào `out/pids/<profile>.pid` để chỉ đóng browser *do pool mở* khi hibernate (browser bạn tự mở →
  `not_managed`, pool không đóng).
- **Số account chạy song song:** `N_alloc = min(N_avail, M_RAM, max(1, ⌈J / Q_target⌉))` — J = số ảnh,
  `Q_target` = ảnh/account (mặc định 25), `M_RAM` = trần browser song song (mặc định 4). Sửa nhanh trong
  UI (ô Q_target ở chế độ batch) hoặc `POST /api/pool/config`.
- **Hot spare & failover:** account không được cấp ở trạng thái *standby*. Khi account đang chạy dính
  429/401/403 hoặc cooldown, pool tự thăng cấp 1 standby thay thế; ảnh đang dở được trả về hàng đợi
  (tối đa 2 lần thử/ảnh). Breaker/cooldown lưu riêng từng account tại `out/breakers/<account>.json`.
- Chip **Pool** trên TopBar: hover để xem danh sách account (port, đang mở/standby, cooldown); chip
  "Batch N_alloc" hiện khi có account đang chạy.

### 5.2 Batch nhiều ảnh (t2i + i2i)
- Panel trái → bật **"Chế độ batch"**: mỗi dòng là 1 prompt/ảnh. Điền **"Ảnh tham chiếu i2i"** (đường
  dẫn file local) → *mọi dòng chạy i2i*; bỏ trống → t2i.
- Nút **Tạo batch (N ảnh)** mở dialog xác nhận (số ảnh, t2i/i2i, N_alloc dự kiến); **Batch dry-run**
  luôn 0 credit.
- Chạy theo **wave phụ thuộc** khi item có `depends_on_shot_id` (dùng qua API/storyboard JSON — ví dụ
  `configs/storyboard_100.json`): wave sau chờ ảnh anchor của wave trước, ảnh tham chiếu được resolve
  từ shot đã xong.
- Tiến độ per-item (status/mode/account/link ảnh) hiện trực tiếp trong khung Nhật ký khi batch đang chạy.
- Xong job: ảnh được copy sang `out/outputs/<slug dự án>/` (tên kiểu NLE `shot_XXX_t2i.jpg` /
  `shot_XXX_i2i.jpg`) để mang sang Premiere/Resolve.

### 5.3 i2i — template-replay (lần đầu 0 credit)
- Lần đầu dùng một ảnh tham chiếu trên một account: job **tự đính ảnh vào `<input type=file>` của app**,
  để app dựng request i2i, rồi **chặn lại** (0 credit) và lưu làm template — cache theo
  `account + sha256(file)` trong `configs/reference_media_cache.json` (gitignored).
- Các shot sau (cùng account, cùng ảnh): replay template với token reCAPTCHA/seed/prompt/UUID mới,
  **không upload lại**. Nhờ vậy batch i2i 100 ảnh chỉ "trả giá" capture 1 lần/account/ảnh tham chiếu.
- Đặc tả kỹ thuật + recipe discovery khi UI Flow đổi: `docs/api_specs/flow_image2image.md`.

---

## 6. Artifact & trạng thái lưu trên đĩa

| Đường dẫn | Nội dung |
| :--- | :--- |
| `out/playground/<ts>_<slug>/meta.json` | metadata run (status, seed, seed_echo, media_id, file, elapsed…) |
| `out/playground/<ts>_<slug>/app_request_body.txt` | body app Flow (capture, bị chặn) |
| `out/playground/<ts>_<slug>/our_request_body.txt` + `our_args.pretty.json` | request của ta (dựng từ builder) |
| `out/playground/<ts>_<slug>/response.txt` | response batchexecute (chỉ có khi real run) |
| `out/playground/<ts>_<slug>/*.jpg` | ảnh đã tải |
| `out/playground_projects.json` | registry dự án hiển thị trong UI |
| `out/bridge_state.json` | circuit breaker CLI/legacy (UI pool dùng `out/breakers/`) |
| `out/outputs/<slug>/` | ảnh batch đã xong (tên kiểu NLE `shot_XXX_t2i.jpg` / `shot_XXX_i2i.jpg`) |
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
| `POST /api/pool/accounts/{id}/wake` / `.../hibernate` / `.../reset` | đánh thức / hạ nhiệt / reset account |
| `GET /api/projects` | registry dự án |
| `POST /api/projects/refresh` | job UpteDb (0 credit) |
| `POST /api/projects/create` `{"title": "...", "confirm": true}` | job jHPbke (0 credit, tạo thật) |
| `POST /api/projects` `{"ref": "<uuid hoặc URL>"}` | thêm dự án ngoài danh sách (không gọi mạng) |
| `DELETE /api/projects/{id}` | bỏ khỏi registry (không xóa trên Google) |
| `POST /api/generate` | job `dry_run` (không cần confirm) hoặc `generate` (bắt buộc `confirm: true`; `423` nếu breaker mở) |
| `POST /api/batch` | batch `dry_run` (không cần confirm) hoặc chạy thật (`confirm: true`; `423` nếu toàn bộ account cooldown); nhận `items[]` hoặc `storyboard_path` |
| `GET /api/jobs` / `GET /api/jobs/{id}` | job list / chi tiết kèm events |
| `GET /api/gallery` | danh sách run có ảnh |
| `GET /api/files/{run}/{file}` | file trong run dir |
| `GET /api/circuit/clear[?account=<id>]` | reset cooldown breaker (mặc định **mọi account**, idempotent) |

Ví dụ chạy thật bằng script (sau khi tự chịu trách nhiệm credit):

```bash
curl -X POST http://127.0.0.1:8787/api/generate -H "Content-Type: application/json" \
  -d '{"project_id":"<uuid>","prompt":"một chú vịt vàng bơi hồ","dry_run":false,"confirm":true}'
```

Batch nhiều ảnh (kể cả i2i + phụ thuộc) bằng storyboard JSON:

```bash
curl -X POST http://127.0.0.1:8787/api/batch -H "Content-Type: application/json" \
  -d '{"project_id":"<uuid>","storyboard_path":"configs/storyboard_100.json","dry_run":false,"confirm":true}'
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
- Ảnh test UI (QA): `out/ui_shots/` — chụp lại bằng `python traces/phase4/shot_webui.py`
  và `python traces/phase4/ui_dry_run.py` (e2e dry-run qua chính UI, 0 credit).

Xem thêm: `docs/phase4_report.md` (§3 bridge mode, §5 module), `docs/api_specs/flow_create_image.md`,
`docs/api_specs/flow_image2image.md`, `docs/upgrade_plan_n_account_pool.md`.
