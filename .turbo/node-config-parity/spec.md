# Node config parity với Google Flow

## Mục tiêu

Node Ảnh / Node Video trong Flow Bench phải phơi ra **đầy đủ** cấu hình giống composer
của Google Flow, và backend phải dùng được các lựa chọn đó khi submit RPC.

## Non-goals

- Không đổi pipeline Lookbook / delivery / QA.
- Không thêm tính năng ngoài những gì composer Flow thực sự có (không bịa option).

## Ràng buộc

- Chỉ dùng tham số **quan sát được** từ Flow (Observed Evidence) hoặc capture 0-credit
  qua decoy hook. Không đoán model key.
- UI lấy option từ `GET /api/node/options` (không hard-code ở React).
- Bật "Tác nhân" (Agent) thì composer Flow **ẩn** toàn bộ cấu hình model → UI ta phải
  phản ánh đúng điều đó, không hiển thị option giả.

## Acceptance criteria (cấp task)

- `GET /api/node/options` trả về đủ option ảnh + video như ma trận đo được.
- Node Ảnh có: mode, aspect, model, count, seed.
- Node Video có: sub-mode (Khung hình/Thành phần), aspect, model, resolution,
  duration, count, seed.
- Chọn option nào thì request submit mang đúng tham số tương ứng (verify bằng dry-run
  hoặc decoy capture).
- Bật Agent ⇒ config node hiển thị rõ "do tác nhân quyết định" thay vì option giả.

## Bằng chứng đã thu (2026-11-03, Chrome DevTools qua CDP 4022)

### Ảnh (Agent OFF) — popover `button.settings-trigger-button`

Chip: `🍌 Nano Banana 2.1 crop_9_16 x1`

| Nhóm | Giá trị (role=radio) |
| --- | --- |
| Mode | `Hình ảnh` (image) / `Video` (videocam) |
| Aspect | `16:9`, `4:3`, `1:1`, `3:4`, `9:16` |
| Model (role=menuitem, aria "Chọn nhóm mô hình") | `Nano Banana Pro`, `Nano Banana 2 Lite`, `Nano Banana 2.1` |
| Count | `x1`, `x2`, `x3`, `x4` |

### Video (Agent OFF)

Chip sau khi chọn Video: `Video · 720p · 8 giây crop_9_16 x1`

| Nhóm | Giá trị |
| --- | --- |
| Sub-mode | `Khung hình` (crop_free) / `Thành phần` (chrome_extension) |
| Aspect | `16:9`, `9:16` (chỉ 2) |
| Model | `Omni 1.1 Flash`, `Veo 3.1 - Lite`, `Veo 3.1 - Fast`, `Veo 3.1 - Quality` |
| Resolution | `360p`, `720p` |
| Duration | `4 giây`, `6 giây`, `8 giây`, `10 giây` |
| Count | `x1`..`x4` |

Ghi chú: `360p` có icon `info` (tooltip giải thích), `x4` không bị disable trong ảnh chụp.
Mặc định khi mở: Video + `Thành phần` + 9:16 + 720p + 8 giây + x1.

### Agent ("Tác nhân") ON

- `button.agent-mode-chip` có `aria-pressed="true"`, class thêm `agent-mode-chip-checked`.
- `button.settings-trigger-button` **rỗng và ẩn** (`offsetWidth/Height = 0`) ⇒ không còn
  chip tóm tắt cấu hình.
- Xuất hiện thêm nút `tune` với `aria-label="Cài đặt"`; nhưng popover của nó là **cài đặt
  hiển thị canvas** (Lưới/Theo nhóm, cỡ N/TB/L, âm thanh hover, trả video không âm thanh,
  hiện chi tiết ô, xoá câu lệnh sau khi gửi) — **không** phải model/aspect/duration.
- Xuất hiện nút `article_spark` aria "Chỉ dẫn cho tác nhân".
- Kết luận: bật Agent ⇒ Flow **không cho chọn** model/aspect/duration; tác nhân tự quyết.

## Verification commands

- `curl -s localhost:4000/api/node/options` (hoặc `Invoke-WebRequest`) → so với ma trận trên.
- `python scratch/probe_config_matrix.py` → sinh lại `traces/flow_config_matrix.json`.
- `pytest tests -q` → không hồi quy.
