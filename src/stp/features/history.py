"""As-of history and cost features: pure reference implementations on plain inputs.

Input: the past *events* of one test (one per run that contained it) and the query (time t, stage s).
The as-of rule: an event is usable iff it had finished by t, i.e. event.end <= t. Events are ordered by (end, seq)
(the order in which results became known; `seq` = the run's start-order index breaks ties).

Two scopes are produced from the same events:
  h_*   all-stage history (every finished run of the project/repo that contained the test)
  hs_*  same-stage history (only finished runs of stage s)
plus `h_last_fail_same_stage` (the most recent failure, by start time, happened in stage s).

Used directly by smartci and by the brute-force leakage check; the LRTS feature store (stp.features.store) computes
the same values with a streaming, vectorised implementation that tests/test_leakage.py compares against this one.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

DAY = 86400.0


@dataclass(frozen=True)
class Event:
    seq: int          # start-order index of the run (tie-breaker)
    start: float      # run start, epoch seconds
    end: float        # run end (start + capped duration); usable for queries at t >= end
    stage: str
    fail: bool
    duration: float   # this test's duration in that run, seconds


@dataclass(frozen=True)
class HistoryParams:
    ema_alpha: float = 0.3
    fail_rate_prior: float = 0.0025
    fail_rate_strength: float = 20.0
    days_never: float = 9999.0

    @classmethod
    def from_config(cls) -> "HistoryParams":
        from stp import paths
        f = paths.config()["features"]
        return cls(f["ema_alpha"], f["fail_rate_prior"], f["fail_rate_strength"], f["days_never"])


HISTORY_STATS = ["n_fail", "days_since_last_fail", "fails_last_7d", "fails_last_30d", "last_outcome",
                 "n_transitions", "n_runs_seen", "fail_rate"]


def available(events: Sequence[Event], t: float) -> list[Event]:
    """Events finished by t, in the order their results became known."""
    return sorted((e for e in events if e.end <= t), key=lambda e: (e.end, e.seq))


def _stats(evs: list[Event], t: float, p: HistoryParams) -> dict:
    fails = [e for e in evs if e.fail]
    n_runs, n_fail = len(evs), len(fails)
    last_fail_start = max((e.start for e in fails), default=None)
    ema = None
    for e in evs:
        ema = e.duration if ema is None else p.ema_alpha * e.duration + (1 - p.ema_alpha) * ema
    return {
        "n_fail": n_fail,
        "days_since_last_fail": (t - last_fail_start) / DAY if last_fail_start is not None else p.days_never,
        "fails_last_7d": sum(1 for e in fails if e.end > t - 7 * DAY),
        "fails_last_30d": sum(1 for e in fails if e.end > t - 30 * DAY),
        "last_outcome": bool(evs[-1].fail) if evs else False,
        "n_transitions": sum(1 for a, b in zip(evs, evs[1:]) if a.fail != b.fail),
        "n_runs_seen": n_runs,
        "fail_rate": (n_fail + p.fail_rate_strength * p.fail_rate_prior) / (n_runs + p.fail_rate_strength),
        "_dur_last": evs[-1].duration if evs else None,
        "_dur_ema": ema,
    }


def history_features(events: Sequence[Event], t: float, stage: str, p: HistoryParams = HistoryParams()) -> dict:
    """All history features of one test for a run of `stage` starting at t, plus raw cost inputs.

    Returns h_<stat>, hs_<stat>, is_new_test, h_last_fail_same_stage and the raw cost pair
    (_dur_last, _dur_ema, _dur_src) where _dur_src = 2 same-stage, 1 all-stage, 0 unseen (see cost_features).
    """
    av = available(events, t)
    ss = [e for e in av if e.stage == stage]
    a, s = _stats(av, t, p), _stats(ss, t, p)
    out = {f"h_{k}": a[k] for k in HISTORY_STATS}
    out.update({f"hs_{k}": s[k] for k in HISTORY_STATS})
    out["is_new_test"] = a["n_runs_seen"] == 0
    fails = [e for e in av if e.fail]
    last_fail = max(fails, key=lambda e: (e.start, e.end, e.seq), default=None)
    out["h_last_fail_same_stage"] = last_fail is not None and last_fail.stage == stage
    if s["n_runs_seen"]:
        out.update(_dur_last=s["_dur_last"], _dur_ema=s["_dur_ema"], _dur_src=2)
    elif a["n_runs_seen"]:
        out.update(_dur_last=a["_dur_last"], _dur_ema=a["_dur_ema"], _dur_src=1)
    else:
        out.update(_dur_last=None, _dur_ema=None, _dur_src=0)
    return out


def cost_features(rows: Sequence[dict], default_duration: float = 1.0) -> list[dict]:
    """Fill dur_last_asof / dur_ema_asof for all tests of one run. Unseen tests get the median dur_ema of the
    run's seen tests (the as-of 'project median' for this run), or `default_duration` if no test was ever seen."""
    import numpy as np

    seen = [r["_dur_ema"] for r in rows if r["_dur_src"] > 0]
    fallback = float(np.median(seen)) if seen else default_duration
    out = []
    for r in rows:
        if r["_dur_src"] > 0:
            out.append({"dur_last_asof": r["_dur_last"], "dur_ema_asof": r["_dur_ema"], "dur_source": r["_dur_src"]})
        else:
            out.append({"dur_last_asof": fallback, "dur_ema_asof": fallback, "dur_source": 0})
    return out
