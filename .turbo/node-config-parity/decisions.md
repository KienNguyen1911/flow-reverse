# Decisions — node-config-parity

## D-001 `flow_catalog.py` là nguồn duy nhất cho option composer

Backend, API và React đều đọc từ `src/Workflows/flow_catalog.py`. React chỉ hiển thị cái nó nhận từ
`GET /api/node/options`. Lý do: mỗi khoá model/aspect là một giá trị **capture được**; hard-code ở FE
sẽ trôi khỏi capture và đoán sai khoá = mất credit.

Đã cân nhắc: để danh sách trong `configs/*.json` rồi cả hai bên đọc file. Loại vì catalog còn chứa
*logic* (map model+duration+resolution+aspect → key, raise khi tổ hợp không tồn tại), không chỉ dữ liệu.

## D-002 `1080p` không phải option của Flow

Composer chỉ có `360p` và `720p`. `1080p` là bước upsample `p0UkFb` của app sau khi render 720p.
Catalog vẫn phơi `1080p` như một *derived resolution* để UI giữ được lựa chọn cũ, nhưng
`capture_resolution()` map `1080p → 720p` trước khi submit. Ghi rõ trong tooltip UI: "1080p (upscale)".

## D-003 Veo không có nhóm resolution/duration ⇒ reject, không đoán

Quan sát: chọn Veo thì composer **biến mất** cả nhóm độ phân giải và thời lượng; chip luôn
`Video · 720p · 8 giây`. Vì vậy `video_model_key()` raise `CatalogError` khi bị yêu cầu Veo + `360p`
hoặc Veo + duration ≠ 8, và `/api/node/video` trả 400. UI disable hai select đó thay vì cho chọn rồi fail.
Đã cân nhắc: âm thầm clamp. Loại, vì người dùng chọn 4s rồi nhận 8s mà không biết là bug im lặng.

## D-004 "Thành phần" (`ingredients`) là text→video thật

Bằng chứng: RPC `YhhmEf` (khác `eb1hJf` của "Khung hình"), spec **không** có media id, `spec[4]` chỉ
là UUID slot. Vì vậy đã **implement** đường text→video (`build_text_video_args`,
`generate_text_video_flow`, `MediaService.generate_text_video`) thay vì map nó về i2v.
Hệ quả UI: node video ở sub-mode này bỏ qua ô chọn ảnh khung và bỏ qua luôn kiểm tra "node nguồn chưa
chạy xong".

## D-005 Agent ON ⇒ dùng default của catalog, và nói rõ

Flow ẩn toàn bộ cấu hình nên giá trị người dùng chọn không thể áp dụng. Vì vậy backend **bỏ qua**
model/aspect/resolution/duration/count (đặt lại `None`/default), dùng default của catalog, và ghi
`agent_mode=True` vào kết quả + một dòng log. UI ẩn hẳn khối config và hiện "Cấu hình do tác nhân
quyết định" thay vì hiện option giả.

## D-006 Không đụng vào "agent" cục bộ đã có

App đã có khái niệm `agentSkillId` / `agentCustomHint` / `prompt-skills/*.md` — đó là prompt agent
của app, **khác** với toggle "Tác nhân" của Flow. Đặt tên trường mới là `agentMode` và giữ nguyên
hai khái niệm tách biệt.

## D-007 3 lỗi `tests/test_account_pool.py` là pre-existing, không fix trong task này

Kiểm chứng: `git stash push --include-untracked` rồi chạy lại → 3 lỗi y nguyên. Nguyên nhân nằm ở code cũ:

- `test_allocation_zero_when_all_cooldown`, `test_allocation_shrinks_when_one_cooldown`:
  `AccountPoolManager.cooldown_remaining_s()` trả `0.0` vô điều kiện (comment "Tool nội bộ: không bao
  giờ khóa cooldown", commit `93743da`) nên breaker file của test không có tác dụng.
- `test_captured_args_has_reference_detects_t2i_baseline`: helper đọc `spec[2]`, nhưng từ commit
  `a105127` reference nằm ở `spec[7]`.

Sửa chúng là thay đổi hành vi pool/breaker — ngoài phạm vi "node config parity". Để lại cho task riêng.

## D-008 Ghi 1080p vào `resolutions` của model nhưng `has_resolution=false` cho Veo

Vì `1080p` là của app, mọi model đều liệt kê nó; cờ `has_resolution` mới là thứ nói lên composer có
nhóm đó hay không. UI dùng cờ để disable, không dùng độ dài danh sách.
