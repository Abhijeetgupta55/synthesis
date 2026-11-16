# smartci global model 0.1.0

Part of **smartci: predicting CI test failures to run the right tests first**. Reordering tests helps enormously. ML gives a modest gain over simple rules on recurring failures, and loses to "fastest test first" on tests that fail for the first time.

Exported 2026-10-21 11:53:19 from git `48a9b04`; variant `var_tr_all_to_tvm`.

## Intended use
Rank the test files of a Python + pytest repository so that the ones most likely to fail for the current change run first. The ranking only reorders; nothing is skipped, so the worst case is no speed-up.

## Not intended for
- deciding which tests to skip (test selection) — the model gives no guarantee any test is safe to skip;
- judging code quality, people or teams;
- non-pytest suites without adapting the test-to-file mapping.

## Training data
LRTS (ISSTA 2024), 10 Apache projects; 9 Java/Scala + TVM (Python/pytest). build-level chronological 70/15/15; model trained on train builds only.
LRTS test *classes* (JVM) and pytest *modules* (TVM) are the training unit; smartci scores pytest test files.

Date ranges per project and split: see `reports/results/splits.json`.

## Inputs
25 features (main model), 13 for the cold-start variant used while a repository has fewer than 5 recorded CI runs (no outcome history, no co-failure memory). Names, order, dtypes and missing-value defaults: `schema.json`.

## Output and ordering
Isotonic-calibrated P(test file fails in this run). priority = max(calibrated P(fail), ordering_floor) / (expected duration + 0.001 s), descending. ordering_floor is 0 by default. ordering_floor_lrts was chosen on LRTS validation and held on LRTS test (RESULTS.md 4.3) but slowed smartci on the NetworkX backtest; enable it with $SMARTCI_FLOOR.

## Evaluation (held-out, time-respecting; numbers generated from reports/results)

- APFDc All (lgbm vs ChangedOrNewFirst): 0.871 vs 0.863
- APFDc FirstFail-asof (lgbm vs QTF): 0.775 vs 0.823
- APFDc FirstFail-old (lgbm vs QTF): 0.708 vs 0.800
- APFDc New/Edited (lgbm vs ChangedOrNewFirst): 0.958 vs 0.981

Python transfer (TVM pytest suites), test PR-AUC: jvm9_to_tvm 0.051, tvm_only 0.037, all_to_tvm 0.062
Chosen by TVM validation PR-AUC: `tvm_only`; confirmed on TVM test: False; shipped: `all_to_tvm`. Declared rule: choose the variant with the best TVM valB PR-AUC, then confirm on TVM testC. If the chosen
    variant is worse on testC than the pooled all-projects variant, confirmation has failed and the pooled variant is
    shipped instead. That fallback uses test information; it is disclosed, and the shipped model's unbiased evaluation
    is on repositories no model has seen (Phase 5).

## Limits
- Trained on 10 Apache projects' CI (9 Java/Scala, 1 Python). Signals such as name/path overlap and recent-failure history transfer; project-specific base rates do not (no project id is used).
- Durations come from the repo's own profile/history; without them every test costs 1 s.
- A simple rule (e.g. changed-files-first or coverage-first) can match or beat the model on a given repo; `smartci backtest` measures this on *your* repo and says so.
- Concurrency-safe history: only runs that finished before the current one started are used.
