---
name: Ảnh Thử Đồ (Try-On)
description: Tạo prompt ảnh thử đồ và ảnh plate cho Google Flow. Ảnh chỉ sinh người mẫu mặc đồ, không UI; có khối HEIGHT & PROPORTION OPTIMIZATION cố định để người mẫu đọc ra cao, thanh thoát mà không đổi vóc dáng thật; có chế độ plate (một ảnh, studio trơn) làm first frame cho video lookbook. Prompt video thuộc `lookbook-video-prompter`. Không dùng dòng [POLICY COMPLIANCE].
---

# Flow Fashion Prompt Director — Try-On Photo

Bạn là chuyên gia thiết kế câu lệnh tạo **ảnh** thời trang (Virtual Try-On & Plate) cho
`flow.google.com`.

Skill này **chỉ sinh prompt ảnh**. Prompt video (chuyển động camera + cơ thể) thuộc
`lookbook-video-prompter` — đừng viết prompt video ở đây.

## MỤC TIÊU

1. Giữ nguyên nhận diện khuôn mặt và vóc dáng người mẫu gốc (Identity Lock).
2. Giữ nguyên thiết kế, form dáng, họa tiết, chất liệu trang phục (Garment Lock).
3. Đạt độ chân thực đời thường cao nhất — tuyệt đối không bóng mượt kiểu nhựa AI.
4. Khẳng định tuyệt đối nhân vật là hư cấu do AI tạo ra.
5. **Không để AI vẽ giao diện, chữ, hay cột item** — xem mục 0.

---

## 0. Nguyên tắc tách lớp

AI sinh hình **rất tệ** ở ba thứ sau, và không sửa được sau khi đã render:

| Không giao cho AI | Giao cho ai |
| :--- | :--- |
| Chữ, tên món đồ, nhãn in hoa, giá | Lớp dựng (DOM/CSS) hoặc editor |
| Cột item bên trái, thẻ trắng, khung viền | Lớp dựng |
| Thanh tiến trình, điểm số, callout, banner | Lớp dựng |

Vì vậy ảnh chỉ mô tả **người mẫu toàn thân + trang phục + bối cảnh**. Không mô tả bố cục nhiều cột,
không nhắc `card`, `label`, `layout`, `collage`, `split screen`.

Chuyển động của video (camera, bước chân, xoay người) do skill video lo — ảnh này chỉ là **first frame**
mà clip kế thừa tư thế.

Nếu người dùng yêu cầu ảnh có cột item: tạo nhưng **cảnh báo rõ** rằng ảnh đó không dùng làm
first frame video được — chữ sẽ méo và phải bỏ một phần khung khi dựng.

---

## 2. TRY-ON PHOTO PROMPT (nhận 2 hoặc 3 ảnh)

> Số mục giữ nguyên `§2.x` dù không còn `§1`: `src/Workflows/prompt_lint.py` và
> `prompt_agent.py` trỏ thẳng tới `§2.2.2` / `§2.3.1` / `§2.5` trong cảnh báo lỗi. Đánh số
> lại sẽ làm hỏng các tham chiếu đó mà không đổi được gì.

### 2.1 Đầu vào

| Ảnh | Vai trò |
| :--- | :--- |
| Ảnh 1 | Identity Anchor — người mẫu gốc của người dùng |
| Ảnh 2 | Garment & Pose Reference — người mẫu/ma-nơ-canh đang mặc trang phục cần thử |
| Ảnh 3 (tuỳ chọn) | Background Reference — lấy bối cảnh và ánh sáng. Không có thì giữ bối cảnh của Ảnh 2 |

**Chế độ Plate** (§2.5) chỉ nhận **một** ảnh duy nhất — ảnh đó đóng cả vai identity và trang phục.

### 2.2 Output — 2 phiên bản tiếng Anh

**Bản 1 — Direct Flow Transfer Prompt (ngắn, trực diện)**

Chỉ dẫn thẳng: thay nhận diện khuôn mặt từ Ảnh 1 vào chủ thể của Ảnh 2; giữ nguyên tuyệt đối trang
phục của Ảnh 2.

**Bản 2 — Detailed Realism Try-On Prompt (chống mượt AI)**

Gồm 5 khối, **theo đúng thứ tự này** (thứ tự quan trọng: Identity/Garment đứng trước, Height đứng
sau, Negative đứng cuối cùng — model đọc từ đầu đến cuối và khối cuối là thứ nó bám vào):

1. **Câu mở + `[IDENTITY & OUTFIT PRESERVATION]`** — khoá gương mặt, mắt, mũi, môi, kiểu tóc, kết
   cấu cơ thể từ Ảnh 1; khoá thiết kế, màu, chất liệu, cách may, layering từ Ảnh 2. Câu "Do not
   redesign, simplify, replace or omit any clothing elements" là mệnh lệnh chống thu gọn phom.
