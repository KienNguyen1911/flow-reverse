---
name: Item Cutout (Flat-Lay From Lifestyle Photo)
description: Sinh prompt tạo ảnh sản phẩm phẳng (flat-lay) trên nền trơn từ ảnh lifestyle Shopee làm reference, để bước sau tách nền bằng rembg. Cấm người mẫu, cấm bối cảnh, cấm chữ. Dùng cho cột item card trong HyperFrames.
---

# Item Cutout Prompter — Flat-Lay Product Plate

Mục đích: biến ảnh **lifestyle có người mẫu** (ảnh Shopee) thành ảnh **chỉ có món đồ trên nền trơn**,
để `scripts/cutout_items.py` tách nền bằng `rembg` (model u2net **general**, không phải human_seg).

```text
ảnh Shopee lifestyle ──▶ [skill này] ──▶ item_plate.png ──▶ rembg ──▶ item_cutout.png (alpha)
```

---

## 0. Vì sao KHÔNG tách nền trực tiếp từ ảnh Shopee

Model tách nền phổ biến (`u2net_human_seg`) được huấn luyện cho **người**. Chạy trên ảnh lifestyle nó
sẽ tách nguyên cả người mẫu ra khỏi bối cảnh — đúng cái ta không muốn. Kể cả model general cũng sẽ giữ
lại tay, tóc, quán café đè lên vải.

Ngay cả `u2net_cloth_seg` — model chuyên tách **quần áo** khỏi người mặc — cũng không cứu được: đo thật
trên `HAVANA/6.jpg` nó ra đúng chiếc áo nhưng méo theo tư thế người mẫu, thủng ở chỗ hở da, và còn rác
dưới gấu. Đó là mask của *chiếc áo đang mặc*, không phải ảnh sản phẩm.

Vì vậy luôn tách 2 bước: **AI dựng lại món đồ trên nền trơn → mới matting**. Ảnh trung gian sạch thì
matting mới sạch. Nhiều khi bước matting còn **không cần**: ảnh Flow đã là sản phẩm trên nền trơn,
đúng thứ lớp dựng cần.

---

## 1. Input

- 1–3 ảnh lifestyle của **đúng món đồ đó** (ảnh sản phẩm thật của người bán).
- Tên món (`item.name`) và góc nhìn cần (`front` / `back` / `detail`).

Ảnh reference phải cho thấy **hình dáng thật và chất liệu vải**. Không dùng ảnh bị che khuất phần lớn
(ví dụ áo ngoài che gần hết áo trong) trừ khi chính món đó là món ngoài.

---

## 2. Nguyên tắc

**BẮT BUỘC:**

- Chỉ **một** món đồ, chính giữa khung, chiếm 60–80% diện tích — **trừ khi** người dùng
  chọn phạm vi `full_set` (xem §2.1). Mặc định vẫn là một món.
- Nền **trơn tuyệt đối** — màu trắng hoặc xám nhạt đồng nhất, không gradient mạnh, không bóng đổ phức tạp.
- Ánh sáng phẳng, đều (flat even lighting) để giữ đúng màu vải.
- Phom dáng giữ **đúng** như ảnh reference: cùng cổ áo, cùng độ dài, cùng chi tiết (nơ, ren, dây).
- Món đồ được "trải phẳng" (flat-lay) hoặc treo trên móc (ghost mannequin) — chọn **một** kiểu và nói rõ.

**CẤM TUYỆT ĐỐI:**

| Nhóm | Từ khoá cấm |
| :--- | :--- |
| Người | `model`, `person`, `woman`, `mannequin with face`, `hands`, `arms wearing`, `body`, `skin` |
| Bối cảnh | `cafe`, `street`, `outdoor`, `room`, `furniture`, `plants`, `background scenery` |
| Chữ / UI | `text`, `label`, `price tag`, `logo`, `watermark`, `banner`, `brand name` |
| Ghép | `collage`, `multiple items`, `grid`, `outfit set on a model`, `two pieces worn together` |

Nếu sản phẩm là **set nhiều món**, tạo **nhiều ảnh riêng**, mỗi ảnh một món. Không ghép chung,
trừ trường hợp `full_set` ở §2.1.

### 2.1 Phạm vi (`item_scope`) — chọn món nào lên ảnh

Ảnh Shopee thường là **cả bộ trên người mẫu**. Không nói rõ món nào thì model tự chọn vật thể
nổi bật nhất — thực tế luôn ra **chiếc áo** (nó chiếm nhiều diện tích và tương phản nhất), không
bao giờ ra quần. Vì vậy phạm vi là **bắt buộc**, không phải tuỳ chọn ngẫu nhiên.

