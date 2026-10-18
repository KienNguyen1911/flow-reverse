# Báo cáo Phase 4 — Google Flow Private API Client

> **Trạng thái:** ✅ HOÀN THÀNH chứng minh end-to-end cho cả 2 feature (`tạo project` + `tạo ảnh`).
> Báo cáo lập ngày 2026-10-18, sau E8 + jHPbke replay + **real run đầu tiên của test script (18:55 — ảnh "Red apple on plate", PASS)**.
> Module production + web playground (Flow Bench): **đã viết xong + đã test 0-credit** — xem §5 và `docs/playground.md`.

---

## 1. Kết quả tổng quan

| Feature | RPC | Trạng thái | Chi phí | Bằng chứng |
| :--- | :--- | :--- | :--- | :--- |
| Transport `batchexecute` (đọc) | `ngNC2` | ✅ PASS (Test 0) | 0 | `traces/phase4/test0_ngNC2_replay.json` |
| **Tạo project** | `jHPbke` | ✅ PASS (replay) | **0 credit** | `run_jhpbke.py` → project `d3059ec6-a97c-41c1-9a25-40fac3954a43` |
| **Tạo ảnh — verbatim** | `ogiZ0b` | ✅ PASS (E7) | ~1 credit | `e7_green_teapot.jpg` (120 KB) |
| **Tạo ảnh — builder của ta** | `ogiZ0b` | ✅ PASS (E8) | ~1 credit | `e8_purple_teapot.jpg` (115 KB) |
| **Tạo ảnh — test script auto (R2)** | `ogiZ0b` | ✅ PASS 1/1 (18:55) | ~1 credit | `out/test_2images_20261018_185519/` — "Red apple on plate" (84,8 KB) |

- **Tổng credit tiêu thụ: ~3** (E7 + E8 + real run R2 18:55). R1 (18:49) bị server từ chối = 0 credit.
- Ghi chú đo credit: RPC `nzlxg` (trạng thái tài khoản) trả `[1050, ...]` **không đổi** trước/trong/sau
  các generation → 1050 không phải bộ đếm ảnh (nhiều khả năng quota tổng/video của gói plan).
  Không có cách đo cost-per-image qua RPC; đếm theo số lần server chấp nhận request.

---

## 2. Những phần đã test (lịch sử thí nghiệm E0 → E8 + jHPbke)