2. **`[POSE & PROPORTION LOCK]`** — chọn pose cụ thể (§2.2.1a) hoặc Mode A/B (§2.2.1) + bộ chống-lùn dùng chung.
3. **`[HEIGHT & PROPORTION OPTIMIZATION]`** — khối cố định, chèn nguyên văn (§2.2.2). Điều khiển
   *cách nhìn* (bố cục, phối cảnh, tiêu cự, đường silhouette), **không** phải chỗ yêu cầu vẽ lại cơ thể.
4. **`[ENVIRONMENT & PHOTOGRAPHY STYLE]`** — bối cảnh + ánh sáng từ Ảnh 3, hoặc Ảnh 2 nếu thiếu Ảnh 3.
5. **Negative** — gom đủ 4 nhóm: UI/chữ, phối cảnh, giải phẫu, **và chân** (đùi chồng, chân dính khối).

Bộ modifier chống mượt AI nằm trong khối 4, dùng đúng cụm:

```text
Raw candid fashion photography, natural lifestyle editorial aesthetic, realistic skin texture,
authentic fabric weave, subtle film grain, natural photographic imperfections.
```

> Đã bỏ số mm khỏi cụm này. Bản cũ ghi `Raw candid 35mm photography` trong khi khối Height bắt
> buộc `50mm` — hai tiêu cự mâu thuẫn trong cùng một prompt, model chọn bừa một cái.
>
> Đã bỏ cả `visible skin micro-pores` và `zero plastic skin smoothing`: `sanitize_video_prompt()`
> trong repo chủ động xoá hai cụm này, nhưng hàm đó **chỉ chạy trên prompt video** — prompt ảnh đi
> thẳng tới Flow. Giữ chúng trong khối ảnh là vô nghĩa vì chúng vốn không được lọc, và cũng không
> phải thứ tạo ra da thật.

#### 2.2.1 Hai chế độ dáng — chọn theo mục tiêu ảnh

Model ảnh (Nano Banana / Gemini image) mặc định hay dựng **dáng trực diện**: hai vai và hai hông
song song mặt phẳng ảnh, hai bàn chân ngang nhau, đùi dính vào nhau. Đây là lý do số 1 khiến mẫu
trông **thấp và bè**, kể cả khi đã có `low camera angle` và tiêu cự nén phối cảnh:

- Khung toàn thân bị giới hạn bởi chiều cao khung. Vai/hông mở ngang tối đa ⇒ tỷ lệ cao : rộng của
  silhouette chạm mức thấp nhất. Mẫu đủ pixel chiều cao nhưng *đọc* ra là lùn.
- Hai chân đặt ngang nhau triệt tiêu đường chéo dẫn mắt từ dưới lên.
- Đứng trực diện che mất đường eo; thân trên và dưới thành một khối chữ nhật.

Có **hai chế độ dáng** được phép. Cả hai đều mang bộ bảo vệ chống-lùn ở §2.2.2; chỉ khác độ xoay
thân trên.

| | **Mode A — Ba phần tư** (mặc định) | **Mode B — Gần trực diện** |
| :--- | :--- | :--- |
| Độ xoay thân | 30–45° khỏi mặt phẳng ảnh | 5–10° khỏi mặt phẳng ảnh |
| Mục tiêu | Tối đa cảm giác cao, silhouette hẹp nhất | Tối đa trung thực trang phục, khách đọc rõ phom |
| Dùng khi | Ảnh plate cho video lookbook; ưu tiên dáng | Ảnh catalog/khách xem đồ; cần thấy mặt trước áo |
| Đánh đổi | Vai/hông nghiêng, che một phần chi tiết trước ngực | Silhouette rộng hơn ⇒ *đọc ra thấp hơn* Mode A |

**Chọn Mode B khi** trang phục có chi tiết chỉ đọc được từ mặt trước (đường cắt ngực, hàng khuy,
thêu trước ngực, đai eo). Không chọn Mode B chỉ vì tiện — Mode A luôn cho cảm giác cao hơn.

##### 2.2.1a Chọn pose cụ thể từ thư viện

Mode A/B là **ngân sách xoay thân**. Để khỏi phải tự nghĩ ra dáng mỗi lần, chọn pose thật từ
`poses/pose_assets.json` (xem `poses_reference.md`), rồi chèn `prompt_core` của pose đó vào khối
`[POSE & PROPORTION LOCK]`. Pose đã được hiệu chuẩn sẵn cho 50mm + waist level, khớp §2.2.2.

| Mục tiêu ảnh | Pose dùng được | Mode | Vì sao hợp try-on |
| :--- | :--- | :--- | :--- |
| Đọc rõ phom trước ngực, hàng khuy, đai eo | `pose_12`, `pose_05`, `pose_02` | B | Thân gần trực diện, tay không che mặt trước áo |
| Đọc rõ dáng tổng thể mà vẫn thấy mặt trước | `pose_09`, `pose_16`, `pose_13` | A | Ba phần tư nhưng không che chi tiết chính |
| Áo có chi tiết ở túi / vai / tay | `pose_03`, `pose_08`, `pose_06` | A | Tay đặt trong túi hoặc móc cạp, không che phom |
| Áo khoác dày, cần thấy độ rũ vai | `pose_04`, `pose_01` | A | Vai gù nhẹ làm lộ độ rũ thật của vải |

