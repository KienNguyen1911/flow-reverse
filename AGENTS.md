# AGENTS.md — Quy chuẩn Kiến trúc & Quy trình Phối hợp cho AI Agents (OpenCode)

Tài liệu này định nghĩa quy trình làm việc, kiến trúc phân tầng và nguyên tắc sử dụng công cụ cho các AI Agent vận hành trong dự án thông qua **OpenCode**. Mọi Agent khi thực thi nhiệm vụ phải tuân thủ nghiêm ngặt việc phân tách giữa **Pha Khám phá (Discovery/Analysis)** và **Pha Vận hành (Deterministic Execution)**.

---

## 1. Phân tầng Kiến trúc & Vai trò Công cụ (Tool Stack)

Hệ thống được chia làm 4 lớp độc lập. Không dùng sai công cụ cho mục đích của lớp khác:

| Lớp kiến trúc | Công cụ chủ đạo | Mục đích sử dụng | Quy tắc giới hạn |
| :--- | :--- | :--- | :--- |
| **1. Browser Runtime & Profile Isolation** | **CloakBrowser** (`cloakbrowser` Python / .NET SDK) | Khởi chạy môi trường trình duyệt độc lập, quản lý `user_data_dir`, giữ cố định cấu hình môi trường (`seed`, `locale`, `timezone`) để bảo toàn trạng thái phiên (Session Continuity). | Không thay đổi `fingerprint_seed` trên một profile đang sử dụng. Luôn đồng bộ `platform` với hệ điều hành máy chủ thật. |
| **2. UI Discovery & Exploration** | **browser-use** (kết nối qua cổng CDP của CloakBrowser) | Điều khiển giao diện tự động bằng LLM khi cần khám phá tính năng mới, kiểm thử thay đổi giao diện (UI), hoặc kích hoạt các luồng tương tác mẫu để thu thập log mạng. | **CHỈ dùng ở Pha Khám phá & Bảo trì.** Không đưa `browser-use` vào vòng lặp sản xuất hàng loạt (Production Loop) để tránh độ trễ và chi phí token. |
| **3. Protocol & Traffic Analysis** | **Playwright Network Listeners / HAR Capture + Kỹ năng `reverse-engineer-anything` (REA)** | Lắng nghe sự kiện mạng (`Fetch/XHR`, `WebSocket`), đối chiếu sự thay đổi giữa các payload (Differential Analysis), và bóc tách đặc tả giao thức (Schema/Models). | Phải tách biệt rõ dữ liệu quan sát được (Observed Evidence) và giả thuyết suy luận (Inference). |
| **4. Production Execution Bridge** | **C# (.NET 10) / Python Deterministic Workers / Extension Bridge** | Thực thi các tác vụ tự động hóa tốc độ cao sau khi đã có đặc tả giao thức rõ ràng, kết hợp quản lý hàng đợi (Queue), kiểm soát nhịp độ (Rate-Limiting) và xử lý lỗi. | Phải áp dụng cơ chế Jitter, Exponential Backoff và Circuit Breaker khi gặp mã lỗi giới hạn tần suất (`429`/`503`). |

---

## 2. Quy trình Làm việc 4 Giai đoạn dành cho Team AI Agent

Khi nhận yêu cầu tích hợp một luồng công việc web hoặc cập nhật giao thức mới, các Agent trong OpenCode phải thực hiện tuần tự 4 bước sau:

### Giai đoạn 1: Khởi tạo Môi trường Cô lập (Profile Vault Setup)
1. Kiểm tra hoặc tạo mới cấu trúc thư mục lưu trữ tại `./browser_vault/<profile_id>/`.
2. Đảm bảo file `config.json` của từng profile chứa cố định:
   - `fingerprint_seed` (số nguyên 8 chữ số được sinh một lần duy nhất khi tạo profile).
   - `platform` (khớp với OS thực tế, mặc định `"windows"`).
   - `timezone_id`, `locale`, và cấu hình `proxy` (nếu có).
   - Cờ bảo vệ rò rỉ mạng: `--webrtc-ip-handling-policy=disable_non_proxied_udp`.
3. Khởi chạy `CloakBrowser` ở chế độ có giao diện (`headless=False`) và mở cổng debug nội bộ (`--remote-debugging-port=9222`) khi cần cho các công cụ phân tích gắn vào.

