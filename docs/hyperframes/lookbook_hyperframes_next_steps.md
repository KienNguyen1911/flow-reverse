# Lookbook HyperFrames — Hướng dẫn thực hiện từng bước

Tài liệu này là **hướng dẫn thao tác**, đi kèm hai tài liệu đã có:

- `docs/hyperframes/lookbook_hyperframes_plan.md` — plan gốc (mục tiêu, timeline, nghệ thuật).
- `docs/lookbook_pipeline.md` — hợp đồng hiện hành giữa script, Flow và HyperFrames.

Lượt này **không tích hợp HyperFrames vào source**. Deliverable là 3 skill đã sửa + tài liệu này.
Các bước dưới đây xếp theo **thứ tự phụ thuộc thật**: bước sau cần đầu ra của bước trước.

---

## 0. Trạng thái xuất phát (đã xong, không cần làm lại)

| Hạng mục | Trạng thái | Bằng chứng |
| :--- | :--- | :--- |
| Skill ảnh "model only, no UI" | ✅ Xong, đã gộp vào try-on §2.5 | `prompt-skills/try-on-image-prompter.md` |
| Skill video "motion only" | ✅ Xong, sống sót qua sanitize | `prompt-skills/lookbook-video-prompter.md` |
| Skill try-on tách lớp | ✅ Xong | `prompt-skills/try-on-image-prompter.md` §0 |
| Route `lookbook-*` trong `select_skill` | ✅ Đã có sẵn | `src/Workflows/prompt_agent.py:77-80` |
| Template composition chạy được | ⚠️ PoC tạm, chưa phải bản chính thức | `scratch/hf_poc/index.html`, `poc_lookbook.mp4` |
| Cutout 4 món đồ | ❌ Chưa có | — |
| Render job trong pipeline | ❌ Chưa có | — |
| Audio (BGM/SFX) | ❌ Chưa có, và đang bị `-an` chặn | `flow_video_bridge.py:692, 753, 803` |
| QA tự động | ❌ Chưa có | — |

**Kết luận:** bước 1 và 2 dưới đây là phần "dùng được ngay"; bước 3–8 là phần "phải xây".

---

## Bước 1 — Sinh ảnh first frame bằng skill mới (làm ngay được)

Đây là bước duy nhất **không cần code mới**. Mục tiêu: có ảnh người mẫu toàn thân, sạch, không UI.

1. Mở Flow Bench, tạo **node ảnh** trên canvas.
2. Đặt `custom_hint` có chữ `plate` để bật chế độ plate của `try-on-image-prompter` §2.5.
   Không có hint thì skill vẫn là try-on nhưng agent sẽ giả định có 2 ảnh đầu vào — node plate
   chỉ có một, nên prompt sinh ra nhắc ảnh không tồn tại.
3. Đính kèm ảnh sản phẩm thật làm tham chiếu trang phục.
4. Chạy prompt agent → dán output vào Flow.

**Tiêu chí nghiệm thu (kiểm bằng mắt, 30 giây):**

- [ ] Người mẫu **toàn thân**, thấy rõ cả gót chân, không cắt đỉnh đầu.
- [ ] Không có cột trái, không có chữ, không có khung card nào.
- [ ] Có khoảng trống ~5–8% trên đầu và dưới chân.
- [ ] Người mẫu căn giữa trục dọc (mẹo lệch phải đã bỏ — HyperFrames desktop tự canh lớp chữ).

Nếu ảnh ra có chữ hoặc cột → **sửa prompt, đừng crop**. Crop là mất 1/3 khung và mất luôn
độ phân giải ngang (xem Bước 2).

---

## Bước 2 — Sinh 2 clip video raw 9:16 (làm ngay được)

1. Tạo **node video** nối từ ảnh ở Bước 1.
2. Prompt agent sẽ trả về **2 khối code** (clip 1 và clip 2) — dán lần lượt.
3. Clip 2 dùng **last frame của clip 1** làm ảnh đầu vào.

