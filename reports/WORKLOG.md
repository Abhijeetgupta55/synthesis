# WORKLOG

Dated entries: key numbers, decisions, surprises. The source of every number is named; machine-readable values live
in `reports/results/*.json`. (This log quotes them for context; reports read the JSON.)

---

## 2026-10-20 · Phase 0: re-verification and setup

**Setup**
- Saved the prompt to `docs/PROMPT.md` (commit `d6a16e0`). Deleted `data/interim/_claude_firstseen_tmp.parquet`.
- Dependencies installed into `.venv` (Python 3.11.16): lightgbm 4.7.0, scikit-learn 1.9.1, optuna 5.0.0,
  shap 0.51.0, streamlit 1.66.0, rank-bm25 0.2.2, coverage 7.16.2, junitparser 5.0.3, gitpython 3.2.1.
  Full lock is in `requirements-lock.txt`.
- `pyproject.toml`: the distribution is renamed `smartci`. It contains both packages (`stp` research, `smartci` tool).
  Core deps are the small set the tool needs inside a user's venv; `[research]`, `[demo]` and `[dev]` hold exact pins.
  `requires-python` is relaxed to `>=3.10` so the tool installs into other projects' venvs.
- Machine: 8 logical CPUs, 16.1 GB RAM with **2.1 GB free**, A: 16.3 GB free. DuckDB is capped at 1.5 GB and spills
  to `data/processed/_duckdb_tmp` (`stp.results.connect`).

**Facts 1–5** (`python -m stp.data.verify_facts` → `reports/results/phase0_facts.json`)

| # | Prompt claim | Our number | Verdict |
|---|---|---|---|
| 1a | Previous run in the same stage unfinished at start: Kafka ~78%, TVM 73%, Hive 68%, others 21–61% | Kafka 77.8%, TVM 72.6%, Hive 67.9%; others 21.3% (HBase) – 61.8% (James); macro 49.8%. Counting *any* earlier-started run: macro 51.8%, Kafka 80.2% | agrees |
| 1b | LRTS `last_outcome` = outcome in the previous run by start time | The test's previous run (by start) in the same stage matches `last_outcome` on 99.97–100% of rows (10% hash sample of classes, 11.0M rows) | agrees |
| 1c | (new) How often is a `last_outcome = fail` taken from a run that had not finished? | **45.8% macro**: Kafka 77.9%, TVM 72.8%, ActiveMQ 59.3%, Hive 51.9%, HBase 10.7% | new finding; the leak is large |
| 1d | build_duration in seconds; median ~10k vs suite ~20.5k; max ~83 days | median 10,034 s vs 20,559 s; max 83.1 days; p99 11.0 h, p99.9 25.6 h; 0.12% of runs > 1 day, 0.016% > 2 days | agrees |
| 2 | FirstFail after burn-in: ~5.8% new, ~8.1% own file edited, ~86% existing (macro) | **4.9% new, 8.3% edited, 86.8% existing**. Basename matching gives the same edited share (8.3%) | agrees; "new" is a bit lower, see note |
| 3 | build_duration / suite median: Kafka 0.35, TVM 0.76, Hive 0.14 | Kafka 0.355, TVM 0.764, Hive 0.141. Note: Karaf 4.9, Log4j 5.0, Hadoop 4.2, James 1.46, ActiveMQ 1.11, i.e. > 1 for small suites (build overhead dominates) | agrees |
| 4 | Kafka failed-run rate 0.60/0.92/0.97; TVM 0.15/0.08/0.06; 58 TVM builds split across splits | Kafka 0.604/0.921/0.973; TVM 0.147/0.078/0.065; 58 TVM builds | agrees |
| 5 | ~2,238 of 2,275 TVM classes under tests/python; ~93% of TVM failures | **2,193** of 2,275 classes (1,467 of 1,547 distinct modules once the ctypes/cython prefix is removed); 93.2% of 31,818 failure rows | count differs (2,193 vs 2,238); share agrees |

Notes and decisions
- **Fact 2, "new" definition.** We call a class new when it appears in no strictly earlier-started run of the
  *project* (any stage). A same-stage definition counts more classes as new (a class first run in a new stage), which
  plausibly explains the prompt's 5.8%. Phase 1 uses `is_new_test` = never seen in a *finished* run (as-of), which will
  again differ slightly.
- **Mapping (stp/features/testmap.py).** JVM `a.b.C$Inner` → suffix `a/b/C.java|.scala`. TVM `ctypes.|cython.tests.python.x.y`
  → `tests/python/x/y.py` (each TVM module appears twice, once per FFI). Match rate = share of distinct classes whose
  mapped file appears among *any* file the project ever changed. That is a lower bound, because only changed files are
  observable. Exact: Kafka 92.4%, TVM 68.6%, James 53.4%, Log4j 44.0%, Hadoop 37.2%, Hive 28.4%, Karaf 26.3%,
  Oak 25.1%, HBase 12.1%, ActiveMQ 7.1% (macro 39.5%). By failure rows the macro is 47.7% (Kafka 99.6%). 99.7% of classes
  produce a syntactically valid suffix. A fallback that strips Gradle shard digits (`GetOffsetShellTest15`) adds ≤ 0.2 pp,
  so we keep the exact mapping only.