| # | Mục đích | Cách làm | Kết quả | Credit |
| :--- | :--- | :--- | :--- | :--- |
| **0** | Chứng minh replay được 1 RPC đọc | Replay `ngNC2` in-page (same-origin fetch, `credentials:'include'`) | ✅ 200 OK. Phát hiện + fix bug double-encode `at` (`%253A`→400): phải `unquote` trước khi urlencode | 0 |
| **B** | Mint token reCAPTCHA bằng API chuẩn | `grecaptcha.enterprise.execute(sitekey, {action:'IMAGE_GENERATION'})` | ✅ Token `0cAFcWeA...` (~2510 chars) mint được | 0 |
| **C** | Fire `ogiZ0b` với token execute (builder còn lỗi: UUID thường, `_reqid` tự chế, timing xa) | Replay in-page | ❌ `UNUSUAL_ACTIVITY` (HTTP 200, lỗi RPC-level) | 0 |
| **E2** | Forensics `reload` | Đọc request/response reload từ trace | `reload` phát từ iframe `www.google.com` (content-type protobuf); replay từ main page bị CORS chặn → **bắt buộc** đọc qua CDP/iframe | 0 |
| **E3** | Chặn request app → 0 credit | Hook `window.fetch`: bắt `ogiZ0b`, reject | ✅ Chặn thành công: 0 request app ra ngoài = 0 credit. (Body app chưa đọc được — app truyền `Request` object, hook cũ chỉ đọc `init.body`) | 0 |
| **E5** | App có tự gọi `grecaptcha.execute` không? | Hook thêm vào `grecaptcha` | ✅ App **KHÔNG** gọi `execute` — token đến qua kênh iframe reload nội bộ | 0 |
| **E6** | Replay với token reload tươi (bug builder cũ vẫn nguyên) | Đọc trace live → trích token → fire sau ~7.8s | ❌ `UNUSUAL_ACTIVITY` → chứng minh **nguồn token không phải biến số duy nhất** | 0 |
| **F** | Forensics header / encoding / `_reqid` / body diff | So byte-level app vs ta | Kết luận: headers app ⊂ ta (khác duy nhất header bypass); encoding = `encodeURIComponent` chuẩn (0 diff); `at` **không** xoay vòng trong phiên; `_reqid` = base ngẫu nhiên ~58–59k + **100000**/request; diff +83 chars giải thích 100% bằng token dài hơn ×2 − seed; **cấu trúc args của ta đúng 100%** | 0 |
| **E7** | Replay **verbatim** (quyết định) | Hook mới đọc được body app (`Request.text()`) → chặn → fire lại y nguyên URL+body | ✅ **200 OK + ảnh thật** (gap 285 ms) | ~1 |
| **E8** | Replay **builder của ta dựng 100%** (chốt) | Builder Python: prompt riêng (tím), seed riêng, **UUID CHỮ HOA**, `_reqid` = app+100000, fire sau 72 ms | ✅ **200 OK + ảnh thật**. Seed + generation UUID của ta được server **echo lại** → kiểm soát tham số đầy đủ | ~1 |
| **J** | Replay `jHPbke` tạo project | Fire in-page với title tùy ý | ✅ 200 OK (258 ms) → project mới; title tùy ý **được chấp nhận**; app SPA-nav vào project mới và load OK (Zzl0ze/ngNC2/mrlkwd = 200) | 0 |
| **R1** | Real run đầu tiên của test script (auto, bridge mode) | Fire 1 ảnh với seed random cũ (`1..2³²−1`) | ❌ `[3]` INVALID_ARGUMENT — **KHÔNG phải** UNUSUAL_ACTIVITY (gRPC status 3, di ~1,8 s). Byte-level diff: body ta = body app ngoại trừ 4 field động → nghi phạm duy nhất: seed `2905577744` > 2³¹ | 0 |
| **R2** | Fix seed (`randint(1, 2³¹−1)`) → fire lại | Seed `464570899`, `_reqid` app+100000, gap 78 ms | ✅ 200 OK + **ảnh thật** `"Red apple on plate"` 1376×768 (84,8 KB), seed echo khớp; long-poll ~24 s | ~1 |

Chi tiết kỹ thuật đầy đủ: `docs/api_specs/flow_create_image.md` §7.5 (bảng đặc điểm bắt buộc),
`docs/api_specs/flow_create_project.md`, `docs/api_specs/flow_transport.md`.

---

## 3. Cách làm hiện tại — “Bridge Mode” (đã kiểm chứng end-to-end)

```text
CloakBrowser (profile flow_main, CDP :9222, đã login sẵn)
   │
[1] Mở/điều hướng page tới flow.google.com (project đích)
   │
[2] Cài hook fetch TRONG PAGE:
       • bắt mọi POST ...rpcids=ogiZ0b  → đọc body (input.text()) + url
       • REJECT ngay  → app không tiêu credit
   │
[3] Type prompt + click nút Generate NHƯ NGƯỜI DÙNG
       └─→ app tự chạy handshake reCAPTCHA (reload từ iframe)
   │
[4] Đọc từ capture của app:
       • recaptcha_token  (args[1][0][7][10][0] — token tươi vừa mint)
       • at               (param form trong body app)
       • _reqid           (counter thật của app, trong URL)
   │
[5] Builder của TA (Python) dựng body mới:
       • prompt/seed riêng, UUID CHỮ HOA (4 uuid: u1, u2, gen)
       • _reqid = app_reqid + 100000
       • fire trong ≤ ~100 ms sau response reload (E8: 72 ms)
   │
[6] fetch in-page (credentials:'include', x-same-domain, header bypass x-harness-ours)
       → long-poll ~18–24 s → payload 200 OK
   │
[7] Bóc 2 lớp JSON → SIGNED_CDN_URL → GET trực tiếp (UA thường) → ảnh JPEG
```

