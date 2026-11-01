# Lookbook HyperFrames — Kế hoạch gốc + Phân tích năng lực source hiện tại

> Tài liệu lưu **nguyên văn** kế hoạch chuyển pipeline Lookbook sang **HyperFrames** (Phần A),
> rồi đối chiếu với năng lực **thực tế** của repo `rev-flow` (Phần B–D), kèm bằng chứng `file:line`
> và danh sách lỗ hổng cần bổ sung.
>
> Trạng thái repo lúc phân tích: nhánh `main`, HEAD `b912aa2`, có 4 file đang sửa dở ở working tree
> (`configs/accounts_pool.json`, `discovery/probe_video_composer.py`, `src/Bridge/flow_bridge.py`,
> `src/Bridge/flow_video_bridge.py`).

---

# PHẦN A — KẾ HOẠCH GỐC (nguyên văn)

Sử dụng **HyperFrames** (nền tảng dựng video bằng HTML/CSS/JS & Agent của HeyGen) là một bước đi cực kỳ thông minh cho dạng video Lookbook này.

Sai lầm lớn nhất khi làm video Lookbook hiện tại là **bắt AI Video (Veo/Flow/Kling) gánh cả phần giao diện cột trái lẫn phần người mẫu bên phải**. AI tạo video rất giỏi làm chuyển động người thật, nhưng lại rất tệ trong việc làm hiệu ứng UI sắc nét, giữ chữ không bị méo và căn nhịp (timing) chuẩn từng mili-giây.

Khi đưa vào **HyperFrames**, bạn sẽ tách bạch hoàn toàn: **AI Video chỉ lo phần người mẫu**, còn **HyperFrames dùng sức mạnh của HTML/CSS/GSAP Animation để làm cột Item bên trái và hệ thống Text giữ chân**.

## 1. Sử dụng HyperFrames thì bạn Edit được những gì? (Vũ khí giữ chân)

Vì bản chất HyperFrames render các phần tử Web (DOM, CSS3, SVG, Canvas) thành MP4 ở 60fps chuẩn xác từng khung hình, bạn làm được những thứ mà AI tạo video thông thường không thể làm được:

1. **Tự động hóa "Active Item Card" (Cột trái sống động 100%):**
   - Thay vì 4 món đồ đứng đơ trên 1 tấm thẻ trắng phẳng lì, bạn chia cột trái thành **4 thẻ (Card) riêng biệt**.
   - Khi video chạy đến đoạn giới thiệu món nào (ví dụ giây thứ 2 nói về Áo yếm), thẻ `HALTER TOP` sẽ tự động **phóng to 115% (`transform: scale(1.15)`), bật viền phát sáng (Glow/Drop-shadow), đổi màu nền sang tone pastel**, trong khi 3 món còn lại mờ nhẹ đi (`opacity: 0.4`). Mắt người xem sẽ bị điều hướng cưỡng bức vào đúng món đồ đó.

2. **Kinetic Typography & Micro-Badges (Chữ chuyển động giữ chân):**
   - **Hook Banner (0s - 3s):** Chữ chạy hiệu ứng Typewriter (gõ chữ) hoặc trượt mượt (Slide-in) kèm hiệu ứng kính mờ (`backdrop-filter: blur(10px)`).
   - **Callout Tags (Nhãn chỉ điểm):** Vẽ một đường kẻ SVG tự động chạy từ chiếc áo trên người mẫu nối thẳng sang thẻ `HALTER TOP` bên trái kèm tag chữ nhỏ (ví dụ: *"Che khuyết điểm bắp tay"*, *"Lưng trần quyến rũ"*).

3. **Thanh tiến trình thông minh (Segmented Progress Bar):**
   - Chia thanh thời gian ở đáy hoặc đỉnh video thành 4 đốt: `1. Top` ➔ `2. Jeans` ➔ `3. Bag` ➔ `4. Full Vibe`. Người xem nhìn thấy cấu trúc 4 phần sẽ có tâm lý **chờ xem hết cả 4 đốt**.

4. **Zoom & Pan động vào Video Raw:**
   - Ngay cả khi video raw AI chỉ quay toàn thân, trong HyperFrames bạn có thể dùng CSS `transform: scale(1.35) translateY(...)` để tự động **Zoom cận cảnh** vào chiếc túi cói hoặc cạp quần Jeans ở giây thứ 8 mà không cần AI phải tự đổi góc máy.

## 2. Danh sách đầy đủ các Assets bạn cần chuẩn bị

Để đưa vào thư mục project của HyperFrames, bạn hãy chuẩn bị bộ nguyên liệu tách rời (Modular Assets) thay vì gộp chung vào 1 ảnh như trước:

### A. Video Raw (Khung bên phải - Cần làm những gì?)

