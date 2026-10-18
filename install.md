# install.md — Cài đặt flow-reverse (dành cho người dùng & AI agent)

Tài liệu này đủ để một **AI agent** (OpenCode, Claude Code, Codex...) đọc và cài đặt toàn bộ repo ngay sau khi
`git clone`. Người dùng cũng có thể làm theo trực tiếp.

Quy ước:

- Mọi lệnh chạy từ **gốc repo** (thư mục chứa `README.md`), trừ khi có ghi chú `cd`.
- Mỗi bước đều có **lệnh kiểm tra** — agent phải chạy đủ trước khi báo "hoàn thành".
- Cài đặt **không tiêu credit nào**. Ảnh thật chỉ được tạo khi người dùng xác nhận rõ ràng (xem mục 9).

---

## 0. Nhờ AI agent cài hộ — prompt mẫu

Dán đoạn sau vào AI agent cùng với repo vừa clone:

```text
Đọc file install.md ở gốc repo và cài đặt dự án theo đúng thứ tự các bước,
chạy đầy đủ lệnh kiểm tra và "Checklist nghiệm thu" trước khi kết luận.

Lưu ý bắt buộc:
- Bước 5 (đăng nhập Google trong CloakBrowser) là thao tác THỦ CÔNG — dừng lại và yêu cầu tôi làm.
- Tuyệt đối không chạy lệnh tạo ảnh thật (tốn ~1 credit/ảnh) khi tôi chưa xác nhận.
- Không sửa fingerprint_seed; không tự đổi cấu hình profile.
- Gặp lỗi thì đối chiếu mục "Xử lý sự cố" trước khi thử cách khác.
```

---

## 1. Yêu cầu hệ thống

| Thành phần | Yêu cầu | Đã kiểm chứng tại thời điểm viết |
| :--- | :--- | :--- |
| OS | **Windows 10/11** (khuyến nghị; profile mặc định `platform: "windows"`). macOS/Linux xem ghi chú bên dưới | win32 |
| Python | **3.11+** | 3.11.9 |
| Node.js + npm | Node **^20.19.0 hoặc ≥ 22.12.0** (Vite 8 yêu cầu) | 24.16.0 |
| Git | bất kỳ | — |
| Tài khoản Google | có quyền dùng **Google Flow** (tự đăng nhập ở Bước 5) | — |
| Dung lượng đĩa | ~700 MB (Chromium ẩn ~536 MB + `node_modules` ~134 MB) | — |
| Mạng | `pypi.org`, `registry.npmjs.org`, `cloakbrowser.dev` (tải Chromium), `*.google.com` | — |

Ghi chú:

- **macOS/Linux:** sau Bước 5, sửa `platform` trong `browser_vault/<profile>/config.json` cho khớp OS thật
  (AGENTS.md yêu cầu không giả lập platform khác vì dễ lộ mismatch fingerprint).
- Python cài từ python.org; nếu lệnh `python` mở Microsoft Store hoặc không tồn tại, dùng `py -3.11` thay thế.
- Các cổng dùng trong dự án: `9222` (CDP của CloakBrowser), `8787` (Flow Bench WebUI), `5173` (Vite dev — chỉ khi dev frontend).

## 2. Cài Python dependencies

```bash
python --version                 # cần >= 3.11
python -m venv .venv             # khuyến nghị (không bắt buộc)
```

Kích hoạt venv (chọn đúng shell):

```bat
:: cmd
.venv\Scripts\activate.bat
```

```powershell
# PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# Git Bash
source .venv/Scripts/activate
```

> Mẹo cho agent: nếu không giữ được trạng thái shell giữa các lệnh, gọi trực tiếp
> `.venv\Scripts\python.exe -m pip ...` và `.venv\Scripts\python.exe -m src.WebUI.app` thay cho `python`.

