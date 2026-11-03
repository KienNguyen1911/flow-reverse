# Prompt try-on V3 — rút gọn có kiểm chứng

Tài liệu này ghi lại **phân tích V2 → V3** cho prompt ảnh thử đồ trong
`prompt-skills/try-on-image-prompter.md`. Khác V2 (bỏ *xung đột*), V3 bỏ *độ dài không mang thông
tin* — theo yêu cầu "không muốn prompt quá dài và khó kiểm soát".

- Phạm vi: chỉ prompt **ảnh** try-on/plate. Prompt video vẫn thuộc `lookbook-video-prompter`.
- Không đổi: 7 module, thứ tự ưu tiên, thư viện pose, ba mốc `76%` / `50mm` / `horizon level`.
- Bằng chứng: `tests/test_tryon_prompt_v2.py`, `tests/test_prompt_skills_contract.py`,
  `tests/test_pose_library.py`.

## 1. V2 phình ở đâu (đo trên template §2.2.3)

| Module | Ký tự | % |
| :--- | ---: | ---: |
| Header | 97 | 2% |
| `[IDENTITY LOCK]` | 358 | 7% |
| `[GARMENT FIDELITY]` | 580 | 11% |
| `[ANATOMY & POSE]` | 298 | 6% |
| `[HEIGHT & PROPORTION OPTIMIZATION]` | 2.200 | 42% |
| `[ENVIRONMENT & LIGHTING]` | 405 | 8% |
| `[PHOTOGRAPHY AESTHETICS]` | 312 | 6% |
| `Negative:` | 947 | 18% |
| **Tổng** | **5.237** | |

Hai khối cuối chiếm 60%. Cảm giác "quá dài" là đúng, và nó có một nguồn cụ thể chứ không rải đều.

## 2. Độ dài không đến từ số module

7 header chỉ tốn ~100 ký tự. Gộp 6 module thành 5 (như bản rút gọn tham khảo bên ngoài) không tiết
kiệm gì đáng kể mà lại phá `test_template_has_seven_modules_in_priority_order`. Toàn bộ phần giảm
nằm ở **nội dung**: các câu diễn giải lại cùng một ý.

Ví dụ trong khối Height, cùng một mệnh lệnh "giữ tỷ lệ Ảnh 1" được nói bốn lần bằng bốn cách:
`preserve the exact head-to-body ratio…`, `Do not lengthen the legs, shorten the torso…`,
`Posture: … neck lengthened by posture rather than anatomy`, `Anatomical Integrity: … No artificial
body stretching`. Chỉ câu đầu là mệnh lệnh; ba câu sau là hệ quả.

## 3. Ba thay đổi

### 3.1 Khối Height: bỏ diễn giải, giữ 7 nhóm và 3 mốc

2.238 → 1.167 ký tự (bản độc lập), 2.200 → 1.129 trong template. Giữ nguyên:

- đủ 7 nhãn `Body Proportion:` … `Anatomical Integrity:` — để agent biết **sửa đúng chỗ** khi ảnh
  sai, và để `test_tryon_template_embeds_height_block` còn ý nghĩa;
- `76 percent` / `50mm` / `waist level` / `three-degree` / `horizon level` — hiệu chuẩn từ batch 8
  ảnh thật trong `prompt-skills/poses/results/`, và `pose_assets.json` dùng chung bộ số này.

Bỏ: `stand back far enough that the whole figure fits`, `keep the camera distance constant and the
feet never read oversized while the legs never read shortened`, `model centred on the vertical axis
of the frame`, `subject scale identical across every image in the same set` (đã có `same
subject-to-camera distance`), `The outfit keeps its own design, cut, fit, drape and styling` (đã là
Garment Fidelity), `No horizontal band from hem, sock line or waistband cuts the figure in half`
(đã có trong câu Visual Silhouette đầu tiên).

### 3.2 `Negative:` → `Constraints:`

