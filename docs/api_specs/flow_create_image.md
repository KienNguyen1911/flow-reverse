# Feature: Tạo Ảnh (Google Flow, Nano Banana 2.1) — RPC `ogiZ0b`

> **Observed:** 2 lần generate thật (prompt chỉ khác 1 từ) — `traces/raw_trace_20261018T091806Z.jsonl`.
> Args đã decode: `traces/decoded/ogiZ0b_args_run1.pretty.json`, `ogiZ0b_args_run2.pretty.json`.
> Responses: `traces/decoded/ogiZ0b_response_1.pretty.json`, `ogiZ0b_response_2.pretty.json`.
> Diff 2 run: `traces/decoded/diff_report_ogiZ0b_WuwhI.txt`.
> Transport: xem `flow_transport.md`.

---

## 1. Hành vi UI (Observed)

- Input prompt: `div.ProseMirror` (contenteditable) trong `.prompt-box-container`, placeholder "Bạn muốn tạo những gì?".
- Nút submit: `button.generate-icon-button` (icon `arrow_forward`, disabled khi prompt rỗng).
- Nhập prompt (ví dụ qua `Input.insertText`) → nút enable → click submit.
- **`POST ogiZ0b` là long-poll**: giữ kết nối tới khi ảnh xong (~22s trong đo đạc), response mang luôn ảnh hoàn chỉnh. Không cần poll vòng ngoài.
- Khi xong: client bắn thêm `ngNC2` (refresh trạng thái project) — tùy chọn, không bắt buộc.

Timeline đo được (run1):
```
T+0.00s   click "Bắt đầu tạo"
T+0.61s   POST ogiZ0b            (seed=1449382406)
T+1.81s   POST WuwhI (telemetry MEDIA_GENERATION)
T+22.5s   response ogiZ0b — ảnh sẵn sàng (created [1792315176,...], completed [1792315194,...])
T+23.1s   ngNC2 (refresh UI)
```

## 2. Anti-bot: reCAPTCHA Enterprise (Observed — mấu chốt!)

Trước mỗi lần submit, page thực hiện handshake reCAPTCHA Enterprise:

```
POST https://www.google.com/recaptcha/enterprise/reload?k=6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV
     body: protobuf (base64) — chứa session id reCAPTCHA + token "mồi" 03AFcWeA...
     → response: )]}' ["rresp","0cAFcWeA4j1LrNRJwe3okr-...<≈2380 ký tự>"]
```

- Token trả về (`0cAFcWeA...`) = **đúng token được nhúng vào `ogiZ0b` args** tại 2 vị trí (`[1][0][7][10]` và `[3][10]`, dạng `[token, 1]`).
- **Token mới mỗi lần generate** (run1 vs run2 khác nhau hoàn toàn).
- Site key: `6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV` (reCAPTCHA Enterprise).
- Ngoài ra có `POST .../recaptcha/enterprise/clr?k=<sitekey>` (protobuf) ngay cạnh — vai trò phụ (đóng session?).

**Vị trí nhúng trong args (Observed):**
```json
[null, 22, null, null, null, "<project_uuid>", null, null, null, null, ["<recaptcha_token>", 1]]
```
(khối "project ref" bị lặp 2 lần — nhúng token ở cả hai)

> ✅ **Giải pháp đã kiểm chứng (E7/E8 — xem §7.5):** bắt token từ **response `reload`** khi app tự chạy
> handshake (trigger bằng click Generate thật trên UI; request `ogiZ0b` của app bị hook chặn → 0 credit).
> Đọc qua **CDP Network/sniffer** — bắt buộc vì request `reload` phát từ iframe cross-origin
> `www.google.com` nên hook in-page không thấy được. Token này nhúng thẳng vào `ogiZ0b` của ta → server chấp nhận.
> Đường (a) `grecaptcha.enterprise.execute`: mint được token `0cAFcWeA...` (~2510 ký tự, E4) nhưng replay
> từng bị `UNUSUAL_ACTIVITY` **trong điều kiện builder cũ** (UUID thường, `_reqid` tự chế, gap ~8s) —
> chưa cô lập lại với builder đã sửa (xem thể loại E9 ở §7.5.4).

## 3. Request `ogiZ0b` (Observed)

```
POST /_/AiSandboxAngularFrontend/data/batchexecute?rpcids=ogiZ0b&source-path=%2Fproject%2F3b368b0d-...&bl=...&f.sid=...&hl=vi&_reqid=2458716&rt=c
```

### 3.1 Args — bố cục đầy đủ (run1)

