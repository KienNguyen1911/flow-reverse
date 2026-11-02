---
name: Ảnh Thử Đồ (Try-On)
description: Tạo prompt ảnh thử đồ và ảnh plate cho Google Flow theo kiến trúc V2 (7 module, thứ tự ưu tiên rõ). Ảnh chỉ sinh người mẫu mặc đồ, không UI; giữ đúng nhận diện và tỷ lệ giải phẫu của Ảnh 1 thay vì áp một tỷ lệ đầu-thân cố định; có khối HEIGHT & PROPORTION OPTIMIZATION cố định để người mẫu đọc ra cao, thanh thoát mà không đổi vóc dáng thật; có chế độ plate (một ảnh, studio trơn) làm first frame cho video lookbook. Prompt video thuộc `lookbook-video-prompter`. Không dùng dòng [POLICY COMPLIANCE].
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
| Ảnh 3 (tuỳ chọn) | Background Reference — **chỉ** lấy bối cảnh và ánh sáng. Không có thì dùng studio trơn mô tả trong module 5 (không kế thừa bối cảnh Ảnh 2) |

**Chế độ Plate** (§2.5) chỉ nhận **một** ảnh duy nhất — ảnh đó đóng cả vai identity và trang phục.

### 2.2 Output — 2 phiên bản tiếng Anh

**Bản 1 — Direct Flow Transfer Prompt (ngắn, trực diện)**

Chỉ dẫn thẳng: thay nhận diện khuôn mặt từ Ảnh 1 vào chủ thể của Ảnh 2; giữ nguyên tuyệt đối trang
phục của Ảnh 2.

**Bản 2 — Detailed Realism Try-On Prompt (V2 — 7 module)**

Prompt gồm **7 module, theo đúng thứ tự này**. Thứ tự là thứ tự ưu tiên khi hai mục tiêu xung đột
với nhau — model đọc từ đầu đến cuối, module đứng trước thắng:

| # | Module | Mức | Kiểm soát điều gì |
| :--- | :--- | :--- | :--- |
| 1 | `[IDENTITY LOCK]` | Critical | Khuôn mặt, mắt, mũi, môi, tóc, da từ Ảnh 1. Không beautify, không làm thon mặt |
| 2 | `[GARMENT FIDELITY]` | Critical | Trang phục từ Ảnh 2: phom, màu, chất liệu, may, layering, branding có thật trên đồ |
| 3 | `[ANATOMY & POSE]` | High | Tỷ lệ cơ thể gốc, tư thế, hướng thân **và hướng đầu/mắt riêng** |
| 4 | `[HEIGHT & PROPORTION OPTIMIZATION]` | High | Cách máy ảnh ghi lại cơ thể: góc, khoảng cách, tiêu cự, bố cục, silhouette |
| 5 | `[ENVIRONMENT & LIGHTING]` | Medium | Bối cảnh + ánh sáng từ Ảnh 3 nếu có; không có thì studio mô tả sẵn |
| 6 | `[PHOTOGRAPHY AESTHETICS]` | Medium | Da thật, vân vải thật, film grain, phong cách editorial |
| 7 | `Negative` | Low | Chỉ những lỗi thật sự cần loại trừ, gom 5 nhóm, **không lặp lại module 1–6** |

Ba mục tiêu của một ảnh try-on, xếp theo mức ưu tiên khi phải hy sinh một cái:

1. **Identity consistency** — kết quả phải là đúng người trong Ảnh 1.
2. **Garment consistency** — đúng bộ đồ trong Ảnh 2.
3. **Anatomy consistency** — đúng vóc dáng thật, không kéo giãn.
4. **Presentation consistency** — tư thế, góc chụp, bố cục.

**Không hy sinh 1–3 để được một tư thế đẹp hơn.** Nếu pose trong thư viện (§2.2.1a) xung đột với
một trong ba mục tiêu đầu, đổi pose — không sửa cơ thể, không sửa trang phục.

