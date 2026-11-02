# Progress

## 2026-11-02 — Pha 1, 2, 3 (F-001..F-003) xong

### Đã làm

**F-001 — script contract**
- `configs/lookbook_script.schema.json`: `clips[]` thêm `goal`, `beats[]` (`at_s`, `duration_s`,
  `action`, `holds_gaze`, `must_not`), `negative[]`.
- `src/Workflows/script_contract.py`: `BeatSpec` dataclass; `ClipSpec.goal/beats/negative` +
  `has_beats` property; `brief()` xuất beats để agent thấy.
- `_validate_beats()`: beat đầu `at_s==0`, không hở, không chồng lấn, tổng == `duration_s`,
  `holds_gaze` bắt buộc có `must_not`, `action` không rỗng, `duration_s>0`.
- `configs/lookbook_script.json`: clip1 (hook) và clip2 (showcase) có 3 beat, `goal`, `negative`.
  `motion_prompt` viết lại thành **bản sao của output renderer** để hai nguồn không lệch.

**F-002 — renderer**
- `src/Workflows/motion_prompt.py` (mới): `beats_to_prompt()`, `prompt_warnings()`,
  `CAMERA_SENTENCES`, `MOTION_VERBS`, `FORBIDDEN_TERMS`, `MAX_PROMPT_WORDS=120`.
- Ba tầng chặn: động từ mở đầu phải nằm trong `MOTION_VERBS`; từ vựng cấm khớp theo word-boundary;
  đại từ `she/her/his` bị từ chối.
- Renderer bù `holds steady eye contact with the lens` khi beat khai `holds_gaze` mà `action` quên.
- `Continuing from that pose` chỉ thuộc câu camera; beat trùng thì bị bỏ.

**F-003 — lint + skill**
- `prompt_lint.py`: `VIDEO_MAX_WORDS` 80 → 120, `VIDEO_MIN_WORDS` 10 → 40.
- Thêm `_in_negative_clause()` + `_find_affirmed_in_clause()`; `UI_TERMS` chuyển sang hàm mới.
  Mệnh đề cấm ("staying inside the frame, with no cut, no added lettering") không còn bị phạt.
- `prompt-skills/lookbook-video-prompter.md`: viết lại §4 (ngân sách), §5 (beats là nguồn),
  §6 (mục tiêu từng clip + hook bằng cử chỉ), §7 (UI), §9 (checklist). Bỏ template tote/halter cứng.

### Verify

```
python -m pytest tests/test_script_beats.py -q          -> 14 passed
python -m pytest tests/test_motion_prompt.py -q         -> 21 passed
python -m pytest tests/test_prompt_skills_contract.py -q -> 38 passed
python -m pytest tests -q                               -> 348 passed, 5 failed (pre-existing)
```

5 test đỏ là **cùng 5 test đỏ có trước khi bắt đầu** (xem decisions D-001), không phải hồi quy.

### Đo được (quan trọng)

| Clip | Từ | `sanitize(aggressive=False)` |
| :--- | --: | :--- |
| clip1 (hook) | 110 | nguyên văn |
| clip2 (showcase) | 99 | nguyên văn |

### Tiếp theo

F-004 (nối `clip_id` từ FE), F-005 (prompt_agent dùng beats), F-006 (raw video QA).
