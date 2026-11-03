# Progress — architecture pass 2

## 2026-11-03 — session continuation

Context: a Zed IDE agent had started this refactor pass and ran out of credit. Two rounds were already
committed (`6fb2fc4` docs + one-off discovery scripts, `734af00` web component split, `32bf447` WebUI/Bridge
split). Two things were literally in flight when it stopped.

### Baseline reproduced before touching anything

- `python -m pytest tests -q` → **3 failed, 449 passed** (the 3 are pre-existing, `tests/test_account_pool.py`).
- `cd web && npx tsc --noEmit` → **4 errors**, all in `components/tryon/SetupStudio.tsx`
  (TS2322 on `<Panel onDragOver=…>` plus 3× TS7006 implicit `any` for the drag handlers).
- `npm run build` → OK.

### F-001 — Panel type regression (tsc)

The previous commit moved the try-on drop zone into `tryon/SetupStudio.tsx`, but `ui.tsx`'s `Panel` still only
accepted `{children, className}`. So the drag-and-drop first-frame upload was passing handlers the component
silently dropped — a real behaviour bug, not just a type error: the drop zone could not highlight or accept a
drop. Fixed by widening `Panel` to `ComponentPropsWithoutRef<"section">` and spreading `...rest` onto the
`<section>`. `tsc` → exit 0, `npm run build` → OK.

### F-002 — `src/Workflows/delivery.py` (961 lines) → package

The previous agent had left an untracked, never-run generator at `src/Workflows/delivery_split_tmp.py`. I did
not trust it as-is: it wrote no `__init__.py`, so `from src.Workflows.delivery import build_delivery` would have
broken, and it emitted `plate.py` with a duplicated `plate_rel` initialisation and an unterminated block.

Rewrote the split as a deterministic line-slicer and validated it in a throwaway copy of the repo
(`%TEMP%\opencode\sb2`) before touching the real tree. Layout:

| module | lines | owns |
| :-- | --: | :-- |
| `models` | 99 | `RunRef` / `ItemRef` / `DeliveryResult`, `DeliveryError`, `repo_root()` |
| `frames` | 221 | pixel + ffmpeg work: baked-board UI, edge strips, clean-plate extraction |
| `plate` | 105 | `_resolve_plate_candidates`, `select_plate` |
| `clips` | 174 | find/copy/measure a run's video, attach raw-video QA |
| `items` | 208 | product stills: resolve, import, copy, alpha check |
| `readme` | 101 | the human handoff README |
| `builder` | 245 | `build_delivery`, `list_deliveries`, `_build_timeline` |
| `__init__` | 81 | facade: re-exports every pre-existing name |

Two compatibility traps had to be preserved, because `tests/test_delivery.py` depends on them:

1. `monkeypatch.setattr(dv, "ROOT", fake_root)` — so relative-path resolution goes through
   `models.repo_root()`, which reads `delivery.ROOT` **at call time**, not at import.
2. `monkeypatch.setattr(dv, "extract_clean_plate", …)` — so `plate.select_plate` looks the function up on the
   package at call time.

`__init__.py` imports `ROOT` from `script_contract` precisely so patch #1 keeps a real attribute to replace.

### Behaviour-preservation evidence

Beyond the test suite, I diffed the AST of every top-level function/class in the original module against the
package, normalising only the three deliberate edits. Result: **27 symbols, none missing**, and the only body
differences are the intended ones — `build_delivery`'s plate block replaced by one `select_plate(...)` call,
`_resolve_readme`'s `f"## Nội dung"` losing a redundant `f`, and two `import` lines reordered by ruff.

### Verification

- `python -m pytest tests/test_delivery.py tests/test_raw_video_qa.py -q` → **60 passed**
- `python -m pytest tests -q` → **3 failed, 449 passed** (identical to baseline)
- `npx tsc --noEmit` → exit 0; `npm run build` → built in 2.10s
- `ruff check src/Workflows/delivery --select F,E9` → clean
- Import smoke test: package façade, `WebUI.jobs.runners_workflow`, `Workflows.raw_video_qa` all import.

### Note on formatting

The repo has **no** `pyproject.toml`/`ruff.toml`, and 19 files under `src/Workflows` are already unformatted.
So I deliberately did **not** run `ruff format` over the new package: it would have created a large unrelated
diff. Only `ruff check --select F541,I001 --fix` was applied (6 cosmetic fixes inside the new files).

### Next

## Backend recon done inline

The spawned `explore` agent for `src/Workflows/` returned an empty final message twice, even when asked to
re-send. Rather than burn a third round I did that recon directly. The frontend agent did report on the second
ask; I verified its load-bearing claims independently (`AccountManagerModal` has 0 render sites; 8 polling
sites; `TERMINAL` defined at `hooks.ts:17`, `canvas/constants.ts:23`, `TryOnPanel.tsx:60`).

Backend findings, each checked at file:line:

- `AutoTryOnPipeline.run` is **590 lines** (125-714) holding eight stages that already have comment banners
  (198, 343, 408, 433, 494, 525, 585, 617, 666) but share one locals namespace. Resume handling is threaded
  through 149-197.
- The user-intent → Flow-model-key derivation (`normalize_video_ratio` → `resolve_video_model` →
  `normalize_video_resolution` → `validate_video_duration` → `normalize_count` → `capture_resolution` →
  `video_model_key`) is repeated verbatim at `media_service.py:733-737`, `787-791`, `869-883`.
- `media_service.py:99-100` defines `VIDEO_RESOLUTIONS` / `VIDEO_DURATIONS_S`, two lines after comments at
  `:85` and `:237` claim `flow_catalog` is the single source of truth. `flow_catalog` exports no such
  constants; it has `video_resolutions(model)`. Two truths, one comment.
- `flow_client.py` is 802 lines with **zero** test files — deliberately not proposed, because no seam exists
  to verify a split against.
- `CircuitBreaker` is honest: `account_pool` imports it rather than reimplementing it. Not a candidate.
- `account_pool.py` has four JSON writers with two indent conventions (`indent=1` at 174/604,
  `indent=2 + "\n"` at 351/468). Cosmetic; left alone.

## Report

Written to `%TEMP%\architecture-review-20261103-154945.html` (33 KB, 7 candidates, 4 Mermaid diagrams) and
opened. Verified well-formed by a tag-balance parse before opening.

- Two background recon agents are mapping the next candidates in `src/Workflows/` and `web/src/`.
- Then: the HTML architecture report in the OS temp dir.
