# discovery — Vòng lặp Khám phá UI → Mạng → Đặc tả

Thư mục này chứa các công cụ cho **Pha Khám phá & Bảo trì** (theo AGENTS.md mục 2). Vòng lặp gồm 4 bước: khởi chạy trình duyệt → chạy sniffer → thao tác UI qua browser-harness (có ghi mốc thời gian) → chạy differential analysis.

Luồng dữ liệu:

```text
launch_profile.py ──▶ Chromium (CDP port 9222) ◀── browser-harness (thao tác UI)
                              ▲
                              │ connect_over_cdp
                        sniffer.py ──▶ traces/raw_trace_<UTC>.jsonl
                                                  │
                                    payload_differ.py ──▶ báo cáo text + report.json
                                                  │
                                       docs/api_specs/<feature>.md  (đặc tả chốt lại)
```

> **Nguyên tắc vàng:** sniffer và browser-harness là **hai client CDP độc lập** attach vào **cùng một trình duyệt**. Không bao giờ mở trình duyệt thứ hai trên cùng profile (Chrome khóa `user_data_dir`).

---

## Bước 1 — Khởi chạy trình duyệt với cổng debug 9222

```bash
python src/BrowserHost/launch_profile.py --profile flow_main --wait
```

- Profile `flow_main` được tạo tự động từ `browser_vault/_template/config.json` trong lần chạy đầu (seed 8 chữ số sinh một lần, không đổi về sau).
- Cờ mở cổng đã nằm trong launcher: `--remote-debugging-port=9222 --remote-allow-origins=*`.
- `--wait` sẽ poll `http://127.0.0.1:9222/json/version` tới khi trình duyệt sẵn sàng. Xem trước lệnh mà không mở trình duyệt: thêm `--dry-run`.
- Kiểm tra nhanh cổng debug: `curl http://127.0.0.1:9222/json/version` (hoặc mở URL này bằng trình duyệt khác).

## Bước 2 — Chạy sniffer (process riêng, trước khi thao tác UI)

```bash
python discovery/sniffer.py --out-dir traces --types xhr,fetch,websocket --max-body 262144
```

- Mặc định `--cdp-url http://127.0.0.1:9222`, ghi **live** ra `traces/raw_trace_<UTC>.jsonl` (mỗi dòng một event JSON).
- Sniffer **chỉ đọc**: không click, không navigate. Có thể `tail -f traces/raw_trace_*.jsonl` ở terminal khác để theo dõi.
- Dừng bằng `Ctrl+C` — file được flush/đóng và in summary số event theo `kind`.
- Body nhị phân/protobuf được ghi dạng base64 kèm `"encoding": "base64"`; body bị cắt theo `--max-body` được đánh dấu `"truncated": true`.
- Response streaming (`text/event-stream`) và response redirect **không lấy body** (tránh treo sniffer khi stream chưa kết thúc) — chúng có `resp_body: null` + `body_error` giải thích.

## Bước 3 — Thao tác UI qua browser-harness, ghi mốc thời gian

Dùng **browser-harness** attach vào `http://127.0.0.1:9222` và thực hiện luồng cần khảo sát (ví dụ: tạo project → tạo ảnh).

**Lặp lại thao tác 2 lần với 1 tham số khác nhau** (ví dụ prompt ảnh khác nhau) để có dữ liệu diff ở bước 4. Trước/sau **mỗi** thao tác quan trọng, ghi lại mốc thời gian (epoch ms) — dùng để ánh xạ *Thao tác UI X → Request Y* khi đối chiếu JSONL (`ts_ms` của event nằm giữa 2 mốc chính là request do thao tác đó sinh ra).

Ghi mốc đơn giản nhất: lưu vào file `traces/action_log.md`, ví dụ:

```text
2026-10-18T09:12:31.220Z  [1] click "New project"       → bấm nút tạo project
2026-10-18T09:12:33.874Z  [1] nhập prompt "a red cat"    → gõ vào ô prompt
2026-10-18T09:12:35.101Z  [1] click "Generate"           → bắt đầu sinh ảnh
2026-10-18T09:13:02.550Z  [2] nhập prompt "a blue dog"   → lần 2, tham số đổi
2026-10-18T09:13:04.019Z  [2] click "Generate"
```

## Bước 4 — Differential Analysis

```bash
python discovery/payload_differ.py traces/raw_trace_<A>.jsonl traces/raw_trace_<B>.jsonl \
    --url-contains "batchexecute" --out traces/diff_report.json
```

- Ghép cặp **request/response theo `(method, url)` — first match** giữa 2 trace; endpoint không ghép được cặp được liệt kê riêng (chỉ có ở A / chỉ có ở B / instance dư).
- JSON body → liệt kê **mọi JSON path thay đổi** kèm giá trị A vs B (phục vụ xác định vị trí tham số như prompt, projectId...).
- Body nhị phân/protobuf → size, content-type, **offset byte khác đầu tiên**, preview ~100 bytes hex (kèm text preview nếu là UTF-8).
- `--url-contains` thu hẹp phạm vi (nên lọc theo endpoint nhóm `batchexecute` / `api` để diff sạch); `--out` xuất report JSON đầy đủ để agent chính đọc và viết đặc tả.

Sau bước 4, kết quả phân tích được chốt thành tài liệu tại `docs/api_specs/<feature>.md` kèm DTO — và từ đó chuyển sang Pha 4 (đóng gói module thực thi cố định trong `src/Workflows`, `src/Bridge`).

---

## Schema JSONL của sniffer (tóm tắt)

| Field | Ý nghĩa |
| :--- | :--- |
| `ts_ms` | epoch milliseconds (`time.time() * 1000`) — đối chiếu với mốc thời gian ở Bước 3 |
| `kind` | `request` \| `response` \| `ws_open` \| `ws_frame` \| `ws_close` |
| `method`, `url`, `status` | HTTP method / URL / status code (ws_*: `url` là URL WebSocket) |
| `resource_type` | Loại tài nguyên Playwright (`xhr`, `fetch`, `websocket`...) |
| `frame_direction` | Chỉ với `ws_frame`: `sent` (payload nằm ở `req_body`) hoặc `received` (ở `resp_body`) |
| `headers` | Header HTTP, giới hạn ~50 mục |
| `req_body` / `resp_body` | Body dạng text UTF-8; nếu nhị phân → base64 + `"encoding": "base64"` |
| `truncated` | `true` nếu body bị cắt theo `--max-body` |
| `body_error` | Lý do không đọc được response body (redirect/streaming/lỗi binary) |

## Xử lý sự cố nhanh

| Triệu chứng | Nguyên nhân thường gặp / cách xử lý |
| :--- | :--- |
| Sniffer báo "cannot attach to http://127.0.0.1:9222" | Chưa chạy Bước 1, hoặc trình duyệt được mở bởi công cụ khác không bật cổng debug. Kiểm tra `curl http://127.0.0.1:9222/json/version`. |
| Không thấy event nào | Sai `--types` (mặc định chỉ xhr/fetch/websocket) — dùng `--types all` hoặc mở rộng danh sách; kiểm tra trang có thật sự gửi request trong lúc sniffer chạy. |
| `resp_body` toàn `null` với `body_error` | Response nhị phân mà Playwright không đọc được, hoặc streaming — với Google Flow hãy xem thêm event `ws_frame`/các request `batchexecute` tương ứng. |
| Differ báo "only in A/B" quá nhiều | URL chứa tham số động (ví dụ `_reqid`, token) làm khóa `(method, url)` không khớp — dùng `--url-contains` để lọc về nhóm endpoint ổn định, và đọc các path khác nhau trong báo cáo để tách phần động. |
