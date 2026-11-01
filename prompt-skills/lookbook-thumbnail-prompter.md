---
name: Ảnh Lookbook Thumbnail (Board NABI)
description: Tạo prompt ảnh bìa/thumbnail Lookbook 9:16 bố cục chia đôi (1/3 cột NABI bên trái + 2/3 người mẫu bên phải). CHỈ dùng làm thumbnail của project. KHÔNG dùng làm first frame video — board dính UI vào pixel sẽ phải crop mất 1/3 khung. Pipeline video dùng `lookbook-model-only-prompter`.
---

# Fashion Lookbook Thumbnail Prompter — Split-Screen Board (NABI Style)

> [!WARNING]
> **Skill này KHÔNG còn là nguồn cho video.** Kể từ khi chuyển sang kiến trúc tách lớp
> (Flow lo người mẫu — HyperFrames lo cột item/chữ), board có cột NABI chỉ còn một công dụng:
> **ảnh bìa / thumbnail của project**.
>
> Dùng board làm first frame video sẽ dẫn tới: chữ dính pixel bị méo, phải crop bỏ 1/3 trái, và bề
> ngang thật sau crop chỉ còn ~453px (không đạt 1080×1920).
>
> Cho pipeline video, dùng [`try-on-image-prompter.md`](try-on-image-prompter.md) ở **chế độ plate**
> (§2.5) — một ảnh đầu vào, studio trơn, negative nền sạch.

Skill thiết kế prompt sinh **Ảnh Lookbook 9:16 bố cục chia đôi (Split-Screen)** cho Google Flow /
Midjourney / Flux — dùng làm **ảnh bìa**.

---

## 0. Phạm vi sử dụng

| Dùng cho | Được? |
| :--- | :--- |
| Ảnh bìa project (thumbnail), ảnh preview trong gallery | ✅ |
| Ảnh tham chiếu cho designer dựng cột item | ✅ |
| First frame của node video | ❌ **tuyệt đối không** |
| Nguồn để crop ra plate | ❌ mất 1/3 khung + mất độ phân giải thật |

---

## 1. QUY CHUẨN TỶ LỆ CƠ THỂ VÀNG & HACK CHIỀU CAO (ANTI-SHORTENING MASTERY)

> [!IMPORTANT]
> **4 Lỗi chí mạng khiến người mẫu bị lùn trong ảnh AI và giải pháp nhiếp ảnh bắt buộc:**

### 1.1 Góc máy hạ thấp ngang hông / đầu gối (Low Camera Angle - Hip/Knee Level)
- **Lỗi phổ biến**: Máy đặt cao ngang ngực hoặc tầm mắt chúc xuống (`high angle / downward tilt`). Khi chụp từ trên xuống, hiệu ứng thu ngắn phối cảnh (foreshortening) khiến phần chân bị co ngắn lại, trong khi phần đầu và vai lại to hơn so với chân, làm tỷ lệ người mẫu bị lùn và mất cân đối.
- **Quy chuẩn prompt bắt buộc**:
  - Đặt camera ở tầm **ngang hông hoặc ngang đầu gối, hơi hếch nhẹ lên trên** (`low camera angle positioned at hip or knee level, subtle upward tilt`).
  - Hiệu ứng thị giác: Kéo dài trục đứng của đôi chân tự nhiên, tạo tỷ lệ cơ thể chuẩn siêu mẫu 8-9 đầu thanh thoát.
  - **Từ khóa prompt**: `low camera angle positioned at hip level with a subtle upward tilt, flattering elongated leg perspective, editorial high-fashion proportions`.

### 1.2 Canh lề sàn chân — Chừa khoảng thở dưới sàn (10–15% Floor Breathing Room)
- **Lỗi phổ biến**: Crop sát rạt ngay dưới đế giày (`cropped tight at shoe soles`). Khi đế giày chạm mép đáy khung hình, mắt người nhìn mất đi điểm tham chiếu mặt sàn, não bộ tự suy diễn là chân đã kết thúc ở đó, tạo cảm giác người mẫu bị cụt chân và lùn đi trông thấy.
- **Quy chuẩn prompt bắt buộc**:
  - Bắt buộc chừa **10–15% khoảng trống mặt sàn nhìn thấy rõ bên dưới chân** (tương đương 10–15cm khoảng hở thị giác) và chừa 5–8% khoảng thở phía trên đỉnh đầu.
  - Tuyệt đối không để đế giày chạm mép dưới hoặc bị cắt cụt.
  - **Từ khóa prompt**: `generous 10-15% visible floor breathing space beneath the shoes, clearly visible floor plane grounding the feet, completely uncropped feet, elegant headroom above`.