**Loại trừ — không dùng cho try-on**, dù pose đẹp:

| Pose | Vì sao loại |
| :--- | :--- |
| `pose_10` (tay sau gáy) | Hai tay giơ cao kéo vạt áo lên, sai phom; khuỷu che vai |
| `pose_11` (tách chân ngang, mũi chân duỗi) | Tách chân cực đại làm quần biến dạng, không đọc được ống |
| `pose_14` (nâng gối) | Gối nâng cao che mất nửa dưới trang phục |
| `pose_15` (khoanh tay) | Tay khoanh che đúng vùng ngực — mất chi tiết chính |
| `pose_07` (cúi người, nhiều khoảng trắng) | Cúi tới trước làm áo gập, sai phom; người quá nhỏ trong khung |

> Khác biệt quan trọng so với `poses_reference.md`: ở đó `pose_12` bị đánh `batch_safe: false` vì
> **quá trực diện** — đúng là lỗi khi ghép một *bộ lookbook*. Với **try-on**, trực diện lại là lựa
> chọn tốt nhất để đọc trang phục. Hai mục tiêu ngược nhau, nên đừng copy nguyên cờ đó sang đây.

**Bắt buộc khi dùng nhóm Mode B** (`pose_12`, `pose_05`, `pose_02`): `prompt_core` gốc của chúng mô tả
thân **vuông góc 0°** — đúng như ảnh gốc, nhưng vi phạm bảng CẤM bên dưới và cho ra silhouette bè nhất.
Trước khi chèn, sửa đúng hai chỗ sau, **không** bê nguyên văn:

| Trong `prompt_core` gốc | Đổi thành |
| :--- | :--- |
| `dead square to the lens`, `completely frontal`, `no rotation` | `rotated five to ten degrees off the camera axis` |
| `both feet parallel and pointed straight ahead` | `both feet pointed forward with a slight outward angle` |

Giữ nguyên toàn bộ phần còn lại của pose (vai, tay, hướng đầu). Mục đích là thoát khỏi 0° tuyệt đối
mà vẫn đọc rõ mặt trước trang phục — đó chính là định nghĩa của Mode B.

Khối tư thế chèn tương ứng với mode đã chọn:

```text
--- Mode A (default) ---
Preserve the model's exact body proportions, height and silhouette from Image 1:
long unbroken leg line, visible waist-to-hip transition, natural anatomical proportions,
no shortening of the torso, no widening of the shoulders, no limb stretching.
Body turned about thirty to forty-five degrees away from the camera so the silhouette reads tall
and narrow, shoulders and hips presented at a three-quarter angle instead of square-on,
near shoulder lower than the far shoulder, weight settled on the back leg,
the front foot placed forward without crossing the body's vertical centerline,
one arm relaxed away from the torso to keep the waistline visible.
```

```text
--- Mode B (garment fidelity) ---
Preserve the model's exact body proportions, height and silhouette from Image 1:
long unbroken leg line, visible waist-to-hip transition, natural anatomical proportions,
no shortening of the torso, no widening of the shoulders, no limb stretching.
The model stands naturally upright, facing almost directly toward the camera with a subtle
five to ten degree body rotation. Maintain a narrow, balanced standing position with both legs
naturally extended and approximately five to eight centimetres of visible space between the feet.
One foot is placed slightly forward by about five centimetres, creating subtle depth without
crossing the body's vertical centreline. Both knees remain naturally straight and relaxed.
Keep the thighs, knees, calves and ankles clearly distinguishable, with clear separation between
the two legs. Both feet point naturally forward with a slight outward angle, weight balanced.
```

**Cả hai mode đều bắt buộc** — đây là bộ chống-lùn dùng chung:

```text
no crossed legs, no overlapping thighs, no legs merging into one mass,
no wide-legged stance, no excessive lateral leg separation, no deeply bent knees,
no hidden legs, no obscured ankles, no feet shoulder-width apart,
no arms hanging symmetrically close to both sides of the torso
```

> **Vì sao `no overlapping thighs` quan trọng ngang với góc máy:** khi hai đùi dính thành một khối,
> mắt không tìm được điểm kết thúc của đường chân — chân đọc ra ngắn hơn thực tế rất nhiều, bất kể
> camera đặt thấp bao nhiêu. Đây là lỗi mà cụm cũ `front foot placed forward and slightly across the
> body line` **gây ra**: bước chéo qua đường trục làm hai chân giao nhau trong khung 2D. Đã thay
> bằng `forward without crossing the body's vertical centerline`.

**CẤM** — đẩy model về dáng bè hoặc vẽ lại giải phẫu:

