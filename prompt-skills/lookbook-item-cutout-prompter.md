---
name: Item Cutout & Coordinate Sheet (From Lifestyle Photo)
description: Sinh prompt tạo ảnh sản phẩm phẳng (flat-lay) trên nền trơn từ ảnh lifestyle Shopee làm reference, để bước sau tách nền bằng rembg. Cấm người mẫu, cấm bối cảnh. Plate `top`/`bottom`/`full_set` cấm chữ; chế độ `coordinate sheet` (§2.2) là ngoại lệ có chủ đích — cả bộ + typography editorial, KHÔNG đem rembg. Dùng cho cột item card và ảnh bìa bộ phối trong HyperFrames.
---

# Item Cutout Prompter — Flat-Lay Plate & Coordinate Sheet

Mục đích: biến ảnh **lifestyle có người mẫu** (ảnh Shopee) thành ảnh **chỉ có món đồ trên nền trơn**,
để `scripts/cutout_items.py` tách nền bằng `rembg` (model u2net **general**, không phải human_seg).
Đường `coordinate sheet` (§2.2) là **deliverable có typography** — không đi qua bước matting này.

```text
ảnh Shopee lifestyle ──▶ [skill này] ──▶ item_plate.png ──▶ rembg ──▶ item_cutout.png (alpha)
```

Skill có **hai đường ra**, đừng lẫn:

| Đường | Dùng cho | Qua rembg? | Chữ trong pixel? |
| :--- | :--- | :--- | :--- |
| **Plate** — `top` / `bottom` / `full_set` (§2.1, §3.1–3.2) | card sản phẩm, layer dựng phim | Có (trừ `full_set`) | **Không** |
| **Sheet** — `coordinate sheet` (§2.2, §3.4) | ảnh bìa, gallery, social, reference cho designer | **Không bao giờ** | **Bắt buộc** |

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
- Riêng `coordinate sheet` (§2.2): ảnh phải thấy **cả bộ** — áo, quần, túi, giày — vì sheet
  không có chỗ cho món suy đoán.

Ảnh reference phải cho thấy **hình dáng thật và chất liệu vải**. Không dùng ảnh bị che khuất phần lớn
(ví dụ áo ngoài che gần hết áo trong) trừ khi chính món đó là món ngoài.

---

## 2. Nguyên tắc

**BẮT BUỘC:**

- Chỉ **một** món đồ, chính giữa khung, chiếm 60–80% diện tích — **trừ khi** người dùng
  chọn phạm vi `full_set` (§2.1) hoặc gọi đích danh `coordinate sheet` (§2.2). Mặc định vẫn là một món.
- Nền **trơn tuyệt đối** — màu trắng hoặc xám nhạt đồng nhất, không gradient mạnh, không bóng đổ phức tạp.
- Ánh sáng phẳng, đều (flat even lighting) để giữ đúng màu vải.
- Phom dáng giữ **đúng** như ảnh reference: cùng cổ áo, cùng độ dài, cùng chi tiết (nơ, ren, dây).
- Món đồ được "trải phẳng" (flat-lay) hoặc treo trên móc (ghost mannequin) — chọn **một** kiểu và nói rõ.

**CẤM TUYỆT ĐỐI** (áp dụng cho **plate**; sheet §2.2 bỏ đúng hai dòng "Chữ / UI" và "Ghép"):

| Nhóm | Từ khoá cấm |
| :--- | :--- |
| Người | `model`, `person`, `woman`, `mannequin with face`, `hands`, `arms wearing`, `body`, `skin` |
| Bối cảnh | `cafe`, `street`, `outdoor`, `room`, `furniture`, `plants`, `background scenery` |
| Chữ / UI | `text`, `label`, `price tag`, `logo`, `watermark`, `banner`, `brand name` |
| Ghép | `collage`, `multiple items`, `grid`, `outfit set on a model`, `two pieces worn together` |

Nếu sản phẩm là **set nhiều món**, tạo **nhiều ảnh riêng**, mỗi ảnh một món. Không ghép chung,
trừ `full_set` (§2.1) và `coordinate sheet` (§2.2).

### 2.1 Phạm vi (`item_scope`) — chọn món nào lên ảnh

Ảnh Shopee thường là **cả bộ trên người mẫu**. Không nói rõ món nào thì model tự chọn vật thể
nổi bật nhất — thực tế luôn ra **chiếc áo** (nó chiếm nhiều diện tích và tương phản nhất), không
bao giờ ra quần. Vì vậy phạm vi là **bắt buộc**, không phải tuỳ chọn ngẫu nhiên.