- **Thay đổi quan trọng nhất:** Bạn **KHÔNG** tạo video từ bức ảnh ghép có sẵn cột trái nữa, hoặc nếu lỡ tạo từ ảnh ghép như video trên, bạn sẽ dùng HyperFrames **cắt bỏ (crop) 1/3 bên trái đi**, chỉ lấy phần người mẫu bên phải (tỷ lệ khoảng `65%` chiều ngang màn hình) để đè cột trái HTML sắc nét của HyperFrames lên.
- **Nội dung Video Raw (14s - 16s, nối từ 2 clip 8s):**
  - **Clip Raw 1 (0s - 8s):**
    - *0s - 3s:* Người mẫu bước nhẹ tới trước, nhìn thẳng ống kính cười tươi, một tay chạm nhẹ vào cổ áo yếm caro đỏ (giữ Eye-contact tuyệt đối, **không** quay lưng ngay ở giây thứ 1 như video cũ).
    - *3s - 8s:* Người mẫu xoay 360 độ mượt mà khoe tấm lưng trần với dây buộc nơ của áo yếm và độ ôm vòng 3 của quần Jeans ống loe, ánh mắt ngoái nhìn qua vai.
  - **Clip Raw 2 (8s - 16s):**
    - *8s - 12s:* Người mẫu đứng nghiêng 45 độ, tay nâng nhẹ chiếc túi cói `TOTE BAG` trên vai, mắt liếc nhẹ xuống túi rồi nhìn lại camera.
    - *12s - 16s:* Người mẫu thả dáng tự nhiên, bước nhẹ tạo hiệu ứng gió thổi bay tóc để làm điểm kết (Loop) mượt về giây 0:00.

### B. Các file Ảnh tách nền (PNG Transparent) cần chèn thêm

Để cột bên trái trong HyperFrames sắc nét tuyệt đối và làm được hiệu ứng 3D/Pop-up, bạn cần tách nền (`remove background`) các file ảnh tĩnh `.png` sau:

| Tên file gợi ý | Mô tả Asset | Mục đích sử dụng trong HyperFrames |
| --- | --- | --- |
| `item_1_top_front.png` | Áo yếm caro đỏ mặt trước | Hiển thị mặc định ở Card 1 |
| `item_1_top_back.png` | Áo yếm caro đỏ mặt sau (có dây nơ) | Dùng hiệu ứng **CSS 3D Card Flip** lật sang mặt sau đúng lúc mẫu xoay lưng ở giây thứ 3! |
| `item_2_jeans.png` | Quần Denim Jeans ống loe | Đặt ở Card 2 (hiệu ứng phóng to + lắc nhẹ khi mẫu khoe dáng quần) |
| `item_3_bag.png` | Túi cói Tote Bag | Đặt ở Card 3 (hiệu ứng nổi khối khi mẫu chạm vào túi) |
| `item_4_sandals.png` *(hoặc `hat.png`)* | Đôi dép cao gót quai mảnh mẫu đang mang (hoặc Mũ cói) | Đặt ở Card 4. (Khuyên dùng ảnh đôi dép mẫu đang đi thực tế dưới chân để đồng bộ 100% với video) |
| `zoom_detail_fabric.jpg` *(Tùy chọn)* | Ảnh crop cận cảnh họa tiết vải caro đỏ & viền ren trắng | Hiển thị dạng **vòng tròn kính lúp (Magnifier Circle)** bật ra ở góc màn hình tại giây thứ 2.5 để giữ chân người xem ngắm chất vải. |

### C. Audio Assets

- `bgm.mp3`: Nhạc nền có nhịp beat rõ ràng (bắt đầu vào beat ở giây thứ 2.5 - 3.0).
- `sfx_pop.mp3` & `sfx_whoosh.mp3`: Tiếng "Pop" nhẹ mỗi khi 1 thẻ quần áo bên trái phóng to và tiếng "Whoosh" khi chữ trượt ra.

## 3. Kịch bản Text On-Screen & Hiệu ứng HyperFrames (Giữ chân từng giây)

Nguyên tắc viết Text cho Lookbook thời trang để giữ chân người xem là: **Không ghi tên món đồ nhàm chán (như "Áo yếm", "Quần bò"), mà phải ghi "Nỗi đau vóc dáng + Giải pháp Hack dáng"**. Người xem sẽ phải dừng lại đọc xem bộ đồ này giải quyết được vấn đề gì.

