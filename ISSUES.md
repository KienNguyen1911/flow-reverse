# ISSUES — việc còn tồn đọng sau khi bỏ batch/try-on/registry

> Trạng thái: sau commit `6bc4d30` (canvas-only). File này liệt kê những chỗ **đã biết là
> chưa sạch** và những quyết định **cần người duyệt xác nhận**.
>
> Baseline hiện tại — dùng làm mốc khi sửa tiếp:
>
> ```bash
> python -m pytest tests -q                          # 476 passed, 11 skipped
> cd web && npx tsc --noEmit -p tsconfig.json       # exit 0
> cd web && npm test                                 # 13 + 7 pass, 3 snippet checks
> cd web && npm run build                            # OK
> ```

---

## A. Cần bạn xác nhận (quyết định sản phẩm)

### A-1. Tab "Thư viện" không hiển thị video của canvas

`scan_gallery` chỉ nhận run có `meta.json` + field `file`. Node **video** ghi
`manifest.json` (`MediaService._write_manifest`) và không có `file`, nên video canvas không
bao giờ vào tab Thư viện.

Đã kiểm chứng:

```text
node video (manifest.json + clip.mp4)  -> gallery: []        ← không hiện
node image (meta.json + a.png)         -> gallery: [img_run_1]
cả hai                                 -> Kho Assets: hiện đủ cả hai
```

Hiện video xem được ở **Kho Assets**, chỉ thiếu ở tab Thư viện.

**Chọn một:**
- (a) Mở rộng `scan_gallery` đọc thêm `manifest.json` cho video → tab Thư viện đủ ảnh + video.
- (b) Giữ nguyên; Thư viện = ảnh, Kho Assets = tất cả. Ghi rõ trong UI.

Tôi nghiêng (a) vì người dùng chỉ dùng canvas sẽ vào Thư viện tìm lại video đã tạo.

### A-2. Có xoá template canvas "Video Thử Đồ (Try-On 16s)"?

Template này **vẫn chạy được** (6 node, toàn bộ qua `/api/node/*`), nhưng nó là tàn dư của
pipeline try-on vừa bỏ và chỉ chiếm chỗ trong menu Mẫu Workflow.

**Chọn một:**
- (a) Giữ — nó là cấu hình canvas hợp lệ, không phải code chết.
- (b) Xoá `createTryOnTemplate` + mục `{id: "tryon"}` trong `BUILTIN_TEMPLATES`.

### A-3. Ghép 2 video thành 1 (16s) giờ không còn đường nào gọi

`concatenate_two_videos` vẫn nằm trong `src/Bridge/flow_video/media_tools.py` và vẫn có test
(`tests/test_watermark_remover.py`), nhưng **không UI nào và không job kind nào gọi nó** nữa —
trước đây chỉ try-on dùng. Node `last_frame` cho phép nối chuỗi video, nhưng không ghép file.

**Chọn một:**
- (a) Xoá hàm + test của nó (dọn sạch theo nguyên tắc "không có consumer thì bỏ").
- (b) Giữ và thêm một job `node_concat` + nút trên canvas để ghép video — tức khôi phục năng
  lực đã mất, có phạm vi rõ ràng.

Nếu bạn định làm lookbook trên canvas thì (b) đáng làm; nếu không, (a).

---

## B. Code chết còn sót lại (tôi chưa xoá vì nằm ngoài phạm vi bạn giao)

### B-1. `AccountPoolManager` còn nguyên API chỉ batch dùng

Sau khi bỏ `BatchRunner`, các method sau **không còn consumer nào trong `src/`**, chỉ còn test
của chính chúng:

| Method | Consumer trong `src/` |
| :--- | :--- |
| `compute_allocation(j)` | không còn |
| `promote_standby()` | không còn |
| `affinity_shas_for_items()` | không còn |
| `set_current_batch()` / `end_batch()` | không còn |
| `current_batch()` + `_current_batch` | chỉ để đưa vào `snapshot()` |

Hệ quả phụ: `/api/pool` vẫn trả `current_batch` và `last_batch`, nhưng **hai field này sẽ luôn
là `null`** từ nay. `web/src/types.ts` (`PoolBatchInfo`) và tab Docs API vẫn mô tả chúng như
thể có nghĩa. Cần chọn: bỏ khỏi snapshot, hay giữ để tương thích script bên ngoài.