| `item_scope` | Phải làm | Tuyệt đối không có |
| :-- | :-- | :-- |
| `top` | Chỉ món **mặc trên**: áo, camisole, cardigan, khoác | quần, váy, shorts |
| `bottom` | Chỉ món **mặc dưới**: quần, váy, shorts | áo, camisole, cardigan |
| `full_set` | **Cả bộ** trên một ảnh, các món xếp cạnh nhau không chồng lấn | người, bối cảnh, chữ |

Ngoại lệ `full_set`: bỏ quy tắc "một món" nhưng **giữ** các quy tắc còn lại (nền trơn, cấm
người, cấm chữ, giữ đúng phom/màu). Ảnh full-set **không đem tách nền** bằng `cutout_items` —
rembg coi cả cụm là một khối, alpha dính liền và không dùng được làm card. Dùng thẳng ảnh nền
trơn. Ngoại lệ thứ hai — `coordinate_sheet` — nằm ở §2.2.

Nếu không xác định được món theo phạm vi (ảnh ref chỉ có một món, hoặc món không nhìn thấy), hỏi
lại bằng cách chọn món **thấy rõ nhất trong khung** và nói rõ trong prompt điều đã chọn.

### 2.2 Chế độ `coordinate sheet` — cả bộ + typography (deliverable)

> [!WARNING]
> Đây là chỗ **duy nhất** được phép có chữ trong pixel. Nó cố tình phá hai luật của plate:
> "chỉ một món" và "cấm chữ". Chế độ này chỉ bật khi người dùng chọn phạm vi **Bộ phối**
> (`coordinate_sheet`) trên node ảnh sản phẩm, hoặc gọi đích danh *coordinate sheet* /
> *style board* / *bảng phối đồ*. Đừng tự chọn khi người dùng chỉ muốn ảnh sản phẩm — card
> cần alpha và không được dính chữ.

| | Plate (`top` / `bottom` / `full_set`) | Sheet (§2.2) |
| :-- | :-- | :-- |
| Số món | 1 (hoặc cả bộ rời, không chồng) | 2–6 món, xếp lớp có chủ đích |
| Chữ | Cấm tuyệt đối | **Bắt buộc**: title, số callout, label, `DETAIL`, `COLOR PALETTE` |
| Nền | Trơn, không chi tiết | Trơn, nhưng có grid + leader line + swatch |
| Đầu ra | Nguyên liệu cho rembg / layer dựng phim | Ảnh hoàn chỉnh (bìa, gallery, social) |
| rembg | Có (trừ `full_set`) | **Không bao giờ** — mask sẽ ăn cả chữ |
| First frame video | Được (plate mode) | **Không** — chữ dính pixel, không sửa/localize được |

**Bố cục bắt buộc** — khung dọc 2:3 (1:2 nếu cần nhiều khoảng trắng), lề 6–8% mỗi cạnh, không
cắt món nào:

| Vùng | Nội dung |
| :-- | :-- |
| Trên trái | Title serif display, chữ đen, letter-spacing rộng (`STYLE COORDINATE`) |
| Trên phải | `NO. <số>` cùng bộ serif, cỡ lớn |
| Cột giữa | Hero stack: áo trên → quần dưới (cạp nằm ngay dưới gấu áo) → giày dưới gấu quần |
| Phải ngang hông | Túi treo nghiêng 3/4, quai vòng lên, không đè lên đồ |
| Cột phải, nửa dưới | 3 ô `DETAIL` vuông, viền hairline, là **zoom của chính món đã vẽ** |
| Dưới trái | 5 swatch tròn, sáng → tối, swatch trắng có viền, caption `COLOR PALETTE` |

**Luật nội dung:**

- **Ghost mannequin, không phải flat-lay phẳng lì.** Quần áo giữ phom 3D như đang mặc (cổ dựng,
  tay áo có khối, ống quần có độ rủ) nhưng **không có thân**: không da, không tóc, không tay,
  không cổ chân. Đây là thứ giữ được silhouette mà flat-lay làm mất.
- **Callout đánh số theo thứ tự mặc**, không theo vị trí trên trang: 01 áo → 02 quần →
  03 phụ kiện → 04 giày. Số callout = số món, không thừa không thiếu.
- **Label tối đa 2 dòng, 2–4 từ, in hoa.** Nhét cả đoạn văn vào ảnh sẽ ra ký tự rác; model
  không có khả năng typeset.
- **Detail crop là zoom thật** của chính món trong ảnh (khoá cổ áo, hardware của túi, chỗ mài
  của denim) — không phải món mới, không có người trong ô crop.
- **Palette đúng 5 ô**, lấy từ reference, xếp sáng → tối. Swatch trắng **phải có viền**, nếu
  không nó biến mất trên nền trắng.
- **Không thêm món không có trong reference** (thắt lưng, dây chuyền, mũ, găng) — kể cả khi
  bố cục trông trống.

