# Phân tích: source hiện tại làm được gì so với kế hoạch Lookbook HyperFrames

> Đối chiếu kế hoạch trong [`lookbook_hyperframes_plan.md`](lookbook_hyperframes_plan.md) với năng lực
> thật của repo tại HEAD `b912aa2` (nhánh `main`). Mọi kết luận đều kèm bằng chứng `file:line` hoặc
> số đo chạy thật trên máy (FFprobe / HyperFrames CLI), không suy đoán.
>
> **TL;DR** — Repo hiện tại làm tốt **nửa trái** của kế hoạch: sinh ảnh lookbook, sinh 2 clip AI 8s nối
> bằng last-frame, ghép 16s, xoá watermark. Repo **không có** bất kỳ năng lực compose/dựng lớp nào:
> không crop-composite, không overlay chữ/UI, không cutout PNG, không audio, không timeline, không
> 60fps. Toàn bộ phần "giữ chân" trong plan (card active, kinetic type, progress bar, zoom/pan, BGM)
> là **phải xây mới**, không phải sửa.

---

## 1. Bản đồ năng lực hiện có (đã kiểm chứng)

### 1.1 Tạo ảnh (khung bên phải + board)

| Năng lực | Trạng thái | Bằng chứng |
| :--- | :--- | :--- |
| Tạo ảnh qua Flow bridge (`ogiZ0b`) | ✅ | `src/Workflows/flow_client.py:415` |
| Tỷ lệ 9:16 đã verify (enum `2`) | ✅ | `src/Workflows/media_service.py:62` (`VERIFIED_IMAGE_ASPECTS = {"16:9": 3, "9:16": 2}`) |
| Ảnh tham chiếu i2i, **nhiều ảnh** một lần | ✅ | `src/WebUI/app.py:96` (`reference_image_paths`), `tests/test_multi_reference.py` |
| Kiểm soát seed (int32), echo seed | ✅ | `src/Workflows/flow_client.py:445` |
| Xoá watermark ✦ trong ảnh | ✅ | `src/Workflows/watermark_remover.py:271` |
| Dry-run 0 credit + confirm bắt buộc | ✅ | `src/WebUI/app.py:552-558` |
| Prompt Lookbook board 1/3 + 2/3 | ✅ (nhưng xem §3.1) | `prompt-skills/lookbook-thumbnail-prompter.md:113-117` |

### 1.2 Tạo video (người mẫu)

| Năng lực | Trạng thái | Bằng chứng |
| :--- | :--- | :--- |
| Image-to-video 8s (`abra_i2v_8s`) | ✅ | `src/Workflows/media_service.py:76`, `src/Bridge/flow_video_bridge.py:76` |
| 9:16 / 16:9, 1080p (upsample `p0UkFb`) + fallback 720p | ✅ | `src/Bridge/flow_video_bridge.py:74-80`, `docs/api_specs/node_media_api.md:48-52` |
| **Bắt buộc** có starting frame (không có text-to-video) | ⚠️ giới hạn | `src/Workflows/media_service.py:210` (`supports_text_to_video: False`) |
| Khoá composer sang chế độ Video trước khi fire | ✅ (vừa sửa) | `git diff src/Bridge/flow_video_bridge.py` → `click_generate(..., expected_mode="video")` |
| Lọc prompt chống policy Prominent People | ✅ | `src/Bridge/flow_video_bridge.py:821` (`sanitize_video_prompt`) |
| Trích last frame chính xác (FFmpeg `-sseof`) | ✅ | `src/Bridge/flow_video_bridge.py:592` |
| Nối 2 clip 8s → 16s (stream copy, fallback re-encode) | ✅ | `src/Bridge/flow_video_bridge.py:710` |
| Xoá watermark video | ✅ | `src/Workflows/watermark_remover.py:330` |

### 1.3 Pipeline & hạ tầng