Cách lấy last frame chính xác (đừng dùng ảnh gốc — người mẫu sẽ nhảy về tư thế đầu):

```python
from src.Bridge.flow_video_bridge import extract_last_video_frame
extract_last_video_frame("clip1.mp4", "clip2_first.png")
```

**Tiêu chí nghiệm thu:**

- [ ] Clip 1: 3 giây đầu người mẫu **nhìn thẳng ống kính**, chưa quay lưng.
- [ ] Clip 1: sau đó xoay trọn 360° rồi về mặt trước.
- [ ] Clip 2: kết thúc ở tư thế **giống tư thế mở đầu clip 1** (để loop 16s→0s không giật).
- [ ] Cả hai: không có chữ, không cột item trong khung.
- [ ] Độ phân giải gốc 9:16 đầy khung (không phải bản đã crop).

> ⚠️ **Đừng dùng lại clip cũ 720×1280 để phát hành.** Sau khi crop bỏ 1/3 trái, bề ngang thật
> chỉ còn ~453px → không đạt 1080×1920, và 24fps nguồn không lên được 60fps thật. Clip cũ chỉ
> dùng để duyệt template (Bước 4), không dùng cho bản cuối.

---

## Bước 3 — Chuẩn bị 5 ảnh cutout (làm song song được với Bước 1–2)

Cần đúng 5 file, tách nền PNG trong suốt:

```text
assets/items/item_1_top_front.png
assets/items/item_1_top_back.png
assets/items/item_2_jeans.png
assets/items/item_3_bag.png
assets/items/item_4_sandals.png
```

**Lấy ảnh ở đâu:** ảnh sản phẩm thật — upload qua canvas (`/api/upload`) hoặc sinh từ node ảnh
(`is_item` + `item_name` để chép vào `out/items/<project_id>/`).

**Tách nền:** dùng công cụ ngoài pipeline:

```bash
npx --yes hyperframes@0.8.216 remove-background in.png -o out.png
```

> ⚠️ Model tách nền (`u2net_human_seg`) được huấn luyện cho **người**, không phải quần áo treo.
> Nó rất dễ ăn mất quai dép, viền ren, dây áo. **Phải mở từng file kiểm tra bằng mắt.** Nếu hỏng
> nhiều, cách chắc ăn hơn là chụp lại món đồ trên nền trơn rồi tách.

**Tiêu chí nghiệm thu:** mỗi file PNG, nền trong suốt, chủ thể không bị mất chi tiết mảnh,
kích thước cạnh dài ≥ 800px.

---

## Bước 4 — Dựng template composition (nền tảng của mọi thứ sau)

Đây là bước nặng nhất. PoC `scratch/hf_poc/index.html` đã chứng minh khả thi nhưng **không dùng
trực tiếp** — nó là bản nháp. Tạo project thật:

```text
lookbooks/<slug>/
├── index.html
├── assets/
│   ├── clip1.mp4
│   ├── clip2.mp4
│   ├── items/*.png        (5 file từ Bước 3)
│   └── audio/bgm.mp3, sfx/*.mp3
└── renders/
```

Timeline 15s theo plan (giữ đúng thứ tự này, nó đã tính cả nhịp mắt người xem):

| Thời điểm | Nội dung | Ghi chú kỹ thuật |
| :--- | :--- | :--- |
| 0.0–2.5s | Hook: người mẫu nhìn ống kính + banner | Dùng 3s eye-contact của clip 1 |
| 2.5–6.0s | Card 1 lật (top) | 3.5s, đủ để đọc |
| 5.5–9.0s | Chuyển sang jeans | Chồng lấn 0.5s với card trước |
| 9.0–12.0s | Bag | — |
| 12.0–15.0s | Finale + progress/score | Chuẩn bị loop về 0:00 |

**Ba lỗi đã gặp trong PoC, đừng lặp lại:**

1. **`rotateY(180deg)` lật ngược chữ trên card.** Phải dựng **2 mặt riêng** + `backface-visibility:
   hidden`, không xoay một mặt.
