# Node Media API — tạo ảnh / video độc lập cho canvas

Tài liệu này mô tả lớp **node media** (`src/Workflows/media_service.py` + 3 endpoint trong
`src/WebUI/app.py`) dùng để dựng các node *tạo ảnh* và *tạo video* trên canvas. Mỗi node là **một
lần gọi độc lập**, không phụ thuộc `AutoTryOnPipeline`.

```
Canvas node ──▶ POST /api/node/image|video ──▶ JobManager (1 account) ──▶ MediaService
                                                                        ├─ FlowClient        (ogiZ0b, ảnh)
                                                                        └─ FlowVideoBridge   (eb1hJf/jwpduf/as29s, video)
```

## 1. Năng lực (options)

`GET /api/node/options` trả về danh sách option *đã verify* để UI dựng form:

```json
{
  "image": {
    "aspect_ratios": { "16:9": 3 },
    "verified_aspect_ratios": ["16:9"],
    "default_aspect_ratio": "16:9",
    "supports_reference_image": true,
    "supports_seed": true,
    "supports_watermark_removal": true
  },
  "video": {
    "aspect_ratios": ["9:16", "16:9"],
    "default_aspect_ratio": "9:16",
    "durations_s": [8],
    "resolutions": ["1080p", "720p"],
    "default_resolution": "1080p",
    "supports_starting_frame": true,
    "supports_text_to_video": false,
    "auto_image_chain": true,
    "supports_seed": true,
    "supports_watermark_removal": true
  }
}
```

Ghi chú quan trọng:

- **Ảnh:** enum tỷ lệ là `int`. Chỉ `16:9 = 3` được verify từ capture
  (`docs/api_specs/flow_create_image.md` §2). Các tỷ lệ khác **không được đoán** — chạy
  `python discovery/capture_image_aspects.py --project <uuid> --ratios 9:16 1:1 4:3`
  (0 credit, request app bị chặn) để ghi `configs/image_aspect_enums.json`; API sẽ tự đọc file này.
- **Video:** hai sub-mode. `Khung hình` là image-to-video (`macaron_cookie_i2v_<n>s`) và bắt
  buộc có starting frame; node không đính kèm ảnh sẽ tự chain **ảnh → video** (`auto_image=true`).
  `Thành phần` là text→video (`YhhmEf`/`MZZa6b`), kèm khung `Kết thúc` thì đổi sang `nprQif`.
- **Thời lượng video** 3..15s trên Omni 1.2 (`durations_s` trong `GET /api/node/options`),
  còn 3..10s khi gắn khung `Kết thúc`. Veo 3.1 Lite cố định 8s.
- **Độ phân giải** `1080p` (upsample `p0UkFb`, fallback 720p khi lỗi) hoặc `720p`.

## 2. POST /api/node/image

```json
{
  "prompt": "a red apple on a wooden table, soft window light",
  "aspect_ratio": "16:9",
  "seed": 123456,
  "reference_image_path": "/api/uploads/1730000000000_dress.png",
  "project_id": "3f9a2c1b-....",
  "dry_run": false,
  "remove_watermark": true,
  "confirm": true
}
```

| Field | Ý nghĩa |
| :--- | :--- |
| `prompt` | Bắt buộc, ≤ 2000 ký tự |
| `aspect_ratio` | Tỷ lệ đã verify (mặc định `16:9`); alias `portrait`/`landscape`/`square` được chuẩn hoá |
| `aspect` | Enum int thô (thắng `aspect_ratio`) — dành cho giá trị đã capture thủ công |
| `seed` | 1..2³¹−1 (int32), bỏ trống = random |
| `reference_image_path` | Ảnh đính kèm (i2i). Nhận path hoặc URL `/api/uploads/...`, `/api/references/...`, `/api/assets/...`, `/api/tryon/files/...` |
| `project_id` | Bỏ trống → tự resolve: tab đang mở → dự án mới nhất → tạo mới |
| `dry_run` | Chỉ capture + dựng payload, **không fire** (0 credit, không tạo file) |
| `remove_watermark` | Xoá watermark ✦ ngay trong core ảnh (mặc định true) |
| `confirm` | Bắt buộc `true` khi `dry_run=false` (~1 credit nếu Google nhận) |

Phản hồi: `{"job_id": "...", "kind": "image", "aspect_ratio": "16:9", "aspect": 3}`.
Kết quả job (`GET /api/jobs/{id}` → `result`) gồm:

```json
{
  "status": "ok",
  "prompt": "...", "aspect_ratio": "16:9", "aspect_enum": 3,
  "project_id": "...", "seed_used": 123456,
  "run_id": "20261028_121301_a_red_apple", "run_dir": "out/nodes/...",
  "file_path": "out/nodes/.../a_red_apple.jpg", "file_url": "/api/node/files/<run_id>/a_red_apple.jpg",
  "file_bytes": 512000, "width": 1376, "height": 768, "resolution": [1376, 768],
  "media_id": "...", "reference_sha256": "…", "reference_media_id": "…",
  "account_id": "flow_main", "elapsed_s": 42.1
}
```

