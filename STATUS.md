# STATUS

**Current:** Phase 5 (NetworkX: mutate 180/300 running; then profile → adapter → backtest → GATE 5 on a quiet
machine), Phase 5.2 (sympy chosen; subset by measured suite time), Phase 6 (demo built and smoke-tested), Phase 7.
**Gates:** GATE 0 PASS · GATE 1 PASS · GATE 2 PASS · GATE 3 PASS · GATE 4 fixture part PASS (NetworkX part pending)
· GATE 5 pending.

## Done
- Phases 0–3 complete. Reports generated from JSON: `reports/BASELINES.md`, `FEATURES.md`, `MODELING.md`,
  `VIVA_NOTES.md`; model exported to `models/global/` and packaged in `src/smartci/model/` (+ MODEL_CARD.md).
  Headline: model beats cbt_LastFail on All (+0.020 [0.008, 0.032]); loses to QTF on first-time failures (all
  ablations too). Shipped model: all-projects variant (TVM-only chosen by val failed confirmation on test; disclosed).
- Phase 4: smartci complete; fixture tests pass; fresh-venv GATE 4 fixture run passes.
- Phase 5: NetworkX pinned `abf2feda2252`; coverage map (259/267 test files); learn: 87 strict candidates → 68 bugs.
- Phase 6: `demo_bundle/` (287 LRTS runs, 36 MB, committed), `app/demo.py`, `stp.demo.{build_bundle,verify,cli,smoke}`,
  scripts; smoke: pages / scoreboard / 20 raw replays OK.

## Next
1. NetworkX: wait for mutate (300); then on a quiet machine `smartci profile` → `learn.fit_adapter` → `backtest --set
   both` → GATE 5 (5 bugs + 5 mutants, logged seed, `compare` sequential) → GATE 4 NetworkX part.
2. sympy: time candidate subsets, pick subset, `profile`, `coverage-map`, `learn --since 2023-01-01`, `mutate`, backtest.
3. `live_demo/public_ci/` scripts; REAL_WORLD.md generator; RESULTS.md; SLIDE_NUMBERS.md; README update.
4. Rebuild demo bundle after backtests; rerun smoke.

## Blockers
None. Keep the machine awake (HUMAN_TODO 1). Timing-sensitive steps need no other heavy job running.

## How to resume
"Continue the smartci project. Read STATUS.md, reports/WORKLOG.md and docs/PROMPT.md, then resume from the next
unfinished step."