2. **Contrast fail.** `hyperframes check` báo 6 lỗi contrast. Chữ trên nền ảnh video phải có
   scrim/gradient phía sau, không đặt chữ trực tiếp lên pixel video.
3. **Type floor.** Cỡ chữ nhỏ nhất ≥ 28px (kiểm bằng `hyperframes check`, không đoán).

**Lệnh kiểm tra (chạy sau mỗi lần sửa lớn):**

```bash
npx --yes hyperframes@0.8.216 lint lookbooks/<slug>/
npx --yes hyperframes@0.8.216 check lookbooks/<slug>/
```

`lint` phải **0 error / 0 warning**. `check` phải hết lỗi contrast trước khi render bản cuối.

**Nghiệm thu Bước 4:** render draft ở 30fps, xem bằng mắt toàn bộ 15s, xác nhận nhịp và
typography ổn. Chưa cần đẹp, cần **đúng nhịp**.

---

## Bước 5 — Ghép nguồn video (chỉ khi còn dùng clip cũ)

Nếu đã có clip raw mới từ Bước 2, **bỏ qua bước này**.

Nếu muốn duyệt template bằng clip cũ, cần crop bỏ 1/3 trái (phần UI cũ dính trong pixel):

```bash
ffmpeg -i old_clip.mp4 -vf "crop=iw*0.63:ih:iw*0.37:0,scale=1080:1920:flags=lanczos" cropped.mp4
```

Đây chỉ là **cầu tạm**. Nhớ: kết quả ~453px bề ngang thật, phóng lên 1080 chỉ là nội suy.

Ghép 2 clip (hàm có sẵn, lossless):

```python
from src.Bridge.flow_video_bridge import concatenate_two_videos
concatenate_two_videos("clip1.mp4", "clip2.mp4", "out_16s.mp4")
```

> ⚠️ Hàm này **xoá audio** (`-c:v copy -an`). Không sao ở bước này vì audio do HyperFrames
> thêm sau. Nhưng nếu sau này muốn giữ tiếng gốc thì phải sửa hàm.

---

## Bước 6 — Đóng gói render thành job (bước đầu tiên chạm vào source)

Đây là lúc bắt đầu viết code production. Tạo `src/Workflows/lookbook_render.py`:

- Gọi `npx hyperframes@0.8.216 render <dir> --fps 60 --quality delivery --json`
  (`--fps` nhận số nguyên 24/25/30/50/60/120/240; `--quality` nhận `draft|looks|delivery`;
  `--json` in JSON lỗi khi fail, và tắt progress khi không có `--batch`)
- Timeout: dùng `--protocol-timeout` (mặc định 300000ms) và `--browser-timeout` nếu composition
  nặng. Đừng để mặc định rồi treo.
- Parse JSON output để lấy đường dẫn file và trạng thái.

Đăng ký job kind `lookbook_render` trong `src/WebUI/jobs.py::_dispatch` (dòng 845–871). Mỗi
nhánh hiện tại đều theo mẫu `if kind == "..." : self._run_xxx(job); return`, thêm một nhánh
tương tự là đủ.

**Nghiệm thu:** gọi job bằng tay, nhận file MP4 1080×1920 @ 60fps, thời lượng 15.000s.

---

## Bước 7 — Thêm API + nút trên UI

- Route trong `src/WebUI/app.py`, phục vụ file output theo mẫu route `/api/node/files` đã có.
- Nút **"Dựng lookbook"** đặt cạnh nút run của node đã có video,
  trong `web/src/components/`.

**Nghiệm thu:** bấm nút từ UI → job chạy → file tải về được, không cần terminal.

---

## Bước 8 — Audio: BGM + SFX (làm sau cùng, dễ nhất để hỏng)