| Mốc thời gian | Hành động trong Video Raw | Hiệu ứng Cột Trái & UI (HyperFrames) | Nội dung Text hiển thị (Đọc để giữ chân) |
| --- | --- | --- | --- |
| **0.0s - 2.5s** *(Hook)* | Mẫu nhìn thẳng ống kính, bước tới, tay chạm nhẹ cổ áo yếm. | Cả 4 item trượt vào theo nhịp domino. Khung video phải hơi zoom nhẹ từ `1.05` về `1.0`. | **Banner Kính mờ giữa màn hình:** *"Vai ngang, lưng ngắn mặc gì đi biển vừa sang vừa hack dáng?"* |
| **2.5s - 5.5s** *(Item 1: Top)* | Mẫu bắt đầu xoay lưng khoe nơ buộc sau của áo yếm caro đỏ. | **Card 1 (`HALTER TOP`)** phóng to `1.15x`, lật 3D từ mặt trước sang mặt sau (`item_1_top_back.png`). Bật kính lúp soi viền ren. | **Tag chỉ vào vai/lưng mẫu:** *"1. Áo yếm cổ V sâu: Gom dáng vai thon, khoe khéo tấm lưng trần"* |
| **5.5s - 9.0s** *(Item 2: Jeans)* | Mẫu hoàn tất vòng xoay, đứng nghiêng hông tôn đường cong và đôi chân dài. | Card 1 thu nhỏ lại. **Card 2 (`DENIM JEANS`)** sáng lên, phóng to `1.15x`. Camera tự động Pan nhẹ xuống phần hông - chân. | **Tag chỉ vào phần đùi/ống quần:** *"2. Jeans loe cạp trễ vừa: Che bắp chân to, kéo chân dài thêm 7cm"* |
| **9.0s - 12.0s** *(Item 3: Bag)* | Mẫu nâng nhẹ túi cói trên vai, liếc mắt nhìn túi rồi cười với camera. | **Card 3 (`TOTE BAG`)** nảy lên (Bounce animation) kèm viền sáng vàng ấm. | **Tag nổi cạnh túi:** *"3. Phối túi cói bản to: Cân bằng lại độ quyến rũ, thêm vibe nàng thơ Hàn Quốc"* |
| **12.0s - 15.0s** *(Item 4 & CTA)* | Mẫu đứng toàn thân, thần thái tự tin, tạo dáng chuẩn bị kết thúc. | **Cả 4 Card** cùng sáng rõ 100%. Thanh điểm số chạy từ `0` lên `9.5/10`. | **Text chốt hạ (Tạo tranh luận/Lưu video):** *"Tổng điểm bộ này: 9.5/10 ✨ Lưu lại phối ngay cho chuyến đi sắp tới!"* |

## 4. Prompt mẫu để bạn ném thẳng vào Agent của HyperFrames

Sau khi bạn đã có file video raw (`model_raw.mp4`) và 4 ảnh tách nền trong thư mục dự án, bạn chỉ cần gõ câu lệnh (Prompt) sau vào **HyperFrames Studio / CLI Agent** để nó tự code toàn bộ hiệu ứng trên cho bạn:

```text
Create a 9:16 vertical (1080x1920, 60fps, 15 seconds) high-retention fashion lookbook video using my local assets:
- Right side (68% width): Embed `model_raw.mp4` cropped and centered on the model.
- Left side (32% width): A dark charcoal (#262523) sidebar with the serif title "NABI" at the top, containing 4 stacked rounded white item cards (`item_1_top_front.png`, `item_2_jeans.png`, `item_3_bag.png`, `item_4_sandals.png`) with clean labels below each.

Implement this exact timeline choreography to maximize viewer retention:
1. Top Segmented Progress Bar: Add a sleek 4-part progress bar at the very top labeled "HOOK | HALTER TOP | FLARE JEANS | STYLING".
2. [0.0s - 2.5s] The Hook: Slide in a frosted-glass (backdrop-filter: blur) pill banner on the right viewport reading: "Vai ngang, lưng ngắn mặc gì vừa sang vừa hack dáng?". Stagger-animate the 4 left cards in from the left.
3. [2.5s - 5.5s] Focus Item 1 (Halter Top): Scale up Card 1 to 1.15x with a soft red-pink glow while dimming Cards 2-4 to 40% opacity. At 3.5s, perform a 3D Y-axis flip on Card 1 to swap `item_1_top_front.png` with `item_1_top_back.png` synced with the model's turn. Animate a floating callout badge on the right reading: "✓ Cổ yếm chữ V: Gom vai thon & khoe lưng trần".
4. [5.5s - 9.0s] Focus Item 2 (Denim Jeans): Reset Card 1, scale up Card 2 (`item_2_jeans.png`) to 1.15x with a spotlight effect. Apply a smooth CSS scale(1.12) pan on `model_raw.mp4` toward the waist and legs. Show callout text: "✓ Jeans ống loe: Che bắp chân, hack dáng +7cm".
5. [9.0s - 12.0s] Focus Item 3 (Tote Bag): Reset video zoom, highlight Card 3 (`item_3_bag.png`) with a gentle floating bounce animation. Show callout text: "✓ Túi cói Tote: Điểm nhấn Vibe nàng thơ".
6. [12.0s - 15.0s] Finale & CTA: Restore 100% opacity to all 4 cards with a subtle wave pulse. Display a sleek rating card at the bottom right: "Score: 9.5/10 ✨ Lưu ngay ý tưởng phối đồ này!".
```

**Câu hỏi cuối của plan:** Bạn muốn bắt đầu từ việc dùng lại ngay file video hiện tại (crop lấy phần người mẫu bên phải để test trên HyperFrames luôn) hay muốn tạo lại 2 video raw mới tinh theo kịch bản tương tác trước?