**Vì sao thiết kế này:**
- Token reCAPTCHA là thứ duy nhất không thể tự mint ở kênh chuẩn (execute từng bị từ chối) —
  cách chắc chắn là để **chính app mint** rồi ta “mượn” token trong tích tắc.
- Chặn request app = không tốn credit cho lần generate “mồi”, đồng thời lấy được đúng
  URL/`_reqid`/`at` mà app sẽ dùng.
- Request cuối cùng là 100% của ta → prompt/seed/số lượng do ta kiểm soát (E8 đã chứng minh).

**Sai số đã biết của bridge mode:** UI phải thao tác được (type + click); app hiện toast lỗi
(do request bị chặn — vô hại); vẫn phụ thuộc cấu trúc UI hiện tại (2 selector: `div.ProseMirror`,
`button.generate-icon-button`).

---

## 4. Cách làm E9 (khi được chạy) — “token sạch”, không cần UI click

**Mục tiêu:** bỏ bước type + click (bước [3]) — nếu thành công, client chạy hoàn toàn bằng code
(page + fetch), không điều khiển UI.

**Các bước dự kiến** (script mới `run_e9_exec_token.py`, tái dùng hạ tầng harness hiện có):

1. SPA-nav page tới `/project/<uuid>`; đặt `window.__blockOgi = true` (giữ hook làm bảo hiểm —
   không click nên app không tự fire; hook chỉ chặn nếu có gì đó tự phát).
2. **Mint token sạch:** `grecaptcha.enterprise.execute('6LdsFiUsAAAAAIjVDzcuLhaHiDn5nnHVXVRQGeMV',
   {action: 'IMAGE_GENERATION'})` → token `0cAFcWeA...` (~2500 ký tự). Đo thời gian mint.
3. Lấy `at` (từ request batchexecute gần nhất của app — hook capture `at`) và `_reqid`
   (counter lớn nhất quan sát được + 100000).
4. Dựng body bằng builder đã chứng minh ở E8 (UUID chữ hoa, args chuẩn, encode URI chuẩn).
5. **Fire ngay ≤ 1 s sau khi mint** (đúng nguyên tắc timing của E7/E8).
6. Poll ~20 s; xử lý 2 kịch bản:
   - ✅ **PASS** (~1 credit, ảnh thật): client có thêm chế độ “headless token” — không cần click UI;
     bridge mode giữ làm fallback.
   - ❌ **FAIL** `UNUSUAL_ACTIVITY` (0 credit): xác nhận backend Flow **chỉ** chấp nhận token
     phát hành qua kênh reload của app → bridge mode là bắt buộc. Ghi kết quả vào spec, dừng hướng này.

**Vì sao có thể fail:** E4 từng fail với token execute — nhưng trong điều kiện builder còn 3 lỗi
(UUID thường, `_reqid` lạ, timing xa). E9 kiểm chứng lại **chỉ với token** là biến số duy nhất.
**Chi phí:** 1 credit nếu accepted; **0 credit nếu rejected** → thí nghiệm “rẻ để biết”.

---

## 5. Module production đã viết (Python) + web playground (Flow Bench)

**Trạng thái:** ✅ đã viết xong và đã test end-to-end bằng các phép thử **0 credit**.
Đóng gói toàn bộ logic đã kiểm chứng thành thư viện + CLI + playground web,
**không phụ thuộc browser-harness / browser-use** — chỉ cần Playwright thuần `connect_over_cdp`.

**Cấu trúc đã triển khai:**

