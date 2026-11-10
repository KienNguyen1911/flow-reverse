# Pipeline Lookbook → Raw Assets → HyperFrames desktop

Tài liệu này mô tả **hợp đồng** giữa ba lớp của pipeline dựng video lookbook, và những
chỗ pipeline cũ làm sai. Đọc `docs/hyperframes/` để biết chi tiết về HyperFrames.

```
 ① Script (dữ liệu)        ② Flow (AI, không UI)          ③ HyperFrames (dựng phim)
 configs/lookbook_script    plate.png, clip1.mp4,          card item, kinetic text,
   .json + .schema.json     clip2.mp4  — chỉ người mẫu      progress bar, zoom, BGM
         │                        │                              │
         └────────────── out/deliveries/<slug>/delivery.json ────┘
                          (hợp đồng máy đọc)
```

## 1. Nguyên tắc tách lớp

AI video giỏi **chuyển động cơ thể và camera**, rất kém **chữ sắc nét, timing và card UI**.
Pipeline cũ nhét cả cột item NABI vào pixel của video rồi cho người mẫu "đẩy văng cột" —
tức là ép AI làm việc nó không làm được.

Bố cục đúng:

| Lớp | Làm gì | Không làm gì |
| :-- | :-- | :-- |
| Flow (Omni 1.2, `macaron_cookie_i2v_<n>s`) | Người mẫu toàn thân, chuyển động, camera | Chữ, card, progress bar, cột thông tin |
| HyperFrames desktop | Card sản phẩm, kinetic text, progress bar, zoom/pan, audio, render | Sinh chuyển động người |

Hệ quả định lượng: board có cột UI chiếm ~37% bề ngang. Crop bỏ cột ⇒ chỉ còn **~453px**
bề ngang thật trong khung 1080. Phóng lên chỉ là nội suy. Bỏ board ⇒ giữ được 1080 thật.

## 2. Script là hợp đồng dữ liệu, không phải văn xuôi

`configs/lookbook_script.schema.json` định nghĩa; `configs/lookbook_script.json` là ví dụ
thật (`havana_donna_set`, 16s, 2 clip nối bằng last frame, 4 shot).

Ràng buộc nghiệp vụ (Schema không diễn đạt được, `src/Workflows/script_contract.py` kiểm):

- `fps ∈ {24, 30}`. **24 là trần nguồn** (ffprobe `r_frame_rate=24/1` của clip Flow);
  đặt 60 chỉ nhân bản khung.
- `clips[].duration_s ≤ 8` — trần của script lookbook (`CLIP_MAX_S`), không phải trần của Flow.
  Muốn dài hơn phải nối bằng `chain_from`.
- `shots[].clip_offset_s + duration_s ≤ clips[].duration_s`.
- `chain_from` phải trỏ tới clip có thật; `emphasis_item` phải trỏ tới item có thật.

## 3. Ba lớp đọc cùng một nguồn

| Lớp | Đọc gì | Code |
| :-- | :-- | :-- |
| Prompt agent | `clips[].role` / `motion_prompt`, `shots[]` rơi vào clip | `src/Workflows/prompt_agent.py` |
| Delivery export | `clips`, `items`, `shots` → file + manifest | `src/Workflows/delivery/` (package) |
| Editor | `delivery.json.timeline` | HyperFrames desktop |

Trước đây mỗi lớp tự đoán: agent hardcode timeline từng giây trong khi sanitizer xoá
chính header đó; editor hardcode `duration_s = 8`; không có gì nói shot nào vào giây nào.

## 4. Bộ prompt skills

| Skill | Dùng cho | Ghi chú |
| :-- | :-- | :-- |
| `try-on-image-prompter` | Ảnh **plate** cho video + ảnh thử đồ | Chế độ plate §2.5: một ảnh, studio trống, cấm tuyệt đối chữ/UI |
| `lookbook-video-prompter` | Mọi prompt video | Motion-only 25–60 từ, đúng 1 câu camera + 2 câu cơ thể |
| `lookbook-item-cutout-prompter` | Ảnh flat-lay sản phẩm | Sinh ảnh sạch từ ảnh Shopee làm reference, cấm người/bối cảnh |
| `lookbook-thumbnail-prompter` | **Chỉ thumbnail** | Board có cột NABI; không được làm first frame video |