- **TVM shard labels.** 54 TVM "classes" are CI shard names (`python-frontend-tensorflow-5-shard-5-cython`, `pytest`).
  They map to no file.
- **Duration cap (for Phase 1).** p99.9 = 25.6 h, and 0.12% of runs exceed 24 h. Proposed cap: 24 h.
- **Disk.** Proxy dry run: Hive, 2.76M rows × 43 planned columns, written as zstd parquet, comes to 26.8 B/row, about
  2.8 GB for 104M rows (≈ 4.2 GB with a 1.5× safety margin). Required: 2 × 4.2 + 5 = 13.4 GB. Free: 16.3 GB. **Pass.**

**GATE 0: PASS.** All five facts were recomputed and logged. The data contradicts none of them in substance; there is
one count difference (fact 5) and one definitional difference (fact 2).

---

## 2026-10-20 · Phase 1: leak-free foundations

**Housekeeping surprise.** `.gitignore` had an unanchored `data/` rule, so `src/stp/data/` (download, build_tables,
audit) had never been committed. It is now anchored to `/data/` and the files are committed.

**1.1 Split** (`python -m stp.data.splits` → `data/processed/splits_build.parquet`, `reports/results/splits.json`)
- Builds are ordered by build start = min stage timestamp, then cut 70/15/15 per project. No build spans two splits;
  the EDA's run-level split had put 58 TVM builds across splits.
- Rolling origin: 30-day windows from the train/val boundary, 1 (Log4j) to 19 (Karaf) windows per project.
- As-of end = start + clip(build_duration, 1 s, **24 h**). 135 runs are capped.

**1.2 As-of rule** Run Q informs run R iff Q.end ≤ R.start. Two history scopes are always computed: `h_*` (all stages
of the project, with an `h_last_fail_same_stage` indicator) and `hs_*` (same stage only). The choice between them is
made on validation in Phase 3.

**1.3 Features** (`src/stp/features/{history,change,cofail,tokens,testmap,schema}.py`, pure functions on plain inputs)
- `fails_last_7d/30d` count failures that *became known* (end time) within the window. `days_since_last_fail` uses
  the failing run's *start*. `last_outcome_asof` is the outcome in the most recently *finished* run.
- `fail_rate` = (n_fail + 20 · 0.0025) / (n_runs + 20). This is fixed Bayesian smoothing toward the pooled
  per-row failure rate (252k / 104M ≈ 0.24%).
- Cost: the duration comes from same-stage history, else all-stage history, else the median EMA of the run's seen
  tests, else 1 s. `dur_source` records which.
- Path features drop layout (src/main/java…), generic (org, apache, util…) and project-name tokens. With that
  normalisation, "aligned prefix overlap" reduces to the longest common prefix between the test's directory path and
  any suffix of a changed file's directory path. That form can be computed with a trie.
- BM25: the corpus is the run's own test list, so IDF never uses tests not yet known. Query weight 1 + ln(count);
  k1 = 1.2, b = 0.75.
- Co-failure: file-level rate cof(f, x) / (nchg(f) + 1), with backoff to the parent directory for files never
  changed before. Aggregated as max, sum and the raw file-level count max.
- Changes are keyed by (build, trunk_sha, head_sha), not by build. 1,546 build ids map to more than one SHA pair
  (TVM reuses ids across Jenkins jobs), and keying by build alone would hand an earlier stage the diff of a later job.

**1.4 Store** (`python -m stp.data.build_diffs`, `python -m stp.features.store`)
- Diff extraction re-reads the raw compare JSON. It matches the EDA change table on files and additions for 100% of
  Log4j changes. TVM's extraction log shows 36,921 s of wall time, i.e. the machine slept mid-run; the job resumed
  fine.
- The store is built in one chronological streaming pass per project with per-test state arrays (not ASOF joins).
  Runs are applied in end order, and sliding windows are decremented when a failure's end leaves the window.
  Small projects take 5–96 s; TVM (16.2M rows) takes 216 s.
- Kafka store: 68.4M rows, 1,126 MB, 1,053 s. Total store 104.0M rows ≈ 1.7 GB (estimate was 2.8 GB).

**1.5 Leakage tests** (`tests/test_leakage.py`, `python -m stp.features.verify_store`)
- (a) Synthetic overlapping runs through the real streaming builder: passes. A run that has not finished is invisible.
  Results that finish exactly at t are usable.
- (b) Brute force from raw tables with the pure reference functions: **45/45 runs match** for the 9 non-Kafka projects
  (39,623 rows; every feature, label and duration; integers and booleans exact, floats to 1e-6 relative).
  The first Kafka attempt was stopped after 50 min without finishing one run: rebuilding ~1,300 tests × ~30k events
  in pure Python under ~400 MB free RAM is too slow. Runs with > 600 tests are now checked on all failing tests,
  all new tests and 40 random tests. Every feature column is still checked. The cost fallback needs all tests and is
  computed fully whenever a sampled test is unseen.

---

## 2026-10-20 · Phase 2: harness, GATE 2

- Metrics: APFDc equals LRTS's own `eval_metric.compute_metrics` (imported in a test) to 1e-12. TTFF includes the
  failing test's own duration, because that is when `pytest -x` reports it. (The prompt said "before"; this is a
  deliberate deviation.)