**Flow không có trường negative.** Prompt ảnh là một chuỗi duy nhất trong args `ogiZ0b`
(`[[["<prompt>"]]]` — `docs/api_specs/flow_create_image.md` §3.1). Không có `negative`/`negative_prompt`
nào trong payload, và không có kênh nào để gửi.

Hệ quả: 947 ký tự `no …, no …` ở V2 thực chất được gửi như **văn xuôi bình thường** tới Gemini image.
Model đọc "no text, no logo, no cropped feet" như một dãy mô tả — và các cụm danh từ (`text`, `logo`,
`card`) có thể **làm tăng** khả năng chúng xuất hiện. V3 đổi thành một câu `Constraints:` khẳng định,
giữ đủ 5 nhóm và chỉ dùng `no …` cho lỗi mà câu khẳng định không diễn đạt được.

Vẫn giữ nguyên tắc V2: một lỗi chỉ nói một lần, và chỉ nói khi module 1–6 chưa xử lý dứt điểm.

### 3.3 Identity Lock không mô tả khuôn mặt

V2 hardcode `East Asian facial features, soft delicate eye shape, … messy high bun with
face-framing wispy strands`. Hai lỗi:

1. Nó tạo **nguồn tham chiếu thứ hai dạng văn bản**, có thể xung đột với pixel của Ảnh 1 — đúng thứ
   mà `preserve the exact identity from Image 1` cố gắng tránh.
2. Nó chỉ đúng với một người mẫu cụ thể, trong khi template dùng cho mọi ảnh.

V3 chỉ còn: `Preserve the exact identity, facial features, hairstyle, hair colour and skin texture
of the model in Image 1. Image 1 is the sole identity reference. Do not beautify, slim, symmetrise
or age the face.`

> Nguyên tắc tổng quát hoá: **text chỉ nên chứa những gì ảnh không tự bảo toàn được.** Model nhìn
> Ảnh 1 là biết phải vẽ ai (mô tả mặt là thừa), nhưng không biết cái gì dễ mất ở garment (độ phồng
> balloon hem, tay áo trùm khớp ngón) — nên garment vẫn cần liệt kê **điểm rủi ro**, không phải
> catalogue đầy đủ.

## 4. Kết quả

| | V2 | V3 |
| :--- | ---: | ---: |
| Template | 5.237 ký tự / 809 từ | **3.451 / 538** (−34%) |
| Khối Height | 2.200 | 1.129 |
| Khối chặn lỗi | 947 (`Negative:`) | 579 (`Constraints:`) |
| Identity Lock | 358 (có catalogue mặt) | 219 |
| 7 module | ✓ | ✓ |
| 3 mốc định lượng | ✓ | ✓ |
| `lint_image_prompt` | ok | ok |

## 5. Guardrail

`prompt_lint.IMAGE_PROMPT_MAX_CHARS = 4500` + cảnh báo `image_prompt_too_long` (mức **warn**).
Template đo 3.451; sau khi điền tên món đồ và chèn `prompt_core` của pose, thực tế rơi vào
3.800–4.200. Mốc 4.500 để phát hiện prompt phình lại cỡ V1 mà không chặn outfit nhiều món.

## 6. Rủi ro còn lại

- **Khối chặn lỗi ngắn hơn** có thể làm tăng nhẹ lỗi chân ở model yếu. Nếu batch đầu cho thấy vậy,
  thêm **một mệnh lệnh khẳng định** vào `[ANATOMY & POSE]` — không nối lại danh sách `no …`.
- **Ba mốc định lượng** được hiệu chuẩn trên pose library (nhân vật 168 cm, 7.5 đầu), không phải
  trên ảnh người dùng. Chúng điều khiển *cách nhìn*, không áp tỷ lệ — nhưng nếu người dùng phàn nàn
  "người mẫu vẫn thấp", câu trả lời là **đổi pose/góc máy**, không phải thêm `elongated legs`.
- **So sánh V2 ↔ V3 phải chấm mù.** Chấm 5 tiêu chí (Identity / Garment / Fabric / Anatomy /
  Background), mỗi biến thể 4 ảnh, cùng seed nếu engine cho phép. Không kết luận từ một ảnh.