| Năng lực | Trạng thái | Bằng chứng |
| :--- | :--- | :--- |
| Pipeline try-on 5 bước (ảnh → video1 → last frame → video2 → ghép) | ✅ | `src/Workflows/auto_tryon_pipeline.py:125-700` |
| Resume theo `run_id` + `start_from_step`, skip bước đã có | ✅ | `src/Workflows/auto_tryon_pipeline.py:169-200, 620-660` |
| Prompt do agent local (`agy`/`pi`) viết, dựa trên skill .md | ✅ | `src/Workflows/prompt_agent.py:61-161`, `src/Workflows/skill_manager.py` |
| Canvas node graph (`ref`/`image`/`video`/`last_frame`), group, retry | ✅ | `src/Workflows/../WebUI/jobs.py:845`, `web/src/components/CanvasDrawer.tsx:26` |
| Pool N account, breaker, hot-spare, retry backoff | ✅ | `src/Workflows/account_pool.py`, `src/Workflows/node_retry.py` |
| Serve file media qua HTTP cho UI | ✅ | `src/WebUI/app.py:630` (`/api/node/files`), `:796` (`/api/tryon/files`) |
| Tải ảnh sản phẩm Shopee | ✅ | `src/Workflows/shopee_downloader.py:226` |

---

## 2. Đối chiếu từng "vũ khí giữ chân" trong plan

| # | Thứ plan cần | Hiện có trong repo? | Ghi chú |
| :--- | :--- | :--- | :--- |
| 1 | Card active scale 1.15x + glow + dim 40% | ❌ **không** | Không có HTML/DOM renderer. CSS đó chỉ tồn tại nếu có HyperFrames/Remotion/Chrome capture. Hiện 100% hiệu ứng nằm trong pixel do Veo sinh. |
| 2 | Kinetic typography / typewriter / callout SVG nối từ món đồ | ❌ **không** | `rg drawtext` trên `src/` → **0 kết quả**. Không có bước vẽ chữ nào vào output. |
| 3 | Segmented progress bar 4 đốt | ❌ **không** | Không có timeline/overlay. |
| 4 | Zoom & pan động vào video raw (`scale(1.35) translateY`) | ❌ **không** | Không có `zoompan`, không có composite. `crop` duy nhất trong repo là `DEFAULT_CROP_916` — **crop_box truyền vào RPC i2v của Flow**, không phải crop file video (`src/Bridge/flow_video_bridge.py:82-83`). |
| 5 | Crop bỏ 1/3 trái của video board cũ | ❌ **không** | Không có hàm cắt file. Phải viết mới (1 lệnh FFmpeg, ~10 dòng Python). |
| 6 | 4 PNG tách nền món đồ (front/back/jeans/bag/sandals) | ❌ **không** | `assets/` chỉ có `nabi_model.png`, `sample_garment.png`, `sample_first_frame.png`. **Không có** background-removal/matting cho vật thể. |
| 7 | 3D card flip mặt trước ↔ mặt sau | ❌ **không** | — |
| 8 | BGM + SFX pop/whoosh, vào beat 2.5s | ❌ **không** | Ngược lại: pipeline **chủ động xoá sạch audio** — `strip_video_audio()` (`flow_video_bridge.py:675`) và watermark remover encode `-an` (`watermark_remover.py:450`). `ffprobe` trên `final_tryon_video_16s.mp4` và `out/nodes/video_*/video.mp4` đều chỉ thấy **1 stream video**, không có audio. |
| 9 | 15s / 1080×1920 / **60fps** | ⚠️ một phần | 1080×1920 có (upsample). Nhưng **24fps là trần** của nguồn (đo thật: `r_frame_rate=24/1`), 60fps chỉ là nhân bản khung. |
| 10 | Cắt 1s cuối để loop mượt về 0:00 | ❌ **không** | Không có bước trim; `concatenate_two_videos` chỉ nối 2 clip. |

---

## 3. Ba xung đột cần biết trước khi bắt tay

### 3.1 Skill ảnh hiện tại đang **sinh ra đúng cái sai lầm** plan muốn bỏ

`prompt-skills/lookbook-thumbnail-prompter.md:101-117` bắt buộc cột trái 1/3 + người mẫu 2/3 **nằm trong
cùng một ảnh**, và `:133-139` mô tả chính xác board đó. Đây là lý do video hiện tại có UI dính cứng vào
pixel. Nếu tiếp tục dùng skill này làm first frame thì mỗi lần vẫn phải crop, và mỗi lần crop lại mất
thêm chi tiết (xem §4).

→ Cần một skill mới chỉ mô tả **người mẫu toàn thân trong studio, không UI, không chữ, không board**.

> **Đã làm, rồi gộp lại.** Skill đó từng tồn tại với tên `lookbook-model-only-prompter.md`, nhưng nó
> chỉ là try-on với một ảnh đầu vào + bối cảnh thay thế — tách riêng sinh ra nguồn sự thật thứ hai
> cho tiêu cự/occupancy và lệch nhau (`85mm` vs `50mm`, `across the body line` chưa vá). Nay là
> **§2.5 chế độ plate** của `prompt-skills/try-on-image-prompter.md`.

