# Báo cáo: Fingerprint CloakBrowser · Proxy per-browser · Auto-Retry `PUBLIC_ERROR_UNUSUAL_ACTIVITY`

Tài liệu này tổng hợp kết quả điều tra (Task 1) và đặc tả triển khai (Task 2, Task 3).
Ngày: 2026-10-29.

---

## 1. Task 1 — Cơ chế khởi tạo Fingerprint của CloakBrowser

### 1.1 Các module liên quan

| File | Vai trò |
| :--- | :--- |
| `src/BrowserHost/launch_profile.py` | **Nguồn duy nhất** khởi tạo tiến trình CloakBrowser (subprocess trực tiếp, không qua Playwright launch wrapper). Đọc `browser_vault/<profile>/config.json`, dựng argv từ `cloakbrowser.build_args()`. |
| `src/BrowserHost/pool_supervisor.py` | Wake/hibernate profile. Không tự tạo browser: gọi `launch_profile.py` qua subprocess, truyền `--profile/--port/--pid-file/--vault-dir`. |
| `src/BrowserHost/run_daemon_browser.py` | Chạy daemon 1 profile cố định, cũng gọi `launch_profile.py`. |
| `src/Workflows/account_pool.py` | Chọn account nào được wake (`ensure_working_set → _wake_one → supervisor.ensure_running`). Không đụng tới fingerprint. |
| `src/Bridge/flow_bridge.py`, `flow_video_bridge.py` | Chỉ `connect_over_cdp()` vào browser **đã chạy**. Không tạo context/UA riêng. |

Kết luận: **không có** chỗ thứ hai nào tạo browser. Mọi thứ đi qua
`launch_profile.build_command()`.

### 1.2 Fingerprint được làm mới hay cố định?

**Cố định theo profile (persistent), không randomize mỗi lần chạy.**

Chuỗi quyết định trong `build_command()`:

```python
extra = [*cfg.extra_flags]
extra.append(f"--fingerprint={cfg['fingerprint_seed']}")   # cố định
extra.append(f"--user-data-dir={user_data_dir}")           # cố định
args = cloakbrowser.build_args(True, extra, timezone=cfg["timezone_id"], locale=cfg["locale"], headless=False)
```

`cloakbrowser.build_args()` (SDK 0.6.3) **mặc định sinh seed ngẫu nhiên mỗi lần**
(`get_default_stealth_args()` → `--fingerprint=<random 10000..99999>`), nhưng
`build_args` dedup theo key cờ, và `--fingerprint=<seed>` do ta chèn vào
`extra_args` **ghi đè** giá trị ngẫu nhiên đó. Đây là lý do fingerprint ổn định.

Do đó, tập thông số **giữ nguyên tuyệt đối giữa các lần khởi động cùng profile**:

| Thông số | Nguồn | Ghi chú |
| :--- | :--- | :--- |
| User-Agent | `--fingerprint=<seed>` | Seed chi phối UA, platform, vendor |
| Canvas / WebGL / AudioContext | `--fingerprint=<seed>` | Cùng seed ⇒ cùng nhiễu |
| Screen Resolution | cửa sổ thật (`start_maximized`) | SDK ghi rõ: kích thước lấy từ display thật, **không** phụ thuộc seed |
| Hardware Concurrency | `--fingerprint=<seed>` | |
| WebRTC | `extra_flags` + `--webrtc-ip-handling-policy=disable_non_proxied_udp` | Chặn rò rỉ IP thật khi có proxy |
| Timezone | `--fingerprint-timezone=<tz>` | `config.timezone_id` |
| Locale | `--lang` + `--fingerprint-locale` | `config.locale` |
| Cookies / localStorage / login | `--user-data-dir` | Session continuity |

Thông số **thay đổi** giữa các lần chạy: chỉ những gì thuộc runtime — thời điểm,
tab đang mở, `_reqid` của mạng, và (nếu bật) proxy.

Seed được sinh **một lần duy nhất** khi tạo profile
(`load_or_create_profile()` → `generate_seed()` 8 chữ số), và `validate_and_repair()`
chỉ sửa khi seed thiếu/hỏng. Không có cơ chế rotate seed.

### 1.3 Vì sao vẫn có thể bị `PUBLIC_ERROR_UNUSUAL_ACTIVITY`?

Fingerprint không phải biến số duy nhất. Theo `docs/api_specs/flow_create_image.md`
§7.5.2 #11/#15 và `docs/reverse_api_study_guide.md`:

1. **reCAPTCHA Enterprise token là ephemeral** (hiệu lực vài trăm ms). Trả lời
   chậm, hoặc fire lệch context ⇒ gRPC `[7]` PERMISSION_DENIED + `PUBLIC_ERROR_UNUSUAL_ACTIVITY`
   (HTTP 200, `di` ~12ms, 0 credit). Đây là nguyên nhân **phổ biến nhất**.