> Skill `lookbook-model-only-prompter` đã **gộp vào `try-on-image-prompter` §2.5** (chế độ plate).
> Nó chỉ là try-on với một ảnh đầu vào + bối cảnh thay thế, nên tách riêng tạo ra hai nguồn sự thật
> cho `50mm`/`76%` và sớm lệch nhau (`85mm`, `across the body line`). Mã cũ vẫn ghi ID đó được map
> sang try-on qua `PromptAgent.LEGACY_SKILL_ALIASES`.

Hai skill cũ `lookbook-video-1-push.md` và `lookbook-video-2-showcase.md` đã **xoá**: chúng
đòi cột UI nằm trong pixel để đẩy văng, trái với quyết định tách lớp.

### Prompt video: những gì bị cấm

`sanitize_video_prompt` (`src/Bridge/flow_video_bridge.py`) chạy trước khi gửi Flow, và
`src/Workflows/prompt_lint.py` cảnh báo sớm cho người dùng:

- Header mốc thời gian (`Timeline:`, `0s-3s:`, `[2s-5s]`) — bị cắt, để lại câu cụt.
- Từ vựng UI (`sidebar`, `card`, `progress bar`, `split screen`, `banner`…) — AI không vẽ
  chữ sắc nét; lớp dựng lo.
- `she` / `her` / `the woman` — bộ lọc aggressive đổi thành `the subject` và làm cụt ngữ pháp.
  Gọi chủ thể là **the model**.
- `[POLICY COMPLIANCE]` trong prompt **video** — vô tác dụng, làm loãng token chuyển động.
  (Prompt **ảnh** thì bắt buộc có.)

> Bug đã sửa: `Camera\s*&\s*Realism:.*$` từng xoá cả phần đuôi prompt vì toàn bộ prompt đã
> được join thành một dòng. Xem `tests/test_prompt_skills_contract.py`
> `test_sanitizer_keeps_tail_after_camera_realism_header`.

## 5. Delivery export

`python -m src.WebUI.app` → nút **Xuất bộ dựng phim** trên canvas, hoặc:

```bash
curl -X POST http://127.0.0.1:4000/api/deliveries -H "content-type: application/json" -d '{
  "script_path": "configs/lookbook_script.json",
  "run_refs": [{"clip_id": "clip1", "run_id": "video_20261030_230016"}],
  "overwrite": true
}'
```

Kết quả `out/deliveries/<slug>/`:

```
delivery.json     ← timeline tuyệt đối + thông số đo thật
README.md         ← handoff cho người dựng
plate.jpg|png     ← ảnh nền plate (chỉ người mẫu, không UI)
clips/clip1.mp4
items/item_1_….png + _review.png
items/_source/    ← ảnh Shopee gốc đã dùng
audio/            ← rỗng; khai báo has_audio
```

**Mọi số trong `delivery.json` là số đo ffprobe** (`src/Workflows/media_probe.py`), không
phải tham số yêu cầu. File thiếu ghi vào `assets_missing`, không bịa giá trị.

### UI dựng sẵn trong pixel: đo và báo, không im lặng

Các run sinh bằng template cũ vẫn còn board NABI **nằm trong pixel** — cả ảnh nền
(`starting_frame.jpg`) lẫn 1.3s đầu của clip. HyperFrames không gỡ được chữ đã burn-in, nên
delivery phải nói rõ chỗ nào dùng được:

| Field | Ý nghĩa |
| :-- | :-- |
| `plate_has_baked_ui` | `true` = plate vẫn dính cột UI (không tìm được ảnh sạch) |
| `clips[].ui_clean_from_s` | giây đầu tiên **không** còn board; `null` = sạch từ đầu |
| `clips[].usable_duration_s` | phần còn dùng được sau mốc đó |

Phát hiện bằng `detect_baked_ui_panel` — hai tín hiệu phải cùng đúng:

1. Vùng sát biên trái **tối** (độ sáng TB < 80)
2. Bước nhảy sáng/tối **dựng đứng** ≥ 140 ở 15–55% bề ngang

Ngưỡng lấy từ dữ liệu thật: board cho 41–46 và 145–169; 42 ảnh Shopee và khung video sạch
cho ≥ 111 và ≤ 120. Không dùng độ lệch chuẩn theo cột — board phẳng cho std cao **giống**
ảnh chi tiết, dấu hiệu ngược.

