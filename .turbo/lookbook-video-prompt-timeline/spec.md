# Spec — lookbook-video-prompt-timeline

## Goal
Prompt video Lookbook phải mang được: mục tiêu clip, nhịp beat trong 8s, hook 3s đầu, "không nên làm gì";
và raw video phải có hợp đồng nghiệm thu trước khi sang HyperFrames.

## Non-goals
- Không cố tạo mốc giây chính xác bằng prompt (payload `abra_i2v_8s` không có trường timeline).
- Không thêm negative-prompt field vào Flow API (không tồn tại).
- Không tự động hoá phán đoán thẩm mỹ (360° hoàn tất, một chủ thể).

## Constraints
- `sanitize_video_prompt()` xoá mọi nhãn thời gian ⇒ chỉ dùng văn xuôi thứ tự.
- Prompt ship đi phải round-trip: `sanitize(p, aggressive=False) == p.strip()`.
- QA chỉ cảnh báo, không chặn delivery (user decision 2026-11-02).
- Từ vựng chuyển động đóng, kiểm qua sanitizer cả 2 mode.
- Beat renderer tất định (user decision): clip có `beats` thì renderer quyết câu chữ.

## Acceptance criteria
1. `configs/lookbook_script.schema.json` + `configs/lookbook_script.json` có `clips[].goal`, `beats[]`, `negative[]`.
2. `script_contract.py` validate beats: at_s=0, liền mạch, tổng == duration_s.
3. `src/Workflows/motion_prompt.py::beats_to_prompt()` render prose sống sót sanitizer.
4. Node video gửi `clip_id`/`clip_role`/`script_path` ở cả 3 call site FE.
5. `/api/node/options` trả `script.clips`.
6. `src/Workflows/raw_video_qa.py` đo >=6 gate, ghi vào `delivery.json`.
7. Tests xanh.

## Verification
```
python -m pytest tests -q
```
