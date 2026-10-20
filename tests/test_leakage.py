"""Leakage tests (Phase 1.5).

(a) synthetic overlapping runs: the real streaming builder must ignore runs that have not finished;
(b) 50 random real runs recomputed by brute force must equal the store   (reads reports/results/leakage_bruteforce.json,
    produced by `python -m stp.features.verify_store`; set SMARTCI_SLOW=1 to recompute here);
(c) no feature is suspiciously predictive on its own (single-feature PR-AUC <= 0.95) and no label/eval column is a
    feature.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import pytest

from stp import paths
from stp.features import store
from stp.features.cofail import RunRecord, cofail_features
from stp.features.history import Event, history_features
from stp.features.schema import EVAL_ONLY, FEATURES, LABELS, feature_names

A, B = "org.x.alpha.AlphaTest", "org.x.beta.BetaTest"
ALPHA_SRC = "alpha/src/main/java/org/x/alpha/Alpha.java"
BETA_SRC = "beta/src/main/java/org/x/beta/Beta.java"

# run: (pr, build, stage, start, duration, change files, {test: (fail, duration)})
RUNS = [
    ("PR-1", 1, "s1", 0.0, 1000.0, [ALPHA_SRC], {A: (True, 5.0), B: (False, 2.0)}),     # R0
    ("PR-2", 1, "s1", 500.0, 600.0, [BETA_SRC], {A: (False, 7.0), B: (False, 3.0)}),    # R1: R0 still running
    ("PR-3", 1, "s2", 1050.0, 100.0, [BETA_SRC], {A: (False, 9.0), B: (True, 4.0)}),    # R3 sees R0, not R1
    ("PR-4", 1, "s1", 2000.0, 100.0, [ALPHA_SRC], {A: (False, 6.0), B: (False, 1.0)}),  # sees R0, R1, R3
]


@pytest.fixture()
def synth(tmp_path, monkeypatch):
    p = "synth"
    rows, runs, split = [], [], []
    for i, (pr, b, st, start, dur, files, res) in enumerate(RUNS):
        for tc, (f, d) in res.items():
            rows.append({"pr_name": pr, "build_id": np.int32(b), "stage_id": st, "build_timestamp": start,
                         "testclass": tc, "duration_s": np.float32(d), "outcome": "fail" if f else "pass",
                         "last_outcome": "pass"})
        runs.append({"project": p, "pr_name": pr, "build_id": b, "stage_id": st, "trunk_sha": f"t{i}",
                     "build_head_sha": f"h{i}", "in_paper_subset": False})
        split.append({"project": p, "pr_name": pr, "build_id": b, "stage_id": st, "build_timestamp": start,
                      "build_duration": dur, "failed": any(f for f, _ in res.values()), "run_id": f"{p}|{pr}",
                      "start_ts": start, "end_ts": start + dur, "duration_capped": False, "build_start_ts": start,
                      "split": "train", "roll_window": pd.NA, "roll_window_start_ts": np.nan})
    tr = tmp_path / "test_results" / f"project={p}"
    tr.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(tr / "part-0000.parquet", index=False)
    pd.DataFrame(runs).to_parquet(tmp_path / "runs.parquet", index=False)
    sp = pd.DataFrame(split)
    sp["roll_window"] = sp["roll_window"].astype("Int16")
    sp.to_parquet(tmp_path / "splits.parquet", index=False)
    dd = tmp_path / "diffs" / f"project={p}"
    dd.mkdir(parents=True)
    ch = pd.DataFrame([{"change_idx": i, "pr_name": r[0], "build_id": r[1], "trunk_sha": f"t{i}",
                        "build_head_sha": f"h{i}", "n_files": len(r[5]), "additions": 1, "deletions": 0,
                        "has_patch": False, "patch_chars_used": 0} for i, r in enumerate(RUNS)])
    ch.to_parquet(dd / "changes.parquet", index=False)
    pd.DataFrame([{"change_idx": i, "filename": f, "status": "modified", "additions": 1, "deletions": 0,
                   "previous_filename": None} for i, r in enumerate(RUNS) for f in r[5]]).to_parquet(
        dd / "files.parquet", index=False)
    tk = pd.DataFrame([{"change_idx": 0, "token": "alpha", "count": 3}])
    tk["token"] = tk.token.astype("category")
    tk.to_parquet(dd / "tokens.parquet", index=False)
    monkeypatch.setattr(paths, "SPLITS_BUILD_PQ", tmp_path / "splits.parquet")
    monkeypatch.setattr(paths, "RUNS_PQ", tmp_path / "runs.parquet")
    monkeypatch.setattr(paths, "TEST_RESULTS_DIR", tmp_path / "test_results")
    monkeypatch.setattr(paths, "FEATURES_DIR", tmp_path / "features")
    monkeypatch.setattr(paths, "DUCKDB_TMP", tmp_path / "duck")
    monkeypatch.setattr(store, "DIFFS_DIR", tmp_path / "diffs")
    monkeypatch.setattr(store, "WORK", tmp_path / "work")
    store.build_project(p)
    import duckdb
    rows = duckdb.sql(f"SELECT * FROM read_parquet('{store.parts_glob(p)}')").df()
    tests = pd.read_parquet(paths.FEATURES_DIR / f"project={p}" / "tests.parquet")
    return rows.merge(tests, on="test_id")


def _row(df, run_idx, tc):
    r = df[(df.run_idx == run_idx) & (df.testclass == tc)]
    assert len(r) == 1
    return r.iloc[0]


def test_a_unfinished_run_is_invisible(synth):
    # run_idx follows start order: R0=0, R1=1, R3(s2, start 1050)=2, R4(start 2000)=3
    a1 = _row(synth, 1, A)            # R1 starts at 500, R0 ends at 1000: R0's failure must not be visible
    assert a1.h_n_fail == 0 and a1.h_n_runs_seen == 0 and a1.is_new_test and not a1.h_last_outcome
    assert a1.cof_max == 0 and a1.cof_count_max == 0
    assert a1.dur_source == 0          # no finished history: duration falls back
    a3 = _row(synth, 2, A)            # stage s2 at 1050: sees R0 (end 1000) but not R1 (end 1100)
    assert a3.h_n_fail == 1 and a3.h_n_runs_seen == 1 and a3.hs_n_runs_seen == 0 and a3.hs_n_fail == 0
    assert not a3.h_last_fail_same_stage and a3.y_fail == False  # noqa: E712
    a4 = _row(synth, 3, A)            # sees R0, R1, R3; last known outcome is R3's (ends last, 1150)
    assert a4.h_n_runs_seen == 3 and a4.h_n_fail == 1 and a4.h_n_transitions == 1 and not a4.h_last_outcome
    assert a4.hs_n_runs_seen == 2 and a4.h_last_fail_same_stage
    assert a4.cof_count_max == 1 and abs(a4.cof_max - 0.5) < 1e-9   # ALPHA_SRC changed in R0 (A failed) only
    assert a4.test_file_in_diff == False  # noqa: E712  (Alpha.java is the source, not the test file)
    b3 = _row(synth, 2, B)
    assert b3.y_fail and b3.y_ftf_asof     # B fails for the first time at R3
    b4 = _row(synth, 3, B)
    assert b4.h_n_fail == 1 and b4.hs_n_fail == 0 and not b4.y_ftf_asof


def test_a_pure_functions_ignore_unfinished():
    evs = [Event(0, 0.0, 1000.0, "s1", True, 5.0), Event(1, 500.0, 1100.0, "s1", False, 7.0)]
    f = history_features(evs, 999.0, "s1")
    assert f["h_n_runs_seen"] == 0 and f["is_new_test"]
    f = history_features(evs, 1000.0, "s1")      # finished exactly at t: usable
    assert f["h_n_fail"] == 1 and f["h_last_outcome"]
    recs = [RunRecord(0, 1000.0, frozenset({ALPHA_SRC}), frozenset({A}))]
    assert cofail_features(A, [ALPHA_SRC], recs, 999.0)["cof_count_max"] == 0
    assert cofail_features(A, [ALPHA_SRC], recs, 1000.0)["cof_count_max"] == 1


def _load(name):
    f = paths.RESULTS / f"{name}.json"
    if not f.exists():
        pytest.skip(f"{f.name} missing: run python -m stp.features.verify_store")
    return json.loads(f.read_text(encoding="utf-8"))


def test_b_bruteforce_matches_store():
    if os.environ.get("SMARTCI_SLOW") == "1":
        from stp.features.verify_store import check_bruteforce
        res = check_bruteforce(50, 7)
    else:
        res = _load("leakage_bruteforce")
    bad = [(r["run_id"], r["mismatches"]) for r in res["runs"] if not r["match"]]
    assert res["n_runs"] >= 50 and not bad, bad[:3]


def test_c_no_single_feature_leak():
    res = _load("leakage_signal")
    assert not res["flagged"], res["flagged"]


def test_c_labels_are_not_features():
    names = set(feature_names())
    assert not names & set(LABELS + EVAL_ONLY + ["run_idx", "test_id"])
    assert set(names) <= set(FEATURES)
    assert "semantic_sim" in FEATURES and "semantic_sim" not in names