### 1.3 Giày "Hack Chân" — Ưu tiên hở cổ chân & mu bàn chân (Footwear Elongation)
- **Lỗi phổ biến**: Sử dụng booties cổ lửng, boots ôm mắt cá hoặc giày có quai ngang to bản (ví dụ: đôi tan cutout booties có quai ngang). Thiết kế này cắt đứt đường thẳng thị giác liền mạch của cẳng chân, khiến chân bị ngắn đi 5–7cm về mặt thị giác.
- **Quy chuẩn chọn item & prompt**:
  - Ưu tiên các dòng giày "hack chiều cao" khoe trọn mu bàn chân và hở cổ chân: **sandal cao 3–5cm quai mảnh (strappy sandals), sandal quai trong suốt (clear transparent strap kitten heels), giày cao gót mũi nhọn (pointed-toe slingbacks), hoặc mule hở cổ chân**.
  - Sự liền mạch từ đùi qua bắp chân xuống tận mũi chân tạo một đường thẳng quang học bất tận, giúp đôi chân trông thon dài vượt bậc.
  - **Từ khóa prompt**: `elongating footwear: open-ankle minimalist strappy kitten heels (3-5cm) or clear transparent strap sandals, exposing the ankle and instep to create an uninterrupted vertical visual line from thigh to toe`.

### 1.4 Tư thế đứng dồn trọng tâm (Elongated Contrapposto Stance) & Ánh sáng liền mạch
- **Lỗi phổ biến**: Người mẫu đứng 2 chân chụm đều, đầu gối chùng, trọng tâm dồn đều 2 bên khiến vóc dáng bị đơ cứng, bắp chân bè ngang; ánh sáng gắt đổ bóng ngang làm chân bị chia khúc.
- **Quy chuẩn tạo dáng & ánh sáng**:
  - **Tư thế Contrapposto**: Trọng tâm dồn vào một chân sau trụ thẳng căng tắp; chân trước hơi bước ra phía trước và **kiễng nhẹ mũi chân**, đầu gối thẳng, hông hơi đẩy nhẹ duyên dáng.
  - **Ánh sáng**: Ánh sáng studio khuếch tán mềm mại chạy dọc theo chiều cao cơ thể (soft vertical diffused lighting), bóng đổ xiên nhẹ nhàng ra phía sau, tuyệt đối không tạo ngấn bóng ngang trên bắp chân.
  - **Từ khóa prompt**: `poised contrapposto fashion stance, weight shifted to the locked back leg, front leg gracefully extended forward with a subtle pointed toe to accentuate long slender legs; continuous soft vertical studio lighting without harsh horizontal cast shadows breaking the calf line`.

### 1.4b Cấm dáng trực diện — nguyên nhân số 1 làm mẫu trông LÙN

`low camera angle` và `85mm` **không đủ**. Model ảnh (Nano Banana / Gemini image) khi không được khoá
tư thế sẽ dựng **dáng trực diện**: hai vai và hai hông song song mặt phẳng ảnh, hai bàn chân ngang
nhau. Lúc đó silhouette có tỷ lệ cao : rộng thấp nhất có thể, mẫu đủ pixel chiều cao nhưng **đọc** ra
là thấp và bè.

**BẮT BUỘC** thêm khối tư thế ba phần tư (đặt ngay sau cụm contrapposto ở §1.4):

```text
Body turned about thirty to forty-five degrees away from the camera so the silhouette reads tall
and narrow, shoulders and hips presented at a three-quarter angle instead of square-on,
near shoulder lower than the far shoulder, one arm relaxed away from the torso to keep the
waistline visible. Preserve the model's exact body proportions, height and silhouette from the
reference image: no shortening of the torso, no widening of the shoulders, no limb stretching.
```

