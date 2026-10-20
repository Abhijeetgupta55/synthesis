"""Ordering metrics for one test-suite run. Inputs are arrays *in execution order*.

APFDc (uniqueBug), ported from LRTS evaluation/eval_metric.py::FaultDetectionMetric.APFDc:
  every failing test is its own fault; for a fault first revealed at position i (1-based),
  cost_i = sum(d[i:]) - d[i]/2   (the remaining suite time, counting the revealing test half);
  APFDc = sum_i cost_i / (n_faults * sum(d)).  1 = all failures at the very start, ~0.5 = random, 0 = all at the end.
  LRTS adds 0.001 s to every duration (eval_main.construct_testrun_objects); we do the same (DURATION_EPS) so that
  zero-duration classes still cost something.

Time to first failure (TTFF), test time: total duration of the tests up to *and including* the first failing one,
i.e. the moment the first failure is reported when tests run one after another (what `pytest -x` shows).
TTFF wall-clock (approximate, labelled): TTFF × the project's median build_duration / summed-suite-duration ratio.
first_fail_in_10pct: TTFF <= 10% of the summed suite time.
"""
from __future__ import annotations

import numpy as np

DURATION_EPS = 0.001


def apfdc(durations, fails, eps: float = DURATION_EPS) -> float:
    d = np.asarray(durations, dtype=np.float64) + eps
    f = np.asarray(fails, dtype=bool)
    n = int(f.sum())
    if n == 0 or len(d) == 0:
        return float("nan")
    suffix = np.cumsum(d[::-1])[::-1]          # suffix[i] = sum(d[i:])
    pos = np.flatnonzero(f)
    return float((suffix[pos] - d[pos] / 2).sum() / (n * d.sum()))


def ttff(durations, fails) -> float:
    d = np.asarray(durations, dtype=np.float64)
    f = np.asarray(fails, dtype=bool)
    if not f.any():
        return float("nan")
    return float(d[: int(np.argmax(f)) + 1].sum())


def run_metrics(durations, fails) -> dict:
    d = np.asarray(durations, dtype=np.float64)
    total = float(d.sum())
    t = ttff(d, fails)
    return {"apfdc": apfdc(d, fails), "ttff_s": t, "suite_s": total,
            "ttff_frac": t / total if total > 0 else float("nan"),
            "first_fail_in_10pct": bool(t <= 0.1 * total) if t == t else False}


def order(keys: list[np.ndarray], rng: np.random.Generator | None = None) -> np.ndarray:
    """Indices sorting by keys (first key = primary, all ascending), remaining ties broken uniformly at random
    (or by original position when rng is None)."""
    n = len(keys[0])
    tie = rng.random(n) if rng is not None else np.arange(n)
    return np.lexsort([tie] + list(reversed(keys)))