- **LRTS evaluation detail found in their code.** The shipped `eval_main` calls `eval_tcp_on_build` without
  `use_ordered_tests`, so filters only select runs. The published FirstFail outcomes nevertheless *remove* filtered
  failing tests for 9 projects; only 22.7% of QTF FirstFail runs have APFDc equal to their All value. **For TVM they do
  not.** The 429 published TVM FirstFail runs equal our All values run by run (mean |Δ| 0.0008 QTF). With removal,
  only 5 TVM runs would keep a failure. That count agrees with LRTS's own `dataset_filter.csv`, where the stage-unique
  filter keeps a failure in 0.6% of TVM failed runs. LRTS's `filter_builds` on `dataset_filter.csv` reproduces the
  paper's run rows exactly for all 10 projects.
- First attempt: GATE 2 **FAILED** on FirstFail (QTF −0.028, cbt_LastFail −0.030, FailCount +0.013), entirely from
  TVM (5 vs 429 runs). All variant: within 0.001.
- Fix: reproduce the *published* protocol. Use the `filter_builds` run set; remove filtered failures except for TVM.
  The macro values with removal applied everywhere are kept in `gate2_reproduction.json → tvm_quirk`.
- **GATE 2: PASS.** All 8 cells are within ±0.005: All QTF −0.0006, LastFail −0.0008, FailCount +0.0001,
  cbt_LastFail −0.0001; FirstFail QTF +0.0005, LastFail −0.0045, FailCount −0.0015, cbt_LastFail −0.0008.
- **Leak effect, same features and same runs, start order → as-of** (macro): All LastFail −0.0055,
  FailCount −0.0059, cbt_LastFail −0.0026, QTF −0.0011. FirstFail moves slightly *up* (+0.002 to +0.006). The macro
  effect is small although 46% of "last fail" values come from unfinished runs. Explanation pending a per-project
  look (Phase 2.6).

**GATE 1: PASS** (2026-10-20)
- (b) Brute force: **50/50 runs match** (39,796 rows; 94 failing, 83 own-file-in-diff, 2,464 non-zero co-failure,
  4 new-test rows). The 5 Kafka runs used the sampled mode (all failing + all new + 40 random tests per run).
- (c) Single-feature PR-AUC on training rows: none flagged (threshold 0.95). The maximum is 0.249 (Hive `cof_max`).
  Per project the maxima are 0.055–0.11, e.g. Kafka 0.107 (`hs_fails_last_7d`).
- (a) Synthetic overlap: passes. All 35 leakage, metric and baseline tests pass.
- Leak effect per project (start order → as-of, All): at most −0.016 (FailCount TVM, ActiveMQ −0.015; LastFail Hadoop
  −0.016, TVM −0.013), most within ±0.005. Interpretation: the leaked outcome is usually the most recent of a
  *streak* of failures, so the as-of history still shows a recent failure one or two runs earlier.

**2.3–2.6 As-of baselines** (`python -m stp.baselines.run_baselines` → `baselines.json`, `reports/BASELINES.md`)
- Failed val+test runs: Kafka 15,523 (1,702 s), TVM 772, others 52–703.
- Test split, macro APFDc (best simple baseline chosen on **val**):
  All → ChangedOrNewFirst 0.863 (cbt_LastFail 0.851; paired Δ −0.012, CI excludes 0);
  FirstFail-asof → QTF 0.823 (cbt_BM25 0.819, LastFail 0.188);
  FirstFail-old → QTF 0.800; New/Edited → ChangedOrNewFirst 0.981.
- History-only rules collapse on first-time failures, as in the paper, and QTF is the bar. A model must beat
  QTF on FirstFail-old and ChangedOrNewFirst on All.
- Small projects have fewer than 30 test runs (ActiveMQ 21, Log4j 26). Cells are marked † and only the pooled
  small-8 macro is interpreted.

---

## 2026-10-20 · Phase 3: modelling

- Data stage (806 s): training sample 3.6M rows / 81.6k positives (Kafka 6,000 of its failed runs, weight 3.72);
  valA 1.2M rows, valB 1.4M, testC 1.9M (unsampled, ≤ 600 runs per project; small projects only 8–40 runs).
- **Surprise: early stopping at round 1.** With inverse-probability sampling weights (up to 211), LightGBM's valA
  PR-AUC was best after the first tree. Diagnosis on 500k rows:
  - weighted: 0.128 → 0.094 at 150 rounds, while train rises 0.53 → 0.79;
  - unweighted: 0.082 → 0.152 at 150 rounds.
  A handful of heavily weighted negatives dominate the gradient, so the effective sample size is tiny.
  **Decision:** train unweighted (`stp.models.common.USE_SAMPLE_WEIGHTS = False`) and remove the probability
  distortion with isotonic calibration on unsampled valB. This follows the prompt's own design, which calibrates
  on unsampled validation runs because sampling distorts probabilities. Weights are still used for the weighted
  univariate statistics.
- The large train/val gap that remains (≈ 0.83 vs 0.15) is out-of-time drift. This is why regularisation and
  early stopping matter here.
- **Scope choice** (unweighted default LightGBM, valB PR-AUC): same-stage `hs` 0.179, all-stage `h` 0.152,
  both 0.183 (34 features). The rule fixed in advance picks a single scope, so the choice is **hs**.