```text
src/
├── BrowserHost/
│   └── launch_profile.py        # ĐÃ CÓ — khởi chạy CloakBrowser + CDP :9222 (giữ nguyên)
├── Bridge/
│   └── flow_bridge.py           # ĐÃ VIẾT — Playwright connect_over_cdp: attach page, cài hook
│                                #   (block+capture ogiZ0b, capture at), nav/type/click,
│                                #   fire batchexecute, poll response, download, parse,
│                                #   jitter, session_ctx từ WIZ_global_data
├── Workflows/
│   ├── flow_models.py           # ĐÃ VIẾT — DTO Pydantic + args builder + parser response
│   │                            #   (parse_uptedb_projects recursive) + validate_seed int32
│   └── flow_client.py           # ĐÃ VIẾT — FlowClient (API cấp cao) + CircuitBreaker + CLI
└── WebUI/
    ├── app.py                   # ĐÃ VIẾT — FastAPI backend (REST + static serve) cho playground
    └── jobs.py                  # ĐÃ VIẾT — JobManager (queue 1 worker thread) + ProjectsStore

web/                             # ĐÃ VIẾT — frontend playground (React 19 + Vite + Tailwind v4)
```

**API đã có:**

```python
client = FlowClient(cdp_url="http://127.0.0.1:9222")   # attach vào CloakBrowser đang mở
st    = client.status()                                 # health check (0 credit)
projects = client.list_projects()                       # UpteDb — 0 credit
p     = client.create_project("Batch 18/10")            # jHPbke — 0 credit (tạo project thật)
res   = client.generate_image(p.id, prompt="...", aspect=3, seed=None, dry_run=False)
```

`generate_image()` trả `GenerationResult` với các status: `ok` / `ok_no_download` / `dry_run` /
`rejected` (kèm `reason`, `hint`, `grpc_code`, `anti_abuse`). **Dry-run** chạy đúng pipeline
(nav → type → click → capture → build) nhưng không fire request → 0 credit, dùng để kiểm tra trước.

**CLI đã có** (real run yêu cầu `--yes` khi không có TTY; dry-run miễn xác nhận):

```bash
python -m src.Workflows.flow_client status
python -m src.Workflows.flow_client list-projects [--json]
python -m src.Workflows.flow_client create-project --title "Batch 18/10"
python -m src.Workflows.flow_client generate --project <uuid> --prompt "..." --dry-run
python -m src.Workflows.flow_client generate --project <uuid> --prompt "..." --yes   # ~1 credit
```

**Resilience layer (đã triển khai theo `AGENTS.md` §4):**
- **Humanized pacing:** jitter Gaussian giữa các thao tác (type/click/fire/reload).
- **Circuit breaker** persisted tại `out/bridge_state.json`: `401/403` → cooldown 30 phút;
  `429` → 10 phút; 3 lần anti-abuse liên tiếp → 30 phút. Đếm `total_accepted` / `total_rejected`.
- **Phân loại reject:** gRPC `[3]` INVALID_ARGUMENT → không retry (lỗi của ta); `[7]`
  UNUSUAL_ACTIVITY → backoff 120 s, retry tối đa N lần (mặc định 1).
- **Seed ép trong int32** (`randint(1, 2³¹−1)`) — bài học R1.

**Web playground (Flow Bench)** — hướng dẫn đầy đủ: `docs/playground.md`.
Backend FastAPI: `/api/status`, `/api/projects` (+`/refresh`, `/create`), `/api/generate`
(bắt buộc `confirm=true` khi chạy thật; trả 423 khi breaker mở), `/api/jobs`, `/api/gallery`,
`/api/files/{run}/{file}`, `/api/circuit/clear`. UI bắt buộc xác nhận credit trong dialog riêng
trước mọi real run; dry-run không cần xác nhận.

**Bằng chứng đã test (toàn bộ 0 credit):**

