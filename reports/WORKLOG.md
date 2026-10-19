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
