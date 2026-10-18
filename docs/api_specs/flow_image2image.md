# Flow image2image (i2i) — Template-Replay Bridge Mode

> Trạng thái: **thiết kế đã triển khai, capture trực tiếp đang chờ phiên đăng nhập khỏe** (2026-10-18:
> phiên Flow trong CloakBrowser bị đăng xuất giữa lúc discovery — cần đăng nhập lại rồi chạy
> `discovery/probe_i2i_composer.py` để xác nhận selector).
>
> Khác với `ogiZ0b` (t2i) đã reverse-engineer đầy đủ trong `flow_create_image.md`, **RPC upload ảnh
> tham chiếu của Flow chưa được bóc tách**. Thay vì đoán giao thức, repo dùng chiến lược
> **template-replay**: để chính app dựng request i2i (khi ta đính ảnh vào composer), chặn + lưu lại
> làm template, rồi replay với tham số thay thế.

## 1. Nguyên tắc (AGENTS.md §2 — Discovery trước, Deterministic sau)

| Thành phần | Nguồn gốc | Ghi chú |
| :--- | :--- | :--- |
| Upload file ảnh | **App tự làm** (`<input type=file>` + change event) | ta không gọi RPC upload nào cả |
| Cấu trúc args i2i (`media_id` nằm ở đâu, ref thay đổi thế nào) | **Capture từ request của app** (bị chặn, 0 credit) | `FlowClient.upload_reference_image()` |
| Token reCAPTCHA khi fire | Capture mới từ app (bị chặn) ở lần generate kế tiếp | giống t2i: `ref[10][0]` |
| Seed / prompt / tracking UUID | Ta thay thế bằng hàm thuần `build_args_from_template()` | vị trí giống t2i: `spec[3]`, leaf prompt, `spec[12]/[13]`, `args[4][0]` |

Không có bước nào dùng LLM/`browser-use` trong vòng lặp sản xuất — chỉ Playwright cố định
(`set_input_files` + click + chặn capture).

## 2. Luồng hoạt động (FlowClient)

```
upload_reference_image(project_id, file, prompt_probe)     # 0 credit
  1. attach CDP → install_hook (chặn ogiZ0b)
  2. nav_home → nav_project
  3. FlowBridge.attach_reference(file)      # set_input_files vào <input type=file> của composer
  4. type_prompt(prompt_probe) → click_generate
  5. wait_capture → app request bị chặn (0 credit)
  6. captured_args_has_reference(args):
       False  → ảnh chưa kịp đính → raise (không fire lung tung)
       True/None → mask token → ReferenceTemplate(template_args, media_id≈, candidates)
  → cache: AccountPoolManager.registry  (account_id + sha256(file) → template)

generate_image(..., reference=<ReferenceTemplate>)         # ~1 credit nếu được nhận
  1. nav_home → nav_project → type_prompt(prompt THẬT) → click_generate
  2. wait_capture (app request t2i, bị chặn) → token mới
  3. build_args_from_template(template, token, seed, prompt, old_prompt, uuids)
       - token: ref[10][0] (fallback: quét leaf 0cAFcWeA…)
       - seed:  spec[3]
       - prompt: thay leaf chứa prompt cũ (app bọc dạng [[[prompt]]])
       - uuid:  spec[12], spec[13], args[4][0]
       - media ref: GIỮ NGUYÊN như app đã ghi (đây là điểm cốt lõi)
  4. fire body của ta trong trang (tái dùng cơ chế "capture-then-fire" của t2i)
```

Cache `configs/reference_media_cache.json` (gitignored) khoá theo **account + sha256**, vì `media_id`
chỉ tồn tại trong project của từng account (plan §2 — lazy upload once per account). Với 100 ảnh i2i
trên cùng một account + cùng ảnh tham chiếu: chỉ 1 lần upload, các shot sau trúng cache.

## 3. Rủi ro đã biết & cách phát hiện sớm

| Rủi ro | Phát hiện | Hành vi |
| :--- | :--- | :--- |
| Composer không có `<input type=file>` (UI đổi) | `attach_reference()` ném `PageInteractionError` tức thì | job dừng với thông báo trỏ về file này |
| Ảnh chưa upload xong → app gửi request t2i | `captured_args_has_reference()` so masked ref với baseline t2i | raise trước khi fire (0 credit) |
| App đổi cấu trúc spec (index seed/uuid lệch) | `build_args_from_template()` guard từng index; prompt/uuids fail → raise | capture lại template |
| Template cũ nhưng media bị xoá khỏi project | fire trả `FAILED_PRECONDITION`/reject | xoá entry cache + `upload_reference_image` lại |

## 4. Discovery recipe (khi cần re-validate hoặc UI đổi)

```bash
# 0 credit — chỉ đọc DOM + (tuỳ chọn) SPA-nav vào 1 project
python discovery/probe_i2i_composer.py                 # probe tab hiện tại
python discovery/probe_i2i_composer.py --fresh --project <uuid>
```

Probe in ra: `prosemirror`, `generate_button`, danh sách `<input type=file>` (accept/multiple/visible),
và ~60 nhãn button. Nếu không có file input trong trang dự án:

1. Mở DevTools (hoặc `br.page.pause`), kích nút "thêm ảnh/nguyên liệu" trong composer.
2. Bắt sự kiện `DOMNodeInserted` quanh composer hoặc `Page.fileChooserOpened` (Playwright event
   `page.on("filechooser")`) để tìm selector mới; có thể phải chuyển từ `set_input_files` sang
   `page.expect_file_chooser()` + click nút.
3. Khi có selector mới: cập nhật `_FILE_INPUTS_JS` / `attach_reference()` trong `src/Bridge/flow_bridge.py`
   — **giữ nguyên nguyên tắc template-replay**, không tự dựng args upload.

Lần chạy i2i thật đầu tiên trên mỗi account+ảnh cũng chính là một lần discovery tự động (0 credit,
lưu tại `out/playground/ref_<tên file>*/` gồm `app_request_body.txt` + `reference_template.pretty.json`
để đối chiếu).

## 5. Lệnh script nhanh (không cần UI)

```bash
# 0 credit — capture template cho 1 account (in registry qua WebUI/API sau đó)
python -m src.Workflows.flow_client status
# i2i qua WebUI: bật "Chế độ batch", điền "Ảnh tham chiếu i2i", dán danh sách prompt
# hoặc POST /api/batch {"project_id": "...", "items": [{"prompt": "...", "mode": "i2i",
#   "reference_image_path": "out/outputs/<project>/anchor.png"}], "confirm": true}
```
