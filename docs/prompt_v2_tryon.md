# Prompt try-on V2 — bản cập nhật theo phân tích

Tài liệu này ghi lại **phân tích V1 → V2** cho prompt ảnh thử đồ và những gì đã đổi trong
`prompt-skills/try-on-image-prompter.md`. Mục tiêu không phải "viết prompt hay hơn" mà là **bỏ
xung đột** — V1 đã dài và chi tiết, nhưng có 6 chỗ các mệnh lệnh tự phủ định nhau.

- Phạm vi: chỉ prompt **ảnh** try-on/plate. Prompt video vẫn thuộc `lookbook-video-prompter`.
- Không đổi: pipeline, node, API, thư viện pose, hai mốc `76%` / `50mm`.
- Bằng chứng: `tests/test_tryon_prompt_v2.py` (khoá từng xung đột) + toàn bộ test prompt/pose hiện có.

## 1. Đánh giá V1

| Hạng mục | Điểm | Ghi chú |
| :--- | :--- | :--- |
| Identity preservation | 9/10 | Xác định rõ đặc điểm cần giữ |
| Garment fidelity | 9/10 | Mô tả cấu trúc, layering, chất liệu kỹ |
| Pose control | 8/10 | Nhiều thông số, nhưng thiếu hướng đầu |
| Camera & composition | 8/10 | Có framing, góc, tiêu cự, occupancy |
| Instruction consistency | 5/10 | Mệnh lệnh đá nhau ở 3 cặp |
| Prompt efficiency | 5/10 | Negative lặp ~70 cụm cho ~6 lỗi |

Điểm mạnh: chia khối theo nhiệm vụ thay vì một đoạn văn dài. Điểm yếu: nhiều cặp mệnh lệnh cùng
giải quyết một vấn đề theo hai hướng ngược nhau.

## 2. Sáu lỗi và cách V2 xử lý

| # | Mức | Lỗi ở V1 | V2 |
| :--- | :--- | :--- | :--- |
| 1 | Critical | Vừa `preserve proportions from Image 1` vừa `seven-and-a-half head-to-body ratio` | Bỏ hẳn tỷ lệ cố định; Ảnh 1 là **tham chiếu tỷ lệ duy nhất** |
| 2 | Critical | Ảnh 3 bị nhắc như thể luôn tồn tại, và bối cảnh lấy từ Ảnh 2 khi thiếu | Hai nhánh rõ ràng: có Ảnh 3 → chỉ lấy môi trường; không có → studio mô tả sẵn |
| 3 | High | Positive "đọc ra cao" + Negative `no tall and slim` | Bỏ câu positive về dáng, bỏ `no tall and slim`; chỉ còn "height through posture / framing / distance" |
| 4 | High | Thân xoay 30–45° nhưng không nói mặt hướng đâu | Thêm `head turned gently back toward the camera` vào cả template và Mode A/B |
| 5 | High | Garment Lock đòi chép đúng mọi chi tiết nhưng Negative cấm `logo` | Negative chỉ cấm **logo bịa thêm**; logo có thật trên đồ phải giữ |
| 6 | Medium | Negative ~70 cụm, lặp cùng một lỗi 3–4 lần | Gom 5 nhóm; bỏ các cụm trùng và các cụm đã được module 1–6 xử lý |

Ngoài 6 lỗi trên, tài liệu phân tích còn đúng ở hai điểm kỹ thuật:

- **50mm không tạo nén phối cảnh.** Nén do khoảng cách máy–chủ thể. V2 khoá thêm
  `same subject-to-camera distance`; chỉ giữ `50mm` như hướng thẩm mỹ + khoá trường nhìn.
- **Chi tiết bị che không được bịa.** V2 thêm quy tắc: chi tiết nhìn thấy → chép đúng; chi tiết bị
  che → không suy diễn; không sửa thiết kế để đồ trông đẹp hơn trong ảnh.

## 3. Kiến trúc V2 — 7 module

Thứ tự dưới đây **là thứ tự ưu tiên khi hai mục tiêu xung đột**, không chỉ là thứ tự trình bày:

| # | Module | Mức | Nội dung |
| :--- | :--- | :--- | :--- |
| 1 | `[IDENTITY LOCK]` | Critical | Mặt, mắt, mũi, môi, tóc, da từ Ảnh 1. Không beautify, không làm thon mặt |
| 2 | `[GARMENT FIDELITY]` | Critical | Phom, màu, chất liệu, may, layering, branding có thật trên đồ |
| 3 | `[ANATOMY & POSE]` | High | Tỷ lệ gốc + tư thế + **hướng đầu tách khỏi hướng thân** |
| 4 | `[HEIGHT & PROPORTION OPTIMIZATION]` | High | Cách máy ghi lại cơ thể: góc, khoảng cách, tiêu cự, bố cục, silhouette |
| 5 | `[ENVIRONMENT & LIGHTING]` | Medium | Ảnh 3 nếu có, không thì studio mô tả sẵn |
| 6 | `[PHOTOGRAPHY AESTHETICS]` | Medium | Da thật, vân vải, film grain, editorial |
| 7 | `Negative` | Low | 5 nhóm lỗi, không lặp lại module 1–6 |

