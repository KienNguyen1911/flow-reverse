# Progress — node-config-parity

Append-only. Newest last.

## 2026-11-03 — Evidence capture (0 credit)

- `discovery/probe_option_matrix.py` → `traces/flow_option_matrix.json`: 5 image aspects + x1..x4 for
  all 3 image models, no disabled option. Video Omni: 16:9/9:16, 360p/720p, 4/6/8/10s, x1..x4.
  Video Veo (Lite/Fast/Quality): **aspect + count only** — no resolution, no duration group.
- `discovery/capture_video_matrix.py` + `discovery/probe_submit_body.py` → `traces/submit_bodies/*`.
  Every `/data/batchexecute` blocked right before Generate, so no credits spent.
- Image aspect enums captured: `4:3→5`, `1:1→1`, `3:4→4` (plus existing `16:9→3`, `9:16→2`).
- `discovery/probe_submode_ingredients.py`: "Thành phần" is a real text→video submit (RPC `YhhmEf`,
  no media id in the spec), not a fake mode. `Khung hình` keeps `eb1hJf`.
- Agent ON: `button.settings-trigger-button` becomes empty and 0×0 → the composer exposes **no**
  config at all. Recorded in `matrix.md`.

## 2026-11-03 — Implementation

- `src/Workflows/flow_catalog.py` (new): single source of truth — aspect enums, image models + keys,
  video models + per-sub-mode/per-aspect keys, counts, sub-modes, cap flags, agent-mode locks.
  `video_model_key()` raises `CatalogError` for an unsupported combination (no guessing).
- `flow_models.build_image_args(..., model_key, count)`: N specs in `args[1]`, `args[2]` stays `1`.
- `flow_video_bridge`: `build_video_args` (i2v, 720p len 6 / 360p len 10 with `spec[9]=[4]`),
  `build_text_video_args` (t2v, 720p len 5 / 360p len 8 with `spec[7]=[4]`),
  `VIDEO_TEXT_SUBMIT_RPC = "YhhmEf"`, plus composer-driving helpers
  (`_ensure_ui_video_mode`, `_pick_video_model`, `_ensure_video_sub_mode`, …).
- `flow_bridge.ensure_ui_image_mode(aspect, model_label, count)` now selects model + batch size.
- `media_service`: `node_options()` serves the catalog; `generate_image(model, count, agent_mode)`;
  `generate_video(model, sub_mode, count, agent_mode)`; new `generate_text_video()`;
  `NodeImageResult`/`NodeVideoResult` gained `model/model_label/model_key/sub_mode/count/agent_mode`.
- `app.py` / `jobs.py`: request models + endpoints + job forwarding for every new field.
- Frontend: `useNodeOptions()`, full config in `CanvasDrawer`, summary pills in `CanvasPanel`,
  per-model disabling of resolution/duration (Veo), agent toggle that hides the config block,
  ingredients sub-mode that skips source selection entirely.

## 2026-11-03 — Verification

- `pytest tests/test_flow_payload_parity.py` → **33 passed** (payload shapes for image/i2v/t2v/count/
  360p, catalog key matrix, Veo rejection).
- `pytest tests/test_node_api.py tests/test_media_service.py tests/test_node_jobs.py` → **42 passed**.
- `pytest tests -q` → 449 passed, 3 failed; all 3 are pre-existing (`tests/test_account_pool.py`) and
  reproduce identically on the stashed pre-change tree. See `decisions.md`.
- `npm --prefix web run build` → OK. `tsc --noEmit` shows no error in any touched file (only the 13
  baseline lines in `TryOnPanel.tsx`, unchanged).
- `discovery/verify_node_config_ui.py` (0 credit, reads DOM only): PASS aspect/model/count lists match
  `/api/node/options` → `traces/verify_node_config_ui.json`.
- `discovery/verify_video_config_ui.py` (0 credit, never clicks "Chạy lại"): **12/12 PASS** — sub-modes,
  4 models, Omni 360p + 4/6/8/10s, Veo disables resolution+duration and forces 8s without 360p,
  agent mode shows the note and hides model/resolution/duration → `traces/verify_video_config_ui.json`.
- `discovery/verify_composer_drivers.py`: drove the real Flow composer through the same helpers a node
  run uses (popover picks only, never Generate). Chips came back exactly as requested:
  `Video · 360p · 4 giây crop_9_16 x2`, `Video · 720p · 8 giây crop_16_9 x1`,
  `Video · 720p · 8 giây crop_9_16 x4`, `🍌 Nano Banana Pro crop_square x3`.
- Workspace round-trip: `PUT /api/workspace/projects/{pid}/canvas` then `GET` returns all seven new
  node fields intact. The endpoint body **is** the canvas state (no wrapper key).

## Next

- F-010 stays open: the 3 `tests/test_account_pool.py` failures are pre-existing and out of scope.
  Ask the user whether to fix them in a follow-up task.
