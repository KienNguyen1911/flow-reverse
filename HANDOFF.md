# HANDOFF — Architecture improvement pass (`arch-pass-3`)

> Viết cho agent khác tiếp nhận. Đọc hết file này trước khi sửa bất cứ dòng nào.
> Cập nhật lần cuối: 2026-11-03, hoàn thành toàn bộ 8/8 feature của pass arch-pass-3.

---

## 1. Mục tiêu

Triển khai 7 đề xuất cải thiện kiến trúc từ báo cáo
`C:\Users\ngkie\AppData\Local\Temp\architecture-review-20261103-154945.html`.

Nguyên tắc bất di bất dịch:

- **Không đổi hành vi người dùng**, trừ khi chính đề xuất đó sửa một lỗi thật.
- **Không thêm dependency.**
- **Không xoá / làm yếu test nào.**
- **Mỗi đề xuất một commit riêng.** Không gộp.

---

## 2. Trạng thái hiện tại — 8/8 xong (Hoàn thành)

| ID | Việc | Trạng thái | Commit |
| :-- | :-- | :-- | :-- |
| F-001 | Xoá `AccountManagerModal` (chết, 758 dòng) | ✅ verified | `02581b0` |
| F-002 | Một vòng đời job thay 8 vòng poll | ✅ verified | `69c0bf7` |
| F-003 | Tách `canvasNodeBits` → `prompt/` + `node-badge/` | ✅ verified | `7ec254b` |
| F-004 | Một shape node canvas, khai báo một lần | ✅ verified | `a1d55f0` |
| F-005 | Tách catalogue API khỏi `ApiDocsPanel` | ✅ verified | `868471d` |
| F-006 | `media_options.py` + video submit plan | ✅ verified | `92d9c6c` |
| F-007 | Tách `AutoTryOnPipeline.run` (588 dòng) | ✅ verified | `c81999a` |
| F-008 | Chạy full suite + build, đối chiếu baseline | ✅ verified | `docs(arch-pass-3)` commit |

### Trạng thái pass

Toàn bộ 8/8 feature trong pass `arch-pass-3` đã hoàn thành và kiểm chứng độc lập:
- F-001 đến F-005 đã commit ở các commit trước.
- F-006 đã commit tại `92d9c6c`.
- F-007 đã commit tại `c81999a`.
- F-008 đã kiểm chứng toàn bộ test suites (Python pytest 449 pass, 3 pre-existing failures giữ nguyên; Web tsc exit 0; Web npm test 13/13 pass + 3 snippet checks; Web npm run build thành công).

---

## 3. Baseline — phải giữ nguyên sau mỗi bước

```powershell
python -m pytest tests -q
#  KỲ VỌNG: 3 failed, 449 passed
#  3 lỗi đó nằm ở tests/test_account_pool.py, CÓ SẴN TỪ TRƯỚC, không liên quan pass này:
#    - test_allocation_zero_when_all_cooldown
#    - test_allocation_shrinks_when_one_cooldown
#    - test_captured_args_has_reference_detects_t2i_baseline
#  Đã ghi nhận ở .turbo/node-config-parity/decisions.md (D-007). KHÔNG sửa chúng.

cd web
npx tsc --noEmit -p tsconfig.json   # exit 0
npm test                            # 13 lifecycle tests pass + 3 snippet checks
npm run build                       # OK
```

Thời gian chạy full pytest: ~80 giây.

---

## 4. F-006 đã làm gì (để agent sau không làm lại)

**Vấn đề:** phép suy ra 8 giá trị của một lần submit video (ratio, model, sub-mode,
resolution, capture_resolution, duration, count, model_key) bị viết **3 lần** trong
`media_service.py`, ở `animate_frame`, `generate_text_video`, `generate_video`. Ba bản
đã lệch nhau: chỉ một bản validate sub-mode; thứ tự validate khác nhau; agent-mode
collapse chỉ có ở một bản.