```jsonc
[null,
 [ // [1][0] — thông số sinh ảnh
   [null, null, null,
    <seed:int>,              // [3]  seed ngẫu nhiên client-side (run1: 1449382406, run2: 12125328)
    <aspect_ratio:int=3>,    // [4]  3 = 16:9 (mặc định từ settings chip). TODO: map enum khác
    "BELUGA",                // [5]  model key (Nano Banana 2.1)
    null,
    [null, 22, null, null, null,
     "<project_uuid>", null, null, null, null,
     ["<recaptcha_token>", 1]],                    // [7]  project ref (tool 22 + token)
    [[["<prompt>"]]],        // [8]  prompt dạng structured: [[[ "text" ]]]
    null, null, null,
    "<client_uuid_1>",       // [12] UUID v4 ngẫu nhiên mỗi request
    "<client_uuid_2>"],      // [13] UUID v4 ngẫu nhiên mỗi request
  1,                         // [2]  count = 1 (nút "x1")
  [null, 22, null, null, null,
   "<project_uuid>", null, null, null, null,
   ["<recaptcha_token>", 1]],                      // [3]  project ref lặp lại
  ["<generation_uuid>"]]     // [4]  UUID v4 client tạo trước; server ECHO lại trong response
```

**Diff 2 run (bằng chứng cô lập tham số):** chỉ khác ở `seed`, `recaptcha_token`, `prompt` (`red`→`blue`), 2 client UUID, `generation_uuid`. Mọi thứ khác bất biến.

### 3.2 Tham số & nguồn gốc

| Tham số | Nguồn | Ghi chú |
|---|---|---|
| `seed` | Client random | response echo lại; cùng seed ⇒ cùng ảnh (Inference) |
| `aspect_ratio` | Settings chip (`crop_16_9`) | 3 = 16:9. Chưa test các giá trị khác |
| `model` | Chip model | `BELUGA`; các model khác chưa capture |
| `prompt` | ProseMirror input | Plain text |
| `recaptcha_token` | Handshake §2 | **Bắt buộc** (gần như chắc chắn) |
| `generation_uuid` | Client uuid4 | Echo trong response (khóa đối chiếu kết quả) |
| `count` | Chip "x1" | 1; chưa test >1 |

## 4. Response (Observed)

Payload (đã bóc 2 lớp lồng):

```jsonc
[[["<media_uuid>",              // vd "b13031dc-0084-47e0-a2fe-ab78d5896fc5"
   null,
   "<item_uuid>",               // vd "c015ee19-1fbe-4a11-833a-509e3e69a917"
   null, null, null,
   [[null, <seed>, null, null, null, null, 1,
     "<prompt>", <prompt_tokens>, null, null, "<item_uuid>", null,
     "<SIGNED_CDN_URL>",        // https://flow-content.google/image/<media_uuid>?Expires=...&Signature=...
     3,                          // aspect_ratio
     [null, null, [["<prompt>", null, [[["<prompt>"]]]]], []],
     null, "<media_uuid>"],
    null, [<width>, <height>],   // vd [1376, 768]
    null, null, [null, "<SIGNED_CDN_URL>"]]]],
 [["<item_uuid>", null, null,
   ["<title>",                   // server tự đặt — vd "Red ceramic teapot on table"
    [<created_s>, <created_ns>],
    null, null,
    "<media_uuid>",
    "<generation_uuid>",         // = UUID client gửi ở args[4][0]
    [<completed_s>, <completed_ns>]],
   "<project_uuid>"]]]
```

Các trường đáng chú ý:

| Trường | Ý nghĩa | Kích thước quan sát |
|---|---|---|
| `SIGNED_CDN_URL` | URL tải ảnh, **signed, hết hạn 6h (21600s)** | GET trực tiếp **không cần cookie** → trả `image/jpeg` (99KB run1 / 133KB run2 — verify bằng tải thật) |
| `item_uuid` | ID "item" trong project (hiển thị UI) | |
| `media_uuid` | ID "media" (trùng tên file trên CDN) | |
| `generation_uuid` | Echo UUID client gửi — dùng đối chiếu | |
| `title` | Server tự đặt theo prompt (quan sát: tiếng Anh, ngay cả khi UI `hl=vi`) | "Red ceramic teapot on table" |
| `[width, height]` | Độ phân giải ảnh | 1376×768 (16:9) |

## 5. Đọc lại nội dung project (để lấy ảnh cũ) — `Zzl0ze`

`POST Zzl0ze` args: `["projects/<uuid>", null, null, null, [1]]`

Payload trả về (Observed, project 62de7bce có 2 ảnh):

