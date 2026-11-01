---
name: Video Motion (Tiêu chuẩn)
description: Tạo prompt video Lookbook 9:16 ngắn gọn cho Image-to-Video trên Google Flow, chỉ mô tả chuyển động cơ thể và camera để lớp dựng phía sau ghép được card/text/progress bar. Dùng cho chuỗi 2 clip 8s nối tiếp. Đã tính tới bộ lọc sanitize_video_prompt của repo.
---

# Fashion Lookbook Video Prompter — Motion Only

Skill thiết kế prompt video 9:16 theo hướng **Image-to-Video (I2V)** trên Google Flow.

Ảnh first frame đã là bản thiết kế đầy đủ (người mẫu, trang phục, bối cảnh, ánh sáng). Prompt chỉ
còn **một** nhiệm vụ: điều khiển **chuyển động cơ thể và camera**. Mọi thứ khác sẽ được lớp dựng
video chèn thêm ở hậu kỳ.

## 0. Ba ràng buộc của repo — sai một cái là hỏng prompt

Prompt sinh ra sẽ đi qua `sanitize_video_prompt()` trong `src/Bridge/flow_video_bridge.py` **trước
khi** được gửi lên Flow. Hàm này tự động bật chế độ `aggressive=True` ở **lần thử thứ 2**, nên prompt
phải sống sót qua cả hai chế độ.

### Ràng buộc 1 — Cấm mọi header mốc thời gian

`0s - 3s (Hook):`, `[2s-5s]`, `Camera & Realism:` — tất cả đều bị regex cắt hoặc để lại rác.

- Riêng `Camera & Realism` bị xoá **từ chỗ đó tới hết prompt** → mất toàn bộ nội dung phía sau.
- `- 0s to 2s (...)` bị xoá, nhưng `- 0s to 3s (...)` thì **không** khớp pattern → sót lại chuỗi rác
  ngay trong prompt gửi Flow.

Muốn tả nhịp, dùng lời văn: `For the first three seconds ... then ... at the end ...`.

### Ràng buộc 2 — Tránh đúng những cụm mà chế độ aggressive sẽ viết lại

| Cụm nên tránh | Bị đổi thành |
| :--- | :--- |
| `glances over her shoulder` | `rotates smoothly` |
| `looks at the camera` / `looking directly at the camera` | `maintaining natural posture` |
| `facing the camera` | `in a balanced front silhouette` |
| `the woman` / `the girl` / `the lady` | `the fashion subject` |
| `she` / `her` | `the subject` / `their` |

Hệ quả: nếu plan cần "giữ eye-contact tuyệt đối ở 3 giây đầu", **không** viết `looks at the camera`.
Viết `holds steady eye contact with the lens` — cụm này không khớp pattern nào nên đi qua nguyên vẹn.

Nếu cần "ngoái nhìn qua vai", viết `turns the head back toward the lens` thay vì `glances over her
shoulder`.

### Ràng buộc 3 — Văn phong trung tính giống

Chế độ aggressive đổi `She` → `the subject` mà **không** viết hoa lại đầu câu, tạo câu cụt ngữ pháp
(`...natural blinks. the subject then turns...`). Vì vậy:

- Gọi chủ thể là **`the model`** (đổi thành `the subject` vẫn đúng ngữ pháp).
- Không mở đầu câu bằng đại từ.
- Không dùng `she`, `her`, `hers`.

## 1. When to Use

Đây là **skill video duy nhất** của pipeline tách lớp. Hai skill cũ `lookbook-video-1-push` và
`lookbook-video-2-showcase` đã bị xoá vì chúng yêu cầu cột UI nằm trong pixel — trái với nguyên tắc
"AI chỉ làm người mẫu".

- Node Video đã có plate làm first frame (`try-on-image-prompter`, chế độ plate §2.5).
- Cần chuỗi 2 clip 8s nối liền mạch: clip 1 (0–8s) hook, clip 2 (8–16s) nối từ last frame clip 1.

### 1.1 Map từ script sang prompt

