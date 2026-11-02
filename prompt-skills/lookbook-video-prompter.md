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

- Mỗi prompt: **70–115 từ**. Trần cứng **120** (`prompt_lint.VIDEO_MAX_WORDS`).
- Một prompt = **1 câu camera + N câu beat + câu phủ định**. Với clip 8s chia 3 beat là 5 câu.
- Nếu thấy mình đang tả lại ảnh → cắt bỏ ngay.

Vì sao 70–115 chứ không phải 25–60 như trước: prompt phải mang được nhịp trong 8s (0–2s làm gì,
2–5s làm gì, 5–8s làm gì) và phải nói rõ điều **không** được xảy ra. Đo thật trên script mẫu: 99–110
từ đi qua `sanitize_video_prompt(aggressive=False)` **nguyên văn**. Dưới 70 từ thì không đủ chỗ cho
3 mốc giây.

## 5. Nhịp trong 8s: `beats` là nguồn, không phải văn xuôi

Nhịp sống ở `configs/lookbook_script.json → clips[].beats[]`, **không** sống trong prompt:

```jsonc
"beats": [
  { "at_s": 0, "duration_s": 2, "action": "Stands square to the lens, holds steady eye contact.",
    "holds_gaze": true, "must_not": ["turn away from the lens"] },
  { "at_s": 2, "duration_s": 3, "action": "Turns a full 360 degrees in place at an even pace." },
  { "at_s": 5, "duration_s": 3, "action": "Completes the turn and settles into the opening stance." }
]
```

`src/Workflows/motion_prompt.py::beats_to_prompt()` đổi beats thành prompt theo đúng một khuôn:

| Beat | Câu sinh ra |
| :--- | :--- |
| beat đầu | `For the first two seconds the model …` |
| beat giữa | `From the second to the fifth second the model …` |
| beat cuối | `In the final three seconds the model …` |

**Agent KHÔNG được viết lại câu beat.** Renderer tất định; agent chỉ được thêm `custom_hint` vào phần
không phải beat. Lý do: gate round-trip sanitizer chỉ có giá trị khi đầu vào không đổi giữa các lần
chạy.

### Vì sao không dùng nhãn giây

| Kiểu viết | Qua `sanitize_video_prompt` |
| :--- | :--- |
| `0s-2s: …` | mốc **bị xoá** |
| `0-2s: …` | mốc **bị xoá** |
| `[0-2s] …` | mốc **bị xoá** |
| `(0s-2s) …` | **sót rác** `(0s-2s)` vào prompt gửi Flow |
| `For the first two seconds …` | **nguyên văn** ✅ |

## 6. Clip 1 và clip 2 khác nhau ở đâu

Mục tiêu từng clip khai ở `clips[].goal` (một câu, cho người đọc; **không** đưa vào prompt — model
không dùng được mục tiêu trừu tượng).

### Clip 1 — `role: hook`

Mục tiêu: giữ người lướt lại đủ lâu để đọc hook.

1. **0–2s:** đứng yên, `holds steady eye contact with the lens`, một tay chạm nhẹ dây áo.
   `holds_gaze: true`. Đây là cử chỉ hook — **mắt khoá ống kính**, không phải cười hay vẫy tay.
2. **2–5s:** xoay trọn 360° tại chỗ, `hem lifting with the turn`.
3. **5–8s:** kết thúc vòng xoay, trả về đúng tư thế mở đầu để clip tự lặp.

### Clip 2 — `role: showcase`

Mục tiêu: khoe phom ở góc nghiêng rồi nối về tư thế mở đầu clip 1.

1. **0–3s:** nghiêng 45°, nâng lớp ngoài (cardigan/khoác) cao hơn trên vai.
2. **3–6s:** thả vai, để lớp ngoài rơi mở ra.
3. **6–8s:** trở về ống kính, kết đúng tư thế mở đầu clip 1 (`so the sequence loops`).

### Câu phủ định (bắt buộc)

Payload Flow **không có trường negative prompt**. Muốn cấm gì thì phải viết thành mệnh đề trong câu,
đặt ở `clips[].negative[]` và renderer nối vào cuối prompt:

```text
One continuous shot, staying inside the frame, with no cut. No added lettering or printed graphics.
```

Đừng viết `no banner / no caption / no card` — linter coi đó là từ vựng UI. Viết
`no added lettering or printed graphics`.

### Ví dụ đầy đủ (sinh từ script mẫu, không viết tay)

Đây là output thật của `beats_to_prompt()` trên `configs/lookbook_script.json`. Test
`test_skill_example_matches_renderer` khoá hai bên khớp nhau — sửa script mà quên sửa skill thì test đỏ.

```text
Camera pushes in slowly at natural real-time speed. For the first two seconds the model stands square to the lens with feet planted, holds steady eye contact, one hand resting on the strap, quiet breathing. From the second to the fifth second the model turns a full 360 degrees in place at an even pace, hem lifting with the turn and hair settling as the back comes into view. In the final three seconds the model completes the turn and settles back into the opening stance, returning to the lens so the clip loops. One continuous shot, staying inside the frame, with no cut. No added lettering or printed graphics.
```

```text
Continuing from that pose, camera drifts closer on the same axis. For the first three seconds the model angles forty-five degrees to one side and lifts the sheer cardigan higher on the shoulder, eyes settling downward once toward the sleeve. From the third to the sixth second the model rolls the shoulders softly and shifts weight between the feet, letting the cardigan fall open over the camisole. In the final two seconds the model returns to the lens and settles into the opening stance of the previous clip so the sequence loops. One continuous shot, staying inside the frame.
```

## 7. Không được nhờ AI vẽ UI

Prompt video **không được** chứa: `card`, `sidebar`, `column`, `label`, `text`, `banner`,
`progress bar`, `split screen`, `collage`, `HALTER TOP / DENIM JEANS / TOTE BAG` viết hoa.

Ngoại lệ duy nhất: các cụm trong `clips[].negative[]` (mệnh đề cấm). Linter dùng phạm vi clause nên
`no added lettering` không bị phạt, còn `turns with a banner` thì vẫn bị.

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

- [ ] 70–115 từ (trần cứng 120).
- [ ] Có đủ 3 mốc: `For the first … seconds` / `From the … to the … second` / `In the final … seconds`.
- [ ] Không header mốc thời gian nào: `0-3s:`, `[2s-5s]`, `Timeline:`, `Camera & Realism:`.
- [ ] Không có `she`, `her`, `the woman`, `the girl`, `the lady` — gọi `the model`.
- [ ] Không có `looks at the camera`, `facing the camera`, `glances over her shoulder`, `slow motion`.
- [ ] Không có từ vựng UI (mục 7), trừ mệnh đề trong `clips[].negative[]`.
- [ ] Không mô tả lại khuôn mặt, trang phục, ánh sáng, bối cảnh.
- [ ] Có đúng 1 câu camera + N câu beat + câu phủ định.
- [ ] `sanitize_video_prompt(prompt, aggressive=False) == prompt.strip()` (test tự kiểm).