- **LR**: the first grid's best C (1e-4) was at the grid edge, so the grid was extended to 1e-6. Elastic-net
  C = 1e-4 is a true interior optimum: valA PR-AUC 0.1634, 14/25 coefficients zero. At C ≤ 1e-5, L1 and EN zero
  every coefficient (PR-AUC → 0.003). L2 plateaus at 0.160.
- **RF**: best depth 10 / leaf 20 / sqrt features, valA 0.182. Depth sweep (train / valA): 4 0.48/0.147,
  8 0.63/0.188, 14 0.82/0.184, 24 0.90/0.181. Validation peaks near depth 8 while train keeps rising. The stage took
  95 min, mostly the final 200-tree fit.
- **LightGBM tuning, change of plan**: with the full 1.2M-row valA set, one Optuna trial took about 20 min, because
  AP is recomputed every round (60 trials ≈ 20 h). Tuning now uses 500k training rows and a fixed 300k-row whole-run
  subsample of valA, at most 1,000 rounds, patience 50, learning rate ≥ 0.02. The refit still uses all training rows
  with early stopping on the full valA.

## 2026-10-20 · Phase 5 (started early): NetworkX

- Pinned at `abf2feda2252` (2026-10-17). Separate venv (Python 3.12; NetworkX needs ≥ 3.12). 10,120 tests collected.
  Collection alone took 289 s under memory pressure.
- `coverage-map`: 262 source files, 259 of 267 test files, 28,014 covered lines. The suite under coverage with
  per-test contexts took 8,154 s while competing with model training.
