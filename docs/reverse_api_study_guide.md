# Cẩm Nang Toàn Diện: Quy Trình & Kỹ Thuật Reverse Engineering Web API
## Từ Nghiên Cứu Thử Nghiệm Đến Source Code Vận Hành (Case Study: Google Flow / rev-flow)

> **Tài liệu tham khảo & học tập kỹ thuật phân tích giao thức web chuyên sâu.**  
> **Dự án thực tế:** [rev-flow (Google Flow Bridge Client & Flow Bench)](file:///D:/Dev/rev-flow/README.md)  
> **Ngày tổng hợp:** 19/10/2026  
> **Kiến trúc quy chuẩn:** [AGENTS.md](file:///D:/Dev/rev-flow/AGENTS.md)

---

## MỤC LỤC

1. [Tổng Quan & Bài Toán Reverse Engineering Web SPA Hiện Đại](#1-tổng-quan--bài-toán-reverse-engineering-web-spa-hiện-đại)
2. [Tư Duy Cốt Lõi: Discovery First, Deterministic Second](#2-tư-duy-cốt-lõi-discovery-first-deterministic-second)
3. [Giai Đoạn 1: Thiết Lập Môi Trường & Cô Lập Trình Duyệt (Profile Vault & CDP Conflict)](#3-giai-đoạn-1-thiết-lập-môi-trường--cô-lập-trình-duyệt-profile-vault--cdp-conflict)
4. [Giai Đoạn 2: Lắng Nghe Dấu Vết Mạng Thụ Động & Action Tagging (CDP Sniffing)](#4-giai-đoạn-2-lắng-nghe-dấu-vết-mạng-thụ-động--action-tagging-cdp-sniffing)
5. [Giai Đoạn 3: Giải Mã Giao Thức Wire Format & Phân Tích Vi Sai (Differential Analysis)](#5-giai-đoạn-3-giải-mã-giao-thức-wire-format--phân-tích-vi-sai-differential-analysis)
6. [Giai Đoạn 4: Chuỗi Thí Nghiệm & Báo Cáo Thực Nghiệm Vượt Rào (E0 → E8, R1 → R2, jHPbke)](#6-giai-đoạn-4-chuỗi-thí-nghiệm--báo-cáo-thực-nghiệm-vượt-rào-e0--e8-r1--r2-jhpbke)
7. [Giai Đoạn 5: Thiết Kế & Xây Dựng Cầu Nối Vận Hành Tất Định (Bridge Mode Implementation)](#7-giai-đoạn-5-thiết-kế--xây-dựng-cầu-nối-vận-hành-tất-định-bridge-mode-implementation)
8. [Giai Đoạn 6: Nâng Cấp Nâng Cao (i2i Template-Replay, N-Account Pool & Storyboard DAG)](#8-giai-đoạn-6-nâng-cấp-nâng-cao-i2i-template-replay-n-account-pool--storyboard-dag)
9. [Quy Trình 7 Bước Chuẩn Mực Cho Mọi Dự Án Reverse API (Playbook & Checklist)](#9-quy-trình-7-bước-chuẩn-mực-cho-mọi-dự-án-reverse-api-playbook--checklist)
10. [10 Nguyên Tắc Vàng Dành Cho Kỹ Sư Reverse Engineering](#10-10-nguyên-tắc-vàng-dành-cho-kỹ-sư-reverse-engineering)
11. [Bài Tập Thực Hành & Tự Đánh Giá (Diagnostic Scenarios & Self-Assessment)](#11-bài-tập-thực-hành--tự-đánh-giá-diagnostic-scenarios--self-assessment)
12. [Bảng Tra Cứu Mã Nguồn & Tài Liệu Kỹ Thuật Trong Repo](#12-bảng-tra-cứu-mã-nguồn--tài-liệu-kỹ-thuật-trong-repo)

---

## 1. Tổng Quan & Bài Toán Reverse Engineering Web SPA Hiện Đại

### 1.1. Bối cảnh dự án
**Google Flow** (trải nghiệm Nano Banana 2.1) là ứng dụng web Single Page Application (SPA) xây dựng trên nền Angular (`AiSandboxAngularFrontend`). Ứng dụng cung cấp công cụ AI tạo hình ảnh và video chất lượng cao từ câu lệnh văn bản (`text2image`) hoặc hình ảnh tham chiếu (`image2image`).

Mục tiêu kỹ thuật của dự án `rev-flow`:
- Xây dựng một **client tự động hoá lập trình (Python CLI / Web UI Playground)** có khả năng thực thi hàng loạt (storyboard 50–100 ảnh cho dựng phim).
- Điều phối **cụm nhiều tài khoản Google (Dynamic N-Account Pool)** mà không gây tràn bộ nhớ RAM.
- **Bảo toàn hạn mức (Zero-Credit Safety):** Đảm bảo trong suốt quá trình phân tích và thử nghiệm, hạn mức tài khoản (~1 credit/lần sinh ảnh thành công) không bị lãng phí do lỗi request.

### 1.2. Các cơ chế phòng thủ thực tế quan sát được
Khác với các RESTful API công khai, Google Flow được bảo vệ bằng nhiều tầng rào cản tinh vi:

| Tầng phòng thủ | Chi tiết quan sát trên Google Flow | Thách thức kỹ thuật cho Reverse API |
| :--- | :--- | :--- |
| **Giao thức đóng (Wire Format)** | Endpoint RPC-style `batchexecute`. Body dạng form URL-encoded với dữ liệu **double-encoded JSON** lồng nhau. Response trả về có tiền tố chống XSSI (`)]}'`) kèm các khối text có độ dài byte đứng trước (length-prefixed framing). | Parser REST/JSON thông thường không dùng được; phải xây dựng bộ codec mã hoá/giải mã riêng. |
| **Ngữ cảnh phiên & CSRF** | Các biến trạng thái sinh ra theo phiên tải trang: `at` (token XSRF mang epoch timestamp), `f.sid` (session id), `bl` (deploy build label), và bộ đếm thứ tự `_reqid` tăng dần (`base + 100000`). | Hard-code tham số sẽ bị lỗi `400 Bad Request` hoặc mất hiệu lực ngay khi trang cập nhật hoặc phiên hết hạn. |
| **Hệ thống Anti-Bot ngầm** | Bắt tay ngầm qua iframe biệt lập `www.google.com/recaptcha/enterprise/reload`, phát hành token biến thiên 2468–2553 ký tự (`0cAFcWeA...`). | Token không thể gọi trực tiếp bằng REST ngoài browser; token có thời gian sống (TTL) cực ngắn; token sai context sẽ bị server từ chối với lỗi `PUBLIC_ERROR_UNUSUAL_ACTIVITY`. |
| **Rủi ro chi phí & Quota** | Mỗi lần tạo ảnh thành công trừ ~1 credit. Thử nghiệm mù (trial & error) sẽ làm cạn kiệt tài khoản và tăng nguy cơ bị khóa tài khoản do spam request lỗi. | Bắt buộc phải thiết kế quy trình **Zero-Credit Testing (Thử nghiệm 0 credit)**: ngắt request trước khi rời trình duyệt. |

---

## 2. Tư Duy Cốt Lõi: Discovery First, Deterministic Second

Sai lầm nghiêm trọng nhất của người mới học reverse API là **vội vàng viết script HTTP thuần (dùng requests/curl) ngay khi vừa thấy endpoint trong DevTools**, hoặc **lạm dụng visual agent (như LLM browser-use) trong môi trường sản xuất**.

Quy chuẩn kiến trúc [AGENTS.md](file:///D:/Dev/rev-flow/AGENTS.md) định nghĩa ranh giới rõ ràng:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       PHA 1: KHÁM PHÁ (DISCOVERY PHASE)                     │
│  CloakBrowser (CDP) ──▶ Playwright Sniffer (JSONL) ──▶ Payload Differ       │
│                             │                                  │            │
│                             ▼                                  ▼            │
│                      Action Tagging                  Đặc Tả Protocol Specs  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHA 2: VẬN HÀNH TẤT ĐỊNH (DETERMINISTIC PHASE)           │
│  CLI / WebUI ──▶ FlowClient ──▶ FlowBridge (In-Page Fetch Hook)             │
│                                       │                                     │
│                                       ▼                                     │
│                         Zero-Credit Decoy Capture                           │
│                                       │                                     │
│                                       ▼                                     │
│                     Direct In-Page Fire ──▶ Signed CDN                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

1. **Pha Khám phá (Discovery):** Sử dụng trình duyệt thật, tài khoản thật, công cụ lắng nghe thụ động (Passive Sniffing), và phân tích vi sai (Differential Analysis) giữa các lần chạy để lập bản đồ cấu trúc dữ liệu chính xác 100%.
2. **Pha Vận hành (Deterministic Execution):** Đóng gói thành mã nguồn Python tất định ([`FlowBridge`](file:///D:/Dev/rev-flow/src/Bridge/flow_bridge.py), [`FlowClient`](file:///D:/Dev/rev-flow/src/Workflows/flow_client.py)). **Hoàn toàn loại bỏ LLM và browser-use** ra khỏi vòng lặp sản xuất để triệt tiêu chi phí token, loại bỏ độ trễ thị giác và đảm bảo tỷ lệ thành công tuyệt đối.

---

## 3. Giai Đoạn 1: Thiết Lập Môi Trường & Cô Lập Trình Duyệt (Profile Vault & CDP Conflict)

### 3.1. Hạn chế của Incognito và Headless thông thường
- Các hệ thống botguard hiện đại (Cloudflare Turnstile, reCAPTCHA Enterprise, Akamai) dễ dàng phát hiện Chromium Headless thông qua các thuộc tính navigator (`navigator.webdriver == true`), Canvas fingerprint, WebGL vendor/renderer, và WebRTC IP leaks.
- Mở profile trắng mỗi lần chạy sẽ làm mất cookie đăng nhập, kích hoạt các bước xác minh 2FA hoặc số điện thoại.

### 3.2. Cấu trúc Profile Vault (`browser_vault/`)
Mỗi tài khoản được cấp một thư mục riêng biệt tại `./browser_vault/<profile_id>/` với file `config.json` mang các giá trị cố định:

```json
{
  "profile_id": "acc_01",
  "fingerprint_seed": 74839201,
  "platform": "windows",
  "locale": "vi-VN",
  "timezone_id": "Asia/Ho_Chi_Minh",
  "webrtc_policy": "disable_non_proxied_udp"
}
```

### 3.3. Bí mật kỹ thuật: Xung đột giữa Playwright Pipe và Cổng CDP ([`src/BrowserHost/launch_profile.py`](file:///D:/Dev/rev-flow/src/BrowserHost/launch_profile.py))
Trong quá trình phát triển, một vấn đề nan giải xuất hiện: **Tại sao gọi SDK `launch()` hoặc Playwright `launch_persistent_context()` không thể mở được cổng remote debugging?**

**Nguyên nhân gốc rễ (Root Cause):**
1. Playwright driver luôn tự động đẩy cờ `--remote-debugging-pipe` vào Chromium `argv` và chủ động từ chối cờ pipe/CDP do người gọi truyền vào.
2. Khi handler pipe đang hoạt động, Chromium **hoàn toàn bỏ qua cờ `--remote-debugging-port`**, khiến endpoint `http://127.0.0.1:9222` không thể mở ra cho các tiến trình khác kết nối vào.

**Giải pháp triển khai trong `launch_profile.py`:**
- Sử dụng SDK CloakBrowser để chuẩn bị binary tàng hình (`ensure_binary()`) và sinh tập cờ fingerprint chuẩn (`build_args()`), nhưng **khởi chạy binary trực tiếp qua `subprocess.Popen`** độc lập thay vì thông qua Playwright launch wrapper.
- Thêm cờ `--remote-debugging-port=<port>` và `--remote-allow-origins=*` (cho phép nâng cấp kết nối WebSocket CDP trên các bản Chromium mới).
- **Loại bỏ cờ nguy hiểm:** SDK thường mặc định thêm cờ `--no-sandbox` (cho môi trường Docker CI). Trên Windows desktop thật, cờ này khiến Chrome hiển thị thanh thông báo màu đỏ: *"You are using an unsupported command-line flag: --no-sandbox. Stability and security will suffer"*. Đây là dấu hiệu cảnh báo bot rõ ràng. Script chủ động bóc tách và loại bỏ cờ này trước khi khởi động.

---

## 4. Giai Đoạn 2: Lắng Nghe Dấu Vết Mạng Thụ Động & Action Tagging (CDP Sniffing)

### 4.1. Tại sao không dùng Proxy (Mitmproxy / Fiddler)?
- Cài đặt Root CA tự ký vào hệ điều hành có thể phá vỡ cơ chế Certificate Pinning của Google hoặc kích hoạt cờ cảnh báo an ninh trình duyệt.
- Giải pháp sạch nhất: **Lắng nghe trực tiếp qua Chrome DevTools Protocol (CDP)** thông qua Playwright API: `page.on("request")`, `page.on("response")`, `page.on("websocket")`.

### 4.2. Bộ bắt gói tin chuyên dụng ([`discovery/sniffer.py`](file:///D:/Dev/rev-flow/discovery/sniffer.py))
Bộ lắng nghe chạy như một tiến trình độc lập, kết nối vào trình duyệt đang mở và lưu trữ luồng traffic dưới dạng JSON Lines (`.jsonl`):

```python
# discovery/sniffer.py — Trích đoạn cơ chế lắng nghe an toàn
def on_request(request):
    record = {
        "ts_ms": time.time() * 1000,
        "kind": "request",
        "method": request.method,
        "url": request.url,
        "headers": dict(list(request.headers.items())[:50]),
        "req_body": request.post_data
    }
    append_jsonl(record)

def on_response(response):
    # Cạm bẫy quan trọng: Tuyệt đối không gọi response.body() trên stream (SSE)
    # vì Playwright sẽ block luồng driver loop cho đến khi stream đóng, gây treo toàn bộ sniffer!
    content_type = response.headers.get("content-type", "")
    if any(skip in content_type for skip in ("text/event-stream",)):
        return
    record = {
        "ts_ms": time.time() * 1000,
        "kind": "response",
        "status": response.status,
        "url": response.url,
        "resp_body": safe_read_body(response)
    }
    append_jsonl(record)
```

### 4.3. Kỹ thuật Action Tagging (Ánh xạ Thao Tác UI ↔ Request Mạng)
Để không bị ngợp giữa hàng trăm request ngầm của SPA (telemetry, analytics, heartbeats), ta đánh dấu mốc thời gian quanh thao tác người dùng:
- $T_{start}$: Người dùng gõ xong prompt và bắt đầu nhấn nút "Generate".
- $T_{end}$: Nút bấm hoàn tất trạng thái click.
- Lọc các request trong cửa sổ $[T_{start}, T_{start} + 2s]$ để phát hiện chuỗi sự kiện hạt nhân:
  1. Handshake iframe: `POST https://www.google.com/recaptcha/enterprise/reload`
  2. Telemetry: `POST ...rpcids=WuwhI`
  3. Lệnh tạo ảnh chính: `POST ...rpcids=ogiZ0b`

---

## 5. Giai Đoạn 3: Giải Mã Giao Thức Wire Format & Phân Tích Vi Sai (Differential Analysis)

### 5.1. Bóc tách Wire Format của Google `batchexecute`
Tham khảo chi tiết tại [`docs/api_specs/flow_transport.md`](file:///D:/Dev/rev-flow/docs/api_specs/flow_transport.md).

#### Cấu trúc Request (Double-Encoded JSON)
Request được gửi dưới dạng POST form URL-encoded tới:
`POST https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=ogiZ0b&_reqid=1258716&bl=...&f.sid=...`

Body gồm 2 tham số form chính:
```text
f.req=[[[ "ogiZ0b", "<ARGS_JSON_STRING>", null, "generic" ]]] & at=<XSRF_TOKEN> &
```
- **Lớp 1:** Mảng tham số `args` được serialize thành chuỗi JSON `<ARGS_JSON_STRING>`.
- **Lớp 2:** Toàn bộ mảng `[[["ogiZ0b", ...]]]` được serialize JSON lần thứ hai rồi gán vào trường form `f.req`.
- **Lớp 3:** Toàn bộ form body được mã hóa URL chuẩn `encodeURIComponent`.

Bộ đóng gói chuẩn trong [`src/Workflows/flow_models.py`](file:///D:/Dev/rev-flow/src/Workflows/flow_models.py):
```python
def enc(s: str) -> str:
    """encodeURIComponent-compatible percent-encoding (byte-identical theo forensics E8)."""
    return quote(s, safe="!'()*-._~")

def encode_batchexecute_form(rpcid: str, args: list, at_param: str) -> str:
    """Form body chuẩn từng byte: f.req=<enc>&at=<enc>&"""
    args_json = json.dumps(args, separators=(",", ":"), ensure_ascii=False)
    f_req = json.dumps([[[rpcid, args_json, None, "generic"]]], separators=(",", ":"), ensure_ascii=False)
    return "f.req=" + enc(f_req) + "&at=" + enc(at_param) + "&"
```

#### Cấu trúc Response (Length-Prefixed Chunk Framing)
Phản hồi trả về có dạng chunked text:
```text
)]}'

1251
[["wrb.fr","ogiZ0b","<PAYLOAD_JSON_STRING>",null,null,null,"generic"],["di",22261]]
26
[["e",4,null,null,1289]]
```
1. Tiền tố `)]}'` ở dòng đầu nhằm vô hiệu hoá kỹ thuật tấn công **JSON Hijacking / XSSI**.
2. Dòng chứa số nguyên (`1251`) chỉ định độ dài byte của khối dữ liệu tiếp theo.
3. Phần tử nhãn `"wrb.fr"` chứa kết quả thực thi của RPC ID tương ứng.
4. Vị trí cột 2 của `"wrb.fr"` là `<PAYLOAD_JSON_STRING>` (chuỗi JSON lồng, cần `json.loads` lần thứ hai).
5. Trường `["di", 22261]` biểu thị thời gian xử lý phía server (~22.2 giây — đặc trưng của cơ chế long-polling chờ tạo ảnh).

#### Cạm bẫy trích xuất CDN Signed URL: Lỗi Regex `\u003d`
Trong payload JSON trả về từ Google Flow, các ký tự dấu bằng (`=`) trong chuỗi query params của CDN URL được mã hóa thành escape unicode `\u003d`:
`https://flow-content.google/image/...Expires\u003d1792336794\u0026Signature\u003d...`

> ⚠️ **Bài học xương máu:** Nếu dùng Regular Expression dạng `https://flow-content\.google/[^\s"]+` để bắt URL trực tiếp từ chuỗi thô, regex sẽ bị dừng hoặc cắt cụt chuỗi tại `\u003d`. Kết quả URL tải về bị thiếu tham số chữ ký mật mã, dẫn đến mã lỗi **`403 AccessDenied`** từ Google Cloud Storage.
> **Cách xử lý đúng:** Bắt buộc parse dòng dữ liệu thành JSON hợp lệ qua `json.loads()`, khi đó Python parser sẽ tự động giải mã `\u003d` thành `=`, đảm bảo tính toàn vẹn của URL ký danh.

### 5.2. Kỹ thuật Phân Tích Vi Sai (Differential Analysis)
Để giải mã mảng `args` dài hơn 5.7 KB với hàng chục tầng lồng nhau không có schema công khai, ta áp dụng **Differential Analysis**:
1. **Lần chạy 1:** Sinh ảnh với prompt `"a red ceramic teapot on wooden table"`.
2. **Lần chạy 2:** Sinh ảnh với prompt `"a blue ceramic teapot on wooden table"`. Mọi tùy chọn khác (tỷ lệ 16:9, nút bấm) giữ nguyên tuyệt đối.
3. Chạy công cụ [`discovery/payload_differ.py`](file:///D:/Dev/rev-flow/discovery/payload_differ.py) để so sánh đệ quy cấu trúc cây JSON giữa 2 lần chạy.

**Kết quả:** 98% cấu trúc dữ liệu là bất biến. Chỉ có duy nhất 6 vị trí thay đổi:

```jsonc
[
  null,
  [
    [
      null, null, null,
      1449382406,             // [1][0][3]  SEED (ngẫu nhiên từ client, int32 có dấu)
      3,                      // [1][0][4]  ASPECT RATIO (3 = 16:9)
      "BELUGA",               // [1][0][5]  MODEL KEY (Nano Banana 2.1)
      null,
      [                       // [1][0][7]  PROJECT REFERENCE KHỐI 1
        null, 22, null, null, null,
        "3b368b0d-...",       // [1][0][7][5] PROJECT UUID
        null, null, null, null,
        ["0cAFcWeA...", 1]    // [1][0][7][10][0] RECAPTCHA ENTERPRISE TOKEN
      ],
      [[["a red teapot..."]]],// [1][0][8][0][0][0] PROMPT VĂN BẢN
      null, null, null,
      "D8A29A44-...",         // [1][0][12] CLIENT UUID 1 (In hoa)
      "71B89807-..."          // [1][0][13] CLIENT UUID 2 (In hoa)
    ]
  ],
  1,                          // [2] SỐ LƯỢNG ẢNH (count = 1)
  [                           // [3] PROJECT REFERENCE KHỐI 2 (Lặp lại khối 1)
    null, 22, null, null, null,
    "3b368b0d-...",
    null, null, null, null,
    ["0cAFcWeA...", 1]
  ],
  ["48CD1612-..."]            // [4][0] GENERATION UUID (Echo lại trong response)
]
```

### 5.3. Phân biệt RPC Nghiệp Vụ vs Telemetry
Sau khi nhấn nút sinh ảnh, trình duyệt gửi thêm một request tới RPC `WuwhI` chứa plaintext về prompt, seed, model.
- **Thử nghiệm loại trừ:** Chủ động chặn `WuwhI` và chỉ gửi `ogiZ0b`. Kết quả server vẫn xử lý và trả ảnh thành công.
- **Kết luận:** `WuwhI` là kênh telemetry/analytics của Google, **không bắt buộc** cho pipeline nghiệp vụ. Bỏ qua nó giúp mã nguồn gọn gàng và tránh rủi ro phát sinh lỗi.

---

## 6. Giai Đoạn 4: Chuỗi Thí Nghiệm & Báo Cáo Thực Nghiệm Vượt Rào (E0 → E8, R1 → R2, jHPbke)

Chuỗi thí nghiệm ghi lại toàn bộ hành trình thử nghiệm thực tế từ [`docs/phase4_report.md`](file:///D:/Dev/rev-flow/docs/phase4_report.md):

```text
E0 (ngNC2 Replay)      ──▶ Khắc phục lỗi Double-Encoding URL của token XSRF 'at'
      │
Stage B / E4           ──▶ Thử mint token bằng grecaptcha.enterprise.execute()
      │                    └──▶ THẤT BẠI: Server trả về UNUSUAL_ACTIVITY (gRPC 7)
      ▼
E2 (Forensics)         ──▶ Token xịn phát từ iframe www.google.com/recaptcha/enterprise/reload
      │                    └──▶ Bị CORS chặn, không thể replay trực tiếp từ main page
      ▼
E3 (In-Page Hooking)   ──▶ Monkey-patch window.fetch để CHẶN request app (0 CREDIT!)
      │                    └──▶ Phát hiện: App truyền Request instance, hook cũ chỉ đọc init.body
      ▼
E5 (grecaptcha Hook)   ──▶ Hook vào grecaptcha xem app có gọi execute() không
      │                    └──▶ KẾT QUẢ: App KHÔNG BAO GIỜ gọi execute; token chỉ đến qua iframe
      ▼
E6 (Timing Test)       ──▶ Bắt token reload tươi từ trace live rồi fire sau 7.8s
      │                    └──▶ THẤT BẠI: UNUSUAL_ACTIVITY (Token có TTL siêu ngắn tính bằng ms)
      ▼
Forensic F             ──▶ So sánh byte-level: encoding chuẩn 100%, _reqid = base + 100000
      │
E7 (Verbatim Replay)   ──▶ Chặn app ──▶ Đọc body qua Request.text() ──▶ Fire y nguyên sau 285ms
      │                    └──▶ THÀNH CÔNG: 200 OK + Ảnh thật đầu tiên e7_green_teapot.jpg (~1 credit)
      ▼
E8 (Custom Builder)    ──▶ Dựng args riêng: Prompt tím, Seed riêng, UUID IN HOA, Fire sau 72ms
      │                    └──▶ THÀNH CÔNG: Server echo lại đúng Generation UUID & Seed (~1 credit)
      ▼
Test J (jHPbke Replay) ──▶ Replay RPC tạo project bằng context đọc từ window.WIZ_global_data
      │                    └──▶ THÀNH CÔNG: 200 OK trong 258ms, tạo project mới (0 credit!)
      ▼
R1 (Auto Script Run)   ──▶ Script chạy tự động, dính lỗi gRPC [3] INVALID_ARGUMENT (0 credit)
      │                    └──▶ NGUYÊN NHÂN: Seed 2905577744 vượt quá giới hạn int32 có dấu (2^31 - 1)
      ▼
R2 (Fix Seed Constraint)──▶ Ép Seed in range(1, 2147483647), Fire sau 78ms
                           └──▶ THÀNH CÔNG HOÀN HẢO: Ảnh quả táo đỏ "Red apple on plate" (~1 credit)
```

### Bảng tổng kết chi tiết các mốc thí nghiệm

| Thí nghiệm | Mục tiêu kiểm chứng | Kỹ thuật áp dụng | Hiện tượng & Lỗi gặp phải | Nguyên nhân & Giải pháp đúc kết | Chi phí |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Test 0** | Kiểm tra khả năng replay 1 RPC đọc đơn giản (`ngNC2`) | Gửi `fetch` cùng origin trong console trình duyệt | HTTP `400 Bad Request` | **Bug URL Double-Encoding:** Tham số `at` chứa dấu `:`. Khi URL encode 2 lần biến thành `%253A`. Cần unquote trước khi encode vào form body. Sửa xong trả về `200 OK`. | 0 credit |
| **Stage B / E4** | Tự mint token reCAPTCHA bằng API JS chuẩn của Google | Gọi `grecaptcha.enterprise.execute(sitekey, {action:'IMAGE_GENERATION'})` | Mint được token `0cAFcWeA...` (~2510 ký tự) nhưng khi fire bị `UNUSUAL_ACTIVITY` | Token tự mint ngoài context trang Flow bị backend từ chối. Token hợp lệ bắt buộc phải gắn với phiên reload nội bộ của Botguard. | 0 credit |
| **E2** | Điều tra nguồn gốc request `reload` | Soi sniffer log xem token xịn sinh ra từ đâu | Request `reload` nằm trong iframe domain `www.google.com` | Replay từ main page bị trình duyệt chặn do vi phạm **CORS**. Không thể giả lập request reload trực tiếp từ code ngoài. | 0 credit |
| **E3** | Chặn đứng request app để bảo toàn credit | Cài đặt monkey-patch `window.fetch` để hủy request `ogiZ0b` | Request bị chặn nhưng `init.body` trả về `undefined` | **Cạm bẫy Fetch API:** Khi code gọi `fetch(new Request(url, {...}))`, body nằm trong instance của `Request` chứ không nằm trong tham số thứ hai `init`. Cần gọi `input.text()` để đọc body stream. | 0 credit |
| **E5** | Kiểm tra app có gọi `grecaptcha.execute()` ngầm? | Monkey-patch hàm `grecaptcha.enterprise.execute` | Hàm hook không nhận được bất kỳ lời gọi nào khi nhấn nút | Khẳng định 100%: App không dùng cơ chế execute công khai mà giao tiếp trực tiếp với iframe reload qua postMessage. | 0 credit |
| **E6** | Kiểm tra độ tươi (freshness) của token reload | Trích token từ live trace rồi gửi qua script sau ~7.8s | Bị `UNUSUAL_ACTIVITY` dù token hoàn toàn do app mint xịn | Token reCAPTCHA trong luồng này là **ephemeral (siêu ngắn)**, chỉ có hiệu lực trong vài trăm mili-giây kể từ lúc cấp phát. | 0 credit |
| **Forensic F** | So sánh byte-level giữa request app và request của ta | Diff nhị phân và kiểm tra header/encoding | Tìm ra quy luật `_reqid` | Header của app là tập con của ta. `at` không xoay vòng trong phiên. `_reqid = base + 100000` mỗi request. Cấu trúc args của ta khớp 100%. | 0 credit |
| **E7** | Replay nguyên bản (Verbatim) trong tích tắc | Hook chặn app, bóc body qua `input.text()`, gửi lại nguyên văn trong 285ms | **THÀNH CÔNG:** HTTP 200, nhận về ảnh thật chiếc ấm trà xanh (`e7_green_teapot.jpg`, 120 KB) | Chứng minh tính khả thi của giải pháp In-Page Bridge: Tái sử dụng token do chính app mint trong cửa sổ thời gian cực ngắn. | ~1 credit |
| **E8** | Tự dựng body (Custom Builder) với tham số của ta | Dựng args từ Python: prompt tím, seed mới, UUID in hoa. Fire sau 72ms | **THÀNH CÔNG:** Nhận về ảnh chiếc ấm màu tím (`e8_purple_teapot.jpg`, 115 KB). Server echo lại đúng UUID của ta! | Xác nhận ta đã kiểm soát 100% tham số đầu vào mà không còn phụ thuộc vào payload gốc của app. | ~1 credit |
| **Test J** | Replay tạo project (`jHPbke`) bằng session context | Lấy `at`, `f.sid` từ `window.WIZ_global_data` và fire in-page | **THÀNH CÔNG:** 200 OK (258 ms), tạo project `d3059ec6-...` | Xác nhận các thao tác quản lý project không cần reCAPTCHA và có thể gọi độc lập hoàn toàn. | 0 credit |
| **Post-E8 Bug** | Tải ảnh từ URL Signed CDN | Regex bắt URL từ chuỗi thô | HTTP `403 AccessDenied` | Regex bị cắt cụt tại ký tự unicode `\u003d` (`=`). Thay bằng `json.loads` để unescape chuẩn xác. Sửa xong tải ảnh thành công. | 0 credit |
| **R1** | Tự động hóa hoàn toàn bằng script Python | Script tự mở trang, nhập prompt, click nút, capture và fire | Thất bại với mã gRPC `[3]` `INVALID_ARGUMENT` (di ~1.8s) | **Lỗi tràn số nguyên Protobuf:** Seed sinh bằng `randint(1, 2**32 - 1)`. Giá trị `2905577744` vượt quá giới hạn **int32 có dấu** ($2^{31}-1 = 2147483647$). | 0 credit |
| **R2** | Khắc phục ràng buộc seed int32 | Đổi seed thành `randint(1, 2147483647)`, fire sau 78ms | **THÀNH CÔNG RỰC RỠ:** Ảnh quả táo đỏ trên đĩa (`"Red apple on plate"`, 1376×768, 84.8 KB). | Hoàn thiện toàn bộ logic của client tự động hóa production. | ~1 credit |

---

## 7. Giai Đoạn 5: Thiết Kế & Xây Dựng Cầu Nối Vận Hành Tất Định (Bridge Mode Implementation)

Từ các phát hiện thực nghiệm trên, mã nguồn vận hành chính thức được cấu trúc thành các module độc lập không phụ thuộc vào LLM.

### 7.1. Chu trình vận hành Bridge Mode ([`src/Bridge/flow_bridge.py`](file:///D:/Dev/rev-flow/src/Bridge/flow_bridge.py))

```text
[1] Attach Playwright via CDP (http://127.0.0.1:9222) vào Tab Flow
                          │
[2] Bơm Fetch Hook vào Page Context (window.__flowHook)
    • Lắng nghe request có rpcids=ogiZ0b
    • Nếu KHÔNG có header 'x-harness-ours':
        - Đọc body qua input.text() hoặc init.body
        - Lưu vào window.__flowHook.cap
        - Chặn bằng Promise.reject() ──▶ APP KHÔNG TIÊU CREDIT (0 credit decoy)
                          │
[3] Giả lập nhập prompt & Click "Bắt đầu tạo" (như người dùng thật)
    • App tự động chạy handshake reCAPTCHA reload
    • App tự build request ogiZ0b và gửi đi
    • Request bị Hook chặn lại trong tích tắc (~50-80ms)
                          │
[4] Python Bridge trích xuất từ Captured Request:
    • Fresh reCAPTCHA token (args[1][0][7][10][0])
    • XSRF token 'at'
    • Sequence counter '_reqid'
                          │
[5] Python Builder dựng Payload mới:
    • Prompt thật của người dùng
    • Seed ngẫu nhiên chuẩn int32 (1 .. 2^31 - 1)
    • UUID4 in HOA (u1, u2, generation_id)
    • _reqid = app_reqid + 100000
                          │
[6] Fire in-page bằng fetch() mang header 'x-harness-ours':
    • Hook phát hiện header bypass ──▶ Cho phép gửi thẳng lên server Google
    • Kết nối giữ long-poll ~18–24s ──▶ Nhận về HTTP 200 payload
                          │
[7] Bóc tách 2 lớp JSON ──▶ Trích SIGNED_CDN_URL (hạn 6h) ──▶ Tải ảnh JPEG về ổ đĩa
```

### 7.2. Hook JavaScript Idempotent Production ([`src/Bridge/flow_bridge.py`](file:///D:/Dev/rev-flow/src/Bridge/flow_bridge.py))
Dưới đây là mã nguồn hook JavaScript hoàn chỉnh, xử lý đồng thời cả `Request` instance và chuỗi string URL/body:

```javascript
// src/Bridge/flow_bridge.py — HOOK_JS
(() => {
  const isOgi = u => {
    const s = String(u || '');
    return s.indexOf('/data/batchexecute?') >= 0 && s.indexOf('rpcids=ogiZ0b') >= 0;
  };
  const isOurs = h => {
    try {
      return !!(h && (h['x-harness-ours'] || (h.get && h.get('x-harness-ours'))));
    } catch (e) {
      return false;
    }
  };

  if (!window.__flowHook) {
    window.__flowHook = { v: 3, cap: null, blocked: false };
    const prevFetch = window.fetch;
    window.fetch = function(input, init) {
      let url = '';
      try { url = typeof input === 'string' ? input : (input && input.url) || ''; } catch (e) {}
      
      // Nếu không phải ogiZ0b hoặc cờ chặn đang tắt -> cho qua bình thường
      if (!isOgi(url) || !window.__blockOgi) return prevFetch(input, init);

      // Trường hợp 1: App gọi fetch bằng Request instance (fetch(new Request(...)))
      if (typeof input !== 'string' && input && typeof input.text === 'function') {
        const ours = isOurs(init && init.headers);
        if (!ours) {
          const cap = { url: String(url), body: '', bodyReady: false, ts: Date.now(), via: 'fetch-request' };
          window.__flowHook.cap = cap;
          input.text().then(t => {
            cap.body = t;
            cap.bodyReady = true;
            window.__flowHook.blocked = true;
          }).catch(e => {
            cap.readErr = String(e);
            cap.bodyReady = true;
          });
          // Reject promise để request không bao giờ rời khỏi máy tính -> 0 credit!
          return Promise.reject(new Error('bridge-blocked-ogiz0b'));
        }
        return prevFetch(input, init);
      }

      // Trường hợp 2: App gọi fetch bằng url string (fetch(url, init))
      const body = String((init && init.body) || '');
      const ours2 = isOurs(init && init.headers);
      if (!ours2) {
        window.__flowHook.cap = { url: String(url), body: body, bodyReady: true, ts: Date.now(), via: 'fetch-init' };
        window.__flowHook.blocked = true;
        return Promise.reject(new Error('bridge-blocked-ogiz0b'));
      }
      return prevFetch(input, init);
    };
  }

  // Đặt lại trạng thái sẵn sàng cho lượt capture mới
  window.__flowHook.cap = null;
  window.__flowHook.blocked = false;
  window.__blockOgi = true;
  return { installed: true };
})()
```

### 7.3. Trích xuất Session Context Tự Động Từ Bộ Nhớ SPA
Với các thao tác không cần reCAPTCHA như **Tạo Project (`jHPbke`)** hoặc **Lấy danh sách Project (`UpteDb`)**, ta không cần click UI mà đọc trực tiếp session context từ bộ nhớ JavaScript của trang:

```python
# src/Bridge/flow_bridge.py — get_session_ctx()
ctx = page.evaluate("""() => {
    const wiz = window.WIZ_global_data || {};
    return {
        at: wiz.SNlM0e || '',      // Token XSRF chính chủ
        f_sid: wiz.FdrFJe || '',   // Session ID phiên SPA
        bl: wiz.cfb2h || ''        // Build label hiện hành
    };
}""")
```

### 7.4. Phân loại Phản hồi & Bảng Mã gRPC Canonical Status
Khi gọi `batchexecute`, Google luôn trả về HTTP status 200. Để xác định thành công hay thất bại, ta phải bóc tách cột thứ 5 của frame `wrb.fr`:

```python
# Cấu trúc frame wrb.fr:
# [["wrb.fr", "ogiZ0b", <PAYLOAD_OR_NULL>, null, null, <GRPC_STATUS_OR_NULL>, "generic"]]
```

| Cột 3 (Payload) | Cột 5 (Status) | Mã gRPC | Ý nghĩa kỹ thuật | Hành vi xử lý của Client |
| :--- | :--- | :--- | :--- | :--- |
| `[...JSON...]` | `null` | `0` (OK) | Yêu cầu thành công, có signed URL. | Parse URL, tải ảnh và lưu metadata. |
| `null` | `[3]` | `3` (INVALID_ARGUMENT) | Sai định dạng hoặc kiểu dữ liệu (ví dụ: Seed vượt int32). | **Lỗi logic của ta:** Không retry, báo lỗi ngay lập tức. |
| `null` | `[7, [...ErrorInfo]]` | `7` (PERMISSION_DENIED) | Anti-abuse từ chối (`PUBLIC_ERROR_UNUSUAL_ACTIVITY`). | Token cũ hoặc spam: kích hoạt backoff, cooldown profile. |
| `null` | `[16]` | `16` (UNAUTHENTICATED) | Hết hạn phiên cookie hoặc XSRF không hợp lệ. | Đánh dấu phiên chết, yêu cầu đăng nhập lại. |

### 7.5. Lớp Bảo Vệ Vận Hành (Resilience Layer)
Được triển khai trong [`src/Workflows/flow_client.py`](file:///D:/Dev/rev-flow/src/Workflows/flow_client.py):
- **Humanized Pacing (Gaussian Jitter):** Giãn cách ngẫu nhiên có độ lệch chuẩn Gauss giữa các thao tác gõ chữ và bấm nút, xóa bỏ nhịp điệu máy móc.
- **Circuit Breaker (Bộ ngắt mạch):** Tự động lưu trạng thái tại `out/bridge_state.json`:
  - Gặp mã `401 / 403`: Cooldown 30 phút.
  - Gặp mã `429`: Cooldown 10 phút.
  - Gặp 3 lỗi anti-abuse liên tiếp: Cooldown 30 phút.
- **Chế độ Dry-Run:** Cho phép chạy toàn bộ quy trình (CDP -> gõ -> click -> chặn -> build) nhưng **dừng lại ngay trước bước fire**. Đảm bảo kiểm tra sức khỏe luồng và selector với **chi phí 0 credit**.

---

## 8. Giai Đoạn 6: Nâng Cấp Nâng Cao (i2i Template-Replay, N-Account Pool & Storyboard DAG)

### 8.1. Kỹ thuật Image-to-Image (i2i) Template Replay
Tham khảo chi tiết tại [`docs/api_specs/flow_image2image.md`](file:///D:/Dev/rev-flow/docs/api_specs/flow_image2image.md).

#### Vấn đề
Giao thức upload nhị phân ảnh tham chiếu lên Google Flow sử dụng luồng multipart phức tạp và sinh ra các `media_id` phụ thuộc vào project. Đảo ngược luồng upload này rất tốn công và dễ bị gãy khi Google đổi định dạng.

#### Giải pháp Template Replay
Thay vì đảo ngược giao thức upload:
1. Dùng Playwright gắn file vào thẻ `<input type="file">` của composer trên giao diện.
2. Ứng dụng tự tải ảnh lên máy chủ và tự tạo khối tham chiếu `media_id`.
3. Hook của ta chặn request sinh ảnh i2i đầu tiên (0 credit) và lưu cấu trúc đó thành một **`ReferenceTemplate`**.
4. Các lượt sinh ảnh tiếp theo chỉ việc lấy template này ra, sử dụng hàm `build_args_from_template()` để thay thế: token mới, seed mới, prompt mới và UUID mới, **giữ nguyên 100% khối media tham chiếu do app đã dựng**.
5. Lưu cache vào `configs/reference_media_cache.json` theo khóa `account_id + sha256(file)`. Với 100 ảnh có chung 1 nhân vật tham chiếu, ta **chỉ cần upload đúng 1 lần duy nhất**.

```python
# src/Workflows/flow_models.py — build_args_from_template() chuẩn Production
def build_args_from_template(
    template_args: list,
    *,
    token: str,
    seed: int,
    prompt: str = "",
    old_prompt: str = "",
    u1: Optional[str] = None,
    u2: Optional[str] = None,
    gen_id: Optional[str] = None,
) -> tuple[list, dict]:
    """Replay template i2i đã capture từ app với token/seed/prompt/UUIDs tươi."""
    args = copy.deepcopy(template_args)
    replaced = {"token": False, "seed": False, "prompt": 0, "uuids": 0}

    # 1. Điền token reCAPTCHA tươi vào vị trí ref chuẩn ref[10][0]
    try:
        ref = args[1][0][7]
        if isinstance(ref, list) and len(ref) > 10 and isinstance(ref[10], list) and ref[10]:
            ref[10][0] = token
            replaced["token"] = True
    except Exception:
        pass
    if not replaced["token"]:
        replaced["token"] = _walk_replace(
            args, lambda s: isinstance(s, str) and bool(_TOKEN_RE.match(s)), token
        ) > 0
    if not replaced["token"]:
        raise ValueError("Template i2i: không tìm thấy chỗ điền token — hãy capture lại template.")

    # 2. Điền seed int32 chuẩn
    try:
        spec = args[1][0]
        if isinstance(spec[3], int) and not isinstance(spec[3], bool):
            spec[3] = int(seed)
            replaced["seed"] = True
    except Exception:
        pass

    # 3. Thay prompt cũ bằng prompt mới thông qua duyệt đệ quy cây AST
    if old_prompt and prompt and old_prompt != prompt:
        replaced["prompt"] = _walk_replace(
            args,
            lambda s: isinstance(s, str) and old_prompt in s,
            lambda s: s.replace(old_prompt, prompt),
        )
        if not replaced["prompt"]:
            raise ValueError("Template i2i: prompt cũ không thấy trong args — hãy capture lại template.")

    # 4. Cập nhật các UUID theo dõi
    try:
        spec = args[1][0]
        if u1: spec[12] = u1; replaced["uuids"] += 1
        if u2: spec[13] = u2; replaced["uuids"] += 1
    except Exception:
        pass
    try:
        if gen_id and isinstance(args[4], list) and args[4]:
            args[4][0] = gen_id
            replaced["uuids"] += 1
    except Exception:
        pass

    return args, replaced
```

### 8.2. Kiến trúc Cụm N-Account Pool Co Giãn ([`src/Workflows/account_pool.py`](file:///D:/Dev/rev-flow/src/Workflows/account_pool.py))
Tham khảo tài liệu thiết kế tại [`docs/upgrade_plan_n_account_pool.md`](file:///D:/Dev/rev-flow/docs/upgrade_plan_n_account_pool.md).

Khi sản xuất số lượng lớn (ví dụ storyboard 100 ảnh), việc mở đồng loạt tất cả trình duyệt sẽ gây tràn RAM (mỗi browser chiếm ~500 MB). Hệ thống áp dụng công thức cấp phát theo nhu cầu thực tế:

$$N_{alloc}(J) = \min\left(N, M_{RAM}, \max\left(1, \left\lceil \frac{J}{Q_{target}} \right\rceil\right)\right)$$

Trong đó:
- $J$: Tổng số ảnh cần sinh trong batch.
- $N$: Tổng số tài khoản sẵn sàng trong vault.
- $Q_{target}$: Ngưỡng tải tối ưu trên mỗi tài khoản (mặc định $25$ ảnh/tài khoản).
- $M_{RAM}$: Giới hạn số trình duyệt mở song song tối đa của phần cứng máy chủ.

#### Ba trụ cột vận hành cụm
1. **Demand-Based Allocation:** Với batch 50 ảnh trên cụm 4 tài khoản, chỉ đánh thức đúng 2 tài khoản (`acc_01`, `acc_02`). Hai tài khoản còn lại ngủ đông hoàn toàn, tiết kiệm 50% RAM.
2. **Wear-Leveling & Affinity:** Lần chạy tiếp theo sẽ ưu tiên các tài khoản có `total_completed` thấp nhất và có sẵn cache `media_id` của ảnh tham chiếu.
3. **Hot-Spare Failover:** Nếu tài khoản đang chạy gặp lỗi `429` hoặc `401`, pool tự động cách ly tài khoản đó và **đánh thức ngay một tài khoản dự phòng (`acc_03`)** vào thế chỗ mà không làm gián đoạn tiến trình chung.

### 8.3. Điều Phối Phụ Thuộc Storyboard DAG ([`src/WebUI/jobs.py`](file:///D:/Dev/rev-flow/src/WebUI/jobs.py))
Để sản xuất bộ 100 ảnh đồng nhất phong cách cho video dài, pipeline phân bổ các shot thành các đợt phụ thuộc (Dependency Waves):
- **Wave 1 (Anchor Shots):** Tạo 10–12 ảnh mốc nhân vật và bối cảnh chính bằng `text2image` (`anchor_char_01`, `anchor_env_01`) và các cảnh b-roll độc lập.
- **Wave 2 (Continuity Shots):** Các cảnh hành động `image2image` có trường `depends_on_shot_id` trỏ vào kết quả của Wave 1. Thuật toán tự động lấy file ảnh xuất ra từ Wave 1 làm ảnh tham chiếu cho Wave 2.
- Hàm `plan_dependency_waves()` tự động phát hiện chu trình phụ thuộc vòng (dependency cycles) hoặc các ID không tồn tại để loại bỏ trước khi gửi lệnh.

---

## 9. Quy Trình 7 Bước Chuẩn Mực Cho Mọi Dự Án Reverse API (Playbook & Checklist)

Dưới đây là cẩm nang từng bước để bạn áp dụng cho bất kỳ hệ thống Web SPA phức tạp nào:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                 7 BƯỚC REVERSE ENGINEERING WEB API CHUẨN MỰC                │
│                                                                             │
│  [Bước 1] Khởi tạo môi trường Vault độc lập, cố định Seed & Hardware Profile│
│                                      │                                      │
│  [Bước 2] Lắng nghe CDP thụ động, lưu JSONL, cấm Mitmproxy xâm lấn          │
│                                      │                                      │
│  [Bước 3] Action Tagging: Gắn nhãn thao tác UI ↔ Cụm Request mạng           │
│                                      │                                      │
│  [Bước 4] Differential Analysis: Chạy 2 lần vi sai để lập bản đồ Schema    │
│                                      │                                      │
│  [Bước 5] Thiết kế cơ chế Zero-Credit / Zero-Cost Testing (Hook in-page)    │
│                                      │                                      │
│  [Bước 6] Thử nghiệm Replay: Verbatim trước ──▶ Custom Builder sau          │
│                                      │                                      │
│  [Bước 7] Đóng gói Module Vận hành Tất định, Circuit Breaker & Cooldown     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Checklist Kiểm Tra Từng Bước
- [ ] **Bước 1:** Trình duyệt có bị hiện banner đỏ cờ lạ không? Sandbox đã bật chưa? WebRTC leak đã được chặn chưa?
- [ ] **Bước 2:** Bộ sniffer có bị treo khi gặp SSE/EventSource không? Có bắt được cả `fetch`, `xhr` lẫn `websocket` không?
- [ ] **Bước 3:** Đã cô lập được chuỗi request chính xác trong khoảng 1–2 giây quanh cú click chưa?
- [ ] **Bước 4:** Đã phân tích diff đệ quy chưa? Có bao nhiêu trường thay đổi? Đã tách riêng telemetry ra khỏi RPC nghiệp vụ chưa?
- [ ] **Bước 5:** Có thể chặn request app ngay tại client để không tốn quota/credit không?
- [ ] **Bước 6:** Khi replay, đã kiểm tra giới hạn kiểu dữ liệu Protobuf (int32 vs uint32), chữ hoa UUID, và chuẩn encode URL chưa?
- [ ] **Bước 7:** Đã trang bị Circuit Breaker tự ngắt khi gặp `429/401` và Humanized Pacing bằng Gaussian jitter chưa?

---

## 10. 10 Nguyên Tắc Vàng Dành Cho Kỹ Sư Reverse Engineering

1. **Không đoán mò wire format:** Hãy để hệ thống mạng tự khai báo thông qua passive sniffer. Một giờ làm differential analysis chất lượng hơn một ngày mò mẫm thử nghiệm mù.
2. **Cạm bẫy Double-Encoding:** Luôn chú ý tới các định dạng JSON lồng trong chuỗi và các tham số form URL. Kiểm tra kỹ xem ký tự đặc biệt (như dấu `:` trong token `at`) có bị biến thành `%253A` hay không.
3. **Tái sử dụng thay vì cố giải mật mã (Reuse over Reinvent):** Khi gặp các hệ thống bot detection tinh vi (reCAPTCHA Enterprise, Turnstile), việc tìm cách tự mint token từ bên ngoài hầu như luôn thất bại. Hãy để chính môi trường trình duyệt thật của ứng dụng sinh token, sau đó "mượn" token tươi thông qua kỹ thuật in-page hooking.
4. **Zero-Credit Testing là bắt buộc:** Khi đảo ngược các dịch vụ có tính phí theo lượt gọi, luôn tìm cách bẻ gãy request trước khi nó rời khỏi trình duyệt (chặn bằng fetch hook hoặc abort request) để phân tích cấu trúc mà không mất chi phí.
5. **Cửa sổ thời gian (Ephemeral TTL):** Token bảo mật thường đi kèm dấu thời gian và có thời hạn sống tính bằng mili-giây. Cơ chế bridge phải bắn request gần như ngay lập tức (< 100ms) sau khi bắt được token.
6. **Kiểm tra giới hạn kiểu dữ liệu (Data Type Constraints):** Các backend viết bằng C++/Go/Java thường ép kiểu dữ liệu chặt chẽ qua Protobuf. Một số nguyên sinh ngẫu nhiên 32-bit không dấu (`uint32`) có thể làm sập parser nếu backend định nghĩa trường đó là số nguyên 32-bit có dấu (`int32` $\le 2^{31}-1$).
7. **Định dạng UUID có thể mang ý nghĩa:** Một số validator backend phân biệt giữa UUID chữ thường (`uuid.lower()`) và UUID chữ hoa (`uuid.upper()`). Hãy luôn bắt chước chính xác 100% định dạng mà web app đang dùng.
8. **Loại bỏ telemetry để giữ mã nguồn gọn nhẹ:** Nhận diện và bỏ qua các request log/analytics (`WuwhI`, Google Analytics, Sentry). Chúng chỉ làm loãng mã nguồn và tăng nguy cơ lỗi không đáng có.
9. **Tách biệt Pha Khám Phá và Pha Vận Hành:** LLM và visual agent rất mạnh để tìm kiếm selector và khám phá luồng, nhưng mã nguồn đưa vào sản xuất phải là code tất định (deterministic Playwright + Python/FastAPI) để đảm bảo tốc độ và độ tin cậy.
10. **Thiết kế khả năng chịu lỗi (Resilience by Design):** Mọi API đảo ngược đều có nguy cơ thay đổi hoặc bị ngắt kết nối tạm thời. Luôn trang bị cơ chế Circuit Breaker, Exponential Backoff, Gaussian Jitter và Hot-Spare Failover ngay từ ngày đầu tiên.

---

## 11. Bài Tập Thực Hành & Tự Đánh Giá (Diagnostic Scenarios & Self-Assessment)

Để củng cố kiến thức, hãy tự trả lời và đối chiếu 4 tình huống thực tế sau:

### Tình huống 1: Replay trả về HTTP 200 nhưng không có kết quả nghiệp vụ
- **Hiện tượng:** Bạn gửi request `batchexecute`, nhận về HTTP status 200. Tuy nhiên thời gian phản hồi chỉ mất 15ms (`di` = 15) và mảng payload trả về `null`.
- **Câu hỏi chẩn đoán:** Lỗi nằm ở đâu? Làm sao để biết nguyên nhân chính xác?
- **Đáp án:** Hãy kiểm tra cột thứ 5 của frame `wrb.fr`. Nếu cột 5 là `[3]`, đây là mã gRPC `INVALID_ARGUMENT` (sai định dạng tham số hoặc tràn số int32). Nếu là `[7]`, đây là `PERMISSION_DENIED` do token anti-bot hết hạn hoặc bị phát hiện hành vi bất thường.

### Tình huống 2: Tải file từ Signed URL bị mã lỗi 403 Forbidden
- **Hiện tượng:** Server trả về URL tải ảnh CDN có dạng `https://...Expires=...&Signature=...`, nhưng khi dùng thư viện `requests.get()` lại nhận mã lỗi HTTP 403.
- **Câu hỏi chẩn đoán:** URL vừa được cấp phát, tại sao lại bị từ chối?
- **Đáp án:** Kiểm tra lại cách trích xuất URL. Nếu trích xuất bằng Regex từ chuỗi raw payload, ký tự `=` trong URL bị Google encode thành `\u003d`. Chuỗi URL bị cắt cụt làm sai chữ ký số. Cần dùng `json.loads()` để giải mã unicode trước khi tải.

### Tình huống 3: Playwright không thể kết nối vào cổng 9222
- **Hiện tượng:** Bạn khởi chạy Chromium bằng lệnh `playwright.chromium.launch(args=["--remote-debugging-port=9222"])`, nhưng script bên ngoài gọi `connect_over_cdp("http://127.0.0.1:9222")` báo lỗi connection refused.
- **Câu hỏi chẩn đoán:** Tại sao cổng 9222 không mở?
- **Đáp án:** Driver của Playwright luôn ngầm chèn cờ `--remote-debugging-pipe`. Khi cờ pipe tồn tại, Chromium tự động tắt cổng HTTP CDP. Bạn phải khởi chạy trình duyệt thông qua `subprocess.Popen` trực tiếp để có toàn quyền kiểm soát tham số dòng lệnh.

### Tình huống 4: Yêu cầu Replay bị lỗi HTTP 400 Bad Request ngay lập tức
- **Hiện tượng:** Gửi lại một request form URL-encoded nhưng server từ chối ngay lập tức với mã 400.
- **Câu hỏi chẩn đoán:** Lỗi thường gặp nhất ở tầng transport là gì?
- **Đáp án:** Lỗi Double-Encoding. Token phiên `at` thường chứa dấu `:` (`%3A`). Nếu hàm serialize form tiếp tục gọi `quote()` thêm một lần nữa, dấu `%` biến thành `%25`, làm token trở thành `%253A`. Cần `unquote()` trước khi đưa vào hàm tạo form URL.

---

## 12. Bảng Tra Cứu Mã Nguồn & Tài Liệu Kỹ Thuật Trong Repo

Bản đồ liên kết trực tiếp tới các module và tài liệu trong kho lưu trữ để tiện tra cứu:

### Tài Liệu Đặc Tả & Báo Cáo
- [`docs/api_specs/flow_transport.md`](file:///D:/Dev/rev-flow/docs/api_specs/flow_transport.md) — Đặc tả chi tiết giao thức vận chuyển `batchexecute`, query params, cấu trúc envelope và danh mục RPC.
- [`docs/api_specs/flow_create_image.md`](file:///D:/Dev/rev-flow/docs/api_specs/flow_create_image.md) — Toàn văn đặc tả RPC sinh ảnh `ogiZ0b`, phân tích diff 2 run và các quy tắc bắt buộc.
- [`docs/api_specs/flow_create_project.md`](file:///D:/Dev/rev-flow/docs/api_specs/flow_create_project.md) — Đặc tả RPC tạo dự án `jHPbke` và đọc dự án `UpteDb`.
- [`docs/api_specs/flow_image2image.md`](file:///D:/Dev/rev-flow/docs/api_specs/flow_image2image.md) — Thiết kế cơ chế i2i Template-Replay không cần đảo ngược RPC upload.
- [`docs/phase4_report.md`](file:///D:/Dev/rev-flow/docs/phase4_report.md) — Báo cáo nhật ký thực nghiệm chi tiết các mốc E0 → E8 và R1/R2.
- [`docs/upgrade_plan_n_account_pool.md`](file:///D:/Dev/rev-flow/docs/upgrade_plan_n_account_pool.md) — Kế hoạch kiến trúc cụm N tài khoản và công thức toán học cấp phát tài nguyên.
- [`docs/playground.md`](file:///D:/Dev/rev-flow/docs/playground.md) — Hướng dẫn vận hành Web UI playground (Flow Bench).

### Công Cụ Khám Phá (Discovery Tools)
- [`discovery/sniffer.py`](file:///D:/Dev/rev-flow/discovery/sniffer.py) — Bộ bắt gói tin Playwright CDP ra định dạng JSON Lines.
- [`discovery/decode_batchexecute.py`](file:///D:/Dev/rev-flow/discovery/decode_batchexecute.py) — Bộ giải mã wire format `batchexecute` (request double-encoded & response chunks).
- [`discovery/payload_differ.py`](file:///D:/Dev/rev-flow/discovery/payload_differ.py) — Công cụ phân tích vi sai đệ quy giữa 2 phiên trace mạng.
- [`discovery/probe_i2i_composer.py`](file:///D:/Dev/rev-flow/discovery/probe_i2i_composer.py) — Script thăm dò DOM composer và các thẻ `<input type="file">`.

### Mã Nguồn Vận Hành Chính Thức (Production Code)
- [`src/BrowserHost/launch_profile.py`](file:///D:/Dev/rev-flow/src/BrowserHost/launch_profile.py) — Quản lý vòng đời profile CloakBrowser cô lập và giải quyết xung đột cổng CDP.
- [`src/BrowserHost/pool_supervisor.py`](file:///D:/Dev/rev-flow/src/BrowserHost/pool_supervisor.py) — Điều phối đánh thức (wake) và đóng băng (hibernate) process Chromium theo PID.
- [`src/Bridge/flow_bridge.py`](file:///D:/Dev/rev-flow/src/Bridge/flow_bridge.py) — Cầu nối in-page CDP, cài fetch hook, bắt token và fire request.
- [`src/Workflows/flow_models.py`](file:///D:/Dev/rev-flow/src/Workflows/flow_models.py) — Pydantic DTOs, request builders, `build_args_from_template` và form encoder.
- [`src/Workflows/flow_client.py`](file:///D:/Dev/rev-flow/src/Workflows/flow_client.py) — Client cấp cao, CLI, Circuit Breaker và kiểm soát xác nhận credit.
- [`src/Workflows/account_pool.py`](file:///D:/Dev/rev-flow/src/Workflows/account_pool.py) — Bộ điều phối cụm N tài khoản với Demand-Based Allocation và Hot-Spare.
- [`src/WebUI/app.py`](file:///D:/Dev/rev-flow/src/WebUI/app.py) & [`src/WebUI/jobs.py`](file:///D:/Dev/rev-flow/src/WebUI/jobs.py) — Backend FastAPI, hàng đợi background job và điều phối DAG Storyboard.
- [`tests/test_account_pool.py`](file:///D:/Dev/rev-flow/tests/test_account_pool.py) — Bộ kiểm thử tự động cho toán học cấp phát pool, wear-leveling và i2i template.