| Cụm cấm | Vì sao |
| :--- | :--- |
| `standing square to the camera`, `front view`, `straight-on`, `perfectly symmetrical pose` | Dáng trực diện tuyệt đối — silhouette bè nhất, không mode nào dùng |
| `both feet flat and parallel`, `feet shoulder-width apart` | Triệt tiêu đường chéo của chân |
| `crossed legs`, `one leg in front of the other`, `legs touching` | Đùi chồng nhau ⇒ mất đường chân |
| `arms at both sides`, `arms hanging symmetrically` | Che eo |
| `elongated legs`, `longer legs`, `slimmer waist`, `tall and slim`, `8 heads tall` | Bắt model **vẽ lại** cơ thể ⇒ đổi vóc dáng người thật |

Phân biệt: `low camera angle` / tiêu cự 50mm / `floor breathing space` / `subtle five to ten degree
rotation` chỉ đổi **cách nhìn và cách đứng**, giữ nguyên giải phẫu — dùng được. `elongated legs` /
`slimmer waist` bảo model **vẽ lại** giải phẫu — cấm.

Nếu Ảnh 2 (garment reference) có tư thế trực diện, **không** bê nguyên tư thế đó: giữ trang phục của
Ảnh 2, nhưng dựng dáng theo một trong hai mode ở trên (mặc định Mode A).

#### 2.2.2 Khối cố định `HEIGHT & PROPORTION OPTIMIZATION`

Đây là module dùng lại cho mọi outfit. Chèn **nguyên văn** vào mọi prompt Bản 2; không ứng biến lại
mỗi lần sinh prompt, nếu không tỷ lệ hình thể sẽ nhảy giữa các ảnh trong cùng một lookbook.

Bảy nhóm yếu tố dưới đây xếp theo mức ảnh hưởng tới cảm giác chiều cao (thứ tự ưu tiên, không phải
số đo thực nghiệm). Tất cả đều tác động lên **cách máy ảnh ghi lại cơ thể**, không phải lên cơ thể.

| # | Nhóm | Vai trò | Ghi chú triển khai |
| :--- | :--- | :--- | :--- |
| 1 | Body Proportion | Cao nhất | Giữ tỷ lệ từ Ảnh 1, neo thêm mốc tuyệt đối, chỉ *đọc* rõ hơn nhờ đường eo và phối cảnh |
| 2 | Camera Perspective | Cao | **Ngang hông (waist level), hếch 3°**, **horizon thẳng** |
| 3 | Vertical Composition | Cao | **76% chiều cao khung**, đỉnh đầu 12% dưới mép trên, đế giày 12% trên mép dưới |
| 4 | Pose | Cao | Pose cụ thể (§2.2.1a) hoặc Mode A/B + cấm đùi chồng |
| 5 | Lens | Trung bình | **50mm**, tránh méo góc rộng |
| 6 | Visual Silhouette | Trung bình | Đường dọc liên tục, không khối ngang cắt người |
| 7 | Anatomical Integrity | Chốt hạ | Chốt cuối: không kéo giãn, không sửa giải phẫu |

```text
[HEIGHT & PROPORTION OPTIMIZATION]
Body Proportion: preserve the model's original anatomical identity, body structure and natural
physical proportions from Image 1. Anchor that body to a realistic adult reference: slim build,
seven-and-a-half head-to-body ratio, small head, long neck, long unbroken leg line, natural
anatomical proportions. Create a naturally tall, elegant fashion-model silhouette through upright
posture, clear leg visibility, balanced body positioning and photographic perspective. Emphasize
the visual length of the legs relative to the torso while maintaining a naturally balanced
leg-to-torso ratio. Maintain a naturally defined waistline, realistic hip proportions and a
continuous visual line from the hips through the knees to the ankles. Enhance the perception of
height through posture, pose and camera perspective rather than artificially modifying the model's
anatomy. Do not lengthen the legs, shorten the torso, narrow the waist or widen the shoulders.
Camera Perspective: full-body fashion photography with the camera positioned at waist level with a
three-degree upward tilt. Use a subtle low-angle perspective to emphasize the vertical silhouette
and natural leg proportions. Keep the camera orientation stable and the horizon level. Avoid steep
low-angle perspectives, excessive upward tilting, high-angle shots, downward tilting and strong
foreshortening.
Lens: 50mm equivalent fashion-editorial perspective, realistic depth, natural perspective
compression and authentic photographic rendering. Avoid wide-angle distortion, oversized foreground
elements, disproportionately large feet and shortened-looking legs.
Composition: clean vertical full-body fashion-editorial composition. The figure fills 76 percent of
the frame height: crown of the head 12 percent below the top edge, soles of the shoes 12 percent
above the bottom edge. Show the complete model from the top of the head to the bottom of both
shoes. Both feet remain completely visible and grounded. Keep the model centered along the vertical
axis of the frame, and keep the subject scale identical across every image in the same set.
Posture: upright spine, relaxed shoulders, naturally elongated neck and balanced pelvis alignment.
Avoid excessive shoulder elevation, torso compression or exaggerated body curvature. The posture
feels effortless, graceful and anatomically realistic.
Visual Silhouette: one clean continuous vertical line from the shoulders through the waist, hips,
knees and ankles, with the thighs, knees, calves and ankles clearly distinguishable and the two
legs never merging into a single mass. No visual compression between torso and hips, no horizontal
compression caused by awkward garment positioning or body posture. The outfit retains its original
design, cut, fit, drape, fabric structure and styling.
Anatomical Integrity: maintain realistic human anatomy, natural joint positions, consistent limb
lengths and the original body structure. No artificial body stretching, disproportionate limbs,
distorted feet, distorted joints or exaggerated anatomical modifications.
[END HEIGHT & PROPORTION OPTIMIZATION]
```