Cài dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install playwright fastapi uvicorn pydantic requests cloakbrowser
```

Combo phiên bản đã kiểm chứng (nếu muốn tái lập môi trường dev chính xác):

```bash
python -m pip install "playwright==1.62.0" "fastapi==0.119.0" "uvicorn==0.52.4" "pydantic==2.10.4" "requests==2.34.2" "cloakbrowser==0.6.3"
```

> **Không cần** chạy `playwright install` — bridge chỉ `connect_over_cdp` vào CloakBrowser,
> không dùng browser bundle của Playwright.

**Kiểm tra:**

```bash
python -c "import playwright, fastapi, uvicorn, pydantic, requests, cloakbrowser; print('deps OK')"
```

## 3. Tải CloakBrowser stealth Chromium

```bash
python -m cloakbrowser install     # tải ~500 MB vào %USERPROFILE%\.cloakbrowser\
python -m cloakbrowser info
```

**Kiểm tra:** output của `info` phải có `Installed: True`. Bản miễn phí (1 phiên đồng thời) là đủ dùng;
license Pro là tuỳ chọn (`python -m cloakbrowser login`).

## 4. Build UI Flow Bench (React + Vite)

```bash
cd web
npm ci            # cài đúng theo package-lock.json; nếu lỗi lockfile thì dùng: npm install
npm run build     # xuất web/dist
cd ..
```

**Kiểm tra:** tồn tại `web/dist/index.html`.

Ghi chú dev frontend (không bắt buộc): `npm run dev` chạy Vite tại `http://127.0.0.1:5173`,
proxy `/api` → `http://127.0.0.1:8787` (xem `web/vite.config.ts`). Sửa frontend thì build lại — server không cần restart.

## 5. Lần chạy đầu — tạo profile & đăng nhập Google (⚠️ THỦ CÔNG)

```bash
python src/BrowserHost/launch_profile.py --profile flow_main --wait
```

- Profile `flow_main` được tạo tự động khi chạy lần đầu (`browser_vault/` không có sẵn sau clone vì bị
  `.gitignore` chặn). `fingerprint_seed` được sinh **một lần duy nhất** — **không bao giờ sửa seed** trên
  profile đang dùng (đổi seed = đổi danh tính fingerprint).
- Muốn xem trước lệnh mà không mở trình duyệt: thêm `--dry-run`.
- **Chỉ mở một trình duyệt trên mỗi profile** (Chrome khóa `user_data_dir`); sniffer/Playwright chỉ được
  attach vào cùng cổng CDP 9222.

> ⛔ **DỪNG LẠI — nhờ người dùng làm thủ công:**
> 1. Trong cửa sổ CloakBrowser vừa mở, **đăng nhập tài khoản Google**.
> 2. Mở `https://flow.google.com`, xác nhận tài khoản truy cập được Flow (chấp nhận điều khoản nếu có).
> 3. Để cửa sổ trình duyệt **mở trong suốt phiên làm việc**.
>
> Agent không được tự đăng nhập (không có credentials).

**Kiểm tra:** CDP đã sẵn sàng —

```bash
curl.exe http://127.0.0.1:9222/json/version     # JSON có trường "Browser"
```

## 6. Smoke test bridge (0 credit)

```bash
python -m src.Workflows.flow_client status        # exit 0, "cdp_ok": true
python -m src.Workflows.flow_client list-projects # mở tab Flow, đọc danh sách dự án (0 credit)
```

- `list-projects` chỉ chạy được **sau khi đã đăng nhập** (Bước 5). Trong lúc job chạy, không thao tác vào tab Flow.
- Các lệnh tốn credit (`generate` không kèm `--dry-run`) **chỉ chạy khi người dùng xác nhận rõ ràng**.

## 7. Khởi động Flow Bench (WebUI)

```bash
python -m src.WebUI.app --port 8787 --open
```

**Kiểm tra:**

```bash
curl.exe http://127.0.0.1:8787/api/status    # HTTP 200, cdp_ok: true, có "breaker"
```

Mở `http://127.0.0.1:8787` — UI "Flow Bench" phải hiện ra. Nếu báo *"UI chưa build"* → quay lại Bước 4.

## 8. Checklist nghiệm thu (agent xác nhận đủ trước khi kết luận)

- [ ] `python -c "import playwright, fastapi, uvicorn, pydantic, requests, cloakbrowser"` → in `deps OK`
- [ ] `python -m cloakbrowser info` → `Installed: True`
- [ ] `web/dist/index.html` tồn tại
- [ ] `curl.exe http://127.0.0.1:9222/json/version` → browser phản hồi (sau Bước 5)
- [ ] `python -m src.Workflows.flow_client status` → exit 0, `cdp_ok: true`
- [ ] `curl.exe http://127.0.0.1:8787/api/status` → HTTP 200, `cdp_ok: true`
- [ ] Người dùng đã đăng nhập Google và mở được `flow.google.com`
- [ ] **Chưa tiêu credit nào** (không chạy generate thật trong quá trình cài)

## 9. Quy tắc an toàn (đọc trước khi vận hành)

- **Credit:** `status` / `list-projects` / `create-project` / `dry-run` = **0 credit**; ảnh thật ≈ **1 credit/ảnh**
  (bị từ chối = 0). Mọi real run cần người dùng xác nhận (UI có dialog, API yêu cầu `confirm: true`).
