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

- Mọi real run **bắt buộc** qua dialog xác nhận trong UI. API cũng chặn: thiếu `confirm=true`
  thì `/api/generate` trả `400` và không có gì được gửi đi.
- Breaker đang mở (cooldown sau lỗi phiên/anti-busy) → `/api/generate` trả `423`.

---

## 2. Chuẩn bị (mỗi phiên)

1. **CloakBrowser phải đang mở** với profile đã đăng nhập Google (`flow_main`):

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
# flags khác: --host, --port, --cdp-url, --out
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
- Job chạy **tuần tự 1 worker** (1 tab mỗi lúc). Log realtime (poll 800 ms): timestamp, kind,
  message; chip trạng thái `Đang chờ / Đang chạy / Hoàn tất / Bị từ chối / Lỗi` + đồng hồ elapsed.
- Cuối job luôn có thẻ kết quả (dry-run / ảnh / reject / lỗi / tạo dự án / refresh).

### 4.5 Gallery
- Quét `out/playground/*/meta.json`; chỉ hiện run có file ảnh thật. Click thẻ để mở ảnh gốc.
- Ảnh phục vụ qua `/api/files/<run>/<file>` (serve local, không phụ thuộc signed URL đã hết hạn).

---

## 5. Artifact & trạng thái lưu trên đĩa

| Đường dẫn | Nội dung |
| :--- | :--- |
| `out/playground/<ts>_<slug>/meta.json` | metadata run (status, seed, seed_echo, media_id, file, elapsed…) |
| `out/playground/<ts>_<slug>/app_request_body.txt` | body app Flow (capture, bị chặn) |
| `out/playground/<ts>_<slug>/our_request_body.txt` + `our_args.pretty.json` | request của ta (dựng từ builder) |
| `out/playground/<ts>_<slug>/response.txt` | response batchexecute (chỉ có khi real run) |
| `out/playground/<ts>_<slug>/*.jpg` | ảnh đã tải |
| `out/playground_projects.json` | registry dự án hiển thị trong UI |
| `out/bridge_state.json` | circuit breaker (`total_accepted`, `total_rejected`, cooldown) |

Job history chỉ nằm trong RAM; restart server không mất ảnh/artifacts đã tạo.

---

## 6. API (dùng được bằng script)

| Method + path | Ghi chú |
| :--- | :--- |
| `GET /api/status` | health: CDP, browser, tab Flow, breaker |
| `GET /api/projects` | registry dự án |
| `POST /api/projects/refresh` | job UpteDb (0 credit) |
| `POST /api/projects/create` `{"title": "...", "confirm": true}` | job jHPbke (0 credit, tạo thật) |
| `POST /api/projects` `{"ref": "<uuid hoặc URL>"}` | thêm dự án ngoài danh sách (không gọi mạng) |
| `DELETE /api/projects/{id}` | bỏ khỏi registry (không xóa trên Google) |
| `POST /api/generate` | job `dry_run` (không cần confirm) hoặc `generate` (bắt buộc `confirm: true`; `423` nếu breaker mở) |
| `GET /api/jobs` / `GET /api/jobs/{id}` | job list / chi tiết kèm events |
| `GET /api/gallery` | danh sách run có ảnh |
| `GET /api/files/{run}/{file}` | file trong run dir |
| `GET /api/circuit/clear` | reset cooldown breaker (idempotent) |

Ví dụ chạy thật bằng script (sau khi tự chịu trách nhiệm credit):

```bash
curl -X POST http://127.0.0.1:8787/api/generate -H "Content-Type: application/json" \
  -d '{"project_id":"<uuid>","prompt":"một chú vịt vàng bơi hồ","dry_run":false,"confirm":true}'
```

---

## 7. Lỗi thường gặp

| Hiện tượng | Xử lý |
| :--- | :--- |
| "Browser offline" | CloakBrowser chưa mở / chưa đăng nhập → mục 2 |
| "Chưa thấy tab Flow" | Mở `flow.google.com` trong CloakBrowser hoặc bấm refresh |
| `423` khi chạy thật | Breaker đang cooldown (lý do hiện trong banner). Chờ hết cooldown, kiểm tra phiên đăng nhập trước khi dùng `/api/circuit/clear` |
| `rejected [3]` | Tham số sai (ví dụ seed ngoài int32) — lỗi của ta, 0 credit, sửa tham số rồi chạy lại |
| `rejected [7]` (UNUSUAL_ACTIVITY) | Anti-abuse; client tự backoff 120 s và retry 1 lần; 3 lần liên tiếp → breaker 30 phút |
| `401/403` | Phiên Google hỏng → đăng nhập lại trong CloakBrowser; breaker 30 phút |
| Job "không tìm thấy ô prompt" | UI Flow đổi cấu trúc → cập nhật selector `div.ProseMirror` / `button.generate-icon-button` trong `src/Bridge/flow_bridge.py` |

---

## 8. Ghi chú kỹ thuật

- Bridge **không bao giờ** gọi `browser.close()` — chỉ `playwright.stop()` (disconnect). Browser
  của user giữ nguyên trạng thái.
- Hook fetch (block+capture `ogiZ0b`) chỉ bật trong lúc job chạy và tự disarm; cuối mỗi lần
  generate trang được reload sạch.
- Token reCAPTCHA / `at` / `_reqid` **luôn đọc tươi** từ capture của app, không hard-code.
- Ảnh test UI (QA): `out/ui_shots/` — chụp lại bằng `python traces/phase4/shot_webui.py`
  và `python traces/phase4/ui_dry_run.py` (e2e dry-run qua chính UI, 0 credit).

Xem thêm: `docs/phase4_report.md` (§3 bridge mode, §5 module), `docs/api_specs/flow_create_image.md`.