## 3. POST /api/node/video

Có ảnh đính kèm:

```json
{
  "prompt": "slow cinematic push-in, fabric moves gently",
  "aspect_ratio": "9:16",
  "frame_path": "/api/node/files/<run_id>/out.jpg",
  "resolution": "1080p",
  "seed": 42,
  "remove_watermark": true,
  "confirm": true
}
```

Không có ảnh (chain ảnh → video):

```json
{
  "prompt": "a dancer in a bright studio, 8 seconds",
  "image_prompt": "full-body portrait of a dancer in a bright studio",
  "image_aspect_ratio": "16:9",
  "auto_image": true,
  "aspect_ratio": "9:16",
  "confirm": true
}
```

| Field | Ý nghĩa |
| :--- | :--- |
| `prompt` | Prompt chuyển động (bắt buộc) |
| `frame_path` | Ảnh đính kèm làm starting frame (path/URL như trên) |
| `auto_image` | Khi không có `frame_path`: `true` = tạo ảnh trước rồi animate; `false` = trả lỗi 400 |
| `image_prompt` | Prompt cho ảnh sinh tự động (mặc định dùng `prompt`) |
| `image_aspect_ratio` | Tỷ lệ ảnh sinh tự động (mặc định `16:9`, giá trị verify được) |
| `aspect_ratio` | `9:16` hoặc `16:9` |
| `resolution` | `1080p`/`720p` |
| `duration_s` | Chỉ `8` (model cố định) |
| `seed`, `remove_watermark`, `dry_run`, `confirm`, `project_id` | Như node ảnh |

Kết quả job:

```json
{
  "status": "ok", "run_id": "video_20261028_121500",
  "video_path": "out/nodes/video_.../video.mp4",
  "video_url": "/api/node/files/video_.../video.mp4",
  "frame_path": "out/nodes/video_.../starting_frame.jpg",
  "frame_url": "/api/node/files/video_.../starting_frame.jpg",
  "frame_source": "provided",           // hoặc "generated"
  "image_prompt": null,
  "aspect_ratio": "9:16", "resolution": "1080p", "duration_s": 8,
  "watermark_removed": true, "video_bytes": 8123456,
  "seed_used": 42, "project_id": "...", "account_id": "flow_main", "elapsed_s": 96.4
}
```

## 4. files & lưu trữ

- Ảnh: `out/nodes/<run_id>/` (do `FlowClient` tạo, kèm `meta.json`).
- Video: `out/nodes/video_<ts>/` gồm `starting_frame.*`, `video.mp4`, `manifest.json`.
- Serve qua `GET /api/node/files/{run_id}/{filename}` (chặn path traversal).
- Upload ảnh đính kèm: dùng `POST /api/upload` hiện có → trả `url: /api/uploads/<name>`.

## 5. Hành vi & giới hạn đã biết

| Chủ đề | Trạng thái |
| :--- | :--- |
| Tuần tự hoá trình duyệt | `MediaService` dùng **một RLock/process cho mỗi CDP endpoint** (`media_service.cdp_lock`); nhiều node chạy song song sẽ xếp hàng thay vì tranh tab |
| Đa tiến trình | Lock chỉ trong 1 process; chạy nhiều server cùng CDP vẫn có thể tranh tab |
| Cache ảnh tham chiếu | `ReferenceMediaRegistry` (account + sha256) dùng chung với batch/pipeline |
| Watermark video | Xoá trong `MediaService` (core video không tự xoá); ảnh xoá trong `FlowClient` |
| Text-to-video | **Chưa có** — cần capture evidence bằng `discovery/probe_video_composer.py` |
| Tỷ lệ ảnh khác 16:9 | **Chưa verify** — capture bằng `discovery/capture_image_aspects.py` |
| Chất lượng/thời lượng video | 8s cố định; 1080p upsample với fallback 720p |

## 6. Ví dụ curl

```bash
# options
curl http://127.0.0.1:4000/api/node/options

# ảnh 16:9 có ảnh đính kèm
curl -X POST http://127.0.0.1:4000/api/node/image \
  -H "content-type: application/json" \
  -d '{"prompt":"a red apple","aspect_ratio":"16:9","reference_image_path":"/api/uploads/1730000000000_dress.png","confirm":true}'

# video 9:16 từ ảnh đã tạo
curl -X POST http://127.0.0.1:4000/api/node/video \
  -H "content-type: application/json" \
  -d '{"prompt":"slow push-in","aspect_ratio":"9:16","frame_path":"/api/node/files/<run_id>/out.jpg","confirm":true}'
```