### 3.2 Skill video mới đã đi đúng hướng, nhưng va vào `sanitize_video_prompt`

`b912aa2` vừa rút prompt video về **25–60 từ, chỉ chuyển động + camera**
(`prompt-skills/lookbook-video-prompter.md:42`) — rất hợp với plan (AI chỉ lo người mẫu). Nhưng bộ lọc
`sanitize_video_prompt(aggressive=True)` (`src/Bridge/flow_video_bridge.py:852-856`) **xoá đúng những
cụm** plan cần: `look at the camera` → `maintaining natural posture`, `glances over her shoulder` →
`rotates smoothly`. Nếu plan yêu cầu "giữ eye-contact tuyệt đối ở 0–3s", phải truyền
`aggressive=False` hoặc chỉnh danh sách thay thế, nếu không prompt sẽ bị làm phẳng trước khi gửi Flow.

### 3.3 "Không quay lưng ngay giây thứ 1" chỉ điều khiển được bằng prompt

Không có cơ chế nào trong repo kiểm tra/ép timeline chuyển động của Veo. Đây là rủi ro nội tại của
phương án "AI lo phần người mẫu": 8s đầu có thể vẫn xoay sớm. Giảm thiểu: chia 2 clip theo plan (0–8
mở đầu tĩnh, 8–16 xoay), và chấp nhận phải render lại nếu clip 1 sai nhịp.

---

## 4. PoC: chạy thật HyperFrames trên dữ liệu hiện có (đã render xong)

Để trả lời câu hỏi cuối của plan ("dùng lại video hiện tại để test trước?"), mình đã dựng PoC thật.

**Đầu vào lấy từ repo (không tiêu credit):**
- `out/affiliate_runs/tryon_20261027_150531/final_tryon_video_16s.mp4` — 720×1280, 24fps, 15.96s.
- Crop 63% phải → `model_raw_right.mp4` (816×1450, phần người mẫu thuần, **không còn UI**).
- 4 cutout món đồ cắt từ `first_frame.png` của chính run đó.

**Composition:** `scratch/hf_poc/index.html` — 1080×1920, 15s, GSAP timeline đúng choreography của
plan: hook banner kính mờ 0–2.5s, card 1 scale 1.15 + flip 3.5s, card 2 + pan xuống hông/chân 5.5–9s,
card 3 bounce 9–12s, finale counter 0→9.5 + CTA 12–15s, progress bar 4 đốt chạy suốt.

> `scratch/` bị `.gitignore` chặn, nên PoC không vào git. Muốn dựng lại: tạo thư mục, copy
> `scratch/hf_probe/model_raw_right.mp4` + 4 ảnh `scratch/hf_poc/assets/item_*.png` vào `assets/`,
> rồi `npx hyperframes@0.8.216 render --output poc.mp4 --fps 30 --quality draft --low-memory-mode`.

**Kết quả đo được:**

| Hạng mục | Kết quả |
| :--- | :--- |
| `hyperframes lint` | **0 error, 0 warning** (sau khi bỏ tween `letterSpacing` — lint bắt đúng lỗi rung glyph) |
| `hyperframes snapshot` | 6 khung đúng nhịp, không lệch timeline |
| `hyperframes render` | **1080×1920, 30fps, 450 frame, 15.000s, 7.6 MB, 40.2s** (low-memory mode, 2 worker, máy i5-1135G7) |
| `hyperframes check` | **fail (exit 1)**: Contrast → 3 error + 3 warning (6 dòng: chữ trên card trắng đạt 1.28–2.8:1, cần 4.5:1); Craft → 4 warning (type floor 28px, chữ caption 12px, và 3 cảnh báo `line_unread` vì chữ hiện ngắn hơn thời gian đọc tối thiểu) |

**Hai lỗi thật phát hiện qua PoC (đáng đưa vào checklist):**

1. **Card flip làm lật ngược chữ.** `rotateY(180deg)` trên cả card khiến label `HALTER TOP` bị mirror
   (thấy rõ ở khung 3.9s: "ꟼOT ЯƎT⅃AH"). Khi làm thật phải dùng 2 mặt (front/back) với
   `backface-visibility: hidden` và counter-rotate phần chữ, hoặc chỉ flip riêng lớp ảnh.