| Hạng mục | Kết quả |
| :--- | :--- |
| CLI `status` | ✅ CDP OK, nhận diện đúng tab Flow + project |
| CLI `list-projects` | ✅ 6 dự án qua UpteDb (parser recursive) |
| CLI `generate --dry-run` | ✅ capture token + build OK, không fire, tab tự reload sạch |
| WebUI job `refresh projects` (POST → worker → store) | ✅ 6 dự án vào registry, job events đầy đủ |
| WebUI e2e dry-run (React → API → worker → bridge → capture → build → reload) | ✅ 18,4 s, result card + log, 0 credit |
| Gallery hiển thị ảnh thật (R2 "Red apple") + `/api/files` | ✅ |

**Chưa chạy lần nào (chờ user duyệt):** real run qua UI/module (fire + download + result card
"ok") — tốn ~1 credit nếu được nhận; `create_project` live qua module (0 credit nhưng tạo project
thật trong tài khoản — tránh tạo rác).

---

## 6. Dọn dẹp & lưu ý an toàn (đã thực hiện)

- 🗑️ **ĐÃ XÓA** `traces/extracted/cookies_dump.json` — file này chứa cookie phiên đầy đủ (nhạy cảm).
- Page test hiện tại: hook còn gắn nhưng **đã tắt chặn** (`window.__blockOgi = false`) —
  dùng app bình thường được ngay; **reload page sẽ xóa sạch mọi hook**.
- `at` / `f.sid` trong trace chỉ đúng với phiên trang hiện tại; **reload page là giá trị đổi mới**.
  Mọi script tương lai phải bắt tươi từ traffic (đúng quy trình hiện tại — không hard-code).
- Các project test: `d3059ec6-…` ("Client Test (delete me)" — xóa tự do), `3b368b0d-…`
  (chứa ảnh teapot + ảnh apple test), `62de7bce-…` (project của user — **không động tới**).
- 🔧 **ĐÃ SỬA** `src/BrowserHost/launch_profile.py`: strip cờ `--no-sandbox` (do SDK tự thêm) —
  Chrome hết banner "unsupported command-line flag … stability and security will suffer";
  đã verify command line sạch + sandbox bật (`traces/phase4/browser_procs.py`).

---

## 7. Index bằng chứng chính (`traces/phase4/`)

| Nhóm | File |
| :--- | :--- |
| **Ảnh kết quả** | `e7_green_teapot.jpg`, `e8_purple_teapot.jpg` |
| **Test script + runs R1/R2** | `discovery/test_generate_2_images.py` · `out/test_2images_20261018_18*/` (metadata/response/JPEG) · helper: `browser_procs.py`, `live_state_check.py`, `diff_bodies.py`, `raw_byte_check.py` |
| **Script E7/E8** | `run_e7_verbatim.py`, `run_e8_built.py`, `post_e7.py`, `post_e8.py` |
| **Script jHPbke** | `run_jhpbke.py`, `jhpbke_replay_response.txt` |
| **Request/response E8** | `e8_our_request_body.txt`, `e8_our_args.pretty.json`, `e8_replay_response.pretty.json` |
| **Capture app (E7)** | `e7_app_body.txt`, `e7_app_args.pretty.json`, `e7_app_captured_meta.json` |
| **Forensics** | `enc_forensics.py`, `str_diff.py`, `analyze_e6.py`, `chk_at.py` |
| **Thí nghiệm cũ (E2–E6)** | `run_e2_reload_replay.py`, `run_e3_hook_capture.py`, `run_e5_exec_hook.py`, `run_e6_trace_token.py`, `e3_*`, `e5_*`, `e6_*` |
| **Logs harness** | `e3/e5/e6/e7/e8_harness_output.txt`, `stage_ab_output.txt`, `stage_c_output.txt` |
| **Cleanup** | `cleanup_phase4.py` |
| **Playground QA (Phase 4 module)** | `out/ui_shots/*.png` (desktop/mobile, dialog xác nhận, gallery) · chụp lại: `traces/phase4/shot_webui.py`, `ui_dry_run.py` (e2e 0 credit), `ui_dialog_shot.py` |
