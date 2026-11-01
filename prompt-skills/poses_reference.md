---
name: Pose Reference Library
description: Thư viện 16 pose lookbook đã trích xuất từ ảnh mẫu, mỗi pose là một bộ tham số kỹ thuật tiếng Anh (camera angle, focal length, weight distribution, limb placement, head & gaze) dùng làm dữ liệu mẫu để sinh prompt tạo ảnh. Dùng khi cần chọn pose cho ảnh người mẫu, giữ pose cố định và thay trang phục/bối cảnh, hoặc khi user nói "chọn pose", "lấy dáng trong thư viện", "tạo 8 ảnh 8 pose". Kèm khối [HEIGHT & PROPORTION OPTIMIZATION] đã hiệu chuẩn để chiều cao người mẫu đồng nhất giữa các ảnh trong cùng một bộ.
---

# Pose Reference Library

Thư viện pose cho pipeline lookbook. Mỗi pose là **một bộ tham số kỹ thuật độc lập với trang phục**: chỉ mô tả
dáng đứng, phân bổ trọng tâm, vị trí tay chân và hướng đầu/ánh mắt. Màu sắc, chất liệu, kiểu dáng quần áo
**không** thuộc về pose — đó là biến số truyền vào từ ảnh reference.

## 0. Nguồn dữ liệu

| File | Vai trò |
| :--- | :--- |
| `poses/pose_assets.json` | Nguồn sự thật, schema v2. 16 pose + `consistency_lock` + `validated_batches`. |
| `poses/*.jpg` | Ảnh mẫu gốc. Tên file trùng field `source_file` của từng pose. |
| `poses/results/*.jpg` | Ảnh sinh thử từ batch đã hiệu chuẩn. Dùng để đối chiếu khi sửa prompt. |

Cấu trúc file JSON:

```json
{
  "schema_version": 2,
  "consistency_lock": {
    "height_anchor": "[HEIGHT & PROPORTION OPTIMIZATION] ... [END HEIGHT & PROPORTION OPTIMIZATION]",
    "setting_lock": "...",
    "negative": "...",
    "why_50mm": "..."
  },
  "validated_batches": [{ "id": "batch_01_athleisure_8pose", "poses": ["..."], "result": "ok" }],
  "poses": [{ "id": "...", "prompt_core": "...", "batch_safe": true, "calibrated": true }]
}
```

Schema một pose:

```json
{
  "id": "pose_03_headphones_hands_in_pockets",
  "source_file": "3e6666b3...jpg",
  "vibe": "cảm giác chung của dáng",
  "camera": {
    "angle": "góc máy của ảnh gốc",
    "framing": "khoảng cách và cách cắt khung của ảnh gốc",
    "focal_length": "consistency_lock (50mm)",
    "source_focal_length": "35mm",
    "applies_to": "single-shot only; in a multi-image set the lock overrides this"
  },
  "weight_and_torso": { "weight": "", "shoulders": "", "torso": "", "hip_chest_rotation": "" },
  "limbs": { "right_hand": "", "left_hand": "", "legs": "", "stance_width": "" },
  "head_and_gaze": { "head": "", "gaze": "", "expression": "" },
  "prompt_core": "pose layer tiếng Anh, KHÔNG chứa focal length hay góc máy",
  "tags": ["..."],
  "batch_safe": true,
  "calibrated": true
}
```

**Quan trọng:** `prompt_core` chỉ chứa **pose layer**. Mọi thứ thuộc về ống kính và khung hình nằm trong
`consistency_lock`. Đây là thay đổi so với schema v1 — bản cũ nhét `35mm`/`85mm` vào cuối `prompt_core`, nên mỗi
ảnh trong bộ bị một tiêu cự khác nhau và người mẫu đọc ra cao thấp khác nhau.

`camera.angle` / `camera.framing` / `source_focal_length` giữ lại **chỉ để tra cứu ảnh gốc**. Khi dựng prompt
cho một bộ nhiều ảnh, chúng bị `consistency_lock` ghi đè.

## 1. Danh mục 16 pose

Cột "Trong bộ" cho biết pose có dùng được trong một set nhiều ảnh hay không.

