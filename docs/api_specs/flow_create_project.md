# Feature: Tạo Project (Google Flow) — RPC `jHPbke`

> **Observed:** trace `traces/raw_trace_20261018T091806Z.jsonl`.
> Request: `traces/decoded/raw_trace_20261018T091806Z__request_1792315118934__jHPbke.json`
> Response: `traces/decoded/raw_trace_20261018T091806Z__response_1792315120060__jHPbke.json`
> Transport (endpoint/`at`/envelope): xem `flow_transport.md`.
>
> ✅ **Replay verified (Phase 4 — `traces/phase4/run_jhpbke.py`):** fire in-page bằng fetch của ta →
> `200 OK` (`di`=258ms) → project mới `d3059ec6-a97c-41c1-9a25-40fac3954a43`, **title tùy ý được chấp nhận**
> ("Client Test (delete me)"), app SPA-nav vào project mới và load OK (Zzl0ze/ngNC2/mrlkwd đều 200).
> **0 credit** (tạo project miễn phí). Response lưu: `traces/phase4/jhpbke_replay_response.txt`.

---

## 1. Hành vi UI quan sát được

- Nút tạo project: `button.new-project-button` (trang home — danh sách project).
- Click → gọi RPC `jHPbke` → nhận UUID → điều hướng SPA tới `/project/<uuid>`.
- Thời gian: từ click tới có URL project ≈ **1.2 giây** (click `T=1792315118853`, URL mới `T=1792315120055`).

## 2. Request (Observed)

```
POST /_/AiSandboxAngularFrontend/data/batchexecute?rpcids=jHPbke&source-path=%2F&bl=...&f.sid=...&hl=vi&_reqid=1058716&rt=c
```

Form body (đã URL-decode):

```
f.req=[["jHPbke","[\"projects/*\",[null,[\"Tháng 10 18 - 16:18\"]],[null,22]]",null,"generic"]]
at=AFfZSpgmiwic4dtoi0JlcRidGLyV:1792315115087&
```

**Args sau khi decode (JSON lồng):**

```json
["projects/*", [null, ["Tháng 10 18 - 16:18"]], [null, 22]]
```

| Vị trí | Giá trị | Ý nghĩa | Xác tín |
|---|---|---|---|
| `[0]` | `"projects/*"` | Resource name wildcard — server tự cấp UUID | Observed |
| `[1][1][0]` | `"Tháng 10 18 - 16:18"` | **Tiêu đề project** | Observed |
| `[2]` | `[null, 22]` | Kích hoạt tool 22 (công cụ ảnh / PINHOLE) cho project mới | Inference mạnh (22 = tool ảnh, khớp `KV2T2d [22]` + `ngNC2` trả `beluga_display`) |

Tiêu đề do **client sinh theo format ngôn ngữ**: `"<TênTháng> <Ngày> - <HH:MM>"` (vi: `Tháng 10 18 - 16:18`).
Chưa kiểm chứng việc server chấp nhận tiêu đề tùy ý / đổi tên (TODO Phase 4).

## 3. Response (Observed)

Payload sau khi bóc envelope:

```json
["3b368b0d-2e22-4ba0-9f8e-c17e698ddcb9", ["Tháng 10 18 - 16:18"]]
```

| Vị trí | Giá trị | Ý nghĩa |
|---|---|---|
| `[0]` | UUID v4 | **project_id** (dùng cho mọi thao tác sau: URL `/project/<uuid>`, `tools/PINHOLE/projects/<uuid>`...) |
| `[1]` | mảng tiêu đề | tiêu đề đã lưu |

Ghi chú kèm bằng chứng:
- `UpteDb` (list projects) sau đó trả về project mới với `created_ts = [1792315119, 300554000]` (~0.45s sau click) — tức server-side creation time.
- Project mới **rỗng**; nội dung project đọc qua `Zzl0ze` (xem `flow_create_image.md` §5).

## 4. Timeline chuẩn (dùng để mô phỏng)

```
T+0.000s  click "Dự án mới"
T+0.081s  POST jHPbke
T+1.2s    response jHPbke (UUID) → UI điều hướng /project/<uuid>
T+1.2s+   loạt RPC load project: HTrJv, LPzVkd, Zzl0ze, ngNC2, tRARke, qJcgMc, mrlkwd, yBhWQ, ve2Lsc, DTaVef...
```

## 5. DTO (Pydantic)

```python
from pydantic import BaseModel, Field


class CreateProjectArgs(BaseModel):
    """Args của RPC jHPbke: [name, [null, [title]], [null, tool_id]]."""
    name: str = "projects/*"
    title: str
    tool_id: int = 22  # 22 = công cụ ảnh (PINHOLE)


class CreateProjectResult(BaseModel):
    """Payload trả về: [uuid, [title]]."""
    project_id: str
    title: str


def build_create_project_args(title: str) -> list:
    return ["projects/*", [None, [title]], [None, 22]]
```

## 6. Sau khi tạo — các RPC client nên gọi (Observed, tùy mục đích)

| RPC | Args | Khi nào | Trả về |
|---|---|---|---|
| `UpteDb` | `["projects/*", 21, null, null, null, null, [1]]` | refresh danh sách | mảng `[uuid, [title, null, [created_s, created_ns], thumbnail_url?, media_uuid?, [thumbnail_url]?]]` |
| `Zzl0ze` | `["projects/<uuid>", null, null, null, [1]]` | mở project | nội dung project (items/media/voices) |
| `ngNC2` | `["tools/PINHOLE/projects/<uuid>"]` | trạng thái tool | `[uuid, [title, cover_media_uuid?], null, null, null, [tools...]]` |

## 7. Câu hỏi mở

- [x] Tiêu đề tùy ý có được chấp nhận không? — **DONE (replay test)**: "Client Test (delete me)" được lưu nguyên văn.
- [ ] Có RPC đổi tên project không? (UI có nút rename — chưa capture)
- [ ] Xóa project? (chưa capture)