**Ba lỗi làm hỏng sheet** (phải chặn ngay trong prompt, đừng để model tự quyết):

1. **Negative của plate giết sheet.** `no text`, `no collage`, `no grid`, `no multiple items`
   trong negative sẽ xoá đúng thứ ta cần. Negative của sheet **phải bỏ 4 cụm đó**.
2. **Model "sửa" chi tiết lạ.** Keyhole hở, gấu xẻ ngược, cạp trễ, ống loe — model có xu hướng
   làm chúng bình thường lại. Khoá bằng khối `FIDELITY LOCKS` (§3.4), mỗi món 1–2 khoá.
3. **Detail crop thành món thứ hai.** Không nói rõ "tight zoom of the same piece" thì model vẽ
   thêm một chiếc túi/áo mới trong ô `DETAIL`, và sheet thành collage sai.

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

### 3.4 Coordinate sheet — cả bộ + typography (`coordinate sheet`)

Điền theo thứ tự: **nhìn reference → tả đúng thứ thấy → mới khoá chi tiết**. Bốn khối bắt buộc:

- `OUTFIT` — 5 dòng: Overall / Upper body / Lower body / Sleeves and materials / Accessories.
  Mỗi dòng là quan sát, không phải lời quảng cáo: phom, chiều dài, chất liệu, màu chính xác.
- `FIDELITY LOCKS` — 3–6 chi tiết "lạ" mà model dễ sửa sai (khe hở, xẻ gấu, cạp trễ, hardware).
- `DO NOT ADD` — món không có trong reference, kể cả phụ kiện nhỏ.
- `TYPE & LIGHT` — 2 typeface, 3 chất liệu đọc được, ánh sáng high-key.

Ba ô `DETAIL` phải chọn **ba chi tiết đặc trưng nhất**, không phải ba góc chụp. Palette 5 màu
lấy từ reference, đặt tên ngắn (`off-white`, `washed grey-blue`, `glossy black`…).

```text
Editorial fashion coordinate sheet, vertical 2:3 portrait, seamless pure white studio background. The outfit is presented as a ghost-mannequin flat-lay: every garment holds the three-dimensional shape it would have on a body, while the body itself is completely absent — no skin, no face, no hair, no hands, no limbs, no feet anywhere in the frame.

LAYOUT
- Top left: "<SHEET TITLE>" in a high-contrast fashion serif, black, wide letter-spacing.
- Top right: "NO. <NUMBER>" in the same serif at display size.
- Centre column, stacked top to bottom with small even gaps: <TOP GARMENT>, then <BOTTOM GARMENT> with its waistband directly under the top's hem, then <SHOES> placed neatly below the hems, toes angled slightly outward, heels just tucked under the fabric so they read as the base of the silhouette.
- Right of the waist: <ACCESSORY> hanging at a slight three-quarter angle, strap arcing upward, fully visible, not covering the garments.
- Callouts: exactly <N> hairline leader lines in light grey, each starting with a small dot on the garment and ending in a two-digit serif numeral with a slash — 01 /, 02 /, 03 /, 04 / — extend to 0N or drop the unused numbers so the count matches the pieces exactly. Each number is followed by a two-line uppercase sans-serif label in mid-grey: 01 <TOP LABEL>, 02 <BOTTOM LABEL>, 03 <ACCESSORY LABEL>, 04 <SHOES LABEL>. Numbers follow the order of dressing, not their position on the page.
- Right column, lower half: three stacked square detail crops with thin grey borders, each captioned "DETAIL" in small uppercase sans-serif above it: <DETAIL 1>, <DETAIL 2>, <DETAIL 3>. Each crop is a tight zoom of one of the pieces already shown — same fabric, same colour, same hardware — never a new item.
- Bottom left: five equal circles in a row, ordered light to dark — <SWATCH 1>, <SWATCH 2>, <SWATCH 3>, <SWATCH 4>, <SWATCH 5> — the lightest one drawn with a hairline outline so it stays visible on white; caption "COLOR PALETTE" in small uppercase sans-serif below.

OUTFIT
Overall: <SILHOUETTE + FABRIC + COLOUR ARRANGEMENT, ONE SENTENCE>.
Upper body: <GARMENT, FIT, NECKLINE, CLOSURE, HEM, ANY CUTOUT>.
Lower body: <GARMENT, RISE, WASH, POCKETS, FLY, HEM WIDTH>.
Sleeves and materials: <SLEEVE SHAPE + CUFFS + THE THREE FABRICS>.
Accessories: <BAG, HARDWARE, STUDS, SHOES>. No other accessory is present.

FIDELITY LOCKS — these must survive unchanged: <LOCK 1>; <LOCK 2>; <LOCK 3>; <LOCK 4>.
DO NOT ADD: <THINGS NOT PRESENT IN THE REFERENCE>.

TYPE & LIGHT
Two typefaces only: the fashion serif for title, issue number and callout numerals; a thin geometric sans-serif uppercase for every label. All type is black or mid-grey, never coloured, never outlined, never inside a card. Flat high-key softbox lighting, one soft contact shadow directly under each piece, no gradient on the background, no coloured cast. Materials must read true: <FABRIC 1>, <FABRIC 2>, <FABRIC 3>. Photorealistic e-commerce editorial, 8k, sharp edge to edge.

Negative: no person, no model, no mannequin body, no dress form, no torso, no neck, no face, no head, no hair, no hands, no arms, no legs, no skin, no feet, no hanger, no clothes rail, no street, no car, no interior, no props, no price tag, no brand logo, no watermark, no extra garments, no duplicated pieces, no overlapping garments in the hero stack, no cropped hero pieces, no warped lettering, no misspelled words, no gibberish text, no long paragraphs, no coloured typography, no drop-shadowed text.
```

