# Decisions — architecture pass 2

## D-001 — Fix `Panel` properly instead of casting at the call site

**Decision:** widen `ui.Panel` to `ComponentPropsWithoutRef<"section">` and spread `...rest`.

**Alternatives rejected:**
- `@ts-expect-error` / `as any` in `SetupStudio.tsx` — hides a real bug: the drag handlers were being
  dropped by the component, so drag-and-drop on the first-frame upload could not work.
- Hand-listing three drag props on `Panel` — only fixes this one caller; the next `onKeyDown` /
  `aria-*` / `data-*` prop would hit the same wall.

**Rationale:** `Panel` is a generic layout primitive. A layout primitive that can't accept DOM props is
shallow in the worst way: it has an interface *narrower* than its job.

## D-002 — Do not reuse the previous agent's `delivery_split_tmp.py`

**Decision:** discard it; regenerate the package with a fresh line-slicer validated in a sandbox copy first.

**Why:** the script never ran. It wrote no `__init__.py` (so every existing import path would break), emitted
`plate.py` with a duplicated `plate_rel: Optional[str] = None` and a missing newline before the appended
`return`, and copied the old body verbatim — including the `import unicodedata` that is unused and the
`f"## Nội dung"` f-string with no placeholder, so lint would have failed at the new package.

**Failed approach, for the record:** I first tried to make the slicer produce ruff-clean blank-line layout by
*adjusting the line ranges* (e.g. `seg(148,354)` vs `seg(149,354)`). That is brittle — the ranges encode
whitespace trivia. Switched to letting `ruff check --select F541,I001 --fix` normalise the generated files
instead, and confirmed with `ruff check --select F,E9` that nothing structural was touched.

## D-003 — Keep `ROOT` and `extract_clean_plate` as patchable package attributes

**Decision:** `models.repo_root()` reads `delivery.ROOT` at call time; `plate.select_plate` resolves
`extract_clean_plate` through the package at call time.

**Why:** `tests/test_delivery.py` monkeypatches both. After a split, a direct
`from ..script_contract import ROOT` inside `items.py` would bind early and silently ignore the patch, so
tests would pass while pointing at the real `out/` tree — a false green. Doing the lookup through the package
keeps the tests honest.

**Cost:** one function call per path resolution, and a local import inside `select_plate`. Acceptable: it is
explicitly documented in both places.

## D-004 — Do not run `ruff format` on the new package

**Decision:** leave formatting alone apart from the 6 auto-fixes.

**Why:** there is no ruff config in the repo and 19 pre-existing files under `src/Workflows` are unformatted.
Running the formatter over only the new files would make the split diff look like it rewrote code, and running
it repo-wide would bury the refactor in unrelated churn. Formatting the codebase is a separate task that needs
the user's agreement.