| ID | Vibe ngắn | Góc gốc | Tiêu cự gốc | Điểm nhấn | Trong bộ |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `pose_01_slouchy_wall_lean` | dreamy, tựa tường, ưỡn lưng | eye-level → low nhẹ | 35mm | lưng ngả ra sau, một tay trong túi, tay kia giữ quai túi | có |
| `pose_02_hands_behind_back_schoolgirl` | dịu, rụt rè, catalogue | eye-level thẳng | 85mm | hai tay giấu sau lưng, chân khép chữ V vào trong | có |
| `pose_03_headphones_hands_in_pockets` | lạnh, streetwear, tai nghe | low hip-level | 35mm | hai tay trong túi áo, vai gù, đầu nghiêng | có (đã hiệu chuẩn) |
| `pose_04_glasses_slumped_nerd` | u ám, grunge 90s | eye-level thẳng | 50mm | lưng cong chữ C, cằm cúi, nhìn qua gọng kính | có |
| `pose_05_hoodie_kangaroo_pocket` | lười, deadpan | eye-level thẳng | 85mm | hai tay chung một túi kangaroo, chân rộng | có |
| `pose_06_boho_waistband_walk` | boho runway, đang bước | low hip-level | 35mm | hai tay móc cạp quần, chân sau bước chéo | có (đã hiệu chuẩn) |
| `pose_07_flatcap_hands_in_pockets` | trầm, indie, nhiều khoảng trắng | high nhẹ | 50mm | người nhỏ giữa khung, nghiêng tới trước, cằm cúi | có |
| `pose_08_open_cardigan_mid_step` | đời thường, bước tới camera | eye-level thẳng | 85mm | chân bước chéo, một tay trong túi | có |
| `pose_09_hand_on_hip_casual_frame` | tươi, catalogue | eye-level thẳng | 85mm | một tay chống hông, đường cong S, chân rộng | có (đã hiệu chuẩn) |
| `pose_10_hands_behind_head_sporty` | sporty Y2K, giãn cơ | eye-level thẳng | 50mm | hai tay sau gáy, khuỷu mở rộng, hở eo | có (đã hiệu chuẩn) |
| `pose_11_pointed_toe_plaid_overshirt` | grunge, mũi chân duỗi | eye-level → low nhẹ | 50mm | tách chân ngang, mũi chân duỗi, gót nhấc cao | có (đã hiệu chuẩn) |
| `pose_12_halter_cargo_power_stance` | power stance, đối kháng | low waist-level | 35mm | chân rộng hơn vai, tay buông, nhìn thẳng | **không** |
| `pose_13_sunglasses_thumbs_in_pockets` | off-duty, hông xệ | high nhẹ | 50mm | hai ngón cái móc túi, lưng trên gù | có (đã hiệu chuẩn) |
| `pose_14_leg_raised_on_boxes` | vui tươi, giữ thăng bằng | eye-level thẳng | 50mm | một gối nâng cao, một tay duỗi ngang | có |
| `pose_15_arms_crossed_bob` | clean-girl, khoanh tay | eye-level thẳng | 50mm | tay khoanh cao, chân bắt chéo mũi chân | có (đã hiệu chuẩn) |
| `pose_16_crossed_leg_piping_pullover` | preppy sạch, catalogue | eye-level thẳng | 85mm | chân bắt chéo, một tay trong túi quần | có (đã hiệu chuẩn) |

### 1.1 Vì sao `pose_12` bị loại khỏi bộ

`pose_12` cố tình **chính diện tuyệt đối**: hai tay buông song song, bàn chân song song, vai ngang bằng, hông
vuông góc. Đặt cạnh các pose xoay ba phần tư, nó luôn đọc ra "cứng" — đây chính là ảnh số 2 trong batch đầu bị
người dùng trả lại. Pose này vẫn dùng tốt **đơn lẻ** khi cần thần thái đối kháng.

Tương tự, `pose_05`, `pose_02` gần trực diện nhưng có tay giấu sau lưng nên vẫn tạo được silhouette bất đối xứng.
Chỉ `pose_12` là bất khả cứu.

## 2. Cách chọn pose

- Cần **chân dài, dáng thanh thoát** → pose có `source_focal_length` 35mm: `pose_01`, `pose_03`, `pose_06`.
  Nhưng nhớ: trong bộ nhiều ảnh, tiêu cự bị lock về 50mm, nên cái giữ được là **tư thế**, không phải ống kính.
- Cần **sạch, an toàn, dùng làm catalogue** → `pose_02`, `pose_05`, `pose_09`, `pose_16`.
- Cần **thần thái lạnh, không cần nhìn máy** → `pose_03`, `pose_04`, `pose_06`, `pose_07`, `pose_13`.
- Cần **năng lượng, chuyển động** → `pose_06`, `pose_08`, `pose_10`, `pose_14`.
- Cần **khoảng trắng lớn để đặt text/card** → `pose_07`, `pose_15`.
- Cần **nhấn phần eo/hông** → `pose_09`, `pose_10`, `pose_13`.

Khi ghép nhiều ảnh trong một bộ: **không lặp cùng một góc máy hai lần liên tiếp**, và trộn ít nhất một pose nhìn
thẳng máy với một pose nhìn đi chỗ khác.

## 3. Ghép pose với người mẫu và trang phục

Prompt hoàn chỉnh gồm bốn lớp, đúng thứ tự:

```text
[1] IDENTITY  - mô tả người mẫu, giữ nguyên từ ảnh reference
[2] GARMENT   - trang phục, giữ nguyên từ ảnh reference
[3] MACRO     - consistency_lock.height_anchor, chèn NGUYÊN VĂN
[4] POSE      - pose.prompt_core, chèn NGUYÊN VĂN
[5] SETTING   - consistency_lock.setting_lock + negative
```

Quy tắc bắt buộc:

