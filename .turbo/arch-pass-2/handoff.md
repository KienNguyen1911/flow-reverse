# Handoff — architecture pass 2

**State: two findings fixed and committed. The remaining candidates still need the report + a decision.**

## Commits this session

- `797e2d8` fix(ui): Panel forwards section props — clears the tsc regression from the component split.
- `e7cb2f6` refactor(delivery): 961-line module → `models/frames/plate/clips/items/readme/builder`
  behind a façade `__init__`. All public and test-visible names preserved.

Previous rounds (not mine): `6fb2fc4` docs + discovery cleanup, `734af00` web components,
`32bf447` WebUI routes + jobs package + Bridge/flow packages.

## Verified baseline (run before AND after)

| check | baseline | now |
| :-- | :-- | :-- |
| `python -m pytest tests -q` | 3 failed, 449 passed | 3 failed, 449 passed |
| `cd web && npx tsc --noEmit` | 4 errors | **0** |
| `npm run build` | OK | OK |
| `ruff check src/Workflows/delivery --select F,E9` | n/a | clean |

The 3 failures are `tests/test_account_pool.py` and are pre-existing —
`.turbo/node-config-parity/decisions.md` D-007. Not touched by this task; needs its own task and the
user's go-ahead.

## Next step

1. ~~Read the two background recon reports~~ Done. The frontend one reported; the backend agent returned empty
   twice, so I did that recon directly (see `progress.md`, "Backend recon done inline").
2. ~~Write the HTML report and open it~~ Done:
   `%TEMP%\architecture-review-20261103-154945.html` (7 candidates).
3. **Awaiting the user's pick.** Do not start a candidate unprompted; the user has not chosen yet.

## Open candidates (in report order)

1. Job watcher — 8 polling loops, 4 cadences, 3 copies of the terminal set. Strong.
2. `media_service` video-config derivation copied 3× + two sources of truth for resolution/duration. Strong.
3. `AutoTryOnPipeline.run` — 590-line method over 8 documented-but-unmodularised stages. Strong.
4. `AccountManagerModal` — 708 lines, **zero render sites**. Strong, zero-risk.
5. `CanvasNodeState` / `CanvasDrawerNode` — same 40 fields declared twice, already drifting. Worth exploring.
6. `canvasNodeBits.tsx` — 10 exports across 3 domains. Worth exploring.
7. `ApiDocsPanel` — 510-line catalogue literal inside the view. Speculative.

## Watch out

- `tests/test_delivery.py` monkeypatches `delivery.ROOT` and `delivery.extract_clean_plate`. If you move
  those lookups back to direct imports, those tests will silently assert against the real `out/` tree.
- No `pyproject.toml`/`ruff.toml` exists, and 19 files in `src/Workflows` are unformatted. Do not run
  `ruff format` without asking: it will bury a refactor in unrelated churn.
- The repo has no conftest.py at the root; pytest resolves `src.*` from the repo root, so always run from
  `D:\Dev\rev-flow`.
