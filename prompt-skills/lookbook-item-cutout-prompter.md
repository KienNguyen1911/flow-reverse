---
name: Coordinate Sheet (Lookbook Board)
description: Sinh prompt dựng **coordinate sheet** — một ảnh bộ phối dọc 2:3 trên nền trơn, có ghost-mannequin, callout đánh số, 3 ô DETAIL và palette 5 màu. Đây là deliverable (ảnh bìa, gallery, social), KHÔNG phải ảnh plate: không đem rembg, không làm first frame video. Skill chỉ có đúng một đường ra này; ảnh plate flat-lay không còn thuộc phạm vi.
---

# Coordinate Sheet Prompter — Bảng phối đồ có typography

Mục đích: biến 1–3 ảnh **lifestyle có người mẫu** (ảnh Shopee) thành **một** ảnh bộ phối hoàn chỉnh,
có chữ, dùng làm bìa / gallery / social.

```text
ảnh Shopee lifestyle ──▶ [skill này] ──▶ coordinate_sheet.png
```

Ảnh ra là **deliverable cuối**, không phải nguyên liệu cho bước sau:

| Câu hỏi | Trả lời |
| :--- | :--- |
| Có chữ trong pixel? | **Bắt buộc** — title, callout `01`…`0N`, `DETAIL`, `COLOR PALETTE` |
| Qua `rembg` / `scripts/cutout_items.py`? | **Không bao giờ** — mask sẽ ăn cả chữ |
| Làm first frame video? | **Không** — chữ dính pixel, không sửa/localize được |

---

## 0. Vì sao dựng sheet thay vì cắt món từ ảnh lifestyle

Model tách nền phổ biến (`u2net_human_seg`) được huấn luyện cho **người**: chạy trên ảnh lifestyle
nó giữ nguyên cả người mẫu. Kể cả `u2net_cloth_seg` (chuyên tách quần áo) cũng chỉ ra *chiếc áo đang
mặc* — méo theo tư thế, thủng ở chỗ hở da, rác dưới gấu.

Sheet không cần tách gì: model **dựng lại** cả bộ trên nền trơn rồi tự đặt chữ lên. Vì vậy bước
matting không những không cần mà còn **phá** sheet — rembg coi chữ là một phần chủ thể và cắt mất.

---

## 1. Input

- 1–3 ảnh lifestyle của **đúng bộ đồ đó** (ảnh sản phẩm thật của người bán).
- Ảnh phải thấy **cả bộ** — áo, quần, túi, giày — vì sheet không có chỗ cho món suy đoán.
- Tên bộ phối (title) và số hiệu (`NO.`) nếu có.

Ảnh reference phải cho thấy **hình dáng thật và chất liệu vải**. Ảnh bị che khuất phần lớn (áo ngoài
che gần hết áo trong) sẽ làm sheet thiếu món — khi đó yêu cầu thêm ảnh, đừng đoán.

---

## 2. Nguyên tắc

### 2.1 Bố cục bắt buộc

Khung dọc 2:3 (1:2 nếu cần nhiều khoảng trắng), lề 6–8% mỗi cạnh, không cắt món nào:

| Vùng | Nội dung |
| :-- | :-- |
| Trên trái | Title serif display, chữ đen, letter-spacing rộng (`STYLE COORDINATE`) |
| Trên phải | `NO. <số>` cùng bộ serif, cỡ lớn |
| Cột giữa | Hero stack: áo trên → quần dưới (cạp nằm ngay dưới gấu áo) → giày dưới gấu quần |
| Phải ngang hông | Túi treo nghiêng 3/4, quai vòng lên, không đè lên đồ |
| Cột phải, nửa dưới | 3 ô `DETAIL` vuông, viền hairline, là **zoom của chính món đã vẽ** |
| Dưới trái | 5 swatch tròn, sáng → tối, swatch trắng có viền, caption `COLOR PALETTE` |

### 2.2 Luật nội dung

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

### 2.3 Ba lỗi làm hỏng sheet

Phải chặn ngay trong prompt, đừng để model tự quyết:

1. **Dán negative của ảnh plate.** `no text`, `no collage`, `no grid`, `no multiple items` xoá
   đúng thứ sheet cần. Negative của sheet **phải bỏ 4 cụm đó**.
2. **Model "sửa" chi tiết lạ.** Keyhole hở, gấu xẻ ngược, cạp trễ, ống loe — model có xu hướng
   làm chúng bình thường lại. Khoá bằng khối `FIDELITY LOCKS` (§3.1), mỗi món 1–2 khoá.
3. **Detail crop thành món thứ hai.** Không nói rõ "tight zoom of the same piece" thì model vẽ
   thêm một chiếc túi/áo mới trong ô `DETAIL`, và sheet thành collage sai.

---

## 3. Template prompt

### 3.1 Coordinate sheet

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

Negative: no person, no model, no mannequin body, no dress form, no torso, no neck, no face, no head, no hair, no hands, no arms, no legs, no skin, no feet, no hanger, no clothes rail, no street, no car, no interior, no props, no price tag, no extra garments, no duplicated pieces, no overlapping garments in the hero stack, no cropped hero pieces, no warped lettering, no misspelled words, no gibberish text, no long paragraphs, no coloured typography, no drop-shadowed text.
```

### 3.2 Ví dụ đã điền — mức chi tiết kỳ vọng

Bộ Y2K: áo keyhole trắng + jean ống loe cạp trễ + túi đen stud + giày nhọn đen. Đây là **phần
`OUTFIT` + khoá**; layout giữ nguyên theo §3.1.

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
<coordinate sheet prompt>
```
````

Không lời chào, không giải thích, không header dạng `[Prompt 1]`. Một bộ phối = một ảnh = một khối.

Ảnh đó là deliverable: **không** đưa vào `cutout_items`, **không** dùng làm first frame. Nếu sheet
xuất hiện trong video thì chữ đã nằm trong pixel — muốn sửa hoặc localize phải sinh lại ảnh.

---

## 5. Tiêu chí nghiệm thu

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