> 🚧 **Chặn trước tiên:** audio đang bị xoá ở **3 chỗ**, phải gỡ trước khi làm bất cứ gì:
>
> - `src/Bridge/flow_video_bridge.py:692` — `strip_video_audio()`
> - `src/Bridge/flow_video_bridge.py:753` — concat method 1
> - `src/Bridge/flow_video_bridge.py:803` — concat method 2 (filter_complex fallback)
>
> Ngoài ra `src/Workflows/watermark_remover.py:464` cũng encode `-an`. Nếu pipeline có chạy qua
> bước xoá watermark thì audio cũng mất ở đó.

Sau khi gỡ: dùng HyperFrames `media-use` / `audio` / `beats` để đặt BGM và SFX theo mốc flip card.
Nhớ **ducking** — hạ BGM khi có SFX, đừng để hai lớp đánh nhau.

**Nghiệm thu:** phát file cuối, nghe được BGM, nghe được tiếng flip, không bị rè/clip.

---

## Bước 9 — QA tự động (khoá lại để không tái phát)

Thêm vào `tests/`:

- `hyperframes check` phải exit 0 (hết contrast error).
- Type floor ≥ 28px.
- `line_unread` không có.
- Thời lượng chính xác 15.000s, 1080×1920, 60fps.

Đây là bước dễ bỏ qua nhất và cũng là bước khiến lần sau không phải sửa lại từ đầu.

---

## Tóm tắt: cần làm gì, theo thứ tự

**Làm được ngay, không cần code:**

1. Sinh ảnh first frame bằng `try-on-image-prompter` chế độ plate (kiểm: toàn thân, không chữ, không cột).
2. Sinh 2 clip raw 9:16 (kiểm: 3s eye-contact đầu, clip 2 loop về tư thế đầu).
3. Chuẩn bị 5 cutout PNG từ ảnh sản phẩm thật (kiểm từng file bằng mắt).
4. Dựng composition + timeline 15s, `lint` 0 error, `check` hết contrast.

**Phải viết code, theo thứ tự phụ thuộc:**

5. (Tuỳ chọn) Hàm crop cho clip cũ — chỉ để duyệt template.
6. `src/Workflows/lookbook_render.py` + job kind `lookbook_render`.
7. API route + nút "Dựng lookbook" trên UI.
8. Gỡ `-an` ở 3 chỗ → thêm BGM/SFX/ducking.
9. Test QA tự động.

**Đường găng (critical path):** Bước 3 (cutout) và Bước 4 (composition) chặn mọi thứ phía sau.
Bước 1–2 chạy song song được với Bước 3. Bước 8 phải làm **sau** Bước 6–7, và phải gỡ `-an`
**trước** khi thêm audio, nếu không sẽ mất công hai lần.

---

## Phụ lục — Những gì đã sửa trong `prompt-skills/` lượt này

### `lookbook-thumbnail-prompter.md` (trước là `lookbook-image-prompter.md`)

- **Mode A "model only" thành mặc định.** Prompt chỉ sinh người mẫu toàn thân trong studio,
  cấm tuyệt đối chữ/UI/cột item. Có bảng phân vai "ai làm gì" để không ai nhầm lại.
- **Mode B "board-with-sidebar"** giữ làm tuỳ chọn cho ảnh bìa, kèm cảnh báo rõ: **không dùng
  làm nguồn video** (chữ méo + mất 1/3 khung).
- Bối cảnh studio khoá cứng để 2 clip nối không lộ mối.
- Thêm mục "lấy 5 cutout ở đâu" — chỉ rõ lấy từ ảnh sản phẩm thật, không nhờ AI vẽ.
- Negative prompt cấm đúng bộ từ khoá bố cục.

### `lookbook-video-prompter.md`

- **§0 "Ba ràng buộc của repo"** — phần quan trọng nhất, viết mới hoàn toàn:
  1. Cấm mọi header mốc thời gian (kèm giải thích `Camera & Realism` bị xoá tới hết prompt).
  2. Bảng cụm bị `aggressive` viết lại (`glances over her shoulder` → `rotates smoothly`, v.v.).
  3. Văn phong trung tính giống — gọi `the model`, không mở đầu câu bằng đại từ.
