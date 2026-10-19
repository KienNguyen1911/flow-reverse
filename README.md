# flow-reverse — Google Flow bridge-mode client + Flow Bench playground

Client Python + playground web điều khiển **Google Flow** (Nano Banana 2.1) theo kiến trúc **bridge mode**:
mọi thao tác đi qua trình duyệt thật đang đăng nhập, tái sử dụng reCAPTCHA token do **chính app mint**
(không bypass, không tự mint token ngoài luồng app).

---

## 1. Mục tiêu

- Nghiên cứu (reverse engineering) giao thức `batchexecute` của Google Flow: endpoint, envelope,
  các RPC nghiệp vụ (`jHPbke` tạo project, `ogiZ0b` tạo ảnh, `UpteDb` đọc danh sách...).
- Hỗ trợ **pool N tài khoản** (browser mở theo nhu cầu, hot-spare failover, breaker riêng từng account) và
  **batch nhiều ảnh** theo storyboard (t2i + i2i) phục vụ pipeline dựng phim.
- Đóng gói quy trình chuẩn 2 pha: **Khám phá** (UI → mạng → đặc tả) → **Thực thi tất định** (module production
  không còn phụ thuộc công cụ điều khiển UI bằng LLM).
- Cung cấp client CLI + playground web tạo ảnh **có kiểm soát credit**: dry-run luôn 0 credit;
  mỗi ảnh thật tốn ~1 credit và luôn yêu cầu người dùng xác nhận trước khi fire.

## 2. Kiến trúc

Bốn lớp độc lập (chi tiết chuẩn hoá tại [`AGENTS.md`](AGENTS.md)):

| Lớp | Công cụ | Vai trò |
| :--- | :--- | :--- |
| **1. Browser Runtime** | CloakBrowser | Profile cô lập (`browser_vault/`), seed/locale/timezone cố định, mở cổng CDP `:9222` |
| **2. Discovery** | Playwright sniffer + payload differ | Thu trace mạng (XHR/fetch/WS), differential analysis → đặc tả tại `docs/api_specs/` |
| **3. Bridge** | Playwright `connect_over_cdp` | Hook fetch trong page: chặn request `ogiZ0b` của app (0 credit) để "mượn" token tươi + `at` + `_reqid`; dựng body riêng (prompt/seed/UUID chữ hoa); fire in-page; long-poll; tải signed CDN URL |
| **4. Production** | Python + FastAPI + React | `FlowClient` (CLI), WebUI backend, playground web, pool N account (launch theo nhu cầu + hot spare); batch t2i/i2i theo storyboard; circuit breaker per account, jitter + exponential backoff |

Luồng bridge mode:

```text
CLI / Web UI ──▶ FlowClient ──▶ FlowBridge (CDP) ──▶ tab Flow (hook capture request app)
                                                                │  build body riêng
                                                                ▼
                                             fire in-page ─▶ long-poll ─▶ tải ảnh ─▶ out/
```

## 3. Công nghệ sử dụng

- **Backend:** Python 3.11+, Playwright (CDP), FastAPI + Uvicorn, Pydantic; CloakBrowser (runtime profile).
- **Frontend (Flow Bench):** React 19, Vite 8, Tailwind CSS v4, Motion, Phosphor Icons, TypeScript.
- **Browser runtime:** CloakBrowser (Chromium) attach qua CDP, profile tách biệt trong `browser_vault/` (không commit).

## 4. Bắt đầu nhanh

```bash
pip install playwright fastapi uvicorn pydantic requests cloakbrowser

# 1) Mở trình duyệt với profile đã đăng nhập Google (cổng CDP :9222) — hoặc để server tự đánh thức khi cần
python src/BrowserHost/launch_profile.py --profile flow_main --wait

# 2) CLI (0 credit với status / list-projects / --dry-run)
python -m src.Workflows.flow_client status
python -m src.Workflows.flow_client list-projects
python -m src.Workflows.flow_client generate --project <uuid> --prompt "a red apple" --dry-run

# 3) Playground web (Flow Bench)
cd web && npm install && npm run build && cd ..
python -m src.WebUI.app --port 8787 --open
```

Tài liệu: [cẩm nang học tập reverse API](docs/reverse_api_study_guide.md) · [đặc tả protocol](docs/api_specs/) · [hướng dẫn playground](docs/playground.md) · [báo cáo tổng hợp](docs/phase4_report.md)

## 5. Miễn trừ trách nhiệm

Dự án chỉ mang tính **học tập và tham khảo** về kỹ thuật phân tích giao thức web.

- Tác giả **không chịu trách nhiệm** với bất kỳ hành vi sử dụng nào cho **mục đích thương mại**, lạm dụng,
  hoặc gây tổn hại đến dịch vụ của bên thứ ba.
- Dự án không liên kết, không được tài trợ hay chứng thực bởi Google.
- Người dùng tự chịu trách nhiệm tuân thủ điều khoản dịch vụ (ToS) của Google Flow và các quy định pháp luật liên quan.