```jsonc
[null,
 [ // [1] item summaries
   ["<item_uuid>", null, null,
    ["<title>", [<created_s>,<created_ns>], null, null, "<media_uuid>", "<generation_uuid>", [<completed_s>,<completed_ns>]],
    "<project_uuid>"], ...],
 [ // [2] media objects (kèm thumbnail hash + prompt + seed)
   ["<media_uuid>", "<project_uuid>", "<item_uuid>", null, null,
    [ [<created>], null, null, null, null, "<THUMBNAIL_URL lh3>", [...prompt...,...], null, null, 1, "<THUMBNAIL_URL>", null, null, <size_bytes> ],
    [ [null, <seed>, ..., "<title>", 36, "", null, "<item_uuid>", null, "<THUMBNAIL_URL>", 3], null, [<w>,<h>], null, null, [ "<THUMBNAIL_URL>" ] ]], ...],
 [ // [3] voices (TTS cho video — không cần cho ảnh)
   ["achernar", 3, "Achernar", [...]], ...],
 null, null, null,
 [ // [7] tool state
   null, null, [ [null,3,2,null,"beluga_display"], [null,2,1,null,"abra"] ], null, 1]]
```

**Cách lấy bytes ảnh cũ (2 con đường đã kiểm chứng):**

| Đường | Cách | Kết quả kiểm chứng |
|---|---|---|
| A. Signed URL (từ response generate) | `GET <SIGNED_CDN_URL>` | `200 image/jpeg`, không cần cookie ✓ (hết hạn 6h) |
| B. Thumbnail same-origin | `GET https://flow.google.com/asb/<hash>=s1600-rw` (hash lấy từ `THUMBNAIL_URL` trong Zzl0ze/UpteDb — phần đuôi sau `/asb/`) | `200`, WebP ~95KB — cần session cookie; fetch same-origin trong page ✓ |

Ghi chú: `<THUMBNAIL_URL lh3>` dạng `https://lh3.googleusercontent.com/asb/<hash>` — gọi trực tiếp không cookie bị `400` (TODO: cần cookie `googleusercontent` hay không).

## 6. Telemetry `WuwhI` — KHÔNG bắt buộc (Observed)

Ngay sau submit, page bắn `WuwhI` (event `MEDIA_GENERATION`) chứa **bản sao plaintext** cấu hình generate (imageModelKey, aspectRatio, seed, count, structuredPrompt, projectId). Response `[]`. Đây là kênh telemetry — **client không cần gửi** để generate thành công (TODO Phase 4 xác nhận bằng thực nghiệm).

## 7. DTO (Pydantic)

```python
from pydantic import BaseModel, Field


class RecaptchaAttestation(BaseModel):
    """[token, 1] — cặp token reCAPTCHA Enterprise + flag."""
    token: str  # "0cAFcWeA..." ≈ 2380 ký tự, mint mới mỗi lần generate
    flag: int = 1


class GenerateImageArgs(BaseModel):
    """Bố cục args ogiZ0b (xem §3.1 cho cấu trúc list thô)."""
    seed: int
    aspect_ratio: int = 3          # 3 = 16:9 (chưa map các giá trị khác)
    model: str = "BELUGA"          # Nano Banana 2.1
    tool_id: int = 22              # PINHOLE (image)
    project_id: str
    prompt: str
    count: int = 1
    client_uuid_1: str             # uuid4
    client_uuid_2: str             # uuid4
    generation_uuid: str           # uuid4 — được echo trong response
    recaptcha_token: str


class GeneratedImage(BaseModel):
    media_id: str
    item_id: str
    generation_id: str             # = generation_uuid client gửi
    seed: int
    prompt: str
    title: str                     # server tự đặt
    aspect_ratio: int
    width: int
    height: int
    signed_url: str                # hết hạn sau 6h
    created_ts: float              # từ [s, ns]
    completed_ts: float
    project_id: str


def build_generate_args(a: GenerateImageArgs) -> list:
    ref = [None, a.tool_id, None, None, None, a.project_id, None, None, None, None,
           [a.recaptcha_token, 1]]
    return [
        None,
        [[None, None, None, a.seed, a.aspect_ratio, a.model, None, ref,
          [[[a.prompt]]], None, None, None, a.client_uuid_1, a.client_uuid_2]],
        a.count,
        ref,
        [a.generation_uuid],
    ]
```

## 7.5. (Phase 4) Đặc tả thực thi ĐÃ KIỂM CHỨNG — E7/E8 (Observed 2026-10-18)