Script (`configs/lookbook_script.json`) đã khai báo `clips[].role` và `clips[].motion_prompt`.
Khi được giao một `clip.id`, đọc đúng entry đó:

| `role` | Ý nghĩa | Đặc điểm prompt |
| :--- | :--- | :--- |
| `hook` | 0–8s, giữ chân người xem | 3 giây đầu **không được quay lưng**; eye contact trước, xoay sau |
| `showcase` | nối tiếp, khoe phom | Mở đầu bằng `Continuing from that pose`; kết ở tư thế mở đầu clip trước để loop |
| `detail` | cận cảnh chi tiết | Camera áp gần, chuyển động cơ thể tối thiểu |

`motion_prompt` trong script là **bản nháp của người viết kịch bản**. Agent được phép viết lại cho đúng
ngân sách từ và đúng bộ lọc, nhưng **không được đổi** thứ tự chuyển động cốt lõi (ví dụ hook vẫn phải
eye-contact trước rồi mới xoay).

## 2. Nguyên tắc cốt lõi — ảnh đã nói thay phần mô tả

**TUYỆT ĐỐI KHÔNG đưa vào prompt:**

- Mô tả lại khuôn mặt, tuổi, quốc tịch/sắc tộc, dáng người, thần thái.
- Liệt kê lại từng món trang phục, chất liệu vải, màu sắc, phụ kiện.
- Mô tả lại ánh sáng, phông nền, studio.
- Tên món đồ in hoa, tên thương hiệu, chữ trên màn hình — lớp dựng lo phần này.
- Từ đệm rỗng: `8k`, `ultra-photorealistic`, `masterpiece`, `best quality`, `award-winning`.
- `slow-motion` (gây cảm giác video AI giả).

**Chỉ giữ 3 thành phần:** chuyển động cơ thể · chuyển động camera · chi tiết vi mô của vải/tóc.

## 3. Từ vựng chuyển động (bản đã kiểm tra qua bộ lọc)

**Chuyển động cơ thể** (chọn 2–3, không dồn hết):
`shifts weight between the feet` · `rolls the shoulders softly` · `turns a full 360 degrees in place`
· `angles forty-five degrees to one side` · `steps forward once` · `brushes the hair back` ·
`adjusts the shoulder strap` · `lifts the tote higher on the shoulder` · `turns the head back toward
the lens`

**Chi tiết vi mô** (chọn 1–2):
`natural blinks` · `quiet breathing` · `fabric sways gently` · `hair settles` · `hem lifts with the turn`

**Chuyển động camera** (chọn 1, giữ cùng trục giữa 2 clip):
`Camera pushes in slowly at natural real-time speed` · `Camera drifts closer on the same axis` ·
`Camera pans gently downward to the waist and hem` · `subtle handheld breathing`

**Nhịp chân thực:** `at natural real-time speed` · `candid unscripted movement`. Không dùng
`slow motion`, `fast`, `dramatic`, `cinematic swoop`.

**Gaze an toàn:** `holds steady eye contact with the lens` · `returns to the lens` · `eyes settle
downward toward the bag`.

## 4. Ngân sách độ dài

- Mỗi prompt: **25–60 từ**. Tuyệt đối không vượt 80.
- Một prompt = 1 câu camera + 2 câu chuyển động cơ thể. Hết.
- Nếu thấy mình đang tả lại ảnh → cắt bỏ ngay.

## 5. Cấu trúc 2 clip nối tiếp

### Clip 1 (0–8s) — Hook: giữ eye-contact trước, xoay sau

Thứ tự bắt buộc, nếu đảo thì mất 3 giây hook:

1. **0–3s:** đứng gần như tĩnh, `holds steady eye contact with the lens`, một tay chạm nhẹ cổ áo.
   Đây là phần giữ người xem lại đọc hook banner.
2. **3–8s:** xoay trọn 360 độ tại chỗ để lộ lưng trần và dây buộc nơ, rồi trở về mặt trước.

