# STATUS

**Current:** Phase 1 (leak-free foundations), step 1, the build-level split.
**Last gate passed:** GATE 0 (2026-10-20).

## Done
- Phase 0: prompt saved (`docs/PROMPT.md`), scratch deleted, dependencies installed and pinned
  (`pyproject.toml`, `requirements-lock.txt`), facts 1–5 recomputed (`reports/results/phase0_facts.json`,
  `reports/WORKLOG.md`), disk check passed.
- Shared modules started: `src/stp/features/testmap.py` (test → file mapping), `src/stp/features/tokens.py`
  (tokeniser and path helpers), `src/stp/results.py` (results JSON + memory-capped DuckDB).

## Next
1. Phase 1.1 `data/processed/splits_build.parquet` (70/15/15 by build start; rolling-origin monthly windows).
2. Phase 1.2–1.3 as-of rule (cap 24 h) and pure feature functions (history, cost, change, co-failure).
3. Phase 1.4 diff-token extraction from `shadata` (resumable), then the per-project feature store.
4. Phase 1.5 leakage tests, then GATE 1.

## Blockers
None. See `HUMAN_TODO.md` (keep the machine awake during long jobs).

## How to resume
"Continue the smartci project. Read STATUS.md, reports/WORKLOG.md and docs/PROMPT.md, then resume from the next
unfinished step."