**CẤM**: `standing square to the camera`, `facing the camera directly`, `front view`, `straight-on`,
`both feet flat and parallel`, `arms at both sides`, `elongated legs`, `slimmer waist`, `tall and slim`.

Phân biệt: `elongating footwear`, `low camera angle`, `floor breathing space` chỉ đổi **cách nhìn**,
giữ nguyên giải phẫu — dùng được. `elongated legs` / `slimmer waist` bảo model **vẽ lại** giải phẫu —
đó là thứ làm mẫu biến dạng so với người thật.

### 1.5 Tiêu cự ống kính chuyên dụng (85mm Lens Compression)
- **Lỗi phổ biến**: Tiêu cự góc rộng (< 35mm) gây méo hình (barrel distortion), phình to ở giữa và co giật ở rìa.
- **Quy chuẩn prompt**:
  - Chỉ định ống kính tele tầm trung **85mm f/2.8** chuyên dụng cho thời trang editorial.
  - **Từ khóa prompt**: `shot on 85mm portrait telephoto lens, flattering perspective compression, perfectly proportioned slender silhouette avoiding wide-angle distortion`.

---

## 2. Cấu trúc bố cục 9:16 chuẩn (Split Layout)

Khung hình dọc tỷ lệ **9:16** được chia làm 2 phần liền mạch:

### 2.1 Cột bên trái (Chiếm 1/3 chiều ngang - Left Column)
- **Nền cột**: Dải màu tối than chì / đen nhám (Dark charcoal / matte black sidebar) chạy dọc từ trên xuống dưới.
- **Tiêu đề thương hiệu (Header)**: Phía trên cùng có dòng chữ thương hiệu trắng kiểu serif thanh lịch: **"NABI"** (hoặc "LOOKBOOK / OOTD").
- **Các thẻ item bóc tách (Vertical Item Cards)**: Một chuỗi các thẻ chữ nhật bo tròn màu trắng xếp dọc, hiển thị chi tiết từng món đồ riêng lẻ được bóc tách dạng flat-lay / ghost mannequin:
  1. Áo khoác / Áo len / Áo thun (Outerwear / Top)
  2. Váy / Đầm / Quần / Chân váy (Dress / Skort / Bottom)
  3. Mũ / Phụ kiện đầu / Túi xách (Headwear / Woven Bag)
  4. Giày kéo dài chân (Strappy Heels / Pointed Slingbacks / Clear Strap Sandals)
- Mỗi thẻ item có nhãn chữ in hoa tối giản bên dưới (ví dụ: `WHITE COTTON T-SHIRT`, `OLIVE GREEN SKORT`, `MINIMALIST STRAPPY HEELS`,...).

### 2.2 Khung hình bên phải (Chiếm 2/3 chiều ngang - Right Model Showcase)
- **Người mẫu toàn thân (Full-body shot - Head-to-toe)**: Người mẫu đứng thẳng, đầu tới chân hiển thị trọn vẹn, mặc **chính xác và đồng bộ 100% tất cả các món đồ** xuất hiện ở cột item bên trái.
- **Tỷ lệ & Góc máy**: Đặt góc máy tầm ngang hông hơi hếch lên nhẹ, lens 85mm nén dáng, chừa 10-15% sàn bên dưới chân.
- **Tư thế**: Đứng tự nhiên dồn trọng tâm (contrapposto), chân trước kiễng nhẹ mũi chân, một tay thả lỏng nhẹ nhàng hoặc cầm túi xách, mắt nhìn thẳng vào ống kính (steady eye contact). **Bắt buộc xoay ba phần tư** — vai và hông lệch 30–45° so với mặt phẳng ảnh (§1.4b); tuyệt đối không để hai vai mở hết ngang.
- **Bối cảnh & Ánh sáng**: Studio chụp ảnh thời trang tối giản, nền tường cong màu be/kem nhạt (warm off-white/beige cyclorama), ánh nắng tự nhiên xiên nhẹ tạo bóng đổ mềm mại phía sau, màu sắc ấm áp, cao cấp chuẩn tạp chí thời trang Hàn Quốc.