- **Candidate filter fix.** The first filter accepted any `#123`. Every squash-merged NetworkX subject ends with its
  PR number, so that admitted 293 commits since 2024, including features and refactors ("Enable backend-only
  functions…"). The strict filter keeps fix/bug/regression/issue keywords or `closes/fixes/resolves #N`, and finds
  **87** candidates since 2024. This matches fact 6 of the prompt ("about 87 commits"). Learn was restarted. Rows
  produced under the old filter are ignored when bugs are loaded.
- **Tuning result**: 60 TPE trials in 46 min after the change. Best valA PR-AUC 0.2079. The top-5 configurations
  score 0.901–0.905 valA APFDc.
- **Classification (testC, first pass)**: LightGBM PR-AUC 0.207 with isotonic vs 0.218 with Platt, at equal Brier
  (0.00255 / 0.00256). RF 0.180 / 0.195, LR 0.174 / 0.193. Soft vote 0.220, stacking 0.227. ROC-AUC is about 0.95
  for every model. Model residuals are 0.98–0.99 correlated.
- **Design fix: isotonic loses ranking.** Isotonic regression is a step function, so it maps many raw scores onto
  one plateau, and average precision (and ordering) loses that resolution. Isotonic stays the calibrator, but ties
  inside a plateau are broken by the raw score (`iso(r) + 1e-9·r`). Probabilities are unchanged to 1e-9, and the
  ranking equals the raw model's. The same is done in `variants.Variant` and in smartci's exported calibrator. The
  classification and domain evaluations were re-run.
- **NetworkX learn** (strict filter, since 2024-01-01): 87 candidates → **68 reproducible bugs (78%)**.
  Excluded 19: no_failure 12, collection_error 4, fails_on_fix 3. So 7 commits could not run in today's pinned
  environment. Rows from the first, loose-filter run were moved to `*_loose_filter_archive.jsonl` and are not used.
  The adapter was not fitted yet: `learn` ran before the global model was exported. Re-run `fit_adapter` after
  export. With 68 bugs, 41 adapt / 27 evaluate.
- `mutate --n 300 --seed 42` started.
- **Classification, final (testC, isotonic with tie-break)**: PR-AUC LR 0.193, RF 0.195, LightGBM 0.218, soft vote
  0.220, stacking 0.227. ROC-AUC 0.95–0.96. Brier 0.00253–0.00261. Recall@10 per failed run 0.54–0.57.
- **Domain evaluation**: Kafka's 8,078 test runs took 37,139 s. The machine was paging at about 600 MB free, and RF
  is predicted three times per run (alone, in the vote, in the stack). Mutate was paused to let it finish.
- **Domain, test split, macro APFDc vs the best simple baseline chosen on val** (`models.json`):
  - All: stack 0.880 vs ChangedOrNewFirst 0.863, Δ +0.018 (CI excludes 0); LightGBM 0.871 (+0.008, n.s.). LightGBM vs
    cbt_LastFail: **+0.020 [+0.008, +0.032]**. The model beats cbt_LastFail on All.
  - FirstFail-asof: LightGBM 0.775 vs QTF 0.823 (−0.047). FirstFail-old: 0.708 vs 0.800 (−0.092).
    New/Edited: 0.958 vs 0.981 (−0.023). **The models lose to QTF on first-time failures.**
  - p-only ordering (lgbm_p) collapses on FirstFail-old: 0.267. The p/d rule is what keeps the model competitive.
  - Hypothesis: the model front-loads tests with recent failures, which wins on All. In first-time-failure runs those
    tests mostly pass and use up time; QTF ignores history. The ablations and error analysis test this.
- **Ablations (testC PR-AUC / first-time PR-AUC)**: A history 0.201 / 0.00028; B + cost 0.202 / 0.00030;
  C + change 0.203 / 0.00040; D + co-failure 0.218 / 0.00039. Co-failure gives the all-failure gain. Change
  relatedness raises first-time PR-AUC by about 40%. APFDc on FirstFail-old comes from the ablation domain run.
- **Python transfer to TVM (valB / testC PR-AUC)**: jvm9→tvm 0.266 / 0.051; tvm-only 0.680 / 0.038;
  all→tvm 0.482 / 0.062. **Validation and test disagree.** The declared rule (best TVM valB) picks tvm-only, which is
  the *worst* on TVM test. It stopped at 59 rounds and fit TVM history from the window just before validation, which
  did not survive TVM's regime shift (63% of test classes unseen in train).
  **Decision:** keep the declared rule for reporting; add the confirmation step the rule already named ("then
  confirmed on TVM test"). Confirmation failed, so the pooled all-projects variant is shipped. This uses test
  information and is disclosed in `transfer.json`, MODELING.md and the model card. The shipped model's unbiased
  evaluation is Phase 5 (repositories no model has seen).
- **Root cause of the paging.** An orphaned NetworkX `pytest` process (a mutant under test) held **4.7 GB**. Mutate was
  stopped without its child process, and the mutated code apparently grew memory without bound. Killing it freed
  5.4 GB. This probably explains why Kafka's model domain evaluation took 10.3 h. Changes: mutate resumed with a
  120 s per-mutant timeout, and long jobs are now stopped with their whole process tree.
- **Ablation domain results (test, macro APFDc)**:
  All: A 0.864, B 0.863, C 0.872, D 0.871.
  FirstFail-asof: A 0.732, B 0.742, **C 0.801**, D 0.775.
  FirstFail-old: A 0.688, B 0.699, **C 0.734**, D 0.708.
  **Answer to the key question: no.** Neither C nor D beats QTF (0.800) on FirstFail-old; the closest is C at −0.067
  [−0.101, −0.034]. Change relatedness closes about 40% of the gap. Co-failure memory raises PR-AUC but adds nothing
  to APFDc on All and hurts first-time failures. On the domain metric, C is the best variant. The shipped model is
  *not* switched on this basis, because that would be selection on test. It is reported as a finding.
- Leave-one-project-out: the macro Δ vs the best baseline is stable (All +0.004 to +0.016; FirstFail-asof −0.036 to
  −0.054). No single project drives the result.
- Per group, LightGBM on All: Kafka 0.884 vs 0.849, TVM 0.913 vs 0.862, small-8 0.864 vs 0.864. On FirstFail, QTF wins
  in every group (Kafka 0.953, TVM 0.991, small-8 0.786).
- Bug: the regime-shift check compared every subset against the All baseline. Fixed to use each subset's own best
  baseline; summary to be re-run.
- **Interpretation**: the top SHAP features are hs_fail_rate 0.91, dur_ema_asof 0.44, hs_n_runs_seen 0.39 and
  hs_days_since_last_fail 0.32. Spearman agreement with the |LR coefficient| ranking is only 0.14: the trees rely on
  duration × history interactions that LR cannot express.
  **Error analysis:** the 20 worst-ranked first-time failures are almost all *long* tests (Hive Iceberg CRUD at position
  0.994, Kafka connect-file tests at 0.94–0.96). Duration raises p, but p/d divides by it, so long never-failed tests
  go last. QTF also runs them last but does not first spend time on recently failing tests.
- **Export**: `models/global` and `src/smartci/model` hold `var_tr_all_to_tvm` (25 features) and the cold-start
  variant (13 features: cost + change). `tests/test_export.py` 3/3 passes: it scores with `stp.paths` blocked, the
  numpy evaluator equals lightgbm, and the packaged copy is byte-identical.
- **Rolling origin (baselines)**: 18,149 failed runs over every 30-day window of val+test (737 FirstFail-asof, 479
  FirstFail-old). The best baseline per subset matches the test split. Models are evaluated at a single origin; this
  is a stated limitation.

**GATE 3: PASS** (deliverables gate). FEATURES.md, MODELING.md and VIVA_NOTES.md are generated from results JSON;
every rubric item has a table and a figure. Plain statement: **the model beats cbt_LastFail on All** (+0.020
[+0.008, +0.032]), **it does not beat the best simple baseline (QTF) on FirstFail-old or FirstFail-asof**, and no
ablation variant does either.

## 2026-10-21 · GATE 4 (fixture part)

- A fresh venv (`uv venv` + `pip install -e .`, Python 3.11) loads the real packaged model (25 features).
- On the fixture repo, with that venv's `smartci` CLI and the real model: `profile` (2 runs, 0.9 s summed test time,
  ~2.7 s pytest start-up), `learn --max 5` (1 candidate, kept), `backtest --set mined` (smartci 0.01 s vs default
  0.61 s simulated) and `compare` (both runs fail on `tests/test_ops.py::test_sub`; smartci ranked it first) all run
  end to end. **Fixture part: PASS.** The NetworkX part follows after mutate and profile.
- Honest overhead: the smartci session took 11.8 s vs 6.2 s for the default session. That is ~5.6 s of imports,
  git diffs, model parsing and history per session, which outweighs any gain on a 6 s suite. It must be measured on
  NetworkX with a quiet machine and reported.
- Between the first test's start and the failure report there is ~0.7–1.2 s beyond the tests' own durations,
  probably pytest building the failure report. This was measured under CPU load from mutate, so it is noisy.

## 2026-10-21 · Phase 5.2: second repository selection

Criteria: pure-Python install on Windows, pytest, suite ≥ 1 min, ≥ 30 reproducible mined bugs since 2023, and enough
test files for file-level ordering. Strict-filter fix candidates since 2023 (shallow clones):
- **attrs**: 15 candidates. Fails the ≥ 30 criterion even at 100% reproduction.
- **black**: 34 candidates, but only 14 test files, with most tests in `test_black.py`; file-level ordering has
  little to work with. At NetworkX's 78% reproduction rate, about 26 bugs (< 30).
- **pydantic**: 277 candidates, 244 test files. It depends on a compiled `pydantic-core` pinned exactly per commit,
  so many old commits are expected to fail under one pinned environment.
- **sympy**: 500 candidates, 633 test files, pure Python. **Chosen.** The full suite is very long, so a documented
  subset of subpackages is used; it will be chosen by measured suite time on a quiet machine.
- **Windows timeout bug, fixed.** A venv's `python.exe` on Windows is a launcher that starts the real interpreter as
  a child. `subprocess.run(timeout=...)` killed only the launcher, so a timed-out mutant's pytest kept running. That
  caused the 4.7 GB orphan, and "120 s" timeouts took up to 271 s. `smartci.runner.run_pytest` now kills the whole
  process tree (`taskkill /F /T`). Test: a 60 s test with a 5 s timeout returns after 5.5 s and leaves no process.
  Mutate was restarted (resumable).

## 2026-10-21 · NetworkX mutants

- `mutate --n 300 --seed 42` finished: **300 mutants kept of 393 attempts** (76% killed by ≥ 1 existing test).
  Excluded: survived 68, timeout 23, error 2. Operators: compare 115, constant 98, return 42, arith 35, boolop 10.
  The run included a ~1.5 h machine sleep (lid closed, 14:44–16:15).
- **Bug found after generation: negated conditions were never produced.** An `if` statement spans several lines,
  and the single-line filter discarded it before the `If` branch. Fixed, with a unit test
  (`test_mutation_operators`). The NetworkX set (seed 42) is **not** regenerated, because that would change a set
  drawn with a logged seed; REAL_WORLD.md states that it contains no negated-condition mutants.
- **NetworkX profile** (quiet machine): 267 test files, 210.9 s summed test time, full runs 260 s / 304 s, pytest
  start-up and collection overhead ~65 s, 0 flaky files, 0 failing on base, 10,120 node ids.
- **Two node-id bugs found and fixed** (`smartci/history.py::_module_of`, `smartci/repair.py`):
  1. *Inherited test methods.* JUnit's `file` attribute names the file that *defines* a method
     (TestDiGraph.test_contains is defined in test_graph.py), so 717 ids were wrong. The module now comes from the
     classname.
  2. *Old commits without a pytest config.* Inside a worktree at an old fix commit, pytest walked up to the main
     checkout for its rootdir, and every id got a `.smartci/worktrees/learn/` prefix (all 68 mined bugs pointed at
     non-existent files). Now `--rootdir` is pinned to the worktree in every smartci pytest run (learn, mutate,
     profile, coverage, compare), and the prefix is stripped when parsing.
  The stored profile, bugs and mutants were re-derived from their saved JUnit XML. Afterwards 10,120 / 10,120 profile
  ids have durations and 68 / 68 bugs map onto profiled test files. Side effect of (2): those old-commit learn runs
  also used the main checkout's `filterwarnings = error`. That makes exclusions more conservative; kept bugs still
  pass at the fix and fail with the source reverted.
- **NetworkX adapter**: fitted on 41 older bugs (10,783 rows): intercept 6.44, coef on the global logit 2.25,
  coef on covers-changed-lines 3.98. Evaluated on the newer 27.
- **NetworkX backtest** (263 test files, 211 s): mined held-out (27): smartci median 0.80 s to first failure vs
  default 66.7 s, coverage-first 0.31 s, changed-files-first 0.72 s. W/T/L vs coverage-first 8/12/7, vs
  changed-files-first 1/12/14 (mean APFDc 0.937 vs 0.986). **On mined bugs smartci does not beat the simple rules.**
  Mutants (300): smartci 0.02 s, coverage-first 0.04 s, default 84.5 s; W/T/L vs coverage-first 30/252/18 (APFDc 0.990
  vs 0.988), effectively a tie. Against default: 27/0/0 and 296/1/3.
  Note: "best simple baseline" in the backtest is the best rule *on the same bugs* (no separate validation). That is
  optimistic for the baseline and therefore conservative for smartci.
- **GATE 5 first attempt stopped; design inconsistency fixed.** The backtest simulated mined bugs on *today's* suite
  (profile at HEAD), but `compare` re-ran each bug at its old fix commit. For bug 32b2c75e, that commit's test file
  errors during collection under today's pytest (`PytestRemovedIn10Warning` plus `filterwarnings = error`), so the
  "real" run measured something else. The script also read a stale receipt, because every compare worktree has the
  same path.
  Fix: new `learn.rebase` applies every mined bug to the profiled base (today's code) with `git apply --3way`, runs its
  touched tests there and records `failing_nodeids_base`. Bugs that no longer apply or no longer fail are excluded and
  listed. The backtest, the adapter split and `compare` all use the same rebased state. Receipts and timing files
  older than the current compare run are ignored. `smartci learn` now runs `rebase` automatically after mining when
  a profile exists.
- **NetworkX rebase** onto base `abf2feda2252`: 68 mined bugs → 46 ok, 21 no_apply (the code has moved since the fix),
  1 no_failure. Adapter refit on the 28 older usable bugs (intercept 4.24, logit 1.84, coverage 3.47); 18 evaluated.
- **Backtest (rebased)**: mined (18) smartci median 0.55 s (APFDc 0.956) vs default 77.4 s, coverage-first 0.27 s
  (0.916), changed-files-first 0.75 s (0.985). W/T/L vs coverage-first 5/6/7, vs changed-files-first 1/6/11.
  Mutants (300): smartci 0.02 s (0.990), coverage-first 0.04 s (0.988), default 84.5 s; W/T/L vs coverage-first
  31/244/25. All (318): vs coverage-first 36/250/32, vs default 315/0/3.
  **Finding:** smartci is about 100× faster to the first failure than pytest's default order on real NetworkX bugs,
  and on par with, but not better than, the simple coverage-first / changed-files-first rules.
- **GATE 5 second attempt: real ≠ simulated, simulation fixed** (the prompt requires fixing before reporting).
  For bug d8081795 both orders failed on the same test as simulated, but the times differed: default 78.4 s real vs
  43.3 s simulated; smartci 23.6 s vs 0.27 s. Causes:
  1. *Per-test framework overhead is missing from the simulation.* JUnit durations exclude pytest's own work
     between tests (hooks, reporting). That is ~10 ms × ~3,000 tests ≈ 35 s here. `profile` now measures the
     test-phase wall time with `--smartci-timing`, derives `per_test_overhead_s` = (wall − Σ durations) / n_tests,
     and the simulator adds it once per executed test.
  2. *The plugin did not pass the coverage signal* to the adapter, while the backtest did, so the real smartci order
     differed from the simulated one. The plugin now computes `covering` from the coverage map when the adapter
     uses it.
  3. *As-of time.* The backtest scored rebased mined bugs as of their 2024 fix date (no history), whereas the plugin
     scores as of now (profile runs are history). Since rebased bugs and mutants run on today's code, the backtest
     now scores them as of now.
  NetworkX re-profiled, adapter refit, backtest and GATE 5 re-run.
- **GATE 5 third attempt, a new finding: the machine was on battery.** In bug 56c7b0d0's default lane, real per-file
  durations were uniformly ~2.35× the profiled ones (traveling salesman 10.4 → 25.8 s, Gomory–Hu 8.5 → 20.9 s), in
  tests unrelated to the bug. So this is machine speed, not the bug. Windows reported battery discharging (77%) and
  processor performance at 42% of nominal. The two profile runs also differed by 1.5× (246 s vs 374 s test phase).
  The smartci lane matched well where the prefix is short (d3e01821: real 129.2 s vs simulated 126.7 s).
  Decision: GATE 5 is judged only on mains power with a profile measured under the same conditions (HUMAN_TODO 0).
  `gate5.py` also reports a speed-normalised check (simulation × per-run speed factor measured from the files run
  before the failure) as a diagnostic.
- **GATE 5 (NetworkX, seed 5, on battery): FAIL, 11/20 checks.** smartci lane 10/10 pass: real within about 1 s of
  simulated (0.3 → 1.3 s, 126.7 → 129.2 s; that 1 s is pytest's failure reporting). Default lane 1/10: real is
  consistently 1.5–2.8× simulated (median about 2.2×) for every bug and mutant, and the first failing test matches the
  simulation in every run. Cause: CPU throttled on battery (42% of nominal) relative to when the profile was measured.
  Kept as `gate5_networkx_battery.json`. **The authoritative GATE 5 is pending a re-run on mains power** with a
  fresh profile (HUMAN_TODO 0). Not reported as a pass anywhere.
- **sympy subset** (pinned `b386392cd62e`, 2026-10-19, own Python 3.12 venv): core, sets, logic, ntheory,
  combinatorics, polys and simplify (144 test files). sympy's own config skips slow tests. Chosen as the core
  algebra stack with enough test files for file-level ordering. 215 strict fix candidates since 2023 touch tests in
  the subset. `learn --paths` mines only those, so every mined bug lands inside the profiled suite.
- **sympy learn, first pass: an environment error of mine.** 35 of the first 75 candidates were excluded as
  collection_error because the sympy venv lacked `hypothesis`, which sympy's conftest requires. Fixed by installing
  sympy's `requirements-dev.txt` (hypothesis 6.170.5, pytest-xdist, pytest-timeout, …). The collection_error rows
  were cleared and learn resumed. Kept so far: 20; fails_on_fix 10; no_failure 9; timeout 1 (the timeout overlapped
  a machine sleep).

## 2026-11-16 · Finishing prompt: Phase A audit, Phase B cleanup

- **Phase A (GATE A pass).** `reports/AUDIT.md`, generated by `python -m stp.reports.audit_md` from
  `scripts/audit_runs.py` and `scripts/audit_spotcheck.py`. All headline numbers equal their JSON. Laptop on battery:
  no timing step was run (GATE 5 / Phase C pending, HUMAN_TODO 0).
- **Spot check.** First attempt used `dur_ema_asof` for QTF and mismatched on 2/3 runs; the documented QTF uses
  `dur_last_asof`. With that, 3/3 model and 3/3 QTF per-run APFDc values match exactly.
- **sympy dropped** from reports, bundle and generators (mined only, never profiled or backtested); one sentence in
  REAL_WORLD.md says it was attempted.
- **Disk.** Deleted `external/cand_*` (git-ignored, no references left): 539 MB freed.
- **Rename.** Name and headline live in `stp.reports.fmt` (NAME, QUESTION, HEADLINE), used by RESULTS.md and the model
  card; README title updated. No "self-healing" wording existed in tracked files.
- **Overclaim fixed.** RESULTS.md said the model beats the best simple rule on All; the CI includes 0, so the
  sentence is now decided by the CI ("is level with").
- **Error analysis** (`python -m stp.models.error_analysis`, RESULTS.md §4). (1) First-time failures: supported:
  before reaching the failure the model has used 16.4% of suite time vs QTF
  9.1%, 74% of it on previously-failed tests.
  (2) TVM collapse: not feature drift (PSI vs train is large in both valB and test); valB is easier: failure rate
  3.1x higher and failures repeat more.

## 2026-11-16 · Finishing prompt: phases C (prep), D, E, F, G

- **Power.** The laptop reported "discharging" at every check, so no timing step ran. `live_demo/phase_c.py`
  (refuses on battery) does profile + GATE 5 + 3x live-demo timings in one command; DEMO_SCRIPT.md fills its timing
  section from its output. `scripts/run_live_compare.ps1` now lists bugs by number (`-Pick N`), takes the user's
  own edit (`-Edit`) and a subset (`-Subset networkx/algorithms`, default; `-Subset ""` = full suite).
- **Phase D.** Probability floor max(P, f) / duration on the tuned LightGBM, all val/test failed runs rescored
  (Kafka about 16 min per split). f* chosen on validation by the declared rule, test reported once: ship rule met
  (RESULTS.md 4.3). **Deployment check, not declared in advance:** on the NetworkX backtest the same floor made
  smartci much slower (the per-repo adapter puts probabilities on another scale, so the floor promotes tiny unrelated
  tests). Shipped default stays 0 (`ordering_floor` in schema.json); opt-in via `SMARTCI_FLOOR`. NetworkX backtest
  re-run with the floor off reproduces the published one exactly (summary and every bug identical).
- **Predict live.** `smartci.whatif.rank_paths` ranks for a paths-only change; `smartci rank --files/--at/--json`
  and the app call it (parity test: identical order and scores). Bug found while building it: with additions =
  deletions = 0 the model treated the change as unusual (large positive SHAP for the zero size) and ranked unrelated
  tests first. A paths-only change now uses the median size of the repo's own mined bug fixes (overridable).
- **Dashboard.** Six pages; reads only `demo_bundle/`; works with the five packages in requirements.txt and no
  package install (`app/demo.py` adds `src/` to its path). Bug found: `demo_bundle/live/networkx/.smartci/` was
  swallowed by the `.smartci/` ignore rule, so a fresh clone had no live data; un-ignored. Screenshot capture with
  Playwright driving the installed Edge.
- **GATE E: PASS.** Fresh clone (no data/, no external/) → `scripts/setup_demo.ps1` → `scripts/run_demo.ps1 -Port
  8503`: health OK, all six pages render. `setup_demo` now picks Python 3.11+ (system `python` here is 3.10, too old
  for the pins); `run_demo` takes `-Port` (8501 was taken by another app).
- **Tests without data:** fresh clone with only `.[ci]` installed: all pass, one skip (LRTS repo not cloned).
- **Publishing.** Local absolute paths scrubbed from bundled/committed JSON (`stp.scrub`);
  `scripts/publish_check.py` passes.

## 2026-11-16 · Making it a product and explaining it

- Still on battery: Phase C not run.
- **`smartci evaluate`** chains profile → learn (+rebase, adapter) → optional mutants → backtest and prints a verdict
  card decided by the numbers (smartci only if it wins more bugs than it loses vs the best rule *and* its median is not
  worse). First draft printed "1483x sooner" for NetworkX: that ratio ignores pytest's own start-up (74 s measured), so
  the card now shows seconds of test time plus the measured start-up instead of a ratio.
- **`--smartci-rule`** runs a simple rule (definitions shared with the backtest via `scoring.rule_order`).
- **Savings data** (`python -m stp.models.savings`): share of the suite waited through before the first failure,
  held-out failed runs, macro over projects: fixed order (random as proxy) 34%, model 2.7%, best rule 4.0%.
- **Guided demo** lists all 18 held-out real bugs with their outcome (including losses) and opens on the median case.
- Tests 54/54; smoke pass (seven pages).