### Giai đoạn 2: Khám phá Giao diện & Thu thập Dấu vết Mạng (UI-to-Network Correlation)
Khi cần tìm hiểu cấu trúc request/response của một thao tác trên trang web:
1. **Gắn bộ lắng nghe (Network Sniffer):** Sử dụng Playwright `page.on("request")` và `page.on("response")` để ghi lại các gói tin thuộc nhóm `xhr`, `fetch` hoặc `websocket` vào file `./traces/raw_trace_<timestamp>.json`.
2. **Kích hoạt thao tác qua `browser-use`:**
   - Kết nối `browser-use` vào cổng CDP `http://127.0.0.1:9222`.
   - Giao nhiệm vụ cụ thể cho `browser-use` thực hiện thao tác trên UI (ví dụ: thực hiện 2 lần với 1 tham số thay đổi trên giao diện để phục vụ việc so sánh diff).
3. **Đánh dấu mốc thời gian (Action Tagging):** Ghi nhận timestamp trước và sau mỗi bước của `browser-use` để ánh xạ chính xác: *Thao tác UI X -> Sinh ra Request mạng Y*.

### Giai đoạn 3: Phân tích Đặc tả Giao thức (Protocol Schema Extraction)
Sử dụng quy trình của kỹ năng **`reverse-engineer-anything`**:
1. Đọc file `./traces/raw_trace_<timestamp>.json` và thực hiện **Differential Analysis** (so sánh hai payload giữa 2 lần thao tác khác nhau) để xác định vị trí của từng tham số.
2. Phân loại rõ các thành phần của Request:
   - **Static/Config Parameters:** Đường dẫn endpoint, tên phương thức/RPC ID, định dạng dữ liệu.
   - **Dynamic Session Context:** Các biến trạng thái phiên được khởi tạo cùng trang, CSRF/XSRF token, số thứ tự request (`_reqid`).
   - **Response Envelope:** Cách giải mã luồng phản hồi (JSON chuẩn, Server-Sent Events, hay Chunked Frame có độ dài byte đi trước).
3. Xuất kết quả phân tích thành tài liệu kỹ thuật tại `./docs/api_specs/<feature_name>.md` kèm theo các Data Transfer Objects (DTO / Pydantic Models / C# Records).

### Giai đoạn 4: Đóng gói thành Module Thực thi Cố định (Deterministic Implementation)
1. Chuyển hóa tài liệu đặc tả ở Giai đoạn 3 thành code thực thi cố định (C# hoặc Python) mà **không còn phụ thuộc vào `browser-use`**.
2. Nếu ứng dụng web yêu cầu ngữ cảnh phiên trực tiếp trên trình duyệt:
   - Thực thi lệnh gọi bên trong ngữ cảnh trang đang mở của `CloakBrowser` hoặc thông qua cầu nối WebSocket nội bộ (`ws://127.0.0.1:<port>`) tới Extension/Page Script.
3. Tích hợp lớp bảo vệ vận hành (Resilience Layer):
   - **Humanized Pacing:** Độ trễ ngẫu nhiên (Gaussian Jitter) giữa các tác vụ.
   - **Circuit Breaker:** Tự động tạm dừng (Cooldown) profile ngay khi phát hiện lỗi xác thực (`401`/`403`) hoặc vượt ngưỡng tần suất (`429`) thay vì thử lại liên tục.

---

## 3. Cấu trúc Thư mục Dự án Chuẩn

Khi viết code mới, các Agent phải đặt file đúng vào cấu trúc sau:

```text
project-root/
├── AGENTS.md                        # File quy chuẩn điều phối AI Agent (OpenCode)
├── browser_vault/                   # Kho lưu trữ các profile độc lập (không commit lên Git)
│   └── <profile_id>/
│       ├── config.json              # Chứa seed, proxy, locale, timezone cố định
│       └── user_data/               # Thư mục dữ liệu trình duyệt của CloakBrowser
├── discovery/                       # Chỉ dùng cho Pha Khám phá & Bảo trì
│   ├── sniffer.py                   # Bộ bắt gói tin Playwright / CDP
│   ├── explorer_agent.py            # Kịch bản browser-use tự động thao tác UI
│   └── payload_differ.py            # Công cụ diff JSON tìm vị trí tham số thay đổi
├── traces/                          # Chứa log mạng và HAR thu thập được
├── docs/
│   └── api_specs/                   # Tài liệu đặc tả Schema sau khi phân tích
└── src/                             # Mã nguồn vận hành chính thức (Production)
    ├── BrowserHost/                 # Quản lý vòng đời CloakBrowser & Profile
    ├── Bridge/                      # Cầu nối WebSocket / In-Page Execution
    └── Workflows/                   # Các pipeline thực thi cố định (Deterministic)