---
name: Video 2 (8s): Last Frame Showcase
description: Tạo prompt Video 2 (8s) nối tiếp từ Frame Cuối của Video 1. Bỏ Policy Compliance, bỏ mô tả dài dòng nhân vật/outfit (chỉ dùng câu ngắn gọn maintain exact), GIỮ NGUYÊN cấu trúc Timeline chi tiết từng giây (0-1s, 1-4s, 4-6s, 6-8s) và Negative.
---

# Fashion Lookbook Video 2 — Last Frame Fashion Showcase (8 Seconds)

Skill quy chuẩn cho **Node Video 2 (8s)** trong workflow thời trang nối tiếp trên Flow Bench.

## 0. Nhiệm vụ của Node Video 2
- **Đầu vào (Input)**: `Frame Cuối (Video 1)` (ảnh trích xuất ở giây thứ 8.0 của Video 1).
- **Trạng thái khung hình**: Đã biến mất toàn bộ cột UI/chữ, camera đã ở cự ly trung cảnh (Medium Shot), bối cảnh studio ấm áp.
- **Mục tiêu**: Nối tiếp chuyển động liền mạch (Seamless Motion Continuity) từ tư thế cuối của Video 1 để trình diễn thời trang (Lookbook Showcase), khoe trọn vẹn phom dáng trang phục, tà váy, tay áo, phụ kiện và thần thái mẫu.
- **TUYỆT ĐỐI KHÔNG**: Nhắc đến cột UI, chữ NABI, hay động tác đẩy (tránh làm AI bị ảo giác vẽ thêm cột rác).

---

## 1. Nguyên Tắc Cốt Lõi

> [!IMPORTANT]
> **Chỉ thực hiện 2 thay đổi so với bản gốc:**
> 1. **TUYỆT ĐỐI KHÔNG chèn `[POLICY COMPLIANCE]`**: Mệnh đề này không có tác dụng trong prompt video và gây loãng token chuyển động.
> 2. **KHÔNG mô tả chi tiết dài dòng về nhân vật/trang phục**: Toàn bộ diện mạo và outfit đã có sẵn trong Frame Cuối. Thay toàn bộ đoạn mô tả nhân vật dài dòng bằng đúng 1 câu mở đầu:
>    `Seamless continuation from the starting frame, maintaining exact model and outfit.`
> 3. **BẮT BUỘC GIỮ NGUYÊN CẤU TRÚC TIMELINE CHI TIẾT TỪNG GIÂY VÀ NEGATIVE**:
>    - Tuyệt đối **KHÔNG ĐƯỢC TÓM TẮT HAY CẮT NGẮN TIMELINE**.
>    - Giữ đầy đủ từng mốc: `0-1s:`, `1-4s:`, `4-6s:`, `6-8s:` với đầy đủ chuyển động của người mẫu, camera và bối cảnh.
>    - Giữ đầy đủ phần `Negative:`.

---

## 2. Kịch Bản Chuyển Động 8 Giây Nối Tiếp

- **0-1s (Fluid Continuation)**: Tiếp tục chuyển động mượt mà từ chính xác tư thế ở frame đầu vào. Nhịp thở tự nhiên, ánh mắt mềm mại nhìn thẳng ống kính, micro-movements tinh tế, camera giữ vững không giật khung hình.
- **1-4s (180° Half-Turn Showcase)**: Người mẫu bước nhẹ và xoay người nửa vòng (180-degree half-turn) duyên dáng để khoe trọn vẹn phom dáng trang phục: tay áo, lưng áo, độ rủ và chuyển động của tà váy/skort. Làn gió nhẹ làm tà áo và tóc bồng bềnh tự nhiên.
- **4-6s (Face Forward Editorial Posing)**: Người mẫu xoay người trở lại đối diện camera, nhẹ nhàng chuyển đổi trọng tâm chân và tạo dáng lookbook thẩm mỹ Hàn Quốc tự tin, tay đung đưa nhẹ phụ kiện / túi xách.
- **6-8s (Beauty Close-up Glide)**: Camera thực hiện cú lướt nhẹ nhàng tiến vào góc cận cảnh gương mặt và phần thân trên (Beauty shot). Người mẫu mỉm cười nhẹ nhàng cuốn hút, ánh nắng tự nhiên tạo viền sáng ấm áp trên tóc và bờ vai.

---

## 3. Template Prompt Chuẩn cho Node Video 2 (Full Timeline)

```text
Seamless continuation from the starting frame, maintaining exact model and outfit.

Timeline:
0-1s: Fluid continuation from the exact starting pose with completely natural micro-movements, steady eye contact with the lens, and soft breathing. Camera remains steady.

1-4s: The model steps softly and executes an elegant 180-degree half-turn to showcase the dynamic silhouette, tailoring, back details, and fabric drape of the outfit. Studio air gently catches the fabric and hair strands.

4-6s: The model gracefully turns back to face forward, shifting weight naturally and posing with poised Korean editorial lookbook micro-movements, gently swaying her accessories.

6-8s: Camera performs a slow, silky-smooth push-in to an elegant beauty close-up / medium-close shot. The model maintains confident, relaxed eye contact with a gentle, warm expression under soft natural studio lighting.

Negative: no jump cut, no morphing, no sudden camera shake, no outfit change, no face distortion, no extra limbs, no UI artifacts, no text, no lingering fragments, no unnatural jitter.
```