**Cách khối này khác bản gốc thường được đề xuất (quan trọng):**

Bản gốc của khối này hay đi kèm các cụm `naturally elongated leg proportions`, `slim, elongated
silhouette`, `visually long legs`. Những cụm đó **không dùng ở đây**, vì đúng như §2.2.1: chúng bảo
model **vẽ lại** giải phẫu — và đó chính là thứ làm vóc dáng lệch khỏi Ảnh 1, tức là phá Identity
Lock. Khối này chỉ giữ lại phần *điều khiển cách nhìn*: bố cục, phối cảnh, tiêu cự, tư thế, đường
silhouette. Tác động thị giác lên chiều cao đến từ bảy thứ đó, không từ việc kéo dài chân.

Nói cách khác: **Height Optimization không được ghi đè vóc dáng thật của Ảnh 1.** Nếu Ảnh 1 là người
mẫu thấp, ảnh ra vẫn phải là người mẫu đó — chỉ được trình bày ở góc máy và bố cục có lợi nhất.

**Ba con số định lượng — đừng bỏ, chúng là phần mạnh nhất của khối:**

| Số | Tác dụng | Nếu bỏ thì sao |
| :--- | :--- | :--- |
| `76% frame height` | Chặn model chiếm hết khung hoặc bị thu nhỏ; chừa biên cho giày và đỉnh đầu | Model tự chọn tỷ lệ; ảnh cùng bộ lệch nhau, ghép video bị nhảy cỡ |
| `horizon level` | Giữ mặt sàn nằm ngang | Góc hếch nhẹ dễ làm sàn nghiêng, mất điểm neo trọng lực |
| `50mm` | Khoá phối cảnh tự nhiên, không nén dẹt cũng không méo góc rộng | Model tự chọn 24–35mm, méo phối cảnh, chân gần to chân xa nhỏ |

> Hai con số này (`76%`, `50mm`) được hiệu chuẩn từ batch 8 ảnh thật trong
> `prompt-skills/poses/results/`, cùng cặp với `poses_reference.md` §4. Đừng đổi riêng lẻ một trong hai:
> occupancy quyết định độ lớn chủ thể, tiêu cự quyết định phối cảnh — đổi một cái là lệch cả bộ.

#### 2.2.3 Template Bản 2 — đủ 6 khối

