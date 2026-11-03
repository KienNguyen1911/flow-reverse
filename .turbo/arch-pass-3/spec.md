# Architecture pass 2 — implement all seven candidates

## Goal

Implement every candidate from `architecture-review-20261103-154945.html`. No behaviour change for
anything user-visible except where a candidate explicitly fixes a defect (blocking polling loops).

## Baseline (must hold after every step)

- `python -m pytest tests -q` → 3 failed, 449 passed (the 3 are pre-existing `test_account_pool`).
- `cd web && npx tsc --noEmit` → exit 0.
- `cd web && npm run build` → OK.

## Candidates

| # | Candidate | Area | Strength |
| :-- | :-- | :-- | :-- |
| 1 | One job watcher, not eight polling loops | web | Strong |
| 2 | Deep video-submit plan in `media_service` | backend | Strong |
| 3 | Split `AutoTryOnPipeline.run` (590 lines) by stage | backend | Strong |
| 4 | Delete dead `AccountManagerModal` (708 lines) | web | Strong |
| 5 | One canvas node shape, declared once | web | Worth exploring |
| 6 | Split `canvasNodeBits` (3 domains, 10 exports) | web | Worth exploring |
| 7 | Extract `apiCatalog` from `ApiDocsPanel` | web | Speculative |

## Constraints

- No new dependencies. No test deleted or weakened.
- Every candidate gets its own commit; unrelated candidates are never batched.
- `tests/test_delivery.py` monkeypatches `delivery.ROOT` and `delivery.extract_clean_plate` — do not
  break those lookups.
- `AutoTryOnPipeline.run` is covered by 28 tests in `tests/test_auto_tryon.py` that call `run()` and
  `main()`. Its public interface must not change.
- No `ruff format` repo-wide (19 pre-existing unformatted files, no ruff config).

## Verification

```
python -m pytest tests -q
cd web && npx tsc --noEmit -p tsconfig.json && npm run build
```
