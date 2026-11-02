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

## 2026-11-02 — F-004, F-005 xong

**F-004 — FE gửi `clip_id`**
- `web/src/types.ts`: `ScriptClipOption`, `NodeMediaOptions.script`, `CanvasNodeState.clipId`.
- `web/src/hooks.ts`: `useScriptClips()` (cache chung với `useLimits`).
- `web/src/components/CanvasPanel.tsx`: `SCRIPT_PATH`, `clipRoleOf()`, 2 call site gửi
  `clip_id`/`clip_role`/`script_path`; template `lb_video_1=clip1`, `lb_video_2=clip2`.
- `web/src/components/CanvasDrawer.tsx`: select clip + call site thứ 3 + cảnh báo khi chưa chọn.
- `src/Workflows/media_service.py`: `node_options()` trả `script.path`/`script.clips`.
- `tests/test_node_options_script.py`: 5 test.

**F-005 — prompt_agent dùng beats**
- `_beat_lines()`: chèn nhịp có cấu trúc + prompt renderer nguyên văn + "KHÔNG đổi thứ tự".
- Thiếu `clip_id` → in `THIẾU \`clip_id\`` + danh sách clip thay vì im lặng.
- `tests/test_prompt_agent_context.py`: 13 test.

Commit: `d1b52db`.

## 2026-11-02 — F-006 xong

**raw video QA**
- `src/Workflows/raw_video_qa.py` (543 dòng): 9 gate — `duration_match`, `fps_ok`,
  `resolution_ok`, `no_hard_cut`, `not_frozen`, `no_baked_ui`, `hook_clean`, `hook_still`,
  `chain_match` — cộng `evaluate_clip()`, `qa_summary()`, `hook_window_s()`.
- Mỗi gate trả `pass`/`warn`/`skip`, **không có `fail`** (người dùng chọn "chỉ cảnh báo").
- Ngưỡng đo từ clip thật, không phải số tròn:
  - `HARD_CUT_THRESHOLD=12` — clip thật đỉnh 10.79 (t=4.0, chỉ đổi tư thế: đã mở 2 khung
    t3.9 vs t4.0 để xác nhận cùng cảnh); cắt cứng tổng hợp 15.63.
  - `FREEZE_NOISE_DB=-50` — `-40dB` báo nhầm đoạn 0.5–0.875s chỉ là chuyển động chậm.
  - `HOOK_STILL_RATIO_MAX=0.6` — đo được 0.429 (hook median 0.95 vs thân 4.55).
  - `CHAIN_SSIM_MIN=0.90` — SSIM nội bộ clip1 là 0.475, nên gate chỉ có nghĩa cho cặp hai clip.
- `delivery.py`: `_attach_clip_qa()` chạy **sau** vòng copy (gate nối cần file clip trước),
  gắn `clips[].qa`, `manifest["qa_summary"]`, bảng QA trong `_render_readme`.
- Không nối QA vào `result.warnings`: README đã có bảng riêng, nối thêm thì mỗi lỗi hiện hai lần.
- `tests/test_raw_video_qa.py`: 26 test.
- Full suite: 392 passed, 5 failed = **đúng baseline D-001**, không phát sinh mới.

### Tiếp theo

Không còn feature nào `passes: false`. Việc mở: nối `delivery.build_delivery` vào API/UI nếu
muốn QA hiện ngay trong Flow Bench; hiện QA chỉ chạy lúc export.