Không cho người mẫu quay lưng trong 3 giây đầu — đó là lỗi của clip hiện tại.

### Clip 2 (8–16s) — Chi tiết & kết vòng lặp

1. **0–4s:** nghiêng 45 độ, nâng túi lên vai, mắt liếc xuống túi một lần rồi quay lại ống kính.
2. **4–8s:** thả dáng tự nhiên, gió làm tóc bay nhẹ, và **kết thúc ở đúng tư thế mở đầu của clip 1**.

Yêu cầu cuối clip là mấu chốt: nếu last frame trùng tư thế first frame thì khi phát lặp 16s → 0s sẽ
không giật. Viết rõ: `settles back into the opening stance so the clip loops`.

### Template

```text
Camera pushes in slowly at natural real-time speed. For the first three seconds the model stands
square to the lens and holds steady eye contact, one hand brushing the halter neckline, natural
blinks and quiet breathing. The model then turns a full 360 degrees in place, hem lifting with the
turn, hair settling as the front silhouette returns.
```

```text
Continuing from that pose, the model angles forty-five degrees, lifts the woven tote higher on the
shoulder, eyes settling downward toward the bag once, then returns to the lens with a small smile.
Camera drifts closer on the same axis. A soft breeze lifts the hair as the model settles back into
the opening stance so the clip loops.
```

## 6. Không được nhờ AI vẽ UI

Prompt video **không được** chứa: `card`, `sidebar`, `column`, `label`, `text`, `banner`,
`progress bar`, `split screen`, `collage`, `HALTER TOP / DENIM JEANS / TOTE BAG` viết hoa.

Nếu cần cột item xuất hiện trong video, đó là việc của lớp dựng (HyperFrames/Remotion/editor), không
phải của Veo. Đưa UI vào prompt = chữ méo + mất 1/3 khung hình.

## 7. Khi bị chặn (Prominent People filter)

Theo thứ tự, dừng ngay khi hết lỗi:

1. **Giữ nguyên ảnh nguồn**, dùng prompt tối giản ở mục 5. Không thêm gì.
2. Nếu vẫn lỗi → thêm **từng thành phần một** (camera, rồi biểu cảm, rồi chi tiết vải) và chạy lại.
   Mỗi lần chỉ đổi 1 biến để biết biến nào gây lỗi.
3. Nếu prompt tối giản vẫn bị chặn với cùng ảnh → **nguyên nhân ở ảnh đầu vào, không phải prompt**.
   Đổi ảnh nguồn hoặc báo người vận hành.

Lưu ý: lần retry thứ 2 tự động bật `aggressive=True`, nghĩa là prompt sẽ bị viết lại mạnh tay hơn.
Nếu lần 2 ra video sai chuyển động, đó có thể là do bộ lọc chứ không phải do prompt gốc — kiểm tra
log `[Bridge Mode 2/2]` trước khi sửa prompt.

## 8. Output Format

Số khối code **bằng đúng số clip được giao**. Nếu chỉ giao một `clip.id` → trả **một** khối. Nếu giao cả
hai → trả hai khối, đúng thứ tự clip1 rồi clip2.

Không giải thích ngoài khối, không header `[Video Prompt N]` (parser sẽ để lại rác `[`):

````text
```text
<clip 1 prompt>
```

```text
<clip 2 prompt>
```
````

---

## 9. Checklist trước khi trả prompt

- [ ] 25–60 từ (trần cứng 80).
- [ ] Không header mốc thời gian nào: `0-3s:`, `[2s-5s]`, `Timeline:`, `Camera & Realism:`.
- [ ] Không có `she`, `her`, `the woman`, `the girl`, `the lady` — gọi `the model`.
- [ ] Không có `looks at the camera`, `facing the camera`, `glances over her shoulder`, `slow motion`.
- [ ] Không có từ vựng UI (mục 6).
- [ ] Không mô tả lại khuôn mặt, trang phục, ánh sáng, bối cảnh.
- [ ] Có đúng 1 câu camera + 2 câu chuyển động cơ thể.