---

## 3. Quy chuẩn an toàn

Không chèn dòng `[POLICY COMPLIANCE]` vào prompt. Nếu ảnh bị bộ lọc Prominent People của Google Flow
chặn, sửa mô tả (bỏ so sánh với người thật, bỏ tên riêng), **không** thêm lại dòng này.

---

## 4. Template Prompt chuẩn cho Node Ảnh Lookbook 9:16 (Đã tối ưu tỷ lệ & chiều cao)

```text
Fashion lookbook catalog layout, vertical 9:16 split-screen editorial composition divided into two distinct sections:

Left side (one-third width): a sleek vertical dark charcoal sidebar featuring the brand header "NABI" in elegant white serif font at the top. Below the header is a neat vertical stack of clean rounded white product cards displaying isolated cutout flat-lay views of each individual garment item from the outfit: [LIỆT_KÊ_CÁC_MÓN_ITEM_BÓC_TÁCH: áo, váy/quần, túi xách, giày sandal quai mảnh hở cổ chân], each item card accompanied by a clean minimalist uppercase label.

Right side (two-thirds width): full-body head-to-toe vertical fashion studio photograph of the fictional Korean model standing, wearing the exact coordinated outfit matching the left item cards. Camera setup and composition: low camera angle positioned at hip level with a subtle upward tilt to elongate the silhouette, captured on an 85mm portrait telephoto lens for flattering perspective compression. The framing preserves a generous 10-15% visible floor breathing room beneath the soles of her shoes with completely uncropped feet grounded on the floor plane. 

The model poses with confident poise in an elegant contrapposto stance, body turned about thirty to forty-five degrees away from the camera so the silhouette reads tall and narrow, shoulders and hips presented at a three-quarter angle instead of square-on, near shoulder lower than the far shoulder, weight shifted to the locked back leg while the front leg is extended slightly forward with a delicate pointed toe, one arm relaxed away from the torso to keep the waistline visible. Preserve the model's exact body proportions, height and silhouette: no shortening of the torso, no widening of the shoulders, no limb stretching. The model wears open-ankle footwear (minimalist strappy kitten heels or clear-strap sandals) leaving the instep and ankles exposed to maximize unbroken vertical lines. 

Background & lighting: Minimalist warm light beige cyclorama studio background with soft continuous vertical natural daylight and gentle diagonal shadows falling behind her. Ultra-clean high-end commercial fashion catalog aesthetic, 8k resolution, crisp photorealistic fabric textures.
```

---

## 5. Negative Prompt (Chống lùn, chống méo góc máy & chống crop sàn)

> **CẢNH BÁO**: **KHÔNG ĐƯỢC** đưa các từ như `no cards, no sidebar, no text, no split screen, no collage` vào negative prompt, vì những từ này sẽ xóa mất cột item NABI!

Negative prompt chuẩn:
```text
prominent people, public figure, celebrity lookalike, real-world living person, high camera angle, overhead perspective, downward camera tilt, foreshortening, cropped feet, cut-off shoes, shoes touching bottom edge, zero floor space, ankle-cutting boots, heavy chunky booties, squat proportions, short legs, bent knees, symmetrical stiff pose, square-on frontal pose, facing the camera directly, straight-on front view, both feet flat and parallel, feet shoulder-width apart, arms hanging symmetrically at both sides, elongated legs, longer legs, slimmer waist, tall and slim, 8 heads tall, altered body proportions, stretched limbs, widened hips, heavy horizontal cast shadows across calves, wide-angle lens distortion, extra limbs, extra fingers, distorted hands, mutated anatomy, blurry face, plastic skin, low resolution, bad proportions.
```

---

## 6. Output Format

Trả về **duy nhất một khối code** chứa prompt tiếng Anh hoàn chỉnh:

```text
<positive prompt mô tả bố cục chia đôi gồm cột item NABI bên trái và người mẫu bên phải, tích hợp góc máy ngang hông hếch nhẹ, chừa 10-15% sàn và footwear hở cổ chân hack chiều cao>
```
