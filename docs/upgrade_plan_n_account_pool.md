# Kế Hoạch Nâng Cấp `flow-reverse`: Dynamic N-Account Pool & Pipeline 100 Ảnh Long-Form

> Nguồn: [Gemini Share — Kế hoạch nâng cấp flow-reverse](https://share.gemini.google/NzCdQdo4ouTQ) · Lưu vào repo ngày 2026-10-18.

Tài liệu này định nghĩa lộ trình nâng cấp kiến trúc của repo `flow-reverse` từ mô hình đơn tài khoản thành hệ thống **Dynamic N-Account Pool** (co giãn linh hoạt theo số lượng tài khoản thực tế người dùng đang có và khối lượng ảnh cần tạo) cùng quy trình sản xuất **100 ảnh (`text2image` + `image2image`)** đồng nhất cho video dài (long-form).

## Phần 1: Mô Hình Toán Học & Cơ Chế Cấp Phát Theo Ngưỡng Khối Lượng

Thay vì mở và sử dụng 100% số tài khoản hiện có cho mọi tác vụ, hệ thống quản lý dựa trên 4 biến số cốt lõi:

- N: **Tổng số tài khoản khả dụng** người dùng đang có trong `./browser_vault/` hoặc `configs/accounts_pool.json` (N ≥ 1).
- J: **Tổng số ảnh cần tạo** trong đợt chạy hiện tại (Batch / Storyboard size).
- Q_target: **Ngưỡng tải chuẩn trên mỗi tài khoản** (`target_jobs_per_account`, mặc định Q_target = 25 ảnh/account). Đây là ngưỡng an toàn để một tài khoản xử lý liên tục trong 1 phiên mà không kích hoạt cảnh báo bất thường và không làm loãng bộ nhớ đệm ảnh gốc (`image2image`).
- M_RAM: **Trần trình duyệt mở song song tối đa theo phần cứng** (`max_active_browsers`, mỗi phiên CloakBrowser có giao diện chiếm ≈ 450–650 MB RAM).

### 1.1. Công thức tính Số lượng Tài khoản Cần Huy động (N_alloc)

Khi người dùng gửi một yêu cầu tạo J ảnh, số lượng tài khoản thực tế được phép đưa vào tổ đội chạy đợt đó (N_alloc) được quyết định bởi công thức:

```text
N_alloc(J) = min(N, M_RAM, max(1, ⌈ J/Q_target ⌉))
```

Số tài khoản còn lại N_standby = N - N_alloc được giữ ở trạng thái **Nghỉ dự phòng (`STANDBY` / `HIBERNATED`)**, hoàn toàn không bị đánh thức trình duyệt nếu không cần thiết.

### 1.2. Bảng minh họa cấp phát với Q_target = 25 ảnh/account (Ví dụ User có N = 4 hoặc N = 8 Accounts)

| Số ảnh yêu cầu (J) | Số Account hiện có (N) | Số Account được cấp phát (N_alloc) | Số Account nghỉ dự phòng (N_standby) | Hành vi của Hệ thống (Wear-Leveling & Caché) |
| --- | --- | --- | --- | --- |
| J = 1 … 25 ảnh | 4 accounts | 1 account | 3 accounts | Chỉ mở 1 trình duyệt xử lý gọn trong ≈ 8 phút; 3 tài khoản kia hoàn toàn không bị đụng tới. |
| J = 50 ảnh | 4 accounts | 2 accounts (⌈ 50/25 ⌉ = 2) | 2 accounts | Đúng chuẩn yêu cầu: Chỉ rút 2 tài khoản (acc_01, acc_02) ra chạy (mỗi acc 25 ảnh). Lần chạy 50 ảnh tiếp theo sẽ tự động ưu tiên gọi acc_03, acc_04. |
| J = 75 ảnh | 4 accounts | 3 accounts (⌈ 75/25 ⌉ = 3) | 1 account | Huy động 3 tài khoản chạy song song, giữ 1 tài khoản làm dự phòng nóng (Hot-Spare). |
| J = 100 ảnh | 4 accounts | 4 accounts (⌈ 100/25 ⌉ = 4) | 0 accounts | Huy động toàn bộ 4 tài khoản, mỗi tài khoản gánh đúng định mức 25 ảnh. |
| J = 100 ảnh | 8 accounts | 4 accounts (⌈ 100/25 ⌉ = 4) | 4 accounts | Dù có 8 tài khoản cũng chỉ dùng 4 tài khoản cho 100 ảnh để tối ưu lượt upload ảnh mẫu image2image và tiết kiệm 50% RAM. |

### 1.3. Ba lợi ích lớn của cơ chế Giới hạn theo Ngưỡng (Q_target)

1. **Giảm tối đa chi phí Upload lại ảnh tham chiếu (`image2image`):**
   Nếu một kịch bản 50 ảnh có 3 nhân vật chính mà phân tán ra cả 4 tài khoản, hệ thống phải upload 3 × 4 = 12 lượt ảnh gốc. Khi giới hạn lại đúng N_alloc = 2 tài khoản, số lượt upload giảm một nửa và tỷ lệ trúng bộ nhớ đệm (`ReferenceMediaRegistry`) tăng gấp đôi.
2. **Bảo vệ an toàn cho tập tài khoản (Blast-Radius Isolation & Wear-Leveling):**
     - Khi chạy đợt 1 gồm 50 ảnh, chỉ có `acc_01` và `acc_02` hoạt động.
     - Khi bạn chạy đợt 2 gồm 50 ảnh tiếp theo, thuật toán chọn tài khoản có `total_completed` và `last_used_at` thấp nhất sẽ tự động chọn `acc_03` và `acc_04`, giúp `acc_01` và `acc_02` có hàng giờ nghỉ ngơi tự nhiên.
3. **Cơ chế Dự phòng Nóng (Hot-Spare Auto-Promotion):**
   Nếu đang chạy đợt 50 ảnh với 2 tài khoản (`acc_01`, `acc_02`) mà `acc_02` bất ngờ gặp lỗi `429 Rate Limit` hoặc hết hạn phiên (`AUTH_EXPIRED`), `AccountPoolManager` sẽ tự động rút `acc_02` ra và **đánh thức ngay 1 tài khoản đang dự phòng (`acc_03`)** vào thế chỗ để giữ nguyên tốc độ xử lý 2 luồng mà không làm gián đoạn batch.

## Phần 2: Giải Quyết Bài Toán `image2image` Xuyên Suốt N_alloc Tài Khoản

Trên `flow.google.com`, lệnh gọi RPC `image2image` truyền **`media_id`** đã được tải lên project của tài khoản đó. Vì `media_id` không dùng chung giữa các tài khoản, hệ thống kết hợp **Batch Working-Set Selection** và **Sticky Reference Affinity**:

1. **Khi chọn N_alloc tài khoản đầu mỗi Batch:**
     - Ưu tiên số 1: Các tài khoản khỏe mạnh đã từng lưu `media_id` của các file `reference_image_path` xuất hiện trong Batch đó.
     - Ưu tiên số 2: Các tài khoản ít sử dụng nhất (Wear-Leveling: `total_completed` thấp nhất, `last_used_at` xa nhất).
2. **Trong quá trình chạy từng Shot trong Batch:**
     - Chỉ phân phối job trong phạm vi tập N_alloc tài khoản đã được cấp phát cho Batch.
     - Nếu shot `image2image` rơi vào một tài khoản trong tập N_alloc chưa có `media_id` của ảnh gốc, hệ thống mới thực hiện **Lazy Upload** đúng 1 lần và ghi vào `configs/reference_media_cache.json`.

## Phần 3: Chiến Lược Sản Xuất 100 Ảnh Cho Video Long-Form

Để bộ 100 ảnh phục vụ video dài (10–20 phút) đồng nhất về nhân vật và ánh sáng, quy trình xử lý được chia làm **3 Pha**:

### Pha 1: Khởi tạo "Visual Bible" — Tạo 10 đến 12 Ảnh Mốc (Anchor Assets) bằng `text2image`

- Vì Pha 1 chỉ có J ≈ 10–12 ảnh (< Q_target = 25), hệ thống tự động tính N_alloc(12) = ⌈ 12 / 25 ⌉ = 1 tài khoản (hoặc tối đa 2 nếu người dùng ép chạy nhanh).
- Tạo ảnh chân dung/bán thân nhân vật chính (`char_01_master.png`) và các bối cảnh cố định (`loc_01_master.png`) kèm chuỗi hậu tố phong cách (`style_suffix`) xuyên suốt.

### Pha 2: Phân bổ Storyboard vào `storyboard_manifest.json`

Chia danh sách shots thành 3 nhóm có quan hệ phụ thuộc (`depends_on_shot_id`):

| Nhóm cảnh (Shot Category) | Tỷ trọng dự kiến | Chế độ gọi API | Cách xử lý trong Pipeline |
| --- | --- | --- | --- |
| Nhóm A: Ảnh Gốc & Cảnh Toàn (Master / Anchor Shots) | ≈ 12–15% | text2image | Chạy ở Đợt 1 (Stage 1) với N_alloc(Stage 1) tài khoản. Kết quả đầu ra làm reference_image_path cho Nhóm B. |
| Nhóm B: Cảnh Nhân Vật & Hành Động Liên Tục (Continuity Shots) | ≈ 55–60% | image2image | Chạy ở Đợt 2 (Stage 2) với N_alloc(Stage 2) tài khoản. Tham chiếu tới ảnh Nhóm A kèm prompt mô tả góc máy và biểu cảm mới. |
| Nhóm C: Cảnh B-Roll, Chi Tiết, Ẩn Dụ (Insert / B-Roll Shots) | ≈ 25–30% | text2image | Chạy song song ở Đợt 2 (Stage 2) trên các tài khoản nằm trong tập N_alloc đang rảnh. |

### Pha 3: Đặt tên file chuẩn Dựng Phim (NLE-Ready Naming)

Toàn bộ ảnh xuất ra được đặt tên tự động:
`outputs/<project_slug>/scene_001_shot_001_t2i.png`, `scene_001_shot_002_i2i.png` để kéo thả thẳng vào Premiere Pro, DaVinci Resolve hoặc CapCut.

## Phần 4: Kiến Trúc Nâng Cấp Trong Repo `flow-reverse`

```
flow-reverse/
├── browser_vault/                      # Tự động quét N thư mục profile hiện có
│   ├── acc_01/                         # Cổng CDP: 9222 + Seed cố định
│   ├── acc_02/                         # Cổng CDP: 9223 + Seed cố định
│   └── acc_N/                          # Cổng CDP: 9222 + (N - 1)
├── configs/
│   ├── accounts_pool.json              # Cấu hình target_jobs_per_account (25), max_active_browsers, accounts[]
│   ├── reference_media_cache.json      # Lưu: account_id -> {sha256(file): media_id}
│   └── storyboard_100.json             # Kịch bản shots (50, 100 hoặc bất kỳ số lượng J nào)
└── src/
    ├── BrowserHost/
    │   ├── launch_profile.py           # (Cập nhật) Chỉ khởi chạy trình duyệt cho các account thuộc tập N_alloc
    │   └── pool_supervisor.py          # (Mới) Đánh thức / đóng băng CloakBrowser theo yêu cầu của Pool
    ├── Workflows/
    │   ├── flow_models.py              # (Cập nhật) Thêm trường mode ("t2i"|"i2i"), reference_image_path
    │   ├── flow_client.py              # (Cập nhật) Thêm upload_reference_image() và hỗ trợ reference_media_id
    │   └── account_pool.py             # (Mới) Bộ điều phối N-Account có Demand-Based Allocation & Hot-Spare Failover
    └── WebUI/
        ├── jobs.py                     # (Cập nhật) Tính N_alloc trước mỗi batch và đẩy qua AccountPoolManager
        └── app.py                      # (Cập nhật) API cấu hình target_jobs_per_account và giám sát Active vs Standby
```

## Phần 5: Danh Sách Nhiệm Vụ Giao Cho Team AI Agent (OpenCode Prompts)

### Task 1: Tự động phát hiện N Profiles & Khởi chạy theo yêu cầu (On-Demand Launch)

> "Đọc `src/BrowserHost/launch_profile.py`. Nâng cấp để hệ thống quét toàn bộ các profile trong `./browser_vault/` hoặc `configs/accounts_pool.json`, nhưng **không mở đồng loạt tất cả trình duyệt lúc khởi động**. Chỉ mở CloakBrowser cho những tài khoản nằm trong tập cấp phát N_alloc mà `AccountPoolManager` yêu cầu."

### Task 2: Bổ sung `image2image` & Upload Reference vào `flow_client.py`

> "Đọc `docs/api_specs/flow_create_image.md`, `src/Workflows/flow_models.py` và `src/Workflows/flow_client.py`. Mở rộng `FlowClient` thêm phương thức `upload_reference_image(file_path, project_id) -> media_id` và cập nhật `generate_image()` nhận `reference_media_id` tùy chọn cho chế độ `image2image`."

### Task 3: Tích hợp `AccountPoolManager` có Demand-Based Scaling vào `jobs.py` & `app.py`

> "Tích hợp `src/Workflows/account_pool.py` vào `src/WebUI/jobs.py` và `src/WebUI/app.py`. Đảm bảo khi người dùng gửi một batch J ảnh, hệ thống tự động tính N_alloc = min(N, M_RAM, ⌈ J / Q_target ⌉) (mặc định Q_target = 25 ảnh/account; ví dụ có 4 account nhưng tạo 50 ảnh thì chỉ cấp phát 2 account chạy chính và giữ 2 account ở chế độ Standby dự phòng nóng)."

### Task 4: Cập nhật Giao diện WebUI hiển thị Active Working Set vs. Standby Pool

> "Cập nhật `web/src/components/TopBar.tsx`, `ComposePanel.tsx` và `JobConsole.tsx` để hiển thị rõ: Tổng số tài khoản hiện có (N), Số tài khoản được huy động cho batch hiện tại (N_alloc), Số tài khoản dự phòng (`STANDBY`), và cho phép người dùng tùy chỉnh thông số `target_jobs_per_account` (mặc định 25 ảnh/account) ngay trên giao diện."