2. **Trùng IP**: nhiều profile `browser_vault/*` cùng đi ra một IP residential/datacenter,
   chạy song song (`max_active_browsers`). Fingerprint khác nhau nhưng IP giống nhau
   ⇒ tín hiệu "nhiều account một máy".
3. **Nhịp độ**: burst nhiều request liên tiếp trên cùng phiên.
4. **Provenance phiên**: cookie/phiên lâu ngày không tương tác UI thật.

Điểm 2 chính là lý do Task 2 (proxy per-browser) được yêu cầu: hiện tại `config.json`
**đã có** field `proxy` và launcher **đã** đọc nó, nhưng **không có đường nào từ UI/API/pool
để set** — mọi profile đều `"proxy": null` ⇒ tất cả dùng chung IP máy.

### 1.4 Đề xuất tối ưu (đã triển khai một phần)

| # | Đề xuất | Trạng thái |
| :--- | :--- | :--- |
| 1 | **Proxy riêng cho từng browser** để tách IP giữa các account | ✅ Task 2 |
| 2 | **Retry có backoff** khi gặp anti-abuse (không mất credit) | ✅ Task 3 |
| 3 | Giữ nguyên seed khi tái sử dụng profile; chỉ tạo profile mới khi cần identity mới | ✅ đã đúng sẵn |
| 4 | Giới hạn số browser song song (`max_active_browsers`) khi dùng chung IP | ⚙️ có sẵn (`M_RAM`), nên hạ xuống 2–3 nếu vẫn direct IP |
| 5 | Giãn nhịp giữa các node (`Gaussian jitter`) | ⚙️ có sẵn (`jitter()` trong `flow_bridge`) |
| 6 | Tương tác UI thật định kỳ cho profile "nguội" | ❌ chưa làm (ngoài phạm vi) |

> Không nên randomize fingerprint mỗi lần launch: đổi seed = đổi danh tính, làm
> cookie/phiên cũ trở nên "lạ" và **tăng** khả năng bị đánh dấu.

---

## 2. Task 2 — Proxy cho từng Browser (fallback Direct IP)

### 2.1 Định dạng chấp nhận

Tất cả các dạng sau đều được chuẩn hoá về một URL duy nhất:

```
null | "" | "   "                     → Direct IP (không thêm cờ nào)
host:port                              → http://host:port
user:pass@host:port                    → http://user:pass@host:port
http://host:8080 · https://host:8443
socks5://host:1080 · socks5://user:pass@host:1080
{"server": "host:8080", "username": "u", "password": "p"}
```

Scheme hỗ trợ: `http`, `https`, `socks5`, `socks5h`. Thiếu scheme ⇒ `http`.

### 2.2 Luồng dữ liệu

```
UI (AccountManagerModal)
  → PATCH /api/pool/accounts/{id}  {proxy, proxy_bypass, clear_proxy}
  → AccountPoolManager.update_account()
      ├─ normalize_proxy_value()  (validate sớm, lỗi rõ ràng)
      ├─ configs/accounts_pool.json   ← nguồn của pool
      └─ browser_vault/<profile>/config.json  ← nguồn của launcher
  → wake → launch_profile.build_command()
      └─ --proxy-server=<url> [--proxy-bypass-list=...]
```

### 2.3 Điểm sửa

| File | Thay đổi |
| :--- | :--- |
| `src/BrowserHost/launch_profile.py` | `normalize_proxy()`, `proxy_to_url()`, `describe_proxy()`; validate trong `validate_and_repair()`; `build_command()` chỉ thêm `--proxy-server` khi có proxy. |
| `src/Workflows/account_pool.py` | `AccountConfig.proxy / proxy_bypass / proxy_managed`; `normalize_proxy_value()`; `proxy_label()`; `add_account(proxy=…)`, `update_account(proxy=…, clear_proxy=…)`; `_sync_profile_proxy()` ghi vào vault; snapshot/detail trả label **không chứa mật khẩu**. |
| `src/WebUI/app.py` | `AddAccountBody`/`UpdateAccountBody` có `proxy`, `proxy_bypass`, `clear_proxy`. |
| `web/src/types.ts`, `api.ts`, `AccountManagerModal.tsx` | Ô nhập proxy khi tạo account, editor proxy từng account, badge `🌐 proxy` / `🌐 Direct IP`. |
| `browser_vault/_template/config.json` | Ghi chú định dạng proxy + `proxy_bypass`. |

### 2.4 Tương thích ngược