2. **Crop từ board 720px làm mềm hình.** Board gốc 720×1280, crop 63% → chỉ còn **453px bề ngang thật**,
   rồi bị phóng lên 816 rồi 734 (canvas 1080). Đây là lý do PoC trông hơi soft dù UI sắc. Kết luận:
   **video raw mới phải sinh ở 9:16 đầy khung, không có UI baked-in**, chứ không phải nuôi bằng board cũ.

**Kết luận PoC:** toàn bộ §1 và §3 của plan (card active, kinetic text, progress bar, zoom/pan,
score counter) **render được thật, đúng 1 khung hình, không cần AI video**. Phần duy nhất PoC *không*
làm được là chất lượng nguồn — vì nguồn là board cũ bị crop.

---

## 5. Việc phải xây mới, xếp theo thứ tự phụ thuộc

| # | Hạng mục | Chỗ đặt (theo cấu trúc AGENTS.md) | Ghi chú |
| :--- | :--- | :--- | :--- |
| 1 | Skill prompt "model only, no UI" | `prompt-skills/try-on-image-prompter.md` §2.5 | Bỏ board khỏi first frame; `prompt_agent.select_skill` bật `plate_mode` khi hint chứa "plate" hoặc node có `clip_role` |
| 2 | Bước crop/composite nguồn (nếu vẫn dùng clip cũ) | `src/Workflows/` (hàm mới) | 1 lệnh FFmpeg; chỉ là cầu tạm cho tới khi có clip raw mới |
| 3 | Cutout 4 món đồ | ngoài pipeline, dùng `npx hyperframes remove-background in.png -o out.png` | Model `u2net_human_seg` thiên về **người**, không phải quần áo treo — phải kiểm chất lượng từng ảnh, hoặc chụp lại món đồ trên nền trơn |
| 4 | Template composition + timeline | thư mục project HyperFrames, ví dụ `lookbooks/<slug>/` | PoC `scratch/hf_poc/index.html` đã là bản nháp chạy được |
| 5 | Lớp render: gọi `npx hyperframes render` như 1 job | `src/Workflows/lookbook_render.py` + `jobs.py` kind `lookbook_render` | Cần: `--fps 60`, `--quality delivery`, `--workers`, timeout, parse `--json` |
| 6 | API + UI: nút "Dựng lookbook" cạnh run đã có video | `src/WebUI/app.py` + `web/src/components/` | Serve output qua route kiểu `/api/tryon/files` |
| 7 | Audio: BGM + SFX + ducking | HyperFrames `media-use` / `audio` / `beats` | **Trước hết phải bỏ `-an`**: hiện audio bị xoá ở 2 chỗ |
| 8 | Checklist QA tự động | `tests/` + `hyperframes check` | Bắt buộc: contrast, type floor ≥28px, `line_unread` |

### Điều kiện môi trường đã kiểm

```
Node 24.16.0  ✓ (HyperFrames yêu cầu >=22)
FFmpeg 9.0.1  ✓
Chrome headless-shell cho HyperFrames  ✓ (đã tự tải)
Docker        ✗ (không có → render không deterministic; chấp nhận được khi dev)
whisper/TTS   ✗ (chỉ cần nếu muốn voiceover)
```

---

## 6. Trả lời câu hỏi cuối của plan

**"Dùng lại file video hiện tại (crop phần người mẫu) để test HyperFrames, hay tạo lại 2 video raw
mới?"**

→ **Cả hai, theo thứ tự này:**

1. **Test bằng clip cũ ngay** — đã chứng minh được ở §4, chi phí 0 credit, 40 giây render. Dùng để
   chốt template, timing, typography, và để team duyệt "cảm giác" trước khi tốn credit.
2. **Nhưng bản phát hành phải dùng video raw mới**, vì:
   - nguồn 720px sau crop chỉ còn 453px → không đạt 1080×1920;
   - UI cũ dính trong pixel ở 1/3 trái, crop bỏ là mất luôn 1/3 khung hình đã render;
   - 24fps nguồn không lên được 60fps thật;
   - clip hiện tại xoay lưng ngay đầu clip — đúng cái plan muốn sửa bằng prompt mới.

Nói cách khác: **clip cũ = dữ liệu để dựng và duyệt template; clip mới = dữ liệu để xuất bản.**
