# STATUS

**Current:** Phase 2.3–2.6 (as-of baselines running), GATE 1 completion (Kafka brute-force sample running).
**Gates:** GATE 0 PASS · GATE 1 pending Kafka sample (45/45 runs match on the other 9 projects) · GATE 2 PASS.

## Done
- Phase 0: facts verified, deps pinned, disk OK.
- Phase 1: build-level split + rolling windows; diff extraction; pure feature functions; streaming as-of feature
  store, 104M rows ≈ 1.7 GB (`data/processed/features/`); leakage tests (a) and (c-structure) pass.
- Phase 2: metrics (APFDc identical to LRTS), harness, PR-clustered bootstrap, heuristic baselines, LRTS
  reproduction (GATE 2 PASS after finding the TVM protocol quirk in the paper artifact; see WORKLOG).
- Phase 3 code written, not yet run: `stp/models/{data,prep,common,univariate,tune_linear_rf,tune_lgbm,calibrate,
  evaluate,variants,interpret,export,pipeline}.py`.
- Phase 4 smartci written and passing fixture-repo tests: plugin, receipts, profile, learn (+adapter), coverage-map,
  mutate, backtest, compare, explain, shadow report, CLI, numpy tree evaluator, GitHub action + workflows.
- NetworkX cloned and pinned (`abf2feda2252`), venv `external/networkx/.venv` (Python 3.12) with smartci installed.
- Report generators: baselines_md, features_md, viva_md, model_card; demo verify.

## Next
1. Finish the Kafka brute-force sample → GATE 1; run `verify_store --only signal` (leak test c).
2. `python -m stp.reports.baselines_md` → BASELINES.md.
3. Phase 3: `python -m stp.models.pipeline` (data, scope, lr, rf, lgbm, calib, cls, domain), then univariate,
   ablations/transfer/coldstart (`stp.models.variants`), interpret, export, MODELING.md/FEATURES.md → GATE 3.
4. Phase 5 on NetworkX (profile, coverage-map, learn, mutate, backtest, GATE 5), second repo.
5. Phase 6 demo, Phase 7 reports.

## Blockers
None. RAM (~0.4–2 GB free) forces jobs to run one or two at a time.

## How to resume
"Continue the smartci project. Read STATUS.md, reports/WORKLOG.md and docs/PROMPT.md, then resume from the next
unfinished step."
