---
name: lookbook-video-prompter
description: Tạo prompt AI tạo video chuyển động thời trang phong cách Lookbook 9:16 (0-8s lia camera từ bảng phối đồ sang người mẫu, 8-16s cận cảnh chất liệu vải và phom dáng). Tích hợp tuyên bố Policy Compliance chống lỗi Prominent People.
---
# Fashion Lookbook Video Prompter

Skill chuyên thiết kế câu lệnh (prompt) tạo video thời trang Lookbook 9:16 trên Google Flow hoặc các mô hình sinh video AI, bám sát layout Lookbook Board (cột 1/3 item cutout và cột 2/3 người mẫu trong studio tối giản ngập nắng xiên).

## 1. When to Use
- Người dùng có ảnh Lookbook hoàn chỉnh (hoặc vừa sinh xong từ Node Lookbook Image).
- Cần tạo 2 video liên tiếp (mỗi video dài 8 giây) liền mạch chuyển động.

## 2. Nguyên tắc Video Lookbook (Anti-AI Video Rules)
1. **Tốc độ chân thực**: TUYỆT ĐỐI KHÔNG dùng từ `slow-motion`. Bắt buộc dùng `real-time natural speed (1x speed)`, `authentic 24fps film cadence`, `candid unscripted movement`.
2. **Chuyển động camera cao cấp**:
   - Dùng chuyển động camera trơn tru: `smooth continuous horizontal camera tracking/pan`, `delicate push-in zoom`, `subtle handheld camera breathing`.
3. **Hành động vi mô tự nhiên**:
   - Người mẫu chuyển động vi mô: nhịp thở nhẹ, ngón tay chạm khẽ vào túi hoặc gấu áo, mắt chớp tự nhiên, tà áo lay nhẹ theo nhịp bước hoặc gió nhẹ studio.
4. **Ánh sáng & Bối cảnh**:
   - Studio tối giản phông kem/greige với vệt nắng xiên ấm áp (diagonal warm sunlight and soft shadows).

## 3. Khẳng định Nhân vật Hư cấu (BẮT BUỘC TRONG MỌI PROMPT)
Mọi prompt video BẮT BUỘC chèn mệnh đề sau ở đầu:
`"An authentic fashion lookbook video featuring an original, completely synthetic, 100% AI-generated fictional model. Strictly non-celebrity, non-public figure, zero intent or resemblance to any living individual, celebrity, or prominent person. Generic fictional persona for virtual fashion catalog only."`

## 4. Cấu trúc Output (2 Video 8s Nối tiếp)

### 🎬 VIDEO 1 (0s – 8s: The Layout Reveal & Full Model Showcase)
- **Điểm bắt đầu**: Khung hình First Frame (Lookbook Board 9:16 hoặc ảnh toàn thân người mẫu).
- **Chuyển động**: Camera lia mượt (smooth horizontal pan / gentle push-in) tập trung vào người mẫu toàn thân, người mẫu hơi nghiêng đầu mỉm cười nhẹ, đổi trọng tâm chân một cách thanh lịch tự nhiên. Ánh nắng xiên đổ bóng mềm mại trên sàn.

### 🎬 VIDEO 2 (8s – 16s: Detail Close-up & Seamless Continuation)
- **Điểm bắt đầu**: Khung hình Frame Cuối của Video 1 (giây thứ 8).
- **Chuyển động**: Tiếp nối mượt mà từ tư thế kết thúc của Video 1. Người mẫu khẽ xoay 45 đến 90 độ để khoe đường nét phía sau và cạnh hông trang phục. Camera tiến lại gần hơn (slow push-in) tập trung vào bề mặt chất liệu vải, đường may, vạt áo lay nhẹ theo quán tính xoay tự nhiên, kết thúc với ánh nhìn thanh lịch về phía ống kính.

## 5. Output Format Template

```text
[Positive Prompt Video 1]
An authentic fashion lookbook video featuring an original, completely synthetic, 100% AI-generated fictional model. Strictly non-celebrity, non-public figure, zero intent or resemblance to any living individual, celebrity, or prominent person. 
The camera performs a smooth, delicate slow push-in at real-time 1x natural speed, 24fps cadence. The fictional female model wearing the {OUTFIT_DESCRIPTION} gently shifts her weight, looking towards the camera with a subtle, confident expression. Natural ambient studio light with warm diagonal sunlight beams, subtle handheld micro-shake, visible authentic fabric weave, photorealistic catalog aesthetic.

[Positive Prompt Video 2]
An authentic fashion lookbook video featuring an original, completely synthetic, 100% AI-generated fictional model. Strictly non-celebrity, non-public figure, zero intent or resemblance to any living individual, celebrity, or prominent person.
Continuing seamlessly from the previous pose, at real-time natural speed, the model gracefully turns 45 degrees to showcase the silhouette and rear drape of the {OUTFIT_DESCRIPTION}. The camera glides softly, capturing the subtle motion of fabric folds and fine craftsmanship details. Authentic human micro-movements, natural eye blinks, soft studio shadows, ultra-photorealistic 8k quality.
```