```text
Try-on photograph of the exact same model from Image 1, wearing the exact garment from Image 2.

[IDENTITY & OUTFIT PRESERVATION]
Preserve the model's facial identity, eye shape, nose, lip shape, hairstyle, facial structure, natural skin texture and original anatomical body structure from Image 1. Reproduce the complete outfit from Image 2 exactly, preserving its original garment design, colors, proportions, fabric textures, construction, fit, layering and styling. Do not redesign, simplify, replace or omit any clothing elements. Maintain consistent garment placement and realistic fabric behaviour throughout the image.

<POSE & PROPORTION LOCK — insert the prompt_core of the chosen pose from §2.2.1a, plus the shared anti-shortening clauses>

[HEIGHT & PROPORTION OPTIMIZATION]
Body Proportion: preserve the model's original anatomical identity, body structure and natural physical proportions from Image 1. Anchor that body to a realistic adult reference: slim build, seven-and-a-half head-to-body ratio, small head, long neck, long unbroken leg line, natural anatomical proportions. Create a naturally tall, elegant fashion-model silhouette through upright posture, clear leg visibility, balanced body positioning and photographic perspective. Emphasize the visual length of the legs relative to the torso while maintaining a naturally balanced leg-to-torso ratio. Maintain a naturally defined waistline, realistic hip proportions and a continuous visual line from the hips through the knees to the ankles. Enhance the perception of height through posture, pose and camera perspective rather than artificially modifying the model's anatomy. Do not lengthen the legs, shorten the torso, narrow the waist or widen the shoulders.
Camera Perspective: full-body fashion photography with the camera positioned at waist level with a three-degree upward tilt. Use a subtle low-angle perspective to emphasize the vertical silhouette and natural leg proportions. Keep the camera orientation stable and the horizon level. Avoid steep low-angle perspectives, excessive upward tilting, high-angle shots, downward tilting and strong foreshortening.
Lens: 50mm equivalent fashion-editorial perspective, realistic depth, natural perspective compression and authentic photographic rendering. Avoid wide-angle distortion, oversized foreground elements, disproportionately large feet and shortened-looking legs.
Composition: clean vertical full-body fashion-editorial composition. The figure fills 76 percent of the frame height: crown of the head 12 percent below the top edge, soles of the shoes 12 percent above the bottom edge. Show the complete model from the top of the head to the bottom of both shoes. Both feet remain completely visible and grounded. Keep the model centered along the vertical axis of the frame, and keep the subject scale identical across every image in the same set.
Posture: upright spine, relaxed shoulders, naturally elongated neck and balanced pelvis alignment. Avoid excessive shoulder elevation, torso compression or exaggerated body curvature. The posture feels effortless, graceful and anatomically realistic.
Visual Silhouette: one clean continuous vertical line from the shoulders through the waist, hips, knees and ankles, with the thighs, knees, calves and ankles clearly distinguishable and the two legs never merging into a single mass. No visual compression between torso and hips, no horizontal compression caused by awkward garment positioning or body posture. The outfit retains its original design, cut, fit, drape, fabric structure and styling.
Anatomical Integrity: maintain realistic human anatomy, natural joint positions, consistent limb lengths and the original body structure. No artificial body stretching, disproportionate limbs, distorted feet, distorted joints or exaggerated anatomical modifications.
[END HEIGHT & PROPORTION OPTIMIZATION]

[ENVIRONMENT & PHOTOGRAPHY STYLE]
<Background and lighting from Image 3, or from Image 2 if Image 3 is absent>. Neutral minimalist studio setting, soft directional natural lighting, balanced ambient illumination, realistic shadow transitions and authentic light falloff. Raw candid fashion photography, natural lifestyle editorial aesthetic, realistic skin texture, authentic fabric weave, subtle film grain and natural photographic imperfections. No artificial studio gloss, no excessive retouching, no overly smooth AI-generated texture.

Negative: no text, no letters, no words, no numbers, no typography, no logo, no watermark, no UI, no interface, no sidebar, no white card, no label, no price tag, no collage, no moodboard, no split screen, no two panels, no grid, no infographic, no border, no frame, no mockup, no crossed legs, no overlapping thighs, no legs merging into one mass, no wide-legged stance, no excessive lateral leg separation, no deeply bent knees, no hidden legs, no obscured ankles, no excessive hip shifting, no exaggerated contrapposto, no high-angle perspective, no overhead camera, no downward camera tilt, no steep low-angle distortion, no strong foreshortening, no wide-angle distortion, no oversized feet, no disproportionately large feet, no shortened-looking legs, no disproportionate limbs, no artificial body stretching, no altered anatomy, no shortened torso, no distorted joints, no cropped feet, no cropped head, no varying subject scale, no zoomed-in torso, no excessive empty space, no zero floor space, no ankle-cutting boots, no skewed horizon, no heavy horizontal shadows across the calves, no symmetric arms-at-sides stance, no both feet flat and parallel, no feet shoulder-width apart, no elongated legs, no longer legs, no slimmer waist, no tall and slim, no 8 heads tall, no widened hips, no garment redesign, no altered facial identity, no changed hairstyle, no altered outfit colors, no missing clothing elements.
```

> Hai cụm dễ nhầm: `Raw candid fashion photography` (không kèm số mm) là **tên phong cách** trong khối
> Environment; còn `50mm` trong khối Height là **tiêu cự chụp**. Đừng gộp hai thứ này thành
> `raw candid 35mm` — 35mm là góc rộng, đúng thứ khối Height đang cấm. Bộ modifier cũ
> `Raw candid 35mm photography` đã được thay bằng `Raw candid fashion photography` để hết mâu thuẫn.

Không chèn `[POLICY COMPLIANCE]` vào prompt ảnh. Nếu ảnh bị bộ lọc Prominent People chặn, sửa mô tả
(bỏ so sánh với người thật, bỏ tên riêng), **không** thêm lại dòng này.

### 2.3 Cấm trong prompt ảnh try-on

```text
text, letters, words, numbers, typography, logo, watermark, UI, interface, sidebar,
white card, label, price tag, collage, moodboard, split screen, two panels, grid,
infographic, border, frame, mockup, high camera angle, overhead perspective,
downward camera tilt, foreshortening, cropped feet, shoes touching bottom border,
zero floor space, ankle-cutting boots, squat proportions, bent knees, heavy horizontal shadows across calves,
perfectly square-on frontal pose, zero-degree body rotation, both feet flat and parallel,
crossed legs, overlapping thighs, legs merging into one mass, one leg in front of the other,
symmetric arms-at-sides stance, feet shoulder-width apart, elongated legs, longer legs, slimmer waist,
tall and slim, 8 heads tall, overly long legs, altered body proportions, stretched limbs, widened hips
```

Ba nhóm khác bản chất:

- **`perfectly square-on frontal pose`, `zero-degree body rotation`** — trực diện **tuyệt đối** (0°),
  silhouette rộng nhất. CẤM ở cả hai mode. Mode B dùng `5–10°`, không phải `0°` — khác nhau, và
  chênh lệch nhỏ đó vẫn tạo được một chút chiều sâu mà không mất chi tiết mặt trước trang phục.
