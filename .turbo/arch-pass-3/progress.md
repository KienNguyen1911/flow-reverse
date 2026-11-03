# Progress — architecture pass 3

Append-only. Newest last.

## Overview

Architecture Improvement Pass 3 implements the 7 refactoring candidates identified in `architecture-review-20261103-154945.html`, plus final baseline verification across Python and Web stacks.

Principles maintained throughout:
- No user-visible behavior changes (except fixing blocking polling loops).
- No new dependencies added to backend or frontend.
- Zero existing tests deleted or weakened.
- Dedicated, atomic git commits per feature proposal.

---

## Completed Features Summary (8/8)

| Feature | Description | Status | Commit | Key Changes & Verification |
| :--- | :--- | :--- | :--- | :--- |
| **F-001** | Delete unreachable `AccountManagerModal` | ✅ Verified | `02581b0` | Deleted dead modal (758 lines). Zero render sites. `tsc` exit 0, `npm run build` clean. |
| **F-002** | Unified job lifecycle watcher | ✅ Verified | `69c0bf7` | Created `jobLifecycle.ts` (pure TS/Node) and `jobWatcher.ts` (React hooks). Removed 8 ad-hoc polling loops. 13 unit tests pass. |
| **F-003** | Split `canvasNodeBits` | ✅ Verified | `7ec254b` | Decomposed into `components/prompt/PromptBits.tsx` and `components/node-badge/NodeBadges.tsx`. Migrated all 7 call sites. Byte-identical content match. |
| **F-004** | Single canvas node shape declaration | ✅ Verified | `a1d55f0` | Unified duplicate node interfaces into single source of truth `CanvasDrawerNode`. Fixed silent drop of `runId` during graph round-trip. |
| **F-005** | Extract API catalogue from `ApiDocsPanel` | ✅ Verified | `868471d` | Separated static data catalog (510 lines) into `components/api-docs/`. Hardcoded BASE unified. Added `verify-snippets.mjs` test to prevent drift. |
| **F-006** | Video submit plan & catalog-driven options | ✅ Verified | `92d9c6c` | Created `src/Workflows/media_options.py` (`VideoSubmitPlan` and `plan_video_submit`). Unified 3 divergent submit preparation blocks in `media_service.py`. 22/22 unit tests pass. |
| **F-007** | Decompose `AutoTryOnPipeline.run` | ✅ Verified | `c81999a` | Refactored 588-line monolithic method into high-level orchestrator and 12 distinct stage methods using `_PipelineRunContext`. All 28 tests in `tests/test_auto_tryon.py` pass unmodified. |
| **F-008** | Full suite & build baseline verification | ✅ Verified | (this commit) | Verified Python pytest suite, Web TypeScript typecheck, Web test suite, and Web production build match baseline. |

---

## Feature Details & Evidence Log

### F-001: Delete dead `AccountManagerModal`
- Commit: `02581b0 refactor(web): delete the unreachable AccountManagerModal`
- Verification: `git rm web/src/components/AccountManagerModal.tsx` (-758 lines). `rg 'AccountManager'` confirmed 0 render sites. `npx tsc --noEmit` exit 0; `npm run build` OK.

### F-002: Unified job watcher module
- Commit: `69c0bf7 refactor(web): one job lifecycle instead of eight polling loops`
- Verification: Created `web/src/jobLifecycle.ts` with terminal state set `['succeeded', 'failed', 'rejected']`. Removed 120-iteration and `for(;;)` blocking loops from `DeliveryModal` and `useNodeRunner`. Added `web/src/jobLifecycle.test.mjs` (13 tests passing).

### F-003: Split `canvasNodeBits` into `prompt/` and `node-badge/`
- Commit: `7ec254b refactor(web): split canvasNodeBits into prompt/ and node-badge/`
- Verification: Extracted `components/prompt/PromptBits.tsx` (10,774 bytes) and `components/node-badge/NodeBadges.tsx` (9,999 bytes). Updated 7 call sites: `CanvasOverlays`, `CanvasPanel`, `ConfigTab`, `ImageNodeBody`, `CanvasNodeCard`, `UpstreamSources`, `VideoNodeBody`. Deleted `canvasNodeBits.tsx`. `tsc` exit 0, vite build clean.

### F-004: Single canvas node shape declaration
- Commit: `a1d55f0 refactor(web): one canvas node shape, declared once`
- Verification: Removed redundant `CanvasNodeState` interface in favor of `export type CanvasNodeState = CanvasDrawerNode`. Fixed bug where `runId` was dropped on graph reconstruction. Unified `CanvasStats` declaration in `TopBar.tsx`.

### F-005: Extract API catalogue from `ApiDocsPanel`
- Commit: `868471d refactor(web): extract the API catalogue out of ApiDocsPanel`
- Verification: Extracted `components/api-docs/{base,types,CodeBlock,quickstart,catalog}`. Reduced `ApiDocsPanel.tsx` from 858 to 182 lines. Shared `TERMINAL_STATES` and `JOB_POLL_MS` from `jobLifecycle`. Added `verify-snippets.mjs` running in `npm test` to validate snippet rendering against runtime exports.

### F-006: Video submit plan in `media_service`
- Commit: `92d9c6c refactor(workflows): one video-submit plan instead of three copies`
- Verification: Extracted `plan_video_submit` and `VideoSubmitPlan` into `src/Workflows/media_options.py`. `media_service.py` delegates `animate_frame`, `generate_text_video`, and `generate_video`. `VIDEO_RESOLUTIONS` and `VIDEO_DURATIONS_S` now derived dynamically from `flow_catalog`. 22/22 unit tests pass in `tests/test_media_service.py`. Baseline pytest preserves 449 passed, 3 pre-existing failures.

### F-007: Split `AutoTryOnPipeline.run` into staged methods
- Commit: `c81999a refactor(workflows): split AutoTryOnPipeline.run into staged methods`
- Verification: Decomposed `AutoTryOnPipeline.run` (lines 125-712) into ~38-line orchestration method and 12 distinct stage methods:
  - `_init_run_context`
  - `_prepare_inputs_and_first_frame`
  - `_ingest_product_assets`
  - `_generate_image_prompt`
  - `_generate_first_frame_image`
  - `_generate_video_prompts`
  - `_generate_video_1`
  - `_postprocess_single_video`
  - `_extract_last_frame`
  - `_generate_video_2`
  - `_stitch_final_video`
  - `_build_and_persist`
  - `_handle_run_exception`
  All 28 tests in `tests/test_auto_tryon.py` pass unmodified.

### F-008: Baseline verification & pass finalization
- Verification executed on 2026-11-03:
  1. `python -m pytest tests -q`
     - Result: 3 failed, 449 passed in 64.67s.
     - Exactly the 3 pre-existing failures in `tests/test_account_pool.py` (`test_allocation_zero_when_all_cooldown`, `test_allocation_shrinks_when_one_cooldown`, `test_captured_args_has_reference_detects_t2i_baseline`). All other 449 tests pass.
  2. `cd web; npx tsc --noEmit -p tsconfig.json`
     - Result: exit code 0. Zero TypeScript errors.
  3. `cd web; npm test`
     - Result: exit code 0. 13 unit tests pass in `jobLifecycle.test.mjs`, 3 snippet assertions pass in `verify-snippets.mjs`.
  4. `cd web; npm run build`
     - Result: exit code 0. Clean Vite production build in 1.40s.
