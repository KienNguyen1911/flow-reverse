# Flow batchexecute Transport — Đặc tả giao thức (Google Flow)

> **Nguồn bằng chứng (Observed):** trace thật ngày 2026-10-18 —
> `traces/raw_trace_20261018T091806Z.jsonl` (tạo project + 2 lần tạo ảnh),
> `traces/raw_trace_20261018T092635Z.jsonl` (mở project có sẵn nội dung).
> Bản decode: `traces/decoded/` (dùng `discovery/decode_batchexecute.py`).
> Các mục ghi chú **Inference** là suy luận, chưa kiểm chứng.

Trang đích: `https://flow.google.com` — frontend Angular (bundle `AiSandboxAngularFrontend`).
Mọi thao tác nghiệp vụ (tạo project, tạo ảnh, đọc nội dung...) đi qua **một endpoint duy nhất**: RPC-style `batchexecute`.

---

## 1. Endpoint

```
POST https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute
```

### 1.1 Query params (Observed)

| Param | Ví dụ (trace) | Ý nghĩa | Ghi chú |
|---|---|---|---|
| `rpcids` | `jHPbke`, `ogiZ0b` | ID của RPC cần gọi | **1 RPC / request** trong mọi quan sát |
| `source-path` | `%2F` (home), `%2Fproject%2F<uuid>` | Route UI lúc gọi | URL-encoded |
| `bl` | `boq_labs-ai-sandbox-frontend_20261016.00_p1` | Build label của frontend | Lấy từ page; đổi theo deploy |
| `f.sid` | `744816825352939461` | Session id của page | Đổi mỗi lần load trang (2 phiên capture khác nhau: `744816825352939461`, `1661927511675113672`) |
| `hl` | `vi` | Ngôn ngữ UI | Theo locale phiên |
| `_reqid` | `1058716`, `2458716`, `2558716`, `2658716` | Số thứ tự request | Opaque; tăng dần trong phiên. **Observed:** server không validate chặt — `app_reqid + 100000` được chấp nhận (E8, R2, production) |
| `rt` | `c` | Không rõ | Giữ nguyên |

### 1.2 Headers (Observed)

| Header | Giá trị |
|---|---|
| `content-type` | `application/x-www-form-urlencoded;charset=utf-8` |
| `x-same-domain` | `1` |
| `referer` | `https://flow.google.com/...` |
| Cookie | Auth Google (`SID`, `HSID`, `SSID`... trên domain `.google.com`) — trình duyệt tự gửi |
| `user-agent`, `sec-ch-ua*` | UA Chrome thật |

### 1.3 Body — form-encoded (Observed)

```
f.req=<urlencoded JSON>&at=<XSRF token>&
```

**Cấu trúc `f.req`** (JSON, URL-encoded):

```json
[[["<rpcid>", "<args dưới dạng JSON string>", null, "generic"]]]
```

- `args` là **chuỗi JSON lồng** (double-encoded) — đây là điểm hay bị nhầm khi decode.
- Cấu trúc batch cho phép nhiều call trong 1 request; mọi quan sát chỉ thấy 1 call.

**Token `at`** (Observed):
- Format: `AFfZSpgmiwic4dtoi0JlcRidGLyV:1792315115087` = `<22 ký tự> : <epoch_ms lúc mint>`.
- **Mint một lần lúc page load** (ms `1792315115087` nằm trong lúc load trang home; trước request đầu tiên).
- Không đổi suốt vòng đời SPA: **30/30 request** trong trace đầu dùng đúng 1 giá trị, xuyên qua cả điều hướng home → project.
- **Observed (Phase 4 + production):** giá trị đọc được trực tiếp từ `window.WIZ_global_data.SNlM0e`; mint lại khi full page load (đã kiểm chứng qua request thật — xem §4).

### 1.4 Response (Observed)

```
)]}'

1251
[["wrb.fr","ogiZ0b","<payload JSON string>",null,null,null,"generic"],["di",22261],["af.httprm",22260,"268834...",55]]
26
[["e",4,null,null,1289]]
```

- Prefix chống XSSI: `)]}'`.
- Sau đó là các **chunk có độ dài đứng trước** (số nguyên 1 dòng, rồi 1 dòng JSON).
- Dòng kết thúc: `[["e",4,null,null,<byte_count>]]`.
- Hàng kết quả: `["wrb.fr","<rpcid>","<payload>", ...]` — `payload` là **chuỗi JSON lồng** (double-encoded), cần `json.loads` lần 2.
- HTTP `200` cũng xảy ra khi RPC lỗi: frame `wrb.fr` payload `null`, cột 5 = **gRPC canonical status** (`[3]` INVALID_ARGUMENT; `[7,...]` PERMISSION_DENIED/anti-abuse). HTTP `401/403/429` ở tầng transport có thể gặp (client dùng làm tín hiệu circuit breaker). Chi tiết: `flow_create_image.md` §7.5.2 #15.

### 1.5 Codec tham chiếu (Python, stdlib)