> Bằng chứng: `traces/phase4/run_e7_verbatim.py` + `run_e8_built.py` (logs `e7/e8_harness_output.txt`),
> request của ta `e8_our_request_body.txt`, args `e8_our_args.pretty.json`, response `e8_replay_response.pretty.json`,
> ảnh `e7_green_teapot.jpg` (120KB), `e8_purple_teapot.jpg` (115KB) — **generate từ code của ta, không dùng UI để submit**.

### 7.5.1. Quy trình "Bridge Mode" (đã kiểm chứng end-to-end)

1. Mở page flow.google.com đúng project (session cookies + `at`/`f.sid` của page hiện hành).
2. Cài hook `window.fetch` trong page: chặn mọi `POST ...rpcids=ogiZ0b` — đọc body qua `input.text()`
   (app truyền **`Request` object**, không phải string — `input.clone().text()` hoặc `input.text()` đều được),
   capture `{url, body, headers}`, rồi `Promise.reject(new Error('harness-blocked'))` → **app không tiêu credit**.
   (Bypass cho request của ta: header `x-harness-ours: 1` — server bỏ qua header lạ, E7/E8 chứng minh.)
3. Click nút Generate như người dùng → app chạy handshake reCAPTCHA (`reload` từ iframe) — **bắt token từ
   response reload** qua CDP Network (sniffer) đồng thời đọc token đó trong body app đã capture.
4. **Builder của ta** dựng body `ogiZ0b` (ai cũng dựng được — xem §7.5.2).
5. Fire trong page bằng `fetch(url, {method:'POST', credentials:'include', headers:{'content-type':...,
   'x-same-domain':'1'}, body})` → long-poll ~18–24s → payload (hoặc lỗi nhanh ≤3s).
6. Bóc 2 lớp JSON → lấy `SIGNED_CDN_URL` → GET trực tiếp (UA thường) → `image/jpeg`.

### 7.5.2. Đặc điểm kỹ thuật BẮT BUỘC / khuyến nghị (bài học E4 → E8)

| # | Đặc điểm | Bằng chứng / ghi chú |
|---|---|---|
| 1 | UUID client (`[12]`, `[13]`, `[4][0]`) nên **CHỮ HOA** (dạng app: `1075A650-CD1A-...`) | So byte body app (E7). Chưa cô lập đơn biến — nhưng E8 dùng chữ hoa ⇒ PASS |
| 2 | `_reqid` theo **counter thật**: base ngẫu nhiên ~58–59k (đổi mỗi page-load) + **+100000 mỗi request** | Session1: `58716,158716,...,2458716`; E8 dùng `app_reqid+100000` ⇒ PASS |
| 3 | **Fire sớm sau reload** — E8: **72ms** sau reload response (app thật: 79–85ms); E6 với gap ~7.8s bị `UNUSUAL_ACTIVITY` | `GAP reload_resp -> our ogiZ0b: 72.4 ms` |
| 4 | **HTTP headers** = app + (chỉ) header bypass của ta; browser tự thêm `sec-ch-ua*`, `referer: https://flow.google.com/` | So trace E6: tập header app ⊂ ta, khác duy nhất `x-harness-ours` |
| 5 | Percent-encoding = **`encodeURIComponent` chuẩn** (space→`%20`); app body ↔ ta byte-identical ở tầng encode | `traces/phase4/enc_forensics.py`: 0 diff |
| 6 | `at` param: giá trị **đã decode** rồi urlencode (`%3A`) — KHÔNG double-encode (bug đầu tiên gây 400) | ngNC2 replay ban đầu |
| 7 | Body form: `f.req=<enc>&at=<enc>&`; `f.req = JSON.stringify([[["ogiZ0b", <args-JSON-string>, null, "generic"]]])` | |
| 8 | Token reCAPTCHA: dài **biến thiên 2468–2553 ký tự**, prefix `0cAFcWeA`, nhúng 2 lần (ref lặp 2 chỗ) | E6 2468, E7 2510, E8 2553 |
| 9 | Response **phải bóc bằng JSON** (payload line → `arr[0][2]` → `json.loads`) — KHÔNG regex: escape `\u003d` trong URL làm regex cắt cụt URL (→ 403 AccessDenied) | bug `post_e8` → sửa = OK |
| 10 | Signed URL: **GET trực tiếp OK ngay** khi URL đầy đủ (E8: attempt 1, 200, 115KB) — không cần cookie/proxy/Referer | |
| 11 | Rejection: HTTP 200 + `wrb.fr null` + `google.rpc.ErrorInfo` `PUBLIC_ERROR_UNUSUAL_ACTIVITY`, `di` ~12ms — ngược hẳn long-poll thành công (`di` ~22800ms) | E4/E6 |
| 12 | `WuwhI` telemetry **KHÔNG cần gửi** — E8 generation thành công mà client không bắn WuwhI (app bắn riêng, độc lập) | |
| 13 | Hook kiểu cũ (chỉ `init.body`) **không đọc được body** vì app gửi `Request` object — phải `input.text()` | E3/E5 vs E7 |
| 14 | **`seed` PHẢI nằm trong int32 CÓ DẤU** (`randint(1, 2147483647)`). Seed > 2³¹−1 → server trả frame `[3]` INVALID_ARGUMENT (di ~1,8 s, 0 credit). Mọi seed app từng quan sát đều < 2³¹ | 2026-10-18: fire seed `2905577744` → `[3]`; fire lại seed `464570899` → 200 OK + ảnh (`out/test_2images_20261018_185519/`) |
| 15 | Cột 5 của frame `wrb.fr` = **gRPC canonical status** khi payload null: `[3]` = INVALID_ARGUMENT (tham số sai) · `[7,...ErrorInfo]` = PERMISSION_DENIED (anti-abuse, `PUBLIC_ERROR_UNUSUAL_ACTIVITY`) | `[3]`: 2026-10-18 18:49 · `[7]`: E2/E4/E6; tham chiếu `github.com/tmc/nlm/internal/batchexecute` ("gRPC canonical status ... frame position 5") |

