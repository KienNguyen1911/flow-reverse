# Architecture pass 2 — continue the refactor

## Goal

Continue the Zed-agent refactor pass that ran out of credit. Two rounds were already committed
(`6fb2fc4` docs/discovery cleanup, `734af00` web components, `32bf447` WebUI + Bridge split).
This pass finishes the work that was literally in flight, then reports on the remaining candidates.

## Non-goals

- No behavior change: route sets, payloads, manifest schema, public import paths stay identical.
- No new features.
- No destructive git operations.

## Constraints

- `pytest tests -q` baseline: **449 passed, 3 failed** (`tests/test_account_pool.py`, pre-existing,
  see `.turbo/node-config-parity/decisions.md` D-007).
- `npx tsc --noEmit` baseline before this pass: **4 errors** in `tryon/SetupStudio.tsx`.
- `tests/test_delivery.py` imports private helpers from `src.Workflows.delivery`
  (`detect_baked_ui_panel`, `detect_edge_strip`, `find_ui_clean_point`, `_resolve_item_image`,
  `_frame_is_clean`, `_render_readme`) and monkeypatches `delivery.ROOT` / `delivery.extract_clean_plate`.
  All of those names must keep resolving on the package.

## Acceptance criteria

1. `npx tsc --noEmit` exits 0.
2. `python -m pytest tests -q` → 449 passed, same 3 pre-existing failures, nothing new.
3. `src/Workflows/delivery.py` is a package whose submodules each own one concept, and every
   pre-existing import path (`from src.Workflows.delivery import X`) still works.
4. Untracked scratch script leaves the tree.
5. An HTML architecture report is written to the OS temp dir and opened for the user.

## Verification commands

```
cd web && npx tsc --noEmit -p tsconfig.json
python -m pytest tests -q
python -m pytest tests/test_delivery.py tests/test_raw_video_qa.py -q
```