```python
import json
import urllib.parse

def build_form(rpcid: str, args, at: str) -> str:
    """Sinh body form: f.req=<double-encoded json>&at=<token>&"""
    args_json = json.dumps(args, separators=(",", ":"), ensure_ascii=False)
    envelope = [[[rpcid, args_json, None, "generic"]]]
    f_req = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)
    return urllib.parse.urlencode({"f.req": f_req, "at": at}) + "&"

def parse_response(body: str) -> list[dict]:
    """Bóc các hàng wrb.fr từ response body thô."""
    text = body.split("\n", 1)[1] if body.startswith(")]}'") else body
    out: list[dict] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.isdigit():
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(chunk, list):
            continue
        for row in chunk:
            if isinstance(row, list) and len(row) >= 3 and row[0] == "wrb.fr":
                payload = row[2]
                try:
                    payload = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    pass
                out.append({"rpcid": row[1], "result": payload})
    return out
```

---

## 2. Danh mục RPC đã phát hiện (Observed)

| RPC ID | Kích thước args | Vai trò (xác tín) | Bằng chứng |
|---|---|---|---|
| `jHPbke` | 233B | **Tạo project** | Bắn ngay lúc click "Dự án mới"; response chứa UUID project mới |
| `ogiZ0b` | ~5.7KB | **Tạo ảnh (submit)** | Bắn lúc click nút "Bắt đầu tạo"; response (sau ~22s) chứa ảnh hoàn chỉnh |
| `UpteDb` | 190B | **Danh sách projects** | args `["projects/*", 21, null, null, null, null, [1]]`; response = mảng project + thumbnail |
| `Zzl0ze` | 213B | **Nội dung project** (items + media + voices) | args `["projects/<uuid>", null, null, null, [1]]` |
| `ngNC2` | 199B | **Trạng thái project** (title, cover, tools) | args `["tools/PINHOLE/projects/<uuid>"]` |
| `HTrJv` | 122B | Catalog tools/models | response: bảng tool (beluga_display, veo_3_1_*, abra...) |
| `yBhWQ` | 122B | Bảng "credit cost" theo tool | response: `[["veo_3_1_fast",1], ["abra",1], ...]` |
| `KV2T2d` | 125B | Kích hoạt tool (image=22) | `[22]` → `[1]`, bắn lúc home load |
| `o30O0e` | 297B | Hồ sơ người dùng ("me") | `[["me"], [[...person.*...]]]` |
| `cPZSdc` | 123B | Config/маркетинг banners | version + banner list |
| `Yizz8d` | 123B | Version/model config | `2026-10-06-v0-nb21-...` (nb21 = Nano Banana 2.1) |
| `nzlxg` | 122B | Credits/billing | `[1050, 1, 2, 2, null, 1050, ...]` (Inference: 1050 = số credits) |
| `xI9TVb` | 153B | User preferences | `["userPreferences/"]` |
| `WuwhI` | 4.2KB / 2.8KB | **Telemetry** (PAGE_VIEW, MEDIA_GENERATION) | Không bắt buộc cho client; response `[]` |
| `NfrxTb` | 122-132B | Feature flags | `[16]`, `[17]`, `[null,22]` → `true`/`[]` |
| `tRARke` | 123B | Catalog "community applets" | ThumbnailForge... |
| `LPzVkd`, `mrlkwd`, `qJcgMc`, `ve2Lsc`, `DTaVef` | ~123-171B | Chưa xác định | Trả `[]` / `true`; vai trò mờ (TODO) |

Nội bộ tool: ảnh = tool id **22**, tên nội bộ **`PINHOLE`**, model **`BELUGA`** (Nano Banana 2.1), hiển thị `beluga_display`.

---

## 3. Vòng đời phiên (Observed)

1. **Page load (home)**: bắn loạt bootstrap — `o30O0e`, `nzlxg`, `cPZSdc`, `Yizz8d`, `KV2T2d`, `UpteDb`, `xI9TVb`, `NfrxTb`... Trong đó có nơi mint token `at`.
2. **Điều hướng SPA** (home → project): `f.sid`, `at` giữ nguyên.
3. **Request nghiệp vụ**: 1 RPC/lần, đúng 1 token `at` cố định.

## 4. Câu hỏi cũ (đã trả lời ở Phase 4)

- [x] **Nguồn cấp `at`/`bl`/`f.sid`:** `at` = `window.WIZ_global_data.SNlM0e`; `f.sid` = `FdrFJe`; `bl`/`hl`/`_reqid` = performance entry `batchexecute` gần nhất. Client tự đọc được hoàn toàn — implemented: `FlowBridge.session_ctx()` (`src/Bridge/flow_bridge.py`).
- [x] **Định dạng lỗi RPC:** HTTP 200 + frame `wrb.fr` payload null + cột 5 gRPC status (`[3]`, `[7]...`); HTTP 401/403/429 ở tầng transport — xem §1.4 và `flow_create_image.md` §7.5.2 #15.
- [x] **`_reqid` validate:** không chặt — `app_reqid + 100000` pass ổn định (E8, R2, production).
- [x] **Header/cookie tối thiểu:** cookie phiên + `content-type` + `x-same-domain: 1` là đủ (E7/E8 + production); header bypass riêng của ta được server bỏ qua.