### 3.5 Ví dụ đã điền — mức chi tiết kỳ vọng

Bộ Y2K: áo keyhole trắng + jean ống loe cạp trễ + túi đen stud + giày nhọn đen. Đây là **phần
`OUTFIT` + khoá**; layout giữ nguyên theo §3.4.

```text
OUTFIT
Overall: fitted white keyhole shirt over low-rise faded grey-blue wide-leg jeans — contoured above the waist and flared through the leg, finished with a black studded shoulder bag and black pointed-toe heels.
Upper body: crisp white fitted short-sleeve collared shirt with cap sleeves, a vertical teardrop keyhole cut open at the centre chest, small buttons closing the bust, and a hem that splits open at the bottom in an inverted V.
Lower body: low-rise wide-leg jeans in washed grey-blue denim with heavy fading across the thighs, classic five-pocket styling, belt loops, a fastened front button, a closed zip fly and wide flared hems.
Sleeves and materials: slightly puffed cap-length sleeves with fitted cuffs; crisp cotton poplin, faded vintage-wash denim, glossy black leather.
Accessories: black leather shoulder bag with patch pockets, metallic buckles and silver-tone studs; black pointed-toe heeled shoes below the hems. No necklace, belt, hat or gloves.

FIDELITY LOCKS: keep the chest keyhole open and teardrop-shaped; keep the inverted-V split at the shirt hem; keep the waistband low-rise and the leg wide and flared; keep the bag's studs and buckles on the front panel.
DO NOT ADD: belt, necklace, hat, gloves, visible underwear, extra jewellery.
```

---

## 4. Output format

Trả về **chỉ một khối code** chứa prompt tiếng Anh:

````text
```text
<plate prompt | coordinate sheet prompt>
```
````

Nếu script yêu cầu nhiều món, trả về nhiều khối code, mỗi khối một món, theo đúng thứ tự `item.id`.

**Mỗi món chỉ một ảnh — mặt trước.** Thẻ sản phẩm trên timeline hiện 2–3s và thường bị chữ che;
sinh thêm ảnh lưng là credit không đổi lại được gì. Đừng đề xuất phương án mặt sau.

Chế độ `coordinate sheet` cũng trả về **một** khối duy nhất. Ảnh đó là deliverable: **không** đưa
vào `cutout_items`, **không** dùng làm first frame. Nếu sheet xuất hiện trong video thì chữ đã nằm
trong pixel — muốn sửa hoặc localize phải sinh lại ảnh.

---

## 5. Tiêu chí nghiệm thu

### 5.1 Plate (trước khi chạy rembg)

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

### 5.2 Coordinate sheet (deliverable — **không** rembg)

- [ ] Đủ **N callout**, số `01`…`0N` theo thứ tự mặc, mỗi số có label 2–4 từ in hoa.
- [ ] Hero stack đủ món, không cắt, không món nào che silhouette món khác (giày được thò dưới gấu).
- [ ] Không người: không mặt, tóc, tay, cổ chân, không bóng người.
- [ ] 3 ô `DETAIL` là zoom của **chính** món đã vẽ — không món mới, không người trong ô.
- [ ] Đúng 5 swatch sáng → tối, swatch trắng có viền, caption `COLOR PALETTE`.
- [ ] Chữ đọc được, không gibberish. Sai chính tả → **sinh lại ảnh**, không retouch tay.
- [ ] `FIDELITY LOCKS` còn nguyên: khe hở ngực, gấu xẻ, cạp trễ, ống loe, hardware của túi.
- [ ] Nền trắng sạch, không gradient, không bóng đổ lạ.

Sheet trượt vì chữ → **giảm số label và độ dài label**, đừng thêm mô tả. Model không typeset được
đoạn văn, và càng nhiều chữ càng dễ ra ký tự rác.