| `item_scope` | Phải làm | Tuyệt đối không có |
| :-- | :-- | :-- |
| `top` | Chỉ món **mặc trên**: áo, camisole, cardigan, khoác | quần, váy, shorts |
| `bottom` | Chỉ món **mặc dưới**: quần, váy, shorts | áo, camisole, cardigan |
| `full_set` | **Cả bộ** trên một ảnh, các món xếp cạnh nhau không chồng lấn | người, bối cảnh, chữ |

Ngoại lệ `full_set`: đây là **trường hợp duy nhất** được bỏ quy tắc "một món". Các quy tắc còn
lại (nền trơn, cấm người, cấm chữ, giữ đúng phom/màu) **giữ nguyên**. Ảnh full-set **không đem
tách nền** bằng `cutout_items` — rembg coi cả cụm là một khối, alpha dính liền và không dùng được
làm card. Dùng thẳng ảnh nền trơn.

Nếu không xác định được món theo phạm vi (ảnh ref chỉ có một món, hoặc món không nhìn thấy), hỏi
lại bằng cách chọn món **thấy rõ nhất trong khung** và nói rõ trong prompt điều đã chọn.

---

## 3. Template prompt

### 3.1 Một món — trải phẳng (`top` / `bottom`)

Trong `<ITEM DESCRIPTION FROM REFERENCE>` phải gọi tên món **theo phạm vi**, và câu mở đầu phải
nói rõ loại món (upper garment / lower garment) để model không tự chọn món khác.

```text
Flat-lay product photograph of a single <UPPER GARMENT | LOWER GARMENT>: <ITEM DESCRIPTION FROM REFERENCE>. Only this one piece appears; the rest of the outfit is excluded entirely. The garment is laid perfectly flat, centered in frame, occupying 60-80% of the image area, fully visible from hem to waistband with no cropping. Seamless pure white studio background, flat even softbox lighting, no harsh shadows, no reflections on the background. Fabric texture, color, stitching, trim and neckline must match the reference photo exactly. Shot top-down with an 85mm lens, sharp focus across the entire garment.

Negative: no person, no model, no hands, no mannequin, no face, no body, no skin, no background scenery, no furniture, no props, no text, no letters, no labels, no price tags, no logo, no watermark, no banner, no collage, no multiple items, no grid, no second garment, <the rest of the outfit>, no shadows on background.
```

### 3.2 Cả bộ trên một ảnh (`full_set` — ngoại lệ có chủ đích)

```text
Flat-lay product arrangement of a complete coordinated set: <TOP ITEM>, and <BOTTOM ITEM>. Both pieces are laid perfectly flat on the same surface, arranged next to each other without overlapping — top placed above, bottom below, with clear even spacing so both silhouettes are fully visible and uncropped. Seamless pure white studio background, flat even softbox lighting, no harsh shadows. Fabric texture, color, stitching, trim and neckline of every piece must match the reference photo exactly. Shot top-down with an 85mm lens, sharp focus across the whole set.

Negative: no person, no model, no hands, no mannequin, no face, no body, no skin, no background scenery, no furniture, no props, no text, no letters, no labels, no price tags, no logo, no watermark, no banner, no overlapping garments, no shadows on background.
```

### 3.3 Chi tiết vải (tuỳ chọn, cho magnifier trong composition)

```text
Extreme close-up macro photograph of the fabric of <ITEM>: <FABRIC DETAIL>, filling the entire frame,
even flat lighting, showing weave and texture clearly. No person, no text, no props, seamless neutral background.
```

---

## 4. Output format

Trả về **chỉ một khối code** chứa prompt tiếng Anh:

````text
```text
<flat-lay prompt>
```
````

Nếu script yêu cầu nhiều món, trả về nhiều khối code, mỗi khối một món, theo đúng thứ tự `item.id`.

**Mỗi món chỉ một ảnh — mặt trước.** Thẻ sản phẩm trên timeline hiện 2–3s và thường bị chữ che;
sinh thêm ảnh lưng là credit không đổi lại được gì. Đừng đề xuất phương án mặt sau.

---

## 5. Tiêu chí nghiệm thu (trước khi chạy rembg)

- [ ] Đúng **phạm vi** đã chọn: `top` không còn quần/váy, `bottom` không còn áo,
      `full_set` có đủ các món và không chồng lấn. Đây là mục hay trượt nhất.
- [ ] Không người, không tay.
- [ ] Nền trơn một màu, không chi tiết.
- [ ] Phom dáng + chi tiết khớp ảnh reference (đối chiếu cạnh nhau).
- [ ] Không chữ, không giá, không logo người bán.
- [ ] Cạnh dài ≥ 800px.

Trượt mục nào → sửa prompt, chạy lại. Đừng chuyển sang rembg với ảnh sai: matting chỉ khuếch đại lỗi.

Sau rembg, mở `items/_review.png` (contact sheet) và kiểm lại từng món: quai dép, viền ren, dây áo
phải còn nguyên. Mất chi tiết mảnh → chụp lại ảnh gốc trên nền trơn, không vá tay.
