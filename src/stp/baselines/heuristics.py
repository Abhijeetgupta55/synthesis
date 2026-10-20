"""Heuristic orderings, all computed from as-of feature-store columns (ascending priority = run earlier).

  Random                 uniform priority (20 seeds)
  QTF                    quickest first: historical duration dur_last_asof
  LastFail               most recently failed first: h_days_since_last_fail (never failed = 9999, ties random)
  FailCount              most failures first: h_n_fail, descending
  cbt_LastFail           LRTS cost-cognizant form: (days_since_last_fail + eps) * (duration + eps); for tests that
                         never failed this reduces to "shorter first"
  LastFail_tiesShort     lexicographic: days since last failure, then shorter first
  cbt_BM25               (1 / (bm25_test_vs_diff + eps)) * (duration + eps)   (LRTS cbt_IR_GitDiff analogue)
  ChangedOrNewFirst      tests whose own file is in the change or that are new first, each block in cbt_LastFail
                         order
  Oracle                 the run's real failures first, shortest first (ceiling; uses the label)
"""
from __future__ import annotations

import numpy as np

EPS = 1e-6
DAYS_NEVER = 9999.0


def _rank(*keys) -> np.ndarray:
    """Dense lexicographic rank (first key primary) as a priority array; exact ties keep equal rank."""
    o = np.lexsort(tuple(reversed(keys)))
    stacked = np.stack([np.asarray(k, dtype=np.float64)[o] for k in keys])
    new = np.r_[True, (np.diff(stacked, axis=1) != 0).any(axis=0)]
    r = np.empty(len(o))
    r[o] = np.cumsum(new)
    return r


def random(d, rng):
    return rng.random(len(d["test_id"]))


def qtf(d, rng):
    return d["dur_last_asof"].astype(np.float64) + EPS


def lastfail(d, rng):
    return d["h_days_since_last_fail"].astype(np.float64)


def failcount(d, rng):
    return 1.0 / (d["h_n_fail"].astype(np.float64) + EPS)


def cbt_lastfail(d, rng):
    return (d["h_days_since_last_fail"].astype(np.float64) + EPS) * (d["dur_last_asof"].astype(np.float64) + EPS)


def lastfail_ties_short(d, rng):
    return _rank(d["h_days_since_last_fail"], d["dur_last_asof"])


def cbt_bm25(d, rng):
    return (1.0 / (d["bm25_test_vs_diff"].astype(np.float64) + EPS)) * (d["dur_last_asof"].astype(np.float64) + EPS)


def changed_or_new_first(d, rng):
    flag = d["test_file_in_diff"].astype(bool) | d["is_new_test"].astype(bool)
    return _rank((~flag).astype(np.float64), cbt_lastfail(d, rng))


def oracle(d, rng):
    return _rank((~d["y_fail"].astype(bool)).astype(np.float64), d["y_duration_s"])


METHODS = {
    "Random": random, "QTF": qtf, "LastFail": lastfail, "FailCount": failcount, "cbt_LastFail": cbt_lastfail,
    "LastFail_tiesShort": lastfail_ties_short, "cbt_BM25": cbt_bm25, "ChangedOrNewFirst": changed_or_new_first,
    "Oracle": oracle,
}
SEEDS = {"Random": 20}          # other methods: ties broken at random, averaged over TIE_SEEDS
TIE_SEEDS = 5
SIMPLE = [m for m in METHODS if m not in ("Random", "Oracle")]   # candidates for "best simple baseline"
COLUMNS = ["dur_last_asof", "h_days_since_last_fail", "h_n_fail", "bm25_test_vs_diff", "test_file_in_diff",
           "is_new_test", "y_fail", "y_duration_s"]