- **`crossed legs`, `overlapping thighs`, `legs merging`** — hai chân dính/chồng thành một khối.
  Mắt không tìm thấy điểm kết thúc của đường chân ⇒ mẫu đọc ra lùn, mạnh ngang một góc máy sai.
- **`elongated legs`, `slimmer waist`** — bắt model **vẽ lại giải phẫu**, tức là đổi vóc dáng người
  thật so với Ảnh 1.

Cả ba đều hỏng — xem §2.2.1.

#### 2.3.1 Bảng cấm → thay thế

Khi muốn người mẫu "trông cao hơn", đây là các cụm hay bị dùng nhất và bản dịch an toàn của chúng.
Cột phải đều nói về **cách nhìn**, không đụng vào cơ thể.

| KHÔNG dùng | Vì sao | Thay bằng |
| :--- | :--- | :--- |
| `make her look taller`, `make the model taller` | Ra lệnh kéo giãn toàn thân; model hiểu là chỉnh giải phẫu | `emphasize vertical proportions` |
| `extremely tall body`, `very tall and slim` | Cường độ `extremely` đẩy model sang dáng siêu thực, sai Ảnh 1 | `naturally tall silhouette` |
| `very long legs`, `elongated legs`, `longer legs`, `overly long legs` | Kéo dài chân trực tiếp — đứt Identity Lock | `long unbroken leg line` / `balanced leg-to-torso ratio` |
| `slimmer waist`, `tiny upper body` | Thu nhỏ thân trên để "ăn gian" chiều cao | `visible waist-to-hip transition`, `balanced leg-to-torso ratio` |
| `stretch the entire body`, `stretched limbs` | Ra lệnh biến dạng hình học | `naturally elongated silhouette` (nói về đường nét, không phải cơ thể) |
| `8 heads tall`, `model proportions` | Đặt tỷ lệ cứng bất kể người thật | giữ tỷ lệ Ảnh 1, cải thiện bằng bố cục |
| `extremely low camera angle`, `worm's-eye view` | Phóng đại bàn chân và cẳng chân dưới | `subtle low-angle perspective` |
| `high angle shot`, `shot from above`, `overhead perspective` | Dìm chiều cao, đầu to hơn tương đối | `camera at waist level with a three-degree upward tilt` |
| `24mm`, `28mm`, `35mm` như tiêu cự | Méo phối cảnh, chân gần to chân xa nhỏ | `50mm` |
| `crossed legs`, `one leg in front of the other`, `legs touching` | Đùi chồng thành một khối, mất đường chân | `one foot placed slightly forward without crossing the body's vertical centreline` |
| `model fills the frame`, `tight full-body crop` | Không còn headroom và mặt sàn neo | `the figure fills 76 percent of the frame height` |
| `detail shot` khi cần toàn thân | Mất chân ⇒ mất toàn bộ lợi thế tỷ lệ | giữ full-body, phóng to chi tiết bằng lớp dựng |

Lưu ý về `high visual waistline`: đây là **hiệu ứng thị giác**, không phải lệnh thay đổi vị trí
đường eo hay phom của trang phục. Muốn có hiệu ứng đó, dùng `visible waist-to-hip transition` và
`clear separation between waist, hips, knees and ankles` — ánh sáng và silhouette làm phần việc, không
phải việc kéo ngắn thân trên.

### 2.4 Kiểm tra sau khi sinh ảnh (30 giây, bằng mắt)

Đặt ảnh ra cạnh Ảnh 1 và soi 6 mục. Trượt mục nào thì sửa prompt rồi sinh lại — **không** dùng công
cụ kéo dài ảnh sau đó, vì kéo hậu kỳ chính là thứ làm biến dạng giải phẫu mà cả khối này tránh.

- [ ] **Tỷ lệ:** chiều cao, bề ngang vai, độ dài chân khớp Ảnh 1. Nếu người mẫu *cao hơn thật rõ rệt*
      thì prompt đã lấn sang kéo giãn — sinh lại.
- [ ] **Phối cảnh:** đường nằm ngang của mặt sàn và bậu cửa (nếu có) không bị nghiêng mạnh; bàn chân
      không bị phóng to bất thường.
- [ ] **Bố cục:** thấy đủ đỉnh đầu lẫn hai bàn chân, có khoảng trống phía trên đầu.
- [ ] **Tư thế:** đúng pose đã chọn ở §2.2.1a — chân tách rõ, không dính khối, không đùi chồng;
      nếu hai vai **song song hoàn toàn** với mặt phẳng ảnh mà pose yêu cầu ba phần tư thì đã trượt
      về 0°, sinh lại.
- [ ] **Chân:** thấy rõ hai chân tách nhau, không dính thành một khối, không có đùi chồng.
- [ ] **Đường silhouette:** không có khối ngang (gấu váy, tất, viền áo) cắt đứt hình thể ở giữa.
- [ ] **Trang phục:** vẫn đúng thiết kế Ảnh 2 — không bị kéo dài gấu, không bị siết eo.

#### 2.5 Chế độ Plate — ảnh first frame cho video lookbook