Khi cả bộ ứng viên đều dính UI, `extract_clean_plate` cắt một khung sạch từ chính clip
(board chỉ nằm ở đoạn đầu) và ghi vào cảnh báo rằng đó là ảnh chụp từ video — vẫn nên sinh
lại bằng một ảnh plate sạch để có độ nét đầy đủ.

### Định dạng nguồn (đo thật)

| Thông số | Giá trị |
| :-- | :-- |
| Kích thước tải về | 720×1280, upsample `p0UkFb` → 1080×1920 |
| Frame rate | 24 fps (trần nguồn) |
| Thời lượng | 8.000s mỗi clip theo `CLIP_MAX_S` của script; Flow (Omni 1.2) cho 3..15s |
| Audio | **không có** — `-an` tại `flow_video_bridge.py` (strip/concat) và `watermark_remover.py` |

## 6. Cutout sản phẩm: Flow sinh ảnh → delivery tự lấy về

Ảnh Shopee (`main_images/*.jpg`) là **ảnh lifestyle có người mẫu**, không phải flat-lay.
`u2net_human_seg` — model mà `npx hyperframes remove-background` dùng — được huấn luyện
cho **người**; chạy trên ảnh này sẽ tách **cả người mẫu**. `u2net` (general) cũng vậy:
vật thể nổi bật nhất trong ảnh là con người. **Tách nền local không thể "nhìn xuyên" ảnh
lifestyle để lấy chiếc áo** — dù thử `u2net_cloth_seg` (model chuyên tách quần áo) cũng chỉ
ra đúng chiếc áo đang mặc trên người, méo theo tư thế ngồi và thủng ở chỗ hở da.

Việc tách sản phẩm phải xảy ra **trong Flow**, với ảnh Shopee làm reference:

```
A. Upload ảnh Shopee làm reference (kéo thả vào node ref)
B. Node ảnh + skill lookbook-item-cutout-prompter
      → ảnh sản phẩm sạch trên nền trơn (~1 credit/món)
C. Tách nền — CHỈ KHI CẦN:  python -m scripts.cutout_items
```

**Bước C là tuỳ chọn.** Ảnh Flow sinh ra đã là sản phẩm trên nền trơn, không có người mẫu —
đúng thứ HyperFrames cần. Chỉ chạy `cutout_items` khi muốn card sản phẩm có alpha thật
(đặt chồng lên video mà không thấy khung chữ nhật).

### Đường ống trong app

Template **Lookbook 16s** có sẵn nhóm 2: `lb_ref_garment_upload` → `lb_node_cutout_front`
(một node mẫu duy nhất). Muốn thêm món thì nhân bản node rồi đặt tên — **không** khai danh
sách món vào kịch bản.

### Phạm vi món (`item_scope`) — áo, quần, hay cả bộ

Ảnh Shopee gần như luôn là **cả bộ trên người mẫu**, còn skill cutout lại bắt "chỉ một món".
Không chỉ định gì thì model chọn vật thể nổi bật nhất — thực tế **luôn ra chiếc áo**, không
bao giờ ra quần. Vì vậy node ảnh sản phẩm có thêm 4 nút chọn phạm vi, mặc định `Áo`:

| Nút | `item_scope` | Ảnh sinh ra | Tách nền được? |
| :-- | :-- | :-- | :-- |
| **Áo** | `top` | Một món mặc trên, quần/váy bị loại hẳn | Có |
| **Quần / Váy** | `bottom` | Một món mặc dưới, áo bị loại hẳn | Có |
| **Cả bộ** | `full_set` | Các món xếp cạnh nhau trên cùng nền | **Không** |
| **Bộ phối** | `coordinate_sheet` | Cả bộ + callout, 3 ô `DETAIL`, palette 5 màu | **Không** |

`full_set` và `coordinate_sheet` là **hai ngoại lệ có chủ đích** của quy tắc "một món" trong
`prompt-skills/lookbook-item-cutout-prompter.md`:

- `full_set` chỉ bỏ "một món" — vẫn **cấm chữ**, vẫn là plate dùng làm layer.
- `coordinate_sheet` bỏ cả "một món" lẫn "cấm chữ": ảnh ra là **deliverable** có typography
  (title, callout `01`–`0N`, 3 ô `DETAIL`, palette 5 màu), dùng cho bìa/gallery/social.

Cả hai đều **không đem tách nền**: rembg coi cả cụm là một khối, và với sheet thì cắt luôn chữ.

