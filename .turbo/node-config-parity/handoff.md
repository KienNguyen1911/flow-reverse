# Handoff — node-config-parity

**Trạng thái: xong 9/10 feature. F-010 (không hồi quy) còn mở vì 3 lỗi test pre-existing ngoài phạm vi.**

## Đã làm

`GET /api/node/options` phục vụ đúng ma trận capture 0-credit; node Ảnh có aspect/model/count/seed;
node Video có sub-mode/aspect/model/resolution/duration/count/seed với disable theo model; toggle
"Tác nhân" ẩn config và backend dùng default. Nguồn duy nhất: `src/Workflows/flow_catalog.py`.

## Bằng chứng đã ghi

- `pytest tests/test_flow_payload_parity.py` → 33 passed
- `pytest tests/test_node_api.py tests/test_media_service.py tests/test_node_jobs.py` → 42 passed
- `pytest tests -q` → 449 passed, **3 failed pre-existing** (`tests/test_account_pool.py`)
- `npm --prefix web run build` → OK; tsc sạch trong mọi file đã sửa
- `discovery/verify_node_config_ui.py` → PASS (ảnh) `traces/verify_node_config_ui.json`
- `discovery/verify_video_config_ui.py` → 12/12 PASS `traces/verify_video_config_ui.json`
- `discovery/verify_composer_drivers.py` → chip composer khớp 100% `traces/verify_composer_drivers.json`
- Workspace round-trip 7 trường mới: OK

## Việc tiếp theo

1. Hỏi người dùng có muốn sửa 3 lỗi `tests/test_account_pool.py` trong một task riêng không
   (nguyên nhân đã ghi trong `decisions.md` D-007). Sửa xong thì F-010 mới đóng được.
2. Commit theo feature (xem ghi chú commit trong `progress.md`). Tất cả thay đổi của task này còn
   **chưa commit**; chỉ `b2706c1` là đã commit.
3. Đừng đụng các thay đổi có sẵn không liên quan: `configs/accounts_pool.json`,
   `docs/prompt_v2_tryon_samples.md`, `prompt-skills/try-on-image-prompter.md`,
   `src/Workflows/prompt_lint.py`, `tests/test_prompt_skills_contract.py`,
   `tests/test_tryon_prompt_v2.py`, `docs/prompt_v3_tryon.md`.

## Lưu ý môi trường

- Server app: `python -m src.WebUI.app --port 4000 --cdp-url http://127.0.0.1:4022`.
- Browser: CloakBrowser profile `flow_main`, CDP `http://127.0.0.1:4022`.
- `traces/` bị gitignore — file bằng chứng không vào commit, nhưng script sinh lại được.
