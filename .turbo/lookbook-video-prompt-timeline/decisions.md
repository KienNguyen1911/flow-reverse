# Decisions

## D-001 Baseline có 5 test đỏ sẵn (2026-11-02)
`python -m pytest tests -q` tại HEAD `d5ece74` + chỉ có `.turbo/` untracked:

```
FAILED tests/test_account_pool.py::test_allocation_zero_when_all_cooldown
FAILED tests/test_account_pool.py::test_allocation_shrinks_when_one_cooldown
FAILED tests/test_account_pool.py::test_captured_args_has_reference_detects_t2i_baseline
FAILED tests/test_media_service.py::test_resolve_image_aspect_reads_capture_config
FAILED tests/test_media_service.py::test_node_options_exposes_capabilities
5 failed, 310 passed
```

Nguyên nhân: `configs/image_aspect_enums.json` (hoặc capture config) đang có thêm `9:16: 2` so với
assert của test. Không liên quan tới task này. **Không sửa** — nếu sửa sẽ là đổi hành vi ngoài scope.
Gate của task này là: số test đỏ không tăng.

## D-002 Canvas giữ 1080x1920, QA cảnh báo upsample
Clip Flow trả 720x1280 nhưng `delivery.json` khai canvas 1080x1920. Quyết định: **giữ 1080x1920**
(nó là đích xuất bản cho TikTok/Reels) và để gate `resolution_ok` báo `warn`
"nguồn 720x1280, phóng 1.5x". Không hạ canvas về 720 vì sẽ làm mất chuẩn đầu ra.
Người dùng vẫn thấy rõ nếu muốn đổi.

## D-003 Beat renderer tất định, agent không được viết lại câu beat
Khi `clips[].beats` có mặt, `motion_prompt.beats_to_prompt()` quyết định câu chữ. Agent chỉ được thêm
`custom_hint` vào phần không phải beat. Lý do: gate round-trip sanitizer chỉ có giá trị nếu đầu vào
tất định; để agent tự do thì mỗi lần chạy ra một câu khác và không thể khoá bằng test.

## D-004 Chỉ văn xuôi thứ tự là định dạng thời gian sống sót
Đo thật 7 kiểu: nhãn `0s-2s:`/`0-2s:`/`[0-2s]` bị `sanitize_video_prompt` xoá; `(0s-2s)` sót rác;
`Beat one:`/`At 0:02` sống nhưng model chưa kiểm chứng. Chọn
`For the first N seconds ... From the Ath to the Bth second ... In the final N seconds`.