Với `full_set`, rembg còn gộp bbox cả cụm nên card sản phẩm hở khoảng trống giữa các món.
`cutout_items` giờ đếm số mảnh alpha rời (`pieces`) và loại ảnh có >1 mảnh kèm lời nhắc sinh
lại theo từng món. Dùng thẳng ảnh nền trơn cho composition.

Đường đi của giá trị: `CanvasNode.itemScope` → `GenerateNodePromptBody.item_scope` →
`NodePromptTask.item_scope` → `PromptAgent.ITEM_SCOPES` (chèn khối "Phạm vi cần tách" vào
instruction của agent). Cả 3 đường gọi agent — nút **AI Prompt** trên thẻ, tab Cấu hình trong
drawer, và JIT lúc chạy workflow — đều gửi kèm `is_item`/`item_name`/`item_scope`.

Đổi phạm vi **không** tự sinh lại prompt: prompt cũ vẫn nằm nguyên trên node. Drawer hiện
nhắc đúng câu đó; phải bấm **AI Prompt** thì prompt mới đổi.

#### Vì sao instruction sheet phải dán lại khung §3.4

Nhắc "dùng §3.4" ở giữa instruction là **không đủ**. `gemini-3.8-flash-low` đọc 21K ký tự
skill rồi vẫn trả về nguyên văn template §3.2 (flat-lay, `no text`, `no collage`) — đúng
triệu chứng "chọn Bộ phối mà prompt không khác gì". Hai lớp chặn:

1. `format_agent_instruction` trích **câu mở đầu** của §3.4 từ chính file skill rồi dán vào
   cuối instruction, ngay trong `ĐỊNH DẠNG ĐẦU RA` — chỗ agent đọc cuối cùng trước khi trả
   lời — kèm danh sách 6 khối bắt buộc. Không chép tay sang Python: sửa template trong
   skill là app theo ngay.
2. `generate_prompt_for_node` kiểm tra hậu sinh bằng `coordinate_sheet_sections_missing`
   (`LAYOUT`, `OUTFIT`, `FIDELITY LOCKS`, `DO NOT ADD`, `TYPE & LIGHT`, `COLOR PALETTE`,
   `Negative:`). Thiếu khối nào thì chạy lại **đúng một lần** với cảnh báo chèn ngay trước
   khối định dạng. Không retry vô hạn: agent hỏng hẳn thì trả kết quả và người dùng thấy.

#### Vì sao instruction luôn đi qua file task

`agy` **treo vô hạn** khi instruction ~21K ký tự được truyền thẳng qua `-p`: không một byte
stdout, quá 200s, kể cả khi `stdin` đã đóng. Đúng nội dung đó ghi ra
`out/_agent_tasks/task_*.md` rồi trỏ agent tới file thì trả lời trong ~24s. Vì vậy
`MAX_INLINE_INSTRUCTION` hạ từ 30.000 xuống **4.000** — mọi instruction thật (skill + ngữ
cảnh node) đều đi qua file. Trước đây ngưỡng 30.000 khiến lượt sinh sheet treo im lặng cho
tới khi hết 75s timeout, và người dùng chỉ thấy prompt cũ không đổi.

### Thư viện ảnh sản phẩm (`out/items/<project_id>/`)

Node ảnh có một ô tick **"Đây là ảnh sản phẩm"** (`is_item`). Tick vào, đặt tên món, chạy
node — server chép ảnh vừa sinh vào `out/items/<project_id>/<slug>.png` ngay khi job xong:

```
Áo Kiểu Nữ Donna  ──▶  out/items/prj_0a7e…/ao_kieu_nu_donna.png
```

Đây là **thư viện dùng lại được**, không phải hợp đồng của một bộ phim: cùng một ảnh phục vụ
nhiều bộ, sinh lại thì **ghi đè** (không đẻ `… (2).png`), và mỗi project có thư mục riêng.

Vì sao không gắn cứng vào `items[]` của script: người bán có hàng trăm sản phẩm. Một dropdown
liệt kê 2 món DONNA/CARDIGAN là vô nghĩa với họ.

| Mảnh | Ở đâu |
| :-- | :-- |
| Ô tick + tên món + phạm vi | `CanvasPanel.tsx` — inspector của node ảnh |
| Chép vào thư viện | `jobs.py::_save_project_item` → `item_library.save_item` |
| Liệt kê thư viện | `GET /api/items/library?project_id=…` |
| Slug tên file | `item_library.safe_item_name` (bỏ dấu NFD, xử lý `đ`, cấm ký tự Windows) |