### 7.5.3. Args builder (đúng như E8 — đã PASS)

```python
ref  = [None, 22, None, None, None, project_id, None, None, None, None, [recaptcha_token, 1]]
spec = [None, None, None, seed, aspect, "BELUGA", None, ref, [[[prompt]]], None, None, None, u1, u2]
args = [None, [spec], 1, ref, [gen]]           # u1,u2,gen = UUID4 .upper()
```
- `seed` = uint32 ngẫu nhiên; `gen` được server **echo lại** trong response item (`generation_uuid`) → khóa đối chiếu kết quả.
- E8 evidence: `seed=1363572693`, `gen=DC206280-27F9-4ABF-84F8-8843BE7C0673` (echo), `title="Purple teapot on wooden table"`.

### 7.5.4. Việc còn mở (E9 optional)

- **Token sạch không cần click UI**: retest `grecaptcha.enterprise.execute(sitekey, {action:'IMAGE_GENERATION'})`
  + builder đã sửa + fire ngay (<1s) — nếu PASS sẽ bỏ được bước UI-click/hook (1 credit nếu accept, 0 nếu reject).
- Map `aspect_ratio` (1/2/3...), `count>1`, model key khác.
- Trạng thái brick UI sau khi chặn request app (app hiện lỗi toast — không ảnh hưởng pipeline).

### 7.5.5. Real run đầu tiên bằng test script (2026-10-18 tối)

Script `discovery/test_generate_2_images.py` (bridge mode + retry type + `--dry-run`):

- Dry-run 2/2 PASS (0 credit).
- **R1 (18:49):** seed `2905577744` > 2³¹ → **REJECT `[3]` INVALID_ARGUMENT** (0 credit) → phát hiện constraint int32 của seed (bảng §7.5.2 #14).
- **R2 (18:55):** fix builder (`randint(1, 2147483647)`) → **PASS** — `"Red apple on plate"`,
  1376×768, 84,8 KB, seed echo khớp, `_reqid` = app+100000, gap 78 ms, long-poll ~24 s.
- Byte-level: body của ta **trùng từng byte** với body app sau khi mask 4 field động
  (seed/u1/u2/gen) — công cụ `traces/phase4/raw_byte_check.py`.
- Bằng chứng: `out/test_2images_20261018_185519/` (metadata.json + response + JPEG);
  reject R1: `out/test_2images_20261018_184946/image_1_response.txt`.

## 8. Câu hỏi mở (Phase 4)

- [x] Tái tạo `recaptcha_token` — **DONE**: bridge mode bắt token từ response `reload` (§7.5.1); đường headless `execute` để ngỏ (E9).
- [x] Replay test 1:1 từ trong page — **DONE E8**: builder own-body PASS (không cần copy body app).
- [ ] Map đầy đủ `aspect_ratio` (1?, 2?, 3?) và `count>1`.
- [ ] Model key khác (nb2.0? `beluga` khác `BELUGA`? các model video `veo_3_1_*`).
- [ ] Ảnh gốc full-res có URL khác không (signed URL hiện tại = ảnh gốc 1376×768).
- [x] Xác nhận `WuwhI` thực sự optional — **DONE**: E8 không gửi, vẫn PASS.
