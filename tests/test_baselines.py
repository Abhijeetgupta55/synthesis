"""Heuristic orderings and the harness scoring on hand-made runs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from stp.baselines import heuristics as H
from stp.evaluation.bootstrap import macro_ci, paired_diff_ci
from stp.evaluation.harness import score_run, target_masks


def run(**kw):
    n = len(kw["y_fail"])
    base = {"test_id": np.arange(n), "dur_last_asof": np.ones(n), "h_days_since_last_fail": np.full(n, 9999.0),
            "h_n_fail": np.zeros(n), "bm25_test_vs_diff": np.zeros(n), "test_file_in_diff": np.zeros(n, bool),
            "is_new_test": np.zeros(n, bool), "y_duration_s": np.ones(n), "y_ftf_asof": np.zeros(n, bool)}
    base.update({k: np.asarray(v) for k, v in kw.items()})
    return base


def test_rank_is_lexicographic():
    r = H._rank(np.array([1, 0, 1, 0]), np.array([5, 9, 2, 1]))
    assert np.argsort(r).tolist() == [3, 1, 2, 0]


def test_lastfail_and_failcount_and_changed_first():
    d = run(y_fail=[0, 0, 1], h_days_since_last_fail=[9999, 2.0, 0.5], h_n_fail=[0, 5, 1],
            test_file_in_diff=[True, False, False])
    rng = np.random.default_rng(0)
    assert np.argmin(H.lastfail(d, rng)) == 2
    assert np.argmin(H.failcount(d, rng)) == 1
    assert np.argmin(H.changed_or_new_first(d, rng)) == 0
    assert np.argmin(H.oracle(d, rng)) == 2


def test_score_run_drops_non_target_failures():
    prio = np.array([0.0, 1.0, 2.0])
    dur = np.array([1.0, 1.0, 1.0])
    fail = np.array([True, False, True])
    tgt = np.array([False, False, True])          # first failure is not a target: removed from the run
    m = score_run(prio, dur, fail, tgt, np.random.default_rng(0))
    assert abs(m["ttff_s"] - 2.002) < 1e-9 and abs(m["suite_s"] - 2.002) < 1e-9


def test_target_masks_subsets():
    d = run(y_fail=[1, 1, 1, 0], y_ftf_asof=[1, 1, 0, 0], is_new_test=[1, 0, 0, 0], test_file_in_diff=[0, 0, 1, 0])
    m = target_masks(d, 0.0, {})
    assert m["All"].tolist() == [True, True, True, False]
    assert m["FirstFail-asof"].tolist() == [True, True, False, False]
    assert m["FirstFail-old"].tolist() == [False, True, False, False]
    assert m["New/Edited"].tolist() == [True, False, True, False]
    m = target_masks(d, 0.0, {1: 10.0})            # JIRA-flaky with a fix after the run: not a first-time target
    assert m["FirstFail-asof"].tolist() == [True, False, False, False]


def test_bootstrap_by_pr():
    rng = np.random.default_rng(0)
    rows = []
    for p in ("a", "b"):
        for pr in range(40):
            for k in range(3):
                rows.append({"project": p, "pr_name": f"PR-{pr}", "run_idx": pr * 3 + k, "method": "x",
                             "apfdc": 0.6 + 0.01 * rng.standard_normal()})
                rows.append({"project": p, "pr_name": f"PR-{pr}", "run_idx": pr * 3 + k, "method": "y",
                             "apfdc": 0.5 + 0.01 * rng.standard_normal()})
    df = pd.DataFrame(rows)
    c = macro_ci(df[df.method == "x"])
    assert c["lo"] < 0.6 < c["hi"] and c["n_prs"] == 40
    d = paired_diff_ci(df, "x", "y")
    assert d["excludes_zero"] and 0.09 < d["mean"] < 0.11