Bộ modifier chống mượt AI nằm trong module 6, dùng đúng cụm:

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
trông **thấp và bè**, kể cả khi đã có `low camera angle` và khoảng cách máy nén phối cảnh:

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
`[ANATOMY & POSE]`. Pose đã được hiệu chuẩn sẵn cho 50mm + waist level, khớp §2.2.2.

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
Head turned gently back toward the camera on the neck, so the face stays readable while the torso
keeps its three-quarter angle; eyes toward the lens or just beside it, chin level.
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
Head facing the camera almost square-on, chin level, eyes to the lens or just beside it.
```

**Cả hai mode đều bắt buộc** — đây là bộ chống-lùn dùng chung, và là **chỗ duy nhất** trong prompt
khai báo tư thế chân. Không lặp lại các cụm này trong Negative:

```text
Natural stance: the two legs clearly separated and individually readable from hip to ankle, both
feet fully visible and grounded, knees relaxed rather than locked or deeply bent.
```

> **Vì sao `no overlapping thighs` (Negative, nhóm 3) quan trọng ngang với góc máy:** khi hai đùi
> dính thành một khối, mắt không tìm được điểm kết thúc của đường chân — chân đọc ra ngắn hơn thực tế
> rất nhiều, bất kể camera đặt thấp bao nhiêu. Đây là lỗi mà cụm cũ `front foot placed forward and
> slightly across the body line` **gây ra**: bước chéo qua đường trục làm hai chân giao nhau trong
> khung 2D. Đã thay bằng `forward without crossing the body's vertical centerline`.

**CẤM** — đẩy model về dáng bè hoặc vẽ lại giải phẫu:

| Cụm cấm | Vì sao |
| :--- | :--- |
| `standing square to the camera`, `front view`, `straight-on`, `perfectly symmetrical pose` | Dáng trực diện tuyệt đối — silhouette bè nhất, không mode nào dùng |
| `both feet flat and parallel`, `feet shoulder-width apart` | Triệt tiêu đường chéo của chân |
| `crossed legs`, `one leg in front of the other`, `legs touching` | Đùi chồng nhau ⇒ mất đường chân |
| `arms at both sides`, `arms hanging symmetrically` | Che eo |
| `elongated legs`, `longer legs`, `slimmer waist`, `tall and slim`, `8 heads tall`, `seven-and-a-half head-to-body ratio` | Bắt model **vẽ lại** cơ thể hoặc áp tỷ lệ không phải của Ảnh 1 |

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
| 1 | Body Proportion | Cao nhất | Giữ **đúng** tỷ lệ đầu-thân, chân-thân và chiều dài chi của Ảnh 1; **không** áp một tỷ lệ đầu-thân cố định. Chỉ *đọc* rõ hơn nhờ đường eo và phối cảnh |
| 2 | Camera Perspective | Cao | **Ngang hông (waist level), hếch 3°**, **horizon thẳng** |
| 3 | Vertical Composition | Cao | **76% chiều cao khung**, đỉnh đầu 12% dưới mép trên, đế giày 12% trên mép dưới |
| 4 | Pose | Cao | Pose cụ thể (§2.2.1a) hoặc Mode A/B + cấm đùi chồng |
| 5 | Lens | Trung bình | **50mm**, tránh méo góc rộng |
| 6 | Visual Silhouette | Trung bình | Đường dọc liên tục, không khối ngang cắt người |
| 7 | Anatomical Integrity | Chốt hạ | Chốt cuối: không kéo giãn, không sửa giải phẫu |