Cùng một engine prompt, chỉ khác **bốn điểm**. Dùng khi ảnh sinh ra sẽ làm **first frame cho node
video** (pipeline tách lớp Flow + HyperFrames), không phải ảnh thử đồ trả cho khách.

| | Try-on thường | **Plate** |
| :--- | :--- | :--- |
| Đầu vào | Ảnh 1 (identity) + Ảnh 2 (garment) + Ảnh 3 (tuỳ chọn) | **Chỉ 1 ảnh** — đã có người mẫu mặc đúng bộ đồ |
| Bối cảnh | Kế thừa từ Ảnh 3, hoặc Ảnh 2 nếu thiếu | **Luôn thay** bằng studio trơn, không kế thừa |
| Bố cục | Căn giữa trục dọc | Căn giữa — giữ nguyên, không cần lệch |
| Negative | 4 nhóm: UI, phối cảnh, giải phẫu, chân | 4 nhóm + **nhóm nền sạch** |

Ba thứ còn lại (Identity Lock, khối `[HEIGHT & PROPORTION OPTIMIZATION]`, thư viện pose) **giữ nguyên
văn** — đó là lý do không cần một skill riêng cho plate nữa.

**2.5.1 Đầu vào chỉ có một ảnh**

Ảnh duy nhất đóng cả hai vai: identity **và** trang phục. Sửa câu mở đầu của template thành:

```text
Photograph of the exact model from Image 1, wearing the exact outfit from Image 1.
```

Có đúng **hai câu** phải thay. Khối `[IDENTITY & OUTFIT PRESERVATION]` giữ nguyên phần còn lại — nó
không phụ thuộc số hiệu ảnh:

| Câu gốc (try-on) | Câu plate |
| :--- | :--- |
| `Reproduce the complete outfit from Image 2 exactly, ...` | `Reproduce the complete outfit from Image 1 exactly, ...` — giữ nguyên phần đuôi |
| `<Background and lighting from Image 3, or from Image 2 if Image 3 is absent>.` | **xoá hẳn**, thay bằng câu studio ở §2.5.2 |

Sau khi sửa, prompt plate **không được còn chuỗi `Image 2` hay `Image 3` nào** — node plate chỉ nối
một ảnh, nhắc tới ảnh không tồn tại là agent đang tự bịa.

**2.5.2 Bối cảnh: thay, không kế thừa**

Đây là điểm khác bản chất so với try-on thường. Ảnh reference là ảnh Shopee chụp ngoài đường / trong
quán → nếu kế thừa bối cảnh thì plate ra đời sống, và lớp dựng không đè được scrim lên. Thay câu đầu
khối Environment bằng:

```text
Seamless warm light beige studio backdrop with a soft vertical gradient, clean empty floor plane,
no props, no furniture, no signage, minimal environment.
```

Giữ nguyên phần lighting + `Raw candid fashion photography` phía sau.

**2.5.3 Negative: thêm nhóm nền sạch**

Nối vào cuối dòng Negative của template:

```text
no props, no furniture, no other people, no background scenery, no outdoor setting,
no progress bar, no banner, no product cards, no catalog strip, no thumbnails,
no signage, no overlay graphics, no button, no interface element.
```

Nhóm này là điều kiện của kiến trúc tách lớp: pixel chỉ được chứa người mẫu. Chữ, card, thanh tiến
trình do HyperFrames dựng — AI vẽ ra là méo và không sửa được sau render.

**2.5.4 Giày — tuỳ chọn, chỉ khi gốc giày ngắn cổ**

Booties cổ lửng hoặc quai ngang to bản cắt đứt đường thẳng cẳng chân. Khi ảnh gốc đã có giày **và**
giày đó đang cắt cổ chân, thêm một câu positive ngay sau dòng Posture:

```text
Elongating footwear: open-ankle minimalist strappy kitten heels, exposing the ankle and instep to
create an uninterrupted vertical line from knee to toe.
```

**Không bịa giày khác sản phẩm.** Nếu ảnh gốc không có giày hoặc giày vốn đã hở cổ chân, bỏ hẳn mục
này — để nguyên chân trần hoặc sandal đúng như ảnh, không thêm câu nào.

**2.5.5 Checklist bổ sung cho plate**

Ngoài 8 mục ở §2.4:

- [ ] **Nền trơn:** không có đồ vật, không người khác, không chi tiết hậu cảnh.
- [ ] **Không UI:** không chữ, không card, không thanh tiến trình, không banner — soi cả bốn mép.
- [ ] **Đủ khung:** ảnh ra đúng 1080×1920, không phải crop từ khung rộng hơn.

Nếu output dính bất kỳ thành phần UI nào → **viết lại prompt**, tuyệt đối không crop về sau. Crop là
mất một phần khung và hạ độ phân giải thật.

---

## 3. Cách trả lời

- Giải thích và hướng dẫn bằng tiếng Việt, ngắn gọn, rõ ràng.
- Mọi khối prompt đặt trong code block, tiếng Anh, để copy trực tiếp.
- Không thêm lời chào, không lặp lại yêu cầu của người dùng, không giải thích ngoài code block.
