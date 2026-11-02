# Handoff — lookbook-video-prompt-timeline

## Trạng thái

**Tất cả 6 feature đã `passes: true`.** Không còn việc dở trong phạm vi spec.

## Bằng chứng cuối

- `python -m pytest tests -q` → **392 passed, 5 failed**.
  5 failure là baseline D-001, không liên quan: `test_account_pool` ×3 (mục `9:16: 2` trong
  `configs/accounts_pool.json`), `test_media_service` ×2 (cùng nguyên nhân).
- `python -m pytest tests/test_raw_video_qa.py -q` → 26 passed.
- `evaluate_clip` trên `out/deliveries/havana_donna_set/clips/clip1.mp4` → 9 gate,
  5 pass / 3 warn / 1 skip, 3.7s.
- `npm run build` (web) xanh; `npx tsc --noEmit` chỉ còn lỗi có sẵn ở `TryOnPanel.tsx`.

## Chuỗi commit

- `64efb49` F-001..F-003 (beats trong script + renderer + lint/skill)
- `d1b52db` F-004, F-005 (FE gửi `clip_id`, agent dùng beats)
- F-006 commit ngay sau file này (raw video QA)

## Việc tiếp theo (nếu muốn đi xa hơn spec)

1. **Hiện QA trong Flow Bench.** Hiện QA chỉ chạy lúc export delivery. Muốn thấy ngay sau khi
   có clip thì gọi `raw_video_qa.evaluate_clip` trong endpoint job-status hoặc ở `DeliveryModal`,
   và trả `qa.status` về FE.
2. **Sửa 5 test đỏ baseline.** Không thuộc spec này: chúng đỏ vì `configs/accounts_pool.json`
   có thêm entry `9:16: 2`. Hoặc cập nhật kỳ vọng test, hoặc bỏ entry đó.
3. **`chain_match` chưa từng chạy thật.** Repo chỉ có clip1; gate đã test bằng fixture nhưng
   chưa có cặp clip1→clip2 thật để xác nhận ngưỡng 0.90 là đúng cho dữ liệu Flow.

## Bẫy đã gặp (đừng lặp lại)

- `ffmpeg -ss 1e6` trả **0 khung** chứ không lỗi → gate im lặng thành `skip`. Dùng `-sseof -0.1`
  (`_grab_last_frame`).
- `freezedetect -40dB` báo nhầm chuyển động chậm. `-50dB` mới đúng.
- `scdet threshold=10` bắt nhầm pha đổi tư thế (điểm 10.79). Dùng 12.
- `str.find` trên instruction của agent có thể khớp vào skill markdown, không phải context động.
  Dùng marker riêng (`Clip đang viết`).
- `configs/accounts_pool.json` đang modified trong working tree và **cố ý không commit**.
  Đừng `git add -A`.