```text
[HEIGHT & PROPORTION OPTIMIZATION]
Body Proportion: preserve the exact head-to-body ratio, leg-to-torso ratio and limb lengths visible
in Image 1; that body is the only proportion reference. Convey height through upright posture,
clear leg separation, framing and camera distance, never through redrawn proportions. Do not
lengthen the legs, shorten the torso, narrow the waist, widen the shoulders or stretch the neck.
Camera Perspective: full-body fashion photography, camera at waist level with a three-degree
upward tilt, horizon level, and the same subject-to-camera distance across every image in the set.
Perspective is set by that distance: stand back far enough that the whole figure fits a
50mm-equivalent frame with natural scale from crown to sole. Avoid steep low angles, high angles,
downward tilt and strong foreshortening.
Lens: 50mm equivalent field of view as the aesthetic target; focal length alone does not compress
or elongate anything, so keep the camera distance constant and the feet never read oversized while
the legs never read shortened. No wide-angle distortion.
Composition: clean vertical full-body editorial composition. Crown of the head 12 percent below the
top edge, soles of the shoes 12 percent above the bottom edge, figure filling 76 percent of the
frame height. Both feet fully visible and grounded, model centred on the vertical axis of the frame,
subject scale identical across every image in the same set.
Posture: upright spine, relaxed shoulders, neck lengthened by posture rather than anatomy, balanced
pelvis. No forced shoulder elevation, torso compression or exaggerated body curvature.
Visual Silhouette: one continuous vertical line from the shoulders through the waist, hips, knees
and ankles, with thighs, knees, calves and ankles individually distinguishable and the two legs
never merging into one mass. No horizontal band from hem, sock line or waistband cuts the figure in
half. The outfit keeps its own design, cut, fit, drape and styling.
Anatomical Integrity: realistic joints, consistent limb lengths and the original body structure from
Image 1. No artificial body stretching, disproportionate limbs, distorted feet or distorted joints.
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
| `50mm` | Giữ một trường nhìn nhất quán giữa các ảnh; không nén dẹt cũng không méo góc rộng | Model tự chọn 24–35mm, méo phối cảnh, chân gần to chân xa nhỏ |

> Hai con số này (`76%`, `50mm`) được hiệu chuẩn từ batch 8 ảnh thật trong
> `prompt-skills/poses/results/`, cùng cặp với `poses_reference.md` §4. Đừng đổi riêng lẻ một trong hai:
> occupancy quyết định độ lớn chủ thể, còn trường nhìn + khoảng cách máy quyết định phối cảnh — đổi
> một cái là lệch cả bộ.

**`50mm` là hướng thẩm mỹ, không phải bộ bảo đảm tỷ lệ.** Nén phối cảnh do **khoảng cách
máy–chủ thể** quyết định, không do tiêu cự. Vì vậy khối này khoá thêm `same subject-to-camera
distance`; nếu chỉ ghi 50mm mà để model tự chọn khoảng cách, bàn chân vẫn có thể phóng to và chân
vẫn đọc ra ngắn. Hai biến phải đi cùng nhau.

**Occupancy cho ảnh bán trang phục (tuỳ chọn, chưa hiệu chuẩn):** `76%` là mức editorial đã
kiểm chứng. Khi ảnh chỉ để khách đọc phom đồ, có thể nâng lên `84–88%` để trang phục chiếm nhiều
pixel hơn. Đây là **lựa chọn cho cả bộ**, không phải cho từng ảnh — đổi giữa bộ là nhảy cỡ khi ghép
video. Chưa có batch kiểm chứng ở mức này, nên mặc định vẫn là `76%`.

#### 2.2.2a V2 đã bỏ gì khỏi khối Height (và vì sao)

Bản V1 neo thêm `seven-and-a-half head-to-body ratio` để "chắc chắn" người mẫu cao. Đó là mâu thuẫn
trực tiếp với `preserve the exact proportions from Image 1`: nếu Ảnh 1 là người 7 đầu, model phải
chọn giữa hai mệnh lệnh — và nó chọn cái nào cũng sai. Tỷ lệ đầu-thân **cố định** chỉ đúng khi người
mẫu là một nhân vật do mình định nghĩa (thư viện pose, xem `poses_reference.md` §4), không đúng khi
identity đến từ ảnh người dùng.

| V1 | V2 | Lý do |
| :--- | :--- | :--- |
| `seven-and-a-half head-to-body ratio` | bỏ hẳn | Xung đột với tỷ lệ thật của Ảnh 1 — Critical |
| `slim build`, `small head`, `long neck` | bỏ hẳn | Đây là mô tả một người khác, không phải người trong Ảnh 1 |
| `naturally tall ... silhouette` + `no tall and slim` | chỉ giữ vế "height through posture/framing/distance" | Positive và Negative đá nhau; một ý chỉ được nói một lần |
| `natural perspective compression` | `focal length alone does not compress` | 50mm không tạo nén phối cảnh; khoảng cách mới tạo |
| `Anatomically realistic posture` (tính từ chung) | mệnh lệnh cụ thể (spine, shoulders, pelvis) | Tính từ chung không điều khiển được gì |

Khối Height **giữ nguyên 7 nhóm** và 3 mốc định lượng, vì đó là phần đã hiệu chuẩn và là thứ test
canh. Chỉ nội dung bên trong đổi: bỏ áp đặt giải phẫu, giữ điều khiển cách nhìn.

#### 2.2.3 Template Bản 2 — đủ 7 module

```text
Try-on photograph of the exact same model from Image 1, wearing the exact garment from Image 2.

