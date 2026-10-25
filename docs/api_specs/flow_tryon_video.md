# Đặc tả Quy trình Tự Động Hóa Affiliate Try-On & Transfer Model (Gemini + Google Flow)

> Tài liệu này mô tả chi tiết giải pháp **tối ưu hóa tự động** quy trình tạo ảnh thử đồ (try-on) và sản xuất video đôi (Video 1 + Video 2) cho người mẫu ảo **Nabi** phục vụ affiliate marketing trên Shopee, TikTok Shop và Reels, hỗ trợ cả **người dùng tự chọn ảnh transfer model** lẫn nguồn Shopee/thư mục cục bộ.

---

## 1. Đối chiếu: Quy trình Thủ công vs Quy trình Tự động (Deterministic Automation)

| Tiêu chí | Quy trình Thủ công (Trước đây) | Quy trình Tự Động Hóa (Mới) |
| :--- | :--- | :--- |
| **Chọn ảnh Transfer Model** | Người dùng tự chọn ảnh trang phục / transfer model và tải về máy. | **Người dùng chủ động chỉ định file** `--garment-path` / `--transfer-image`, hoặc dùng thư mục `--product-dir` / `--extra-images`. Bỏ ràng buộc bắt buộc phải crawl Shopee. |
| **Tạo Prompt Ảnh (Gemini)** | Mở `gemini.google.com/notebook/7fc78691-...`, kéo thả ảnh Nabi + mẫu thử, gõ `@try-on-prompter create image prompt`, copy text. | `GeminiNotebookBridge` tự động attach file qua CDP (cổng 4022), gửi prompt `@try-on-prompter`, bóc tách prompt tạo ảnh sạch. |
| **Tạo First Frame (Flow)** | Vào `flow.google.com`, tải ảnh lên, chọn model @nabi, dán prompt (1), chờ tạo ảnh. | `FlowVideoBridge` tự động đẩy prompt và ảnh tham chiếu transfer model vào Flow composer, bắt luồng render và tải về `first_frame.png`. |
| **Tạo Prompt Video (Gemini)** | Quay lại Gemini, upload First Frame, gõ `@try-on-prompter create video prompt`, copy 2 prompt 8s. | Tự động tải `first_frame.png` lên Gemini tab, gửi lệnh và trích xuất `video_prompt_1` + `video_prompt_2` (8s mỗi đoạn). |
| **Tạo Video 1 & Lưu Last Frame** | Chọn First Frame làm starting frame, tạo Video 1. Chờ render xong, click video, click menu góc phải trên để "Lưu last frame". | `FlowVideoBridge` tự động chạy Video 1. Trích xuất **Last Frame bằng FFmpeg bit-exact** (`-sseof -0.2`): 100% chính xác từng pixel, không phụ thuộc UI selector, 0 latency. |
| **Tạo Video 2 & Nối Video** | Lấy last frame làm first frame cho Video 2, dán prompt 2, tạo video 2. Tải 2 video về máy rồi tự mở app dựng để ghép. | Tự động đẩy last frame làm starting frame cho Video 2, tạo video 2. **Tự động nối Video 1 (8s) + Video 2 (8s) thành Video 16s hoàn chỉnh** (`final_tryon_video_16s.mp4`). |
| **Thời gian thao tác của người** | 10 – 15 phút (phải ngồi canh từng bước) | **0 phút** (Chạy 1 lệnh duy nhất hoặc 1 click trên WebUI) |

---

## 2. Kiến trúc 4 Lớp Module

```text
[ User Chosen Transfer Image / Product Folder ]
                     │
                     ▼
┌──────────────────────────────────────────────┐
│  1. Ingestion & Validation                   │
│     - Model path: @nabi (assets/nabi_model)  │
│     - Transfer model: --garment-path         │
│     - Optional: --product-dir/--extra-images │
└──────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────┐
│  2. GeminiNotebookBridge (CDP Port 4022)     │
│     - Notebook: 7fc78691-ccce-46a9-9f51-...  │
│     - Upload Nabi + Transfer Image           │
│     - Gửi: @try-on-prompter                  │
│       => Image Prompt (1)                    │
└──────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────┐
│  3. Google Flow First Frame Generator        │
│     - Model @nabi + Garment Image            │
│     - Prompt (1)                             │
│     => first_frame.png                       │
└──────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────┐
│  4. GeminiNotebookBridge (Lần 2)             │
│     - Upload first_frame.png                 │
│     - Gửi: @try-on-prompter create video...  │
│     => video_prompt_1 (8s) & video_prompt_2  │
└──────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────┐
│  5. Flow Video Chaining & FFmpeg Stitch      │
│     - First Frame + Prompt 1 => video_1.mp4  │
│     - Trích xuất: last_frame_video_1.png     │
│     - Last Frame + Prompt 2 => video_2.mp4   │
│     - Ghép FFmpeg: final_tryon_video_16s.mp4 │
└──────────────────────────────────────────────┘
```

---

## 3. Cách Sử Dụng

### 3.1. Chạy CLI với ảnh Transfer Model do người dùng tự chọn

```bash
# 1. Chạy với ảnh mẫu thử tự chọn:
python -m src.Workflows.auto_tryon_pipeline \
    --garment-path "path/to/my_garment.png" \
    --model-path "assets/nabi_model.png"

# 2. Chạy thử nghiệm Dry-run (0 credit, xác thực toàn bộ parser, file, FFmpeg):
python -m src.Workflows.auto_tryon_pipeline \
    --garment-path "path/to/my_garment.png" \
    --model-path "assets/nabi_model.png" \
    --dry-run

# 3. Kèm thư mục ảnh sản phẩm bổ sung:
python -m src.Workflows.auto_tryon_pipeline \
    --garment-path "path/to/my_garment.png" \
    --product-dir "path/to/product_extras"
```

### 3.2. Chạy qua WebUI API / Playground

```bash
# Khởi động WebUI Flow Bench (port mặc định 4000):
python -m src.WebUI.app --port 4000

# Gửi yêu cầu tự động hóa với ảnh transfer model:
POST /api/tryon/start
{
  "garment_path": "path/to/chosen_garment.png",
  "model_path": "assets/nabi_model.png",
  "dry_run": false,
  "confirm": true,
  "auto_stitch": true
}

# Xem danh sách các mẻ video đã hoàn thành:
GET /api/tryon/runs
```

---

## 4. Cấu trúc Output của Mỗi Lần Chạy

Mỗi lần chạy sẽ sinh ra một thư mục riêng biệt tại `out/affiliate_runs/tryon_<timestamp>/`:

- `image_prompt.txt`: Prompt tạo ảnh First Frame bóc tách từ Gemini.
- `prompts.json`: Metadata chứa cả 3 prompt (Image Prompt, Video Prompt 1, Video Prompt 2).
- `first_frame.png`: Ảnh First Frame tạo từ Google Flow.
- `video_1.mp4`: Video đoạn 1 (8 giây).
- `last_frame_video_1.png`: Khung hình cuối trích xuất chính xác từ Video 1.
- `video_2.mp4`: Video đoạn 2 (8 giây) tiếp nối nhịp chuyển động của Video 1.
- `final_tryon_video_16s.mp4`: **Video 16 giây hoàn chỉnh đã ghép nối**, sẵn sàng đăng tải ngay lập tức.
- `manifest.json`: Báo cáo chi tiết toàn bộ tham số, thời gian thực thi và đường dẫn file.