* `proxy` không có / `null` / `""` ⇒ argv **y hệt** trước đây (không có `--proxy-server`).
* Profile cũ cấu hình proxy trực tiếp trong `browser_vault/*/config.json` vẫn chạy:
  pool chỉ ghi đè khi `proxy_managed = true` (tức khi proxy được set **qua pool**).
* Không có migration bắt buộc; `configs/accounts_pool.json` cũ đọc được nguyên vẹn.

---

## 3. Task 3 — Auto-Retry khi gặp `PUBLIC_ERROR_UNUSUAL_ACTIVITY`

### 3.1 Module mới: `src/Workflows/node_retry.py`

```python
run_with_retry(fn, kind="image"|"video", log=job.add_event, abort=job.cancel_event)
```

| Kind | Retry 1 | Retry 2 | Sau đó |
| :--- | :--- | :--- | :--- |
| `image` | chờ 10s | chờ 20s | `NodeExecutionError(code="EXECUTION_ERROR")` |
| `video` | chờ 30s | chờ 60s | `NodeExecutionError(code="EXECUTION_ERROR")` |

Nhận diện lỗi (`is_unusual_activity`): result/exception chứa
`PUBLIC_ERROR_UNUSUAL_ACTIVITY`, hoặc `grpc_code == 7`, hoặc `anti_abuse == True`
**trên một kết quả rejected/failed**. Lỗi khác (file thiếu, aspect sai, safety
filter, prominent-people…) **không** retry — propagate ngay như cũ.

### 3.2 Điểm sửa

| File | Thay đổi |
| :--- | :--- |
| `src/Workflows/node_retry.py` | **Mới.** Policy + detection + sleep có thể hủy. |
| `src/WebUI/jobs.py` | `Job.cancel_event` / `Job.cancel()` / `Job.cancelled`; `_run_node_image` và `_run_node_video` bọc bằng `run_with_retry`; dispatcher bắt `NodeExecutionError` → `job.error = "[EXECUTION_ERROR] …"`; bắt `RetryAborted` → job dừng sạch. |
| `src/WebUI/app.py` | `POST /api/jobs/{jid}/cancel`. |
| `src/Workflows/account_pool.py` | `report_item_result(..., status="cancelled")` không tính là lỗi account. |
| `web/src/components/CanvasDrawer.tsx` | Banner "Đang chờ để tự động thử lại" + nút **Dừng chờ**, nút **Dừng** ở footer khi node đang chạy; nhánh chẩn đoán lỗi `UNUSUAL_ACTIVITY` riêng. |
| `web/src/api.ts` | `api.cancelJob(jobId)`. |

### 3.3 Log trên UI

Mỗi lần retry ghi **hai** event vào nhật ký của node (kind `retry` / `info`):

```
[retry] [Retry 1/2] Gặp lỗi PUBLIC_ERROR_UNUSUAL_ACTIVITY khi tạo video. Đang chờ 30s trước khi thử lại...
[info]  [Retry 1/2] Hết thời gian chờ (30s) — thử lại tạo video...
```

Nếu cạn lượt:

```
[error] [EXECUTION_ERROR] Vẫn bị hệ thống chống lạm dụng từ chối (PUBLIC_ERROR_UNUSUAL_ACTIVITY)
        sau 2 lần thử lại khi tạo video. <hint từ Flow>
```

### 3.4 Hủy khi đang đếm ngược

`_sleep_interruptible()` poll `abort` mỗi 250 ms ⇒ bấm dừng là thoát gần như tức thì,
không phải chờ hết 30/60s. Node kết thúc với `state=failed`,
`error="Đã dừng node tạo video theo yêu cầu (hủy trong lúc chờ retry)."` và một event
`warn` "[Retry 1/2] Đã hủy chờ…".

### 3.5 Kiểm thử

```
python -m pytest tests/test_node_retry.py tests/test_node_retry_jobs.py tests/test_browser_proxy.py -q
```

Bao phủ: đúng lịch backoff 10/20 và 30/60, retry rồi thành công, cạn lượt ⇒
`EXECUTION_ERROR` sau đúng 3 lần gọi, lỗi không liên quan không retry, hủy giữa
backoff kết thúc < 5s, proxy normalization + persistence + mirror vào vault.

---

## 4. Task 4 — Visual Group / Scope trên Canvas

### 4.1 Mục tiêu

Gom các node liên quan vào **một khung viền có tên** (ví dụ *Nhóm 1: Sinh ảnh
Lookbook*, *Nhóm 2: Render Video Try-on*), chọn node bằng **Shift + click** hoặc
**quét chuột**, và chạy workflow theo từng nhóm. Khi một node lỗi, chỉ **nhóm
chứa node đó dừng**, các nhóm khác vẫn chạy tiếp.