**Cách sửa:** module mới `src/Workflows/media_options.py` sở hữu toàn bộ phép suy ra.

- `VideoSubmitPlan` — dataclass frozen, chứa 8 giá trị đã thống nhất.
- `plan_video_submit(...)` — **đường duy nhất** tạo ra plan. Thứ tự validate cố định:
  ratio → model → sub-mode → resolution → duration → count → model_key. Nhờ vậy lỗi
  luôn nêu cái sai nông nhất, không phụ thuộc thứ tự check.
- `agent_mode` collapse **trước** khi validate (giống composer: chip "Tác nhân" ẩn
  nhóm cấu hình, nên giá trị cũ từ UI không được phép làm fail submit).
- `VIDEO_RESOLUTIONS` và `VIDEO_DURATIONS_S` nay **suy ra từ `flow_catalog`**
  (`video_resolutions(None)` / `video_durations(None)`), không còn là tuple chép tay.
  Comment cũ ghi "kept in sync with flow_catalog" — comment không phải cơ chế.
- `media_service.py` import lại và **re-export** mọi tên cũ, nên `__all__` và
  `src/WebUI/routes/node.py` không phải sửa một dòng nào.

**Bằng chứng đã chạy:**

- `python -m pytest tests/test_media_service.py -q` → **22 passed**
- `python -m pytest tests -q` → **3 failed, 449 passed** = đúng baseline
- `rg --fixed-strings '"360p", "720p", "1080p"'` trong `media_service.py` → không còn
- `rg 'plan_video_submit'` → 3 call site (3 phương thức cũ) + import + `__all__`

**Chưa làm (nếu muốn hoàn thiện thêm):** tiêu chí "plan has its own tests" trong
features.json chưa được đáp ứng bằng test riêng. Hiện độ phủ đến từ 22 test cũ của
`test_media_service.py` đi xuyên qua plan. Nếu làm, tạo `tests/test_media_options.py`
kiểm trực tiếp `plan_video_submit` (agent-mode bỏ qua giá trị rác, thứ tự validate,
model Veo từ chối 360p, 1080p capture ở 720p).

---

## 5. F-007 — Tách AutoTryOnPipeline.run (Đã hoàn thành)

Đã hoàn thành và commit tại `c81999a`:
- Tách `AutoTryOnPipeline.run` thành orchestrator gọn (~38 dòng) và 12 phương thức stage riêng biệt (`_init_run_context`, `_prepare_inputs_and_first_frame`, `_ingest_product_assets`, `_generate_image_prompt`, `_generate_first_frame_image`, `_generate_video_prompts`, `_generate_video_1`, `_postprocess_single_video`, `_extract_last_frame`, `_generate_video_2`, `_stitch_final_video`, `_build_and_persist`, `_handle_run_exception`) thông qua `_PipelineRunContext`.
- Chữ ký public API và tương thích tham số `media.animate_frame` được bảo toàn nguyên vẹn.
- Toàn bộ 28 tests trong `tests/test_auto_tryon.py` đều pass mà không cần sửa test code.

---

## 6. F-008 — Chốt hạ và kiểm chứng baseline (Đã hoàn thành)

Đã chạy đủ các cổng ở mục 3:
- `python -m pytest tests -q` → 3 failed, 449 passed in 64.67s (đúng baseline, 3 lỗi pre-existing trong `tests/test_account_pool.py` giữ nguyên).
- `cd web; npx tsc --noEmit -p tsconfig.json` → exit 0.
- `cd web; npm test` → 13 lifecycle tests pass + 3 snippet checks pass.
- `cd web; npm run build` → vite build hoàn thành sạch sẽ trong 1.40s.
Đã cập nhật `.turbo/arch-pass-3/features.json`, `.turbo/arch-pass-3/progress.md` và `HANDOFF.md`.

---

## 7. Bẫy môi trường (PowerShell trên Windows) — đọc trước khi gõ lệnh