Thứ tự hy sinh khi bất khả kháng: **identity → garment → anatomy → presentation**. Không đổi khuôn
mặt, không đổi thiết kế đồ, không kéo giãn cơ thể chỉ để được một tư thế đẹp hơn.

## 4. Đã đo được gì

Đo trên cùng file, trước và sau (template chưa điền tên món đồ):

| Chỉ số | V1 | V2 | Ghi chú |
| :--- | ---: | ---: | :--- |
| Ký tự template | 5.855 | 5.237 | −10,5% |
| Ký tự Negative | 1.413 | 938 | −33,6% |
| Số cụm Negative | ~70 | 43 | 5 nhóm, không lặp |
| Xung đột positive ↔ negative | 3 cặp | 0 | có test khoá |
| Tỷ lệ đầu-thân cố định | có | không | có test khoá |
| Nhánh Ảnh 3 | 1 (ngầm định) | 2 (tường minh) | có test khoá |

Sau khi điền danh sách trang phục thật, prompt rơi vào khoảng 5,5–5,8k ký tự — dưới trần
`max_prompt_chars = 7200` trong `configs/limits.json`.

**Không kết luận V2 cho ảnh đẹp hơn.** Ít xung đột hơn là điều kiện cần, không phải điều kiện đủ.
Phải so sánh bằng ảnh thật, cùng model và cùng bộ ba ảnh tham chiếu.

## 5. Giữ nguyên có chủ đích

| Thứ | Lý do |
| :--- | :--- |
| `76%` occupancy + `12%` headroom/footroom | Đã hiệu chuẩn từ batch 8 ảnh thật (`prompt-skills/poses/results/`) |
| `50mm` + `waist level` + tilt `3°` + `horizon level` | Cặp thông số dùng chung với thư viện pose; đổi một cái là lệch cả bộ |
| Neo `168 cm` + `7.5 đầu` trong `poses_reference.md` | Ở đó người mẫu là **nhân vật tự định nghĩa**, không phải người trong ảnh khách. Đây là ngoại lệ có ghi chú, không phải chỗ bị bỏ sót |
| 7 nhóm của khối Height | Cấu trúc này đang được linter và test canh; V2 chỉ đổi nội dung bên trong |
| Toàn bộ §2.2.1a (chọn pose) và §2.5 (plate) | Không liên quan tới 6 lỗi; đã có test riêng |

## 6. Cách so sánh V1 và V2

Chuẩn bị **một** bộ ba ảnh (model, garment, background) và **một** model/thiết lập sinh ảnh. Sinh
mỗi bản 3 lần, cùng seed nếu có. Chấm theo thứ tự ưu tiên ở §3:

1. **Identity** — mặt còn đúng người Ảnh 1 không? (đặt cạnh Ảnh 1, nhìn mắt/mũi/hàm)
2. **Garment** — đúng phom, đúng màu, đủ chi tiết, logo có thật còn nguyên?
3. **Anatomy** — chiều cao/vai/chân khớp Ảnh 1, không bị kéo giãn?
4. **Presentation** — thân ba phần tư, mặt vẫn đọc được, chân tách rõ, không cắt đầu/gót?
5. **Artifact** — tay/chân lỗi, vải dính, chữ hoặc UI lọt vào khung?

Ghi kết quả vào bảng 2 cột (V1 / V2) theo từng lần sinh. Nếu V2 thắng ở 1–3 nhưng hoà hoặc thua ở 4,
giữ V2 — vì 4 là thứ có thể sửa bằng pose, còn 1–3 là thứ không sửa được sau khi render.

## 7. Rủi ro còn lại

- **Occupancy 84–88%** cho ảnh bán trang phục chỉ là gợi ý **chưa hiệu chuẩn**. Muốn dùng phải chạy
  một batch 8 ảnh như lần hiệu chuẩn `76%`, và đổi cho **cả bộ**, không đổi từng ảnh.
- **Negative ngắn hơn** có thể làm tăng nhẹ lỗi chân ở model yếu. Nếu batch đầu tiên cho thấy vậy,
  thêm lại đúng một cụm (`no overlapping thighs`) — đừng thêm lại cả danh sách cũ.
- **Ảnh 3 thiếu** giờ mặc định về studio trơn thay vì bối cảnh Ảnh 2. Nếu người dùng muốn giữ bối
  cảnh gốc, phải nói rõ trong ghi chú node — đây là thay đổi hành vi có chủ đích, không phải bug.