### 4.2 Mô hình dữ liệu

`Graph` trong localStorage (`fb_canvas_graph_v1`) có thêm `groups`:

```ts
interface CanvasGroup {
  id: string;
  name: string;
  nodeIds: string[];   // mỗi node chỉ thuộc tối đa 1 nhóm
  color?: string | null;
}
```

Khung nhóm **không lưu toạ độ** — nó được suy ra từ vị trí + chiều cao thực của
các node thành viên (`ResizeObserver` báo chiều cao), nên khung luôn bám sát khi
kéo node hoặc đổi nội dung node.

### 4.3 Thao tác trên UI

| Thao tác | Kết quả |
| :--- | :--- |
| Kéo chuột trên nền canvas | Quét (rubber-band) chọn các node giao với vùng kéo |
| `Shift` + kéo trên nền | Quét cộng dồn vào vùng chọn hiện tại |
| `Shift`/`Ctrl`/`Cmd` + click node | Bật/tắt node trong vùng chọn |
| `Ctrl+G` hoặc nút **Tạo nhóm** | Tạo nhóm từ vùng chọn (mở ô đổi tên ngay) |
| Nháy đúp tên nhóm | Đổi tên nhóm; `Enter`/`Esc` để chốt |
| Kéo header nhóm | Di chuyển toàn bộ node trong nhóm |
| Nút ✓ trên header | Chọn toàn bộ node của nhóm |
| Nút ✕ trên header | Giải tán nhóm (giữ nguyên node) |
| `Esc` | Bỏ chọn |
| `Space` + kéo / chuột giữa | Di chuyển canvas (pan) |

Click thường vào node **không** đổi vùng chọn — vùng chọn chỉ thay đổi qua
`Shift`+click hoặc quét chuột, để nhãn "Chạy vùng chọn (N)" không bị đổi ý ngoài
ý muốn. Kéo một node đang nằm trong vùng chọn sẽ di chuyển **toàn bộ** vùng chọn.
Node đã thuộc nhóm này không thể được gán sang nhóm khác (phải bỏ ra trước).

Mỗi nhóm có màu riêng (xoay vòng 6 màu) và nhãn trạng thái:
`N node` → `Đang chạy` → `Hoàn tất`, hoặc `Lỗi — dừng nhóm`.

### 4.4 Ngữ nghĩa thực thi (`runWorkflow`)

1. `buildRunUnits()` chia canvas thành các **unit** độc lập: mỗi nhóm là 1 unit,
   các node không thuộc nhóm được tách theo **thành phần liên thông** (qua liên
   kết nguồn) thành các unit ảo `Node lẻ (nhánh k)`, để hai pipeline rời nhau
   không chặn nhau khi một bên lỗi.
2. Nếu có vùng chọn: chỉ chạy các nhóm **chứa** node được chọn (chạy cả nhóm, vì
   nhóm là đơn vị nguyên tử) cộng các node lẻ đang chọn.
3. Unit được sắp theo `chainDepth` nhỏ nhất để nhóm thượng nguồn chạy trước.
4. Trong mỗi unit, node chạy theo `chainDepth` tăng dần (cha trước con).
5. **Khi một node lỗi:** các node còn lại *trong cùng unit* bị đánh dấu `skipped`
   với lý do "Đã hủy vì <tên nhóm> gặp lỗi trước đó", rồi vòng lặp chuyển sang
   unit kế tiếp. Node phụ thuộc chéo nhóm vẫn bị chặn qua bảng `srcOk`.
6. Kết thúc: toast tổng kết liệt kê các nhóm bị dừng, ví dụ
   `Workflow kết thúc — 1 nhóm bị dừng: Nhóm 2: Render Video Try-on.`

### 4.5 Hộp thoại xác nhận

Modal **Xác nhận chạy thật** liệt kê từng unit sẽ chạy kèm số node ảnh / video /
frame và tổng credit ước tính (Frame Cuối = 0 credit), thay cho con số gộp trước đây.

### 4.6 Điểm sửa

| File | Thay đổi |
| :--- | :--- |
| `web/src/components/CanvasPanel.tsx` | `CanvasGroup`, `groupFrame()`, `buildRunUnits()`, `unitMembers()`; state `selectedIds` / `marquee` / `nodeHeights`; drag kinds `group` + `marquee`; render khung nhóm + hình chữ nhật quét chọn; toolbar chọn nhóm; `runWorkflow` chạy theo unit. |
| `web/src/components/TopBar.tsx` | `CanvasStats` thêm `groupCount` / `selectedCount`; badge nhóm + badge vùng chọn; nút đổi nhãn thành "Chạy N node chọn" và tooltip mô tả chính sách dừng theo nhóm. |

