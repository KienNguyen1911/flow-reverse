---
name: Video 1 (8s): Push UI & Hook
description: Tạo prompt Video 1 (8s) từ ảnh Lookbook 9:16 gốc. Bỏ Policy Compliance, bỏ mô tả dài dòng nhân vật/outfit (chỉ dùng câu ngắn gọn maintain exact), GIỮ NGUYÊN cấu trúc Timeline chi tiết từng giây (0-1s, 1-2s, 2-4s, 4-8s) và Negative.
---

# Fashion Lookbook Video 1 — The Push UI & Hook (8 Seconds)

Skill quy chuẩn cho **Node Video 1 (8s)** trong workflow thời trang 2 giai đoạn trên Flow Bench.

## 0. Nhiệm vụ của Node Video 1
- **Đầu vào (Input)**: Ảnh tĩnh Lookbook 9:16 có bố cục chia đôi (Cột item bên trái, người mẫu toàn thân bên phải).
- **Mục tiêu**: Tạo cú "Hook" mở đầu video giật mắt người xem: người mẫu dùng tay đẩy bay cột UI ra khỏi màn hình, để lại khoảng trống tĩnh sạch sẽ để dựng phim chèn text đồ họa, rồi camera zoom mượt mà vào người mẫu lookbook.

---

## 1. Nguyên Tắc Cốt Lõi

> [!IMPORTANT]
> **Chỉ thực hiện 2 thay đổi so với bản gốc:**
> 1. **TUYỆT ĐỐI KHÔNG chèn `[POLICY COMPLIANCE]`**: Mệnh đề này không có tác dụng trong prompt video và gây loãng token chuyển động.
> 2. **KHÔNG mô tả chi tiết dài dòng về nhân vật/trang phục**: Toàn bộ khuôn mặt, kiểu tóc, áo, váy, túi, giày đã có sẵn 100% trong ảnh nguồn. Thay toàn bộ đoạn mô tả nhân vật dài dòng bằng đúng 1 câu mở đầu:
>    `Maintain exact model and outfit from the reference image.`
> 3. **BẮT BUỘC GIỮ NGUYÊN CẤU TRÚC TIMELINE CHI TIẾT TỪNG GIÂY VÀ NEGATIVE**:
>    - Tuyệt đối **KHÔNG ĐƯỢC TÓM TẮT HAY CẮT NGẮN TIMELINE**.
>    - Giữ đầy đủ từng mốc: `0-1s:`, `1-2s:`, `2-4s:`, `4-8s:` với đầy đủ chuyển động của người mẫu, camera và bối cảnh.
>    - Giữ đầy đủ phần `Negative:`.

---

## 2. Kịch Bản Chuyển Động 8 Giây

- **0-1s (Completely LOCKED Camera)**: Camera khóa cứng hoàn toàn, không di chuyển, không zoom, không rung lắc. Giữ trọn vẹn bố cục 9:16 với cột item NABI nền đen bên trái và người mẫu tạo dáng tay chống hông bên phải, ánh mắt kiên định nhìn thẳng ống kính.
- **1-2s (High Explosive Push Action)**: Người mẫu đưa tay phải lên và dứt khoát đẩy toàn bộ cột item bên trái văng ra khỏi khung hình với tốc độ bùng nổ và motion blur cực mạnh. Cột item bay biến mất hoàn toàn trong 0.5s theo quán tính woosh. Camera tiếp tục khóa cứng.
- **2-4s (Locked Negative Space for Post-Editing)**: Camera tiếp tục khóa cứng tuyệt đối, giữ trọn vẹn khoảng trống tĩnh sạch sẽ bên trái nơi cột item vừa biến mất (để editor chèn text/đồ họa). Người mẫu lấy lại tư thế tự nhiên với các chuyển động vi mô nhẹ nhàng và nhịp thở êm.
- **4-8s (Silky-Smooth Push-in Zoom)**: Camera thực hiện cú push-in zoom mượt mà tiến về phía người mẫu. Người mẫu chuyển sang các chuyển động tạo dáng lookbook thẩm mỹ Hàn Quốc: xoay nhẹ thân trên, đổi tư thế chân, đung đưa nhẹ chiếc túi xách, tóc bồng bềnh trong làn gió nhẹ. Bối cảnh studio màu be sáng ấm với ánh nắng tự nhiên. Kết thúc ở cự ly trung cảnh (Medium Shot) thanh lịch ở giây thứ 8.

---

## 3. Template Prompt Chuẩn cho Node Video 1 (Full Timeline)

```text
Maintain exact model and outfit from the reference image.

Timeline:
0-1s: Completely LOCKED camera, zero motion, zero zoom, zero shake. Original 9:16 composition preserved with the vertical black NABI item sidebar on the left and the model standing poised on the right with hand on hip, maintaining steady direct eye contact with the lens.

1-2s: The model raises her right hand and forcefully pushes the entire left item column to the left with high explosive speed and strong motion blur. The column flies cleanly out of frame within 0.5 seconds with a sharp woosh inertia. Camera remains rigidly LOCKED.

2-4s: Camera remains strictly LOCKED with zero movement, preserving clean empty negative space on the left side where the column disappeared for post-editing graphic overlays. The model regains poise with subtle, natural micro-movements and gentle breathing.

4-8s: Camera executes a silky-smooth, controlled push-in zoom towards the model. The model flows into subtle Korean aesthetic lookbook posing: gentle torso rotation, shifting foot stance, gently swaying the woven straw tote bag, soft dark hair strands moving gently in a light warm breeze. Setting is a minimalist warm light beige studio with soft natural sunlight and subtle window shadows. Frame settles into an elegant medium shot at second 8.

Negative: no jump cut, no morphing, no camera shake, no change of outfit, no change of face, no background change, no scale jump, no distorted hands, no extra limbs, no lingering UI fragments.
```
