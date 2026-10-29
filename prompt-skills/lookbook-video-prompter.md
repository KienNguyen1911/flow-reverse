---
name: lookbook-video-prompter
description: Tạo prompt video thời trang Lookbook 9:16 ngắn gọn, chỉ tập trung vào chuyển động cơ thể và camera cho Image-to-Video. Không mô tả lại những gì ảnh nguồn đã thể hiện. Dùng cho chuỗi 2 video 8s nối tiếp.
---
# Fashion Lookbook Video Prompter

Skill thiết kế prompt video Lookbook 9:16 theo hướng **Image-to-Video (I2V)** trên Google Flow / Veo. Ảnh khung hình nguồn đã là "bản thiết kế" đầy đủ; prompt chỉ còn một nhiệm vụ duy nhất: **điều khiển chuyển động và camera**.

## 1. When to Use
- Node Video đã có ảnh First Frame (Lookbook Board 9:16 hoặc ảnh toàn thân người mẫu).
- Cần tạo chuỗi 2 video 8 giây liền mạch: Video 1 (0–8s) mở đầu, Video 2 (8–16s) nối tiếp từ Frame Cuối của Video 1.

## 2. Nguyên tắc cốt lõi — Ảnh đã nói thay phần mô tả

Ảnh nguồn đã chứa sẵn khuôn mặt, dáng người, trang phục, chất liệu, màu sắc, ánh sáng và bối cảnh. Prompt **không thể cải thiện** những thứ đã có trong ảnh, và mô tả lại chúng chỉ làm loãng trọng số của phần chuyển động.

**TUYỆT ĐỐI KHÔNG đưa vào prompt:**
- Mô tả lại khuôn mặt, tuổi, quốc tịch/sắc tộc, dáng người, thần thái.
- Liệt kê lại từng món trang phục, chất liệu vải, màu sắc, phụ kiện.
- Mô tả lại ánh sáng, phông nền, bối cảnh studio.
- Mệnh đề miễn trừ danh tính / policy disclaimer dài dòng.
- Từ đệm chất lượng rỗng: `8k`, `ultra-photorealistic`, `masterpiece`, `best quality`, `award-winning`.
- Từ `slow-motion` (gây cảm giác video AI giả).

**Chỉ giữ 3 thành phần:** chuyển động cơ thể · chuyển động camera · chi tiết vi mô của vải/tóc.

## 3. Từ vựng chuyển động

**Chuyển động cơ thể** (chọn 2–3, không dồn hết):
`shifts weight between her feet` · `rolls her shoulders softly` · `turns 45 degrees to her right` · `brushes hair back` · `adjusts the strap` · `steps forward once` · `glances over her shoulder`

**Chi tiết vi mô** (chọn 1–2):
`natural blinks` · `subtle breathing` · `fabric sways gently` · `hair settles` · `hem lifts with the turn`

**Chuyển động camera** (chọn 1, giữ liền mạch giữa 2 video):
`gradual push-in` · `slow horizontal pan` · `subtle handheld breathing` · `slight low-angle drift`

**Nhịp chân thực:** `at natural real-time speed` · `candid unscripted movement`. Không dùng `slow motion`, không dùng `fast`, `dramatic`, `cinematic swoop`.

## 4. Ngân sách độ dài

- Mỗi prompt: **25–60 từ**. Tuyệt đối không vượt 80 từ.
- Một prompt = 1 câu camera + 1–2 câu chuyển động cơ thể. Hết.
- Nếu thấy mình đang tả lại ảnh → cắt bỏ ngay, đó là dấu hiệu prompt đang phình sai hướng.

## 5. Cấu trúc 2 Video nối tiếp

### Video 1 (0–8s) — Mở đầu, giữ nguyên bố cục ảnh
- Bắt đầu **đúng** từ First Frame, không đổi khung hình đột ngột.
- Camera tiến/pan nhẹ để tạo cảm giác sống.
- Người mẫu chuyển động vi mô tại chỗ: đổi trọng tâm chân, nhún vai, chớp mắt.

### Video 2 (8–16s) — Nối tiếp từ Frame Cuối
- Bắt đầu **đúng** từ tư thế kết thúc của Video 1 (Frame Cuối), không nhảy cóc.
- Người mẫu xoay 45–90° để lộ phom dáng, đường may, độ rũ của vải.
- Camera tiếp tục **cùng trục** với Video 1, chỉ tiến gần hơn.

## 6. Output Format Template

```text
[Video 1]
Camera gradually pushes in at natural real-time speed. She shifts weight between her feet, rolls her shoulders softly, natural blinks, fabric sways gently. Subtle handheld breathing.

[Video 2]
Continuing from the previous pose, she turns 45 degrees to her right, hem lifting with the turn. Camera glides closer along the same axis. Hair settles, one slow blink to camera.
```

## 7. Khi bị chặn (Prominent People filter)

Theo thứ tự, dừng lại ngay khi hết lỗi:

1. **Giữ nguyên ảnh nguồn**, dùng prompt chuyển động tối giản ở mục 6. Không thêm gì.
2. Nếu vẫn lỗi → thêm **từng thành phần một** (camera, rồi biểu cảm, rồi chi tiết vải) và chạy lại. Mỗi lần chỉ đổi 1 biến để biết biến nào gây lỗi.
3. Nếu prompt tối giản vẫn bị chặn với cùng ảnh → **nguyên nhân nằm ở ảnh đầu vào, không phải prompt**. Không cắt ngắn prompt thêm một cách máy móc; hãy đổi ảnh nguồn hoặc báo lỗi cho người vận hành.

Lưu ý: chưa có bằng chứng xác nhận rằng độ dài prompt hay một từ khóa cụ thể là nguyên nhân gây chặn. Vì vậy chỉ kết luận sau khi đã thử tách biến theo bước 2 — không suy đoán cơ chế bộ lọc.