| Bẫy | Cách né |
| :-- | :-- |
| Heredoc, `<<'PY'`, regex có `[.\/]` bị PowerShell xé nát | Viết script ra `.py` dưới `C:\Users\ngkie\AppData\Local\Temp\opencode\` rồi gọi bằng đường dẫn |
| `python -c "..."` dài, có nháy lồng | Cùng cách trên — đừng cố nhồi vào một dòng |
| `rg` với alternation `\|` | Dùng `--fixed-strings`, hoặc gọi rg trực tiếp không qua pipe |
| `npx tsc` phải chạy **trong** `web/` | `cd web; npx tsc --noEmit -p tsconfig.json` |
| `npm test` chạy từ `web/` | `verify-snippets.mjs` đã tính đường dẫn theo `import.meta.url`, đừng sửa thành đường dẫn tuyệt đối |

Script có sẵn ở `C:\Users\ngkie\AppData\Local\Temp\opencode\`:
`outline.py`, `seg.py` (in dải dòng), `defs.py`, `equiv.py`, `bodydiff.py`,
`split_bits.py`, `split_apidocs.py`.

---

## 8. Quyết định đã chốt — không mở lại

- **`ui.Panel` mở rộng thành `ComponentPropsWithoutRef<"section">`** chứ không cast tại
  chỗ gọi. Việc rơi drag handler là **lỗi thật** (drop zone khung đầu không highlight
  và không nhận drop được), không phải chỉ là lỗi type.
- **`jobLifecycle.ts` không có runtime import** — transport truyền vào qua `fetchJob`.
  Nhờ vậy test bằng `node --test` không cần React.
- **`waitForJob` trả về job `failed` chứ không throw** — caller cần lý do để render.
  Chỉ timeout/abort mới reject.
- **Re-export shim được ưu tiên hơn phá import** (`hooks.ts`, `canvas/constants.ts`),
  nhưng `canvasNodeBits.tsx` đã xoá hẳn sau khi migrate đủ 7 call site.
- **Không chạy `ruff format` toàn repo** — không có config ruff, và có 19 file trong
  `src/Workflows` vốn đã không format. Format chúng sẽ tạo diff nhiễu.

---

## 9. Định nghĩa "xong"

- Mỗi feature `passes: true` kèm `evidence` là **lệnh thật + output quyết định**.
- 3 cổng ở mục 3 xanh, đúng baseline.
- Working tree sạch, mỗi feature có commit riêng.
- `handoff.md` phản ánh đúng thực tế.

---

## 10. File quan trọng

```
.turbo/arch-pass-3/
  spec.md           mục tiêu, ràng buộc, lệnh verify
  features.json     8 feature + trạng thái (F-001..F-006 true sau khi commit F-006)
  progress.md       nhật ký append-only

src/Workflows/
  media_options.py       MỚI (F-006) — plan video submit, option suy từ catalog
  media_service.py       đã sửa (F-006) — 3 phương thức dùng plan
  auto_tryon_pipeline.py MỤC TIÊU F-007 — run() 588 dòng, dòng 125-712
  delivery/              package tách ở pass trước (8 module)

web/src/
  jobLifecycle.ts        lõi vòng đời job, không import runtime
  jobWatcher.ts          binding React
  jobLifecycle.test.mjs  13 test
  components/api-docs/   MỚI (F-005) — base/types/CodeBlock/quickstart/catalog
  components/prompt/     PromptBits.tsx
  components/node-badge/ NodeBadges.tsx
  components/canvas-drawer/types.ts   khai báo shape node DUY NHẤT
  verify-snippets.mjs    chặn tài liệu API lệch khỏi code

tests/
  test_media_service.py  22 test, phải xanh
  test_auto_tryon.py     28 test, phải xanh, KHÔNG sửa
  test_account_pool.py   3 lỗi có sẵn — ngoài phạm vi
```