### Xuất bộ dựng phim

`delivery.json → items[]` tự đầy từ hai nguồn, không cần copy tay:

1. **Script khai** (`items[].cutout`) — khi muốn timeline trỏ tới đường dẫn cố định.
2. **`is_item` không thuộc script** — file vào `items/<slug>.png` và được thêm vào manifest
   với `name` là tên người dùng gõ. Đây là đường dẫn phổ biến.

```bash
curl -X POST http://127.0.0.1:4000/api/deliveries -H "content-type: application/json" -d '{
  "script_path": "configs/lookbook_script.json",
  "item_refs": [
    {"name": "Áo Kiểu Nữ Donna", "run_id": "20261031_021335_..."},
    {"name": "Sheer Cardigan", "item_id": "item_2", "run_id": "..."}
  ],
  "overwrite": true
}'
```

### Guard của `cutout_items.py`

Chỉ áp dụng cho **bước C** (tách nền), và nó bảo vệ đúng thứ nó cần bảo vệ: nhận ra ảnh
nguồn **không phải sản phẩm sạch**. Đo trên chính 2 thư mục Shopee của bạn, cả 17 ảnh đều bị
chặn — đúng, vì không ảnh nào là flat-lay:

| Tầng | Bắt được | Ngưỡng |
| :-- | :-- | :-- |
| 1. Nền đồng nhất | lifestyle (café, tường, ngoài trời) | lệch 4 góc < 26, nền ≥ 45% |
| 2. Bảng kẻ | ảnh bảng size/thông số trên nền trắng | ≥ 6 đường kẻ dài |
| 3. Có người | **studio nền trơn vẫn có model** | human_seg phủ ≥ 8% **và** mask cao ≥ 55% khung |

Tầng 3 phải dùng **hai** tín hiệu: `SUGAL/8.jpg` (model đứng, viền trắng rộng) chỉ phủ
11.5% nhưng mask người cao 85.4% khung — đo mỗi độ phủ sẽ để lọt đúng ca này.

Nó cũng xuất `_review.png` (contact sheet trên nền caro) để duyệt cả bộ một lần.

Ngưỡng kiểm file ra: cạnh dài ≥ 800px, ≥ 5% pixel trong suốt, bbox chiếm ≥ 45% cạnh dài.

Ảnh crop sát món đồ (đúng thứ ta muốn) sẽ bị tầng 1 từ chối vì gần như không còn nền —
đó là lý do có `--force`, và cũng là lý do script **không** tự chạy trong vòng production.

Ghi thẳng vào delivery với đúng tên item trong script:

```bash
python -m scripts.cutout_items --src <thư mục flat-lay> \
  --dest out/deliveries/<slug>/items \
  --suffix "" --rename "pink_wrap=item_1_top_front,white_cami=item_2_cardigan"
```

Cài đặt:

```bash
pip install rembg onnxruntime      # ~176MB model tải ở lần chạy đầu
```

## 7. Những gì chưa làm (đã ghi nhận)

- Gỡ `-an`: cần quyết định có dùng audio gốc của Veo hay luôn thay BGM.
- BGM/SFX: `script.audio` đã có chỗ khai báo, chưa có module xử lý.
- Job render HyperFrames tự động (hiện là export thư mục, dựng tay trong desktop app).
- MCP/CLI integration: đã revert, phạm vi lần này là export.

## 8. Kiểm chứng

```bash
python -m pytest tests/test_delivery.py tests/test_prompt_skills_contract.py \
                 tests/test_prompt_agent.py -q

# Bug P0 — đuôi prompt phải sống sót
python -c "from src.Bridge.flow_video_bridge import sanitize_video_prompt as s; \
  print(repr(s('Camera & Realism: x. The model turns.', aggressive=True)))"

# Chất lượng nguồn sau export (kỳ vọng 1080,1920,24/1 — không phải 453px)
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate \
  -of csv=p=0 out/deliveries/havana_donna_set/clips/clip1.mp4

# Chỗ nào còn UI dựng sẵn trong pixel (kỳ vọng ui_clean_from_s=1.3, usable=6.7)
python -c "import json;m=json.load(open('out/deliveries/havana_donna_set/delivery.json',encoding='utf-8'));\
[print(c['id'],c['ui_clean_from_s'],c['usable_duration_s']) for c in m['clips']];\
print('plate_has_baked_ui =',m['plate_has_baked_ui'])"
```
