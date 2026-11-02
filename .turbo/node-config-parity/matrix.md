# Ma trận cấu hình Google Flow (Observed Evidence, 0 credit)

Nguồn: Chrome DevTools/CDP 4022 trên `flow.google.com/project/01c4173f-…`, 2026-11-03.
Mọi payload lấy bằng cách **chặn toàn bộ** `/data/batchexecute` ngay trước khi bấm Generate
(không có request nào tới server ⇒ 0 credit).

## 1. Popover settings (Agent OFF)

### Ảnh — chip `🍌 Nano Banana 2.1 crop_16_9 x1`

| Nhóm | Giá trị |
| --- | --- |
| Mode | `Hình ảnh` (radio, icon `image`) / `Video` (icon `videocam`) |
| Aspect | `16:9`, `4:3`, `1:1`, `3:4`, `9:16` |
| Model (dropdown `aria-label="Chọn nhóm mô hình"`) | `🍌 Nano Banana Pro`, `🍌 Nano Banana 2 Lite`, `🍌 Nano Banana 2.1` |
| Count | `x1`, `x2`, `x3`, `x4` |

Giống nhau cho cả 3 model (không option nào bị disable).

Enum aspect ảnh (từ `args[1][0][4]` của request `ogiZ0b` bị chặn):

| Tỷ lệ | Enum | Icon |
| --- | --- | --- |
| 16:9 | 3 | `crop_16_9` |
| 9:16 | 2 | `crop_9_16` |
| 4:3 | 5 | `crop_landscape` |
| 1:1 | 1 | `crop_square` |
| 3:4 | 4 | `crop_portrait` |

Model key ảnh (`args[1][0][5]`):

| Model | Key |
| --- | --- |
| Nano Banana Pro | `GEM_PIX_2` |
| Nano Banana 2 Lite | `HARBOR_SEAL` |
| Nano Banana 2.1 | `BELUGA` |

Count ảnh: `x4` ⇒ `args[1]` có **4 spec**, mỗi spec seed + `u1`/`u2` riêng, `args[2]` vẫn `1`.

### Video — sub-mode `Khung hình` (image→video)

Chip: `Video · 720p · 8 giây crop_9_16 x1`

| Nhóm | Giá trị |
| --- | --- |
| Sub-mode | `Khung hình` (icon `crop_free`) / `Thành phần` (icon `chrome_extension`) |
| Aspect | `16:9`, `9:16` (chỉ 2) |
| Model | `Omni 1.1 Flash`, `Veo 3.1 - Lite`, `Veo 3.1 - Fast`, `Veo 3.1 - Quality` |
| Resolution | `360p` (có icon `info`), `720p` — **chỉ có khi model = Omni** |
| Duration | `4 giây`, `6 giây`, `8 giây`, `10 giây` — **chỉ có khi model = Omni** |
| Count | `x1`..`x4` |

⚠️ Chọn model Veo ⇒ popover **mất hẳn** nhóm resolution + duration. Veo cố định 8s / 720p.

Model key (RPC `eb1hJf`, `spec[1]`):

| Model | 9:16 | 16:9 | 360p |
| --- | --- | --- | --- |
| Omni 1.1 Flash | `abra_i2v_{4,6,8,10}s` | `abra_i2v_{4,6,8,10}s` | `abra_i2v_{4,6,8,10}s_360p` |
| Veo 3.1 Lite | `veo_3_1_i2v_lite` | `veo_3_1_i2v_lite` | — |
| Veo 3.1 Fast | `veo_3_1_i2v_s_fast_portrait` | `veo_3_1_i2v_s_fast` | — |
| Veo 3.1 Quality | `veo_3_1_i2v_s_portrait` | `veo_3_1_i2v_s` | — |

Payload shape (Khung hình):

- 720p: `spec` dài **6** — `[prompt_slot, model, aspect, seed, [None, sf_id, None,None,None, crop], [None,None,None,None,u1,u2]]`
- 360p: `spec` dài **10** — thêm `spec[9] = [4]` (đánh dấu 360p)
- `x2` ⇒ `args[0]` có **2 spec**, mỗi spec `u1`/`u2` riêng và `seed` riêng (app để `null`, ta set int32).

### Video — sub-mode `Thành phần` (text→video, KHÔNG cần frame)

Đây là **đường text-to-video thật** mà pipeline chưa dùng:

- RPC: **`YhhmEf`** (không phải `eb1hJf`)
- `spec[4]` = `[null, null, null, null, u1, u2]` (không có starting frame)
- Model key prefix `abra_t2v_*`:

| Model | 9:16 | 16:9 |
| --- | --- | --- |
| Omni 1.1 Flash | `abra_t2v_{4,6,8,10}s` | `abra_t2v_{4,6,8,10}s` |
| Veo 3.1 Lite | `veo_3_1_t2v_lite` | `veo_3_1_t2v_lite` |
| Veo 3.1 Fast | `veo_3_1_t2v_fast_portrait` | `veo_3_1_t2v_fast` |
| Veo 3.1 Quality | `veo_3_1_t2v_portrait` | `veo_3_1_t2v` |

- 720p: `spec` dài **5**
- 360p: `spec` dài **8** — thêm `spec[7] = [4]`
- `x2` ⇒ `args[0]` có 2 spec.

### Agent ("Tác nhân") ON

- `button.agent-mode-chip` → `aria-pressed="true"` + class `agent-mode-chip-checked`.
- `button.settings-trigger-button` **rỗng và ẩn** (`offsetWidth/Height = 0`) ⇒ không còn chip tóm tắt.
- Xuất hiện `button` `aria-label="Cài đặt"` (icon `settings_2`) — popover của nó là **cài đặt hiển thị
  canvas** (Lưới/Theo nhóm, N/TB/L, âm thanh khi hover, trả video không âm thanh, hiện chi tiết ô,
  xoá câu lệnh sau khi gửi), **không** phải model/aspect/duration.
- Xuất hiện `article_spark` `aria-label="Chỉ dẫn cho tác nhân"`.
- Kết luận: bật Agent ⇒ Flow **không cho người dùng chọn** model/aspect/duration/count.

## 2. File bằng chứng

| File | Nội dung |
| --- | --- |
| `traces/flow_config_matrix.json` | dump popover ảnh/video/agent-tune |
| `traces/flow_option_matrix.json` | option matrix theo từng model (read-only) |
| `traces/image_model_keys.json` | model key ảnh |
| `traces/submit_bodies/*_summary.json` | payload submit đã decode (ảnh, i2v, t2v, count, 360p) |
| `configs/image_aspect_enums.json` | enum 5 tỷ lệ ảnh |

## 3. Probe tái sử dụng được (0 credit)

```bash
python discovery/probe_option_matrix.py            # ma trận option theo model (read-only)
python discovery/capture_image_aspects.py --dump-only
python discovery/capture_video_matrix.py           # i2v: model/duration/resolution
python discovery/probe_submit_body.py --name X --dur "10 giây"
python discovery/probe_submode_ingredients.py --name X --model "Veo 3.1 - Fast"
python discovery/probe_count_res.py --kind video --count x2
```
