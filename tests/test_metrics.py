"""Metric unit tests on hand-made orderings, including LRTS's own reference implementation."""
from __future__ import annotations

import sys

import numpy as np
import pytest

from stp import paths
from stp.evaluation.metrics import apfdc, order, run_metrics, ttff


def lrts_apfdc(durations, fails):
    """Verbatim port of the LRTS loop (eval_metric.FaultDetectionMetric.APFDc, uniqueBug), durations + 0.001."""
    d = [x + 0.001 for x in durations]
    tfis = [i + 1 for i, f in enumerate(fails) if f]
    if not tfis:
        return float("nan")
    costs = [sum(d[p - 1:]) - d[p - 1] / 2 for p in tfis]
    return sum(costs) / (len(tfis) * sum(d))


def test_apfdc_extremes():
    d = [1, 1, 1, 1]
    assert apfdc(d, [1, 0, 0, 0]) == pytest.approx((4 - 0.5) / 4, rel=1e-3)   # first: ~0.875
    assert apfdc(d, [0, 0, 0, 1]) == pytest.approx(0.5 / 4, rel=1e-3)         # last: ~0.125
    assert np.isnan(apfdc(d, [0, 0, 0, 0]))


def test_apfdc_cost_matters():
    # a failing test after a long test is found later in time than after a short one
    assert apfdc([10, 1, 1], [0, 1, 0]) < apfdc([1, 10, 1], [1, 0, 0])


@pytest.mark.parametrize("seed", range(20))
def test_apfdc_equals_lrts_reference(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(1, 40))
    d = rng.exponential(5, n).tolist()
    f = (rng.random(n) < 0.2).tolist()
    if not any(f):
        f[int(rng.integers(n))] = True
    assert apfdc(d, f) == pytest.approx(lrts_apfdc(d, f), rel=1e-12)


def test_lrts_module_itself_if_present():
    src = paths.LRTS_ARTIFACT / "evaluation"
    if not (src / "eval_metric.py").exists():
        pytest.skip("LRTS repo not cloned")
    sys.path.insert(0, str(src))
    sys.path.insert(0, str(paths.LRTS_ARTIFACT))
    try:
        import eval_metric
        import eval_utils
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"cannot import LRTS modules: {e}")
    d = [3.0, 1.0, 4.0, 1.0, 5.0]
    f = [0, 1, 0, 0, 1]
    tests = [eval_utils.Test(str(i), d[i] + 0.001, f[i], 0) for i in range(5)]
    ref = eval_metric.compute_metrics(tests)["APFDc_uniqueBug"]
    assert apfdc(d, f) == pytest.approx(ref, rel=1e-12)


def test_ttff_inclusive_and_10pct():
    assert ttff([2, 3, 5], [0, 1, 0]) == 5
    assert np.isnan(ttff([1, 2], [0, 0]))
    m = run_metrics([1, 9, 90], [1, 0, 0])
    assert m["ttff_s"] == 1 and m["first_fail_in_10pct"]
    m = run_metrics([50, 50], [0, 1])
    assert m["ttff_frac"] == 1.0 and not m["first_fail_in_10pct"]


def test_order_ties_and_keys():
    a = np.array([2, 1, 2, 1])
    b = np.array([0, 5, 1, 4])
    assert order([a, b]).tolist() == [3, 1, 0, 2]
    rng = np.random.default_rng(0)
    seen = {tuple(order([np.zeros(3)], rng).tolist()) for _ in range(50)}
    assert len(seen) > 1          # ties are randomised