[IDENTITY LOCK]
Preserve the facial identity from Image 1 exactly: East Asian facial features, soft delicate eye shape, natural nose structure, natural lips, messy high bun with face-framing wispy strands, natural skin texture. Same person, same face, same age as Image 1. Do not beautify, slim, symmetrise or age the face, and do not change the hairstyle.

[GARMENT FIDELITY]
Reproduce the complete outfit from Image 2 exactly: <name each visible garment from Image 2 by category and colour — visible elements only>. Copy only what the reference shows: seams, weave, trims, hardware and branding that are physically part of the garment are reproduced; anything hidden behind the body, hair or another layer is not invented, extended or restyled. Where this description and Image 2 disagree, Image 2 wins. Do not redesign, simplify, replace, omit, recolour or re-proportion any element, and do not improve the outfit for the photograph.

[ANATOMY & POSE]
<insert the prompt_core of the chosen pose from §2.2.1a, or the Mode A / Mode B block, plus the shared stance clause>
Head turned gently back toward the camera on the neck so the face stays readable while the torso keeps its angle; chin level, eyes to the lens or just beside it.

[HEIGHT & PROPORTION OPTIMIZATION]
Body Proportion: preserve the exact head-to-body ratio, leg-to-torso ratio and limb lengths visible in Image 1; that body is the only proportion reference. Convey height through upright posture, clear leg separation, framing and camera distance, never through redrawn proportions. Do not lengthen the legs, shorten the torso, narrow the waist, widen the shoulders or stretch the neck.
Camera Perspective: full-body fashion photography, camera at waist level with a three-degree upward tilt, horizon level, and the same subject-to-camera distance across every image in the set. Perspective is set by that distance: stand back far enough that the whole figure fits a 50mm-equivalent frame with natural scale from crown to sole. Avoid steep low angles, high angles, downward tilt and strong foreshortening.
Lens: 50mm equivalent field of view as the aesthetic target; focal length alone does not compress or elongate anything, so keep the camera distance constant and the feet never read oversized while the legs never read shortened. No wide-angle distortion.
Composition: clean vertical full-body editorial composition. Crown of the head 12 percent below the top edge, soles of the shoes 12 percent above the bottom edge, figure filling 76 percent of the frame height. Both feet fully visible and grounded, model centred on the vertical axis of the frame, subject scale identical across every image in the same set.
Posture: upright spine, relaxed shoulders, neck lengthened by posture rather than anatomy, balanced pelvis. No forced shoulder elevation, torso compression or exaggerated body curvature.
Visual Silhouette: one continuous vertical line from the shoulders through the waist, hips, knees and ankles, with thighs, knees, calves and ankles individually distinguishable and the two legs never merging into one mass. No horizontal band from hem, sock line or waistband cuts the figure in half. The outfit keeps its own design, cut, fit, drape and styling.
Anatomical Integrity: realistic joints, consistent limb lengths and the original body structure from Image 1. No artificial body stretching, disproportionate limbs, distorted feet or distorted joints.
[END HEIGHT & PROPORTION OPTIMIZATION]

[ENVIRONMENT & LIGHTING]
If Image 3 is provided: take only the space, surfaces, ambient light and shadow behaviour from it — never the person or the garment from Image 3. If Image 3 is not provided: clean minimalist studio with a curved white cyclorama wall and floor, bright soft directional window-pane daylight casting gentle diagonal shadows across the wall and floor plane, realistic light falloff.

[PHOTOGRAPHY AESTHETICS]
Raw candid fashion photography, natural lifestyle editorial aesthetic, realistic skin texture with visible pores and fine facial hair, authentic fabric weave, subtle film grain, natural photographic imperfections. No plastic skin, no HDR glow, no over-sharpening, no AI-smooth texture.