- **Không thêm tiêu cự vào prompt riêng lẻ.** Tiêu cự đã nằm trong `MACRO`. Thêm `shot on 35mm` là tự phá lock.
- **Không đổi `camera.angle`** của pose khi dựng bộ. `MACRO` đã cố định góc ngang hông + tilt 3°.
- **Không trộn hai pose.** Lấy tay của pose A và chân của pose B thường tạo ra dáng bất khả thi về giải phẫu.
- Giữ nguyên `head_and_gaze` nếu muốn giữ đúng "thần thái" của ảnh gốc.

## 4. Khối macro (bắt buộc, chèn nguyên văn)

Đây là `consistency_lock.height_anchor` trong JSON. Dùng đúng chuỗi này, không viết lại:

```text
[HEIGHT & PROPORTION OPTIMIZATION]
Body Proportion: the same 168 cm tall adult woman, slim build, seven-and-a-half head-to-body ratio,
small head, long neck, long unbroken leg line, natural anatomical proportions. Preserve her original
anatomical identity and body structure from the reference image. Do not lengthen the legs, shorten
the torso, narrow the waist or widen the shoulders.
Camera Perspective: full-body fashion photography with the camera positioned at waist level and a
three-degree upward tilt. Keep the horizon level. Avoid steep low-angle perspectives, high-angle
shots, downward tilting and strong foreshortening.
Lens: 50mm equivalent fashion-editorial perspective, realistic depth, natural perspective
compression. Avoid wide-angle distortion and oversized foreground elements.
Composition: full body head to toe, the figure fills 76 percent of the frame height, crown of the
head 12 percent below the top edge, soles of the shoes 12 percent above the bottom edge. Both feet
remain completely visible and grounded. Identical camera distance and subject scale across the whole
set.
Posture: the pose described below is the only variable between images. Spine, shoulder and pelvis
alignment change with the pose, never with the camera.
Visual Silhouette: one clean continuous line from the shoulders through the waist, hips, knees and
ankles, with the thighs, knees, calves and ankles clearly distinguishable and the two legs never
merging into a single mass.
Anatomical Integrity: realistic human anatomy, natural joint positions, consistent limb lengths and
the original body structure. No artificial body stretching, disproportionate limbs, distorted feet,
distorted joints or exaggerated anatomical modifications.
[END HEIGHT & PROPORTION OPTIMIZATION]
```

Khối này là bản điều chỉnh của khối cùng tên trong `try-on-image-prompter.md`. Hai tham số đã đổi so với bản
try-on, có lý do:

| Tham số | Try-on | Pose library | Vì sao đổi |
| :--- | :--- | :--- | :--- |
| Tiêu cự | 70mm | **50mm** | Pose có tay giơ cao, gối nâng, chân tách ngang. 70mm nén các chi này vào thân và làm dáng đọc ra "dẹt". 50mm giữ được độ sâu của tư thế. |
| Occupancy | 82-85% | **76%** | 82-85% quá sát mép: `pose_14` (gối nâng cao) và `pose_11` (mũi chân duỗi) bị cắt gót. 76% chừa đủ biên cho mọi pose trong thư viện. |

## 5. Negative prompt dùng chung

```text
Negative: no square-on symmetric stance, no arms hanging straight down symmetrically, no parallel
feet, no varying subject scale, no cropped feet, no zoomed-in torso, no exaggerated limb elongation,
no legs merging into a single mass, no text, no graphics, no props, no other people.
```

## 6. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| :--- | :--- | :--- |
| Model to nhỏ khác nhau giữa các ảnh | Mỗi prompt một tiêu cự, hoặc thiếu câu occupancy | Chèn nguyên văn `MACRO`; chỉ đổi số `76` khi cần thu nhỏ/phóng to cả bộ |
| Chiều cao không đồng nhất | `preserve proportions` chỉ giữ tỉ lệ **tương đối**, không neo mốc tuyệt đối | Dùng `168 cm` + `seven-and-a-half head-to-body ratio` trong `Body Proportion` |
| Dáng bị trả về trực diện | Model tự cân bằng lại pose | Thêm vào negative: `no square-on symmetric stance` |
| Chân ngắn, người lùn | Đổi 50mm thành 85mm nhưng vẫn để camera cao | Không đổi tiêu cự; giữ cặp 50mm + waist level + tilt 3° |
| Bàn chân bị cắt | Occupancy quá cao | Hạ `76` xuống `72`; **không** sửa mô tả pose |
| Tay bị dính vào túi, mất ngón | Mô tả tay quá ngắn | Dùng đúng câu `prompt_core` gốc, thêm `visible thumb hooked over the pocket edge` |

## 7. Output format

Khi user yêu cầu chọn pose cho một bộ ảnh, trả về **bảng chọn trước**, rồi **prompt từng ảnh** trong khối code:

````text
| # | Pose ID | Lý do chọn |

```text
<ảnh 1 prompt>
```
````

Không giải thích ngoài khối code trừ bảng chọn ban đầu.