- **Circuit breaker:** lỗi `401/403` → cooldown 30 phút; `429` → 10 phút; 3 lần anti-abuse liên tiếp → 30 phút.
  Khi breaker mở, `/api/generate` trả `423` — không cố thử lại liên tục; xem "Xử lý sự cố".
- **Không sửa** `fingerprint_seed`, `platform`, `timezone_id`, `locale` trên profile đang dùng.
- Không commit `browser_vault/`, `traces/`, `out/` (đã có `.gitignore` — chứa cookie phiên và token).
- Dự án chỉ dành cho học tập/nghiên cứu; tuân thủ ToS của Google Flow (xem `README.md` mục 5).

## 10. Pha khám phá (tuỳ chọn — chỉ cho bảo trì, không cần cho cài đặt)

```bash
# Bắt gói tin (process riêng, chạy trước khi thao tác UI):
python discovery/sniffer.py --out-dir traces --types xhr,fetch,websocket

# So sánh 2 trace để định vị tham số thay đổi:
python discovery/payload_differ.py traces/raw_trace_<A>.jsonl traces/raw_trace_<B>.jsonl --url-contains batchexecute
```

- Điều khiển UI bằng LLM trong pha khám phá cần `browser-use` (tuỳ chọn): `python -m pip install browser-use`,
  attach vào CDP `http://127.0.0.1:9222`. **Không** đưa vào vòng lặp production (AGENTS.md mục 1).
- Chi tiết quy trình: `discovery/README.md`. Script `discovery/test_generate_2_images.py` là bản legacy
  (dùng browser-harness) — không cần cài để vận hành.

## 11. Xử lý sự cố

| Triệu chứng | Nguyên nhân / cách xử lý |
| :--- | :--- |
| `python` không tồn tại hoặc mở Microsoft Store | Cài Python 3.11+ từ python.org, hoặc dùng `py -3.11` |
| `npm` not found / *"npm.ps1 cannot be loaded"* (PowerShell) | Cài Node.js LTS, hoặc chạy trong cmd / dùng `npm.cmd` |
| Build frontend lỗi do Node quá cũ | Nâng Node lên ^20.19.0 || ≥ 22.12.0 (Vite 8) |
| `[launch] !! cloakbrowser is not installed` (exit 2) | Sai môi trường Python (venv khác?) → kích hoạt đúng venv rồi `pip install cloakbrowser` |
| `--wait` báo "CDP endpoint not ready" | Tăng `--wait-timeout`, hoặc firewall chặn cổng 9222; kiểm tra `curl.exe http://127.0.0.1:9222/json/version` |
| UI báo *"UI chưa build"* | Chưa chạy Bước 4 (`cd web && npm run build`) |
| Lỗi *"port already in use"* khi chạy WebUI | Đổi cổng: `python -m src.WebUI.app --port 8788` |
| UI báo *"Browser offline"* | CloakBrowser chưa mở / CDP chết → chạy lại Bước 5 |
| `423` khi tạo ảnh | Breaker đang cooldown (lý do hiện trong banner). Kiểm tra phiên đăng nhập trước, rồi `curl.exe http://127.0.0.1:8787/api/circuit/clear` |
| `401/403` | Phiên Google hỏng → đăng nhập lại trong CloakBrowser (Bước 5) |
| Mở trình duyệt thứ hai trên cùng profile bị lỗi | Chrome khóa `user_data_dir` — chỉ dùng `launch_profile.py`, các tool khác attach qua CDP 9222 |
| Job báo "không tìm thấy ô prompt" | UI Flow đổi cấu trúc → cập nhật selector trong `src/Bridge/flow_bridge.py` (xem `docs/playground.md` mục 7) |

Tham chiếu thêm: `docs/playground.md` (vận hành Flow Bench) · `docs/api_specs/` (đặc tả protocol) ·
`AGENTS.md` (quy chuẩn cho AI agent).

## 12. Cài lại sạch / gỡ cài đặt

| Muốn xoá | Xoá gì | Lưu ý |
| :--- | :--- | :--- |
| Môi trường Python | `.venv/` | rồi làm lại Bước 2 |
| Frontend | `web/node_modules/`, `web/dist/` | rồi làm lại Bước 4 |
| Phiên đăng nhập + fingerprint | `browser_vault/` | **mất đăng nhập Google**; profile tạo lại sẽ có seed mới |
| Chromium của CloakBrowser | `%USERPROFILE%\.cloakbrowser\` (hoặc `python -m cloakbrowser clear-cache`) | tải lại ~500 MB ở Bước 3 |
| Artifact & breaker | `out/` | mất lịch sử ảnh, registry dự án, trạng thái circuit breaker |
| Trace mạng | `traces/` | chỉ là dữ liệu khám phá, xoá an toàn |
