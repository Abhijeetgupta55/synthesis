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