Negative: no altered facial identity, no changed hairstyle, no different face, no plastic or airbrushed skin; no garment redesign, no simplified, recoloured or re-proportioned garment, no missing or added clothing elements, no floating or merged fabric layers, no branding beyond what the reference garment actually carries; no elongated legs, no longer legs, no stretched limbs, no artificial body stretching, no slimmed waist, no widened shoulders, no distorted joints, no distorted or extra feet, no crossed legs, no overlapping thighs, no legs merging into one mass; no high-angle or overhead framing, no steep low-angle distortion, no wide-angle distortion, no oversized feet, no cropped head, no cropped feet, no tilted horizon, no inconsistent subject scale, no zoomed-in torso; no text, no letters, no numbers, no added logos, no watermark, no UI, no card, no label, no price tag, no collage, no split screen, no grid, no border, no frame.
```

> Ba chỗ điền trong template:
>
> - `<name each visible garment ...>` — agent đọc Ảnh 2 rồi liệt kê **món nhìn thấy được** (áo, váy,
>   tất, giày). Không suy diễn lớp bên trong bị che, không tự thêm chi tiết cho đẹp.
> - `<insert the prompt_core ...>` — pose thật từ §2.2.1a, hoặc block Mode A/B nếu không dùng thư viện.
> - `Image 3` — nếu node chỉ nối hai ảnh, bỏ hẳn câu "If Image 3 is provided" và giữ câu studio.
>   Câu về Ảnh 3 chỉ được nói **môi trường**, không được nói người hay trang phục.

> Hai cụm dễ nhầm: `Raw candid fashion photography` (không kèm số mm) là **tên phong cách** trong
> module Aesthetics; còn `50mm` trong khối Height là **tiêu cự chụp**. Đừng gộp hai thứ này thành
> `raw candid 35mm` — 35mm là góc rộng, đúng thứ khối Height đang cấm. Bộ modifier cũ
> `Raw candid 35mm photography` đã được thay bằng `Raw candid fashion photography` để hết mâu thuẫn.
>
> **Logo:** Negative cấm `added logos` — tức logo bịa thêm — chứ không cấm logo **có thật trên trang
> phục tham chiếu**. V1 cấm tuyệt đối `no logo`, trong khi module Garment lại đòi chép đúng mọi chi
> tiết; nếu đôi giày trong Ảnh 2 có logo đặc trưng thì hai mệnh lệnh đá nhau và model tự bỏ logo.
> Cùng lý do, `no ankle-cutting boots` đã bị bỏ: giày nào là do Ảnh 2 quyết định, không phải prompt.

Không chèn `[POLICY COMPLIANCE]` vào prompt ảnh. Nếu ảnh bị bộ lọc Prominent People chặn, sửa mô tả
(bỏ so sánh với người thật, bỏ tên riêng), **không** thêm lại dòng này.

### 2.3 Cấm trong prompt ảnh try-on

```text
text, letters, words, numbers, typography, added logo, invented branding, watermark, UI,
interface, sidebar, white card, label, price tag, collage, moodboard, split screen,
two panels, grid, infographic, border, frame, mockup, high camera angle, overhead perspective,
downward camera tilt, foreshortening, cropped feet, shoes touching bottom border,
squat proportions, bent knees, heavy horizontal shadows across calves,
perfectly square-on frontal pose, zero-degree body rotation, both feet flat and parallel,
crossed legs, overlapping thighs, legs merging into one mass, one leg in front of the other,
symmetric arms-at-sides stance, feet shoulder-width apart, elongated legs, longer legs, slimmer waist,
tall and slim, 8 heads tall, seven-and-a-half head-to-body ratio, overly long legs,
altered body proportions, stretched limbs, widened hips
```

Bốn nhóm khác bản chất:

- **`perfectly square-on frontal pose`, `zero-degree body rotation`** — trực diện **tuyệt đối** (0°),
  silhouette rộng nhất. CẤM ở cả hai mode. Mode B dùng `5–10°`, không phải `0°` — khác nhau, và
  chênh lệch nhỏ đó vẫn tạo được một chút chiều sâu mà không mất chi tiết mặt trước trang phục.
- **`crossed legs`, `overlapping thighs`, `legs merging`** — hai chân dính/chồng thành một khối.
  Mắt không tìm thấy điểm kết thúc của đường chân ⇒ mẫu đọc ra lùn, mạnh ngang một góc máy sai.
- **`elongated legs`, `slimmer waist`, `seven-and-a-half head-to-body ratio`** — bắt model **vẽ lại
  giải phẫu** hoặc áp một tỷ lệ không phải của người trong Ảnh 1. Tỷ lệ cố định chỉ dùng ở thư viện
  pose (`poses_reference.md` §4), nơi người mẫu là nhân vật do mình định nghĩa — không dùng ở đây.
- **`added logo`, `invented branding`** — chỉ cấm logo **bịa thêm**. Logo/thương hiệu có thật trên
  trang phục trong Ảnh 2 phải được giữ, vì Garment Fidelity yêu cầu chép đúng mọi chi tiết.

Cả bốn đều hỏng — xem §2.2.1 và §2.2.2a.

#### 2.3.2 Negative — 5 nhóm, không lặp lại module 1–6

Negative chỉ để **chặn lỗi**, không phải nơi nhắc lại yêu cầu. Một lỗi chỉ nói một lần, và chỉ nói
khi nó chưa được module 1–6 xử lý dứt điểm:

| Nhóm | Nội dung | Ghi chú |
| :--- | :--- | :--- |
| 1. Identity | `no altered facial identity`, `no changed hairstyle`, `no plastic skin` | Chặn beautify, đổi mặt, đổi tóc |
| 2. Garment | `no garment redesign`, `no recoloured garment`, `no missing or added elements`, `no branding beyond the reference` | Chặn thu gọn phom và bịa logo |
| 3. Anatomy | `no elongated legs`, `no stretched limbs`, `no slimmed waist`, `no distorted joints`, `no extra feet`, `no crossed legs`, `no overlapping thighs`, `no legs merging` | Nhóm nặng nhất — chân là nơi lỗi đọc ra rõ nhất |
| 4. Framing | `no high-angle or overhead framing`, `no wide-angle distortion`, `no cropped head/feet`, `no tilted horizon`, `no inconsistent subject scale` | Chặn lỗi bố cục giữa các ảnh trong bộ |
| 5. Graphics | `no text`, `no UI`, `no card`, `no label`, `no collage`, `no border` | Điều kiện của kiến trúc tách lớp (§0) |

Những cụm **đã bỏ khỏi Negative ở V2** vì trùng hoặc mâu thuẫn: `no tall and slim` (đá với mệnh
lệnh "đọc ra cao"), `no logo` (đá với Garment Fidelity), `no ankle-cutting boots` (giày do Ảnh 2
quyết định), `no zero floor space` (đã có `visible floor space` trong Composition), và toàn bộ biến
thể lặp của cùng một lỗi chân (`no hidden legs`, `no obscured ankles`, `no lateral leg separation`,
`no wide-legged stance`).

#### 2.3.1 Bảng cấm → thay thế

Khi muốn người mẫu "trông cao hơn", đây là các cụm hay bị dùng nhất và bản dịch an toàn của chúng.
Cột phải đều nói về **cách nhìn**, không đụng vào cơ thể.

| KHÔNG dùng | Vì sao | Thay bằng |
| :--- | :--- | :--- |
| `make her look taller`, `make the model taller` | Ra lệnh kéo giãn toàn thân; model hiểu là chỉnh giải phẫu | `emphasize vertical proportions` |
| `extremely tall body`, `very tall and slim` | Cường độ `extremely` đẩy model sang dáng siêu thực, sai Ảnh 1 | `read tall through posture, framing and camera distance` |
| `very long legs`, `elongated legs`, `longer legs`, `overly long legs` | Kéo dài chân trực tiếp — đứt Identity Lock | `long unbroken leg line` / `balanced leg-to-torso ratio` |
| `slimmer waist`, `tiny upper body` | Thu nhỏ thân trên để "ăn gian" chiều cao | `visible waist-to-hip transition`, `balanced leg-to-torso ratio` |
| `stretch the entire body`, `stretched limbs` | Ra lệnh biến dạng hình học | `one clean continuous vertical line` (nói về đường nét, không phải cơ thể) |
| `8 heads tall`, `model proportions`, `seven-and-a-half head-to-body ratio` | Áp tỷ lệ cứng bất kể người thật | giữ đúng tỷ lệ Ảnh 1, cải thiện bằng bố cục và khoảng cách máy |
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

Đặt ảnh ra cạnh Ảnh 1 (và Ảnh 2) và soi 8 mục. Trượt mục nào thì sửa prompt rồi sinh lại — **không**
dùng công cụ kéo dài ảnh sau đó, vì kéo hậu kỳ chính là thứ làm biến dạng giải phẫu mà cả khối này tránh.

- [ ] **Danh tính:** vẫn đúng người trong Ảnh 1 — không bị làm thon mặt, không đổi tóc, không trẻ hơn.
- [ ] **Tỷ lệ:** chiều cao, bề ngang vai, độ dài chân khớp Ảnh 1. Nếu người mẫu *cao hơn thật rõ rệt*
      thì prompt đã lấn sang kéo giãn — sinh lại.
- [ ] **Phối cảnh:** đường nằm ngang của mặt sàn và bậu cửa (nếu có) không bị nghiêng mạnh; bàn chân
      không bị phóng to bất thường.
- [ ] **Bố cục:** thấy đủ đỉnh đầu lẫn hai bàn chân, có khoảng trống phía trên đầu.
- [ ] **Hướng mặt:** thân ba phần tư nhưng mặt vẫn đọc được về phía máy — nếu mặt quay đi quá xa thì
      tăng vế `head turned gently back toward the camera`, đừng xoay cả thân về trực diện.
- [ ] **Tư thế:** đúng pose đã chọn ở §2.2.1a — chân tách rõ, không dính khối, không đùi chồng;
      nếu hai vai **song song hoàn toàn** với mặt phẳng ảnh mà pose yêu cầu ba phần tư thì đã trượt
      về 0°, sinh lại.
- [ ] **Đường silhouette:** không có khối ngang (gấu váy, tất, viền áo) cắt đứt hình thể ở giữa.
- [ ] **Trang phục:** vẫn đúng thiết kế Ảnh 2 — không bị kéo dài gấu, không bị siết eo, **logo có
      thật trên đồ vẫn còn**, không xuất hiện logo lạ.

#### 2.5 Chế độ Plate — ảnh first frame cho video lookbook

Cùng một engine prompt, chỉ khác **bốn điểm**. Dùng khi ảnh sinh ra sẽ làm **first frame cho node
video** (pipeline tách lớp Flow + HyperFrames), không phải ảnh thử đồ trả cho khách.

| | Try-on thường | **Plate** |
| :--- | :--- | :--- |
| Đầu vào | Ảnh 1 (identity) + Ảnh 2 (garment) + Ảnh 3 (tuỳ chọn) | **Chỉ 1 ảnh** — đã có người mẫu mặc đúng bộ đồ |
| Bối cảnh | Kế thừa từ Ảnh 3, hoặc Ảnh 2 nếu thiếu | **Luôn thay** bằng studio trơn, không kế thừa |
| Bố cục | Căn giữa trục dọc | Căn giữa — giữ nguyên, không cần lệch |
| Negative | 5 nhóm: identity, garment, anatomy, framing, graphics | 5 nhóm + **nhóm nền sạch** |

Ba thứ còn lại (Identity Lock, khối `[HEIGHT & PROPORTION OPTIMIZATION]`, thư viện pose) **giữ nguyên
văn** — đó là lý do không cần một skill riêng cho plate nữa.

**2.5.1 Đầu vào chỉ có một ảnh**

Ảnh duy nhất đóng cả hai vai: identity **và** trang phục. Sửa câu mở đầu của template thành:

```text
Photograph of the exact model from Image 1, wearing the exact outfit from Image 1.
```

Có đúng **hai câu** phải thay. Hai module `[IDENTITY LOCK]` và `[GARMENT FIDELITY]` giữ nguyên phần
còn lại — chúng không phụ thuộc số hiệu ảnh:

| Câu gốc (try-on) | Câu plate |
| :--- | :--- |
| `[GARMENT FIDELITY] Reproduce the complete outfit from Image 2 exactly, ...` | `Reproduce the complete outfit from Image 1 exactly, ...` — giữ nguyên phần đuôi |
| `If Image 3 is provided: take only the space ... If Image 3 is not provided: ...` | **xoá hẳn**, thay bằng câu studio ở §2.5.2 |

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

**2.5.4 Giày — không bao giờ đổi sản phẩm**

Giày thuộc Garment Fidelity: giữ đúng đôi giày trong ảnh. **Không** thay bằng kitten heels, sandal hay
bất kỳ đôi nào khác để "đường chân dài hơn" — đó là redesign trang phục, đúng thứ module 2 cấm, và
khách sẽ nhận được ảnh không còn đúng sản phẩm.

Nếu giày trong ảnh cắt ngang cổ chân và làm gãy đường chân, cách xử lý hợp lệ **chỉ** là bố cục:
giữ nguyên giày, giữ đủ khoảng trống dưới đế (`12 percent` ở Composition), và chọn pose có chân tách
rõ. Không sửa sản phẩm để bù cho một tư thế xấu.

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