- Từ vựng chuyển động chia 3 nhóm, đã kiểm tra qua bộ lọc.
- Ngân sách 25–60 từ (trần 80).
- Template 2 clip **dạng 2 code block riêng** (xem ghi chú parser bên dưới).
- Quy trình xử lý khi bị Prominent People chặn, theo thứ tự từng biến một.

### `try-on-image-prompter.md`

- **Bỏ `visible skin micro-pores` và `zero plastic skin smoothing`** khỏi modifier mặc định.
- Thêm **§0 tách lớp** cho ảnh.
- **Đã xoá toàn bộ §3 (video prompt)** — skill này chỉ sinh prompt ảnh; nội dung video chuyển hẳn
  sang `lookbook-video-prompter`. Giữ cả hai nơi thì agent có hai bộ quy tắc video mâu thuẫn nhau.

### `tests/test_prompt_skills_contract.py` (mới, 6 test pass)

Khoá lại các ràng buộc trên để lần sau sửa skill không vô tình phá:
skill load + có policy clause · template ảnh cấm từ khoá bố cục · template video sống sót qua
sanitize cả 2 chế độ, không mất >15% nội dung, ≤80 từ · template không chứa cụm bị lọc ·
parser đọc đúng output shape · skill try-on có ghi lại các cụm bị viết lại.

---

## Phụ lục — Hai lỗi thật phát hiện trong lúc sửa skill

### 1. `sanitize_video_prompt` xoá tới hết prompt khi gặp `Camera & Realism`

Regex `Camera\s*&\s*Realism:.*$` (dòng 845) dùng cờ không phải DOTALL, nhưng dòng 828 đã
join toàn bộ prompt thành **một dòng duy nhất** trước đó, nên `.*$` ăn tới hết chuỗi. Prompt bắt đầu bằng header này → **output rỗng**, gửi lên Flow một
prompt trống.

Ngoài ra regex timecode chỉ khớp `0s to 2s` / `2s to 6s` / `6s to 8s`, nên header kiểu
`- 0s to 3s (Hook):` (đúng nhịp plan) **không bị xoá** mà sót nguyên văn vào prompt gửi Flow.

Đã xử lý ở tầng skill: cấm hẳn header, thay bằng lời văn. **Chưa sửa code** — nếu muốn sửa gốc
thì đó là việc riêng, và nên làm cùng lúc với việc mở rộng regex timecode.

### 2. `parse_gemini_video_prompts` để lại rác `[` khi header có ngoặc vuông

Với output dạng `[Video Prompt 1] ... [Video Prompt 2] ...`, Pattern A khớp tới `2` nhưng
phần `]` còn lại bị nuốt vào prompt 1 → prompt 1 kết thúc bằng `...in place.\n\n[`.

Đã xử lý ở tầng skill: template dùng **2 code block riêng biệt**, parser đọc bằng Pattern C,
ra đúng 2 prompt sạch (đã verify end-to-end). Header dạng `Video Prompt 1:` (không ngoặc vuông)
cũng sạch, nhưng 2 code block là dạng ổn định nhất.

### Đã verify

```text
pytest tests/test_prompt_agent.py tests/test_prompt_skills_contract.py  →  11 passed
```

End-to-end qua đúng pipeline production (sanitize + parse):

| Nguồn | normal | aggressive | Parse ra 2 prompt sạch |
| :--- | :--- | :--- | :--- |
| lookbook clip 1 (58 từ) | giữ 100% | giữ 126% | ✅ |
| lookbook clip 2 (59 từ) | giữ 100% | giữ 127% | ✅ |
| try-on clip 1 (58 từ) | giữ 100% | giữ 126% | ✅ |
| try-on clip 2 (51 từ) | giữ 100% | giữ 131% | ✅ |

(aggressive >100% vì nó **thêm** modifier vào cuối, không phải vì phình nội dung.)

Template ảnh: 161 từ, roundtrip qua `parse_gemini_image_prompt` giữ nguyên, `[POLICY COMPLIANCE]`
sống sót.