`hot-spare failover` cũng thuộc nhóm này: `promote_standby` không còn được gọi, nên khi một
account dính 429/401/403 thì **không còn account dự phòng tự thế chỗ** — job đơn giản chỉ thất
bại và trả về. Với mô hình canvas (mỗi lúc một node, đã có `node_retry` + breaker) điều này
chấp nhận được, nhưng đó là một năng lực đã mất và cần bạn biết.

### B-2. Docstring `account_pool.py` còn mô tả batch

Phần đầu file mô tả "ưu tiên account có `media_id`/template cho ảnh tham chiếu **của batch**"
và "hot-spare failover". Sửa docstring cho khớp thực tế, hoặc làm B-1 trước rồi sửa một lần.

---

## C. Vấn đề đã phát hiện nhưng KHÔNG do đợt refactor này gây ra

### C-1. `parse_gemini_video_prompts` cắt mất ký tự đầu của prompt thứ hai

`gemini_bridge.parse_gemini_video_prompts` trả sai khi prompt bắt đầu bằng chữ "S":

```python
raw = "```text\nFirst prompt body here.\n```\n\n```text\nSecond prompt body here.\n```\n"
parse_gemini_video_prompts(raw)
# -> ('First prompt body here.', 'econd prompt body here.')   # mất 'S'
```

Tôi đã đối chiếu với bản `gemini_bridge.py` ở `HEAD` trước khi sửa: **bug có sẵn từ trước**,
không phải do đợt refactor này. Hiện chỉ còn `tests/test_prompt_skills_contract.py` dùng hàm
này; test đó vẫn xanh vì nó so với chuỗi có sẵn.

Đây là bug thật (regex dùng `[0-8\s\-sS]` trong pattern cắt tiền tố thời gian, nên ăn luôn chữ
cái đầu). Sửa hay bỏ luôn hàm là quyết định của bạn — tôi chưa đụng.

### C-2. `pytest` có 11 test skipped

Số này **không đổi** qua đợt refactor (baseline trước cũng 11 skipped). Tôi chưa rà lý do skip.
Nếu muốn dọn thì nên làm thành một việc riêng.

---

## D. Đã sửa trong đợt này (ghi lại để khỏi báo lại)

- **Tab Thư viện sẽ rỗng vĩnh viễn** sau khi bỏ `generate`/`batch`: `scan_gallery` giờ đọc
  `out/nodes` (canvas, phục vụ qua `/api/node/files`) **và** `out/playground` (legacy, qua
  `/api/files`). `scan_output_assets` truyền `node_out` nên không liệt kê trùng.
- **Link chết `/api/tryon/files`**: `scan_output_assets` từng quét `out/affiliate_runs` và tạo
  URL trỏ vào route vừa xoá. Section đó đã bỏ.
- **`max_batch_items`**: bỏ khỏi `limits.py` / `configs/limits.json` / payload `/api/node/options`
  / types + hooks frontend / tab Docs API (consumer duy nhất là `BatchRunner`).
- **`ProjectsStore`** (write-only sau khi bỏ route): bỏ hẳn; `MediaService` map
  workspace → Flow project qua `WorkspaceStore`, vốn đã là nguồn sự thật.
- **Hub dữ liệu cũ trên đĩa**: `out/affiliate_runs/`, `out/playground/` là dữ liệu người dùng,
  **không xoá** và **không commit** (đã gitignored). Chỉ code đọc chúng là đã dọn.

---

## E. Ghi chú để không mất ngữ cảnh

- `flow_client.list_projects()` / `create_project()` **được giữ có chủ ý**: `MediaService.resolve_project`
  gọi chúng để lazy-create Flow project cho mỗi workspace project, theo từng account.
- `gemini_bridge` giữ lại **đúng 2 parser thuần**; toàn bộ phần CDP/Playwright của notebook Nabi
  đã xoá cùng try-on.
- `scripts/cutout_items.py` vẫn dùng được (tách nền sản phẩm), nhưng **không còn là bước
  nào của pipeline**: skill `lookbook-item-cutout-prompter` giờ chỉ sinh coordinate sheet,
  và sheet có chữ nằm sẵn trong pixel nên rembg sẽ cắt luôn chữ.
