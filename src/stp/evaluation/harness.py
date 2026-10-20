"""Evaluation harness on the feature store: which runs, which failures count, per-run metrics for any ordering.

Evaluation subsets (a run belongs to a subset if at least one *target* failure remains; non-target failing tests
are removed from the run before scoring, passing tests always stay, exactly like LRTS's FirstFail variant):
  All             every failing test
  FirstFail-asof  failing tests with no failure in any finished earlier run (y_ftf_asof), minus JIRA-flaky classes
                  whose fix date is after the run (JIRA labels are future knowledge: a filter, never a feature)
  FirstFail-old   FirstFail-asof failures of tests that are neither new (never seen finished) nor edited in the
                  change (own file in the diff): the hard case, where neither history nor names give it away
  New/Edited      failing tests that are new or whose own file is in the change (any failure, first or not)

A *method* is a function (features dict of arrays, rng) -> priority array, ascending = run earlier.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from stp import paths
from stp.evaluation.metrics import DURATION_EPS
from stp.features.store import store_dir

SUBSETS = ["All", "FirstFail-asof", "FirstFail-old", "New/Edited"]
EVAL_COLS = ["test_id", "y_fail", "y_ftf_asof", "y_duration_s", "is_new_test", "test_file_in_diff"]

Method = Callable[[dict, np.random.Generator], np.ndarray]


def eval_runs(project: str, splits=("val", "test")) -> pd.DataFrame:
    r = pd.read_parquet(store_dir(project) / "runs.parquet")
    return r[r.failed & r.split.isin(splits)].copy()


def jira_flaky_ids(project: str, tests: pd.DataFrame) -> dict[int, float]:
    """test_id -> earliest JIRA fix timestamp. Strict match: the FQN equals the listed class or ends with '.' + it
    (LRTS uses a looser plain `endswith`; stp.baselines.lrts_repro keeps that one for the reproduction)."""
    fl = pd.read_parquet(paths.FLAKY_PQ)
    fl = fl[(fl.project == project) & fl.testclass.notna() & fl.fix_timestamp.notna()]
    fl = fl.sort_values("fix_timestamp").drop_duplicates("testclass")
    out: dict[int, float] = {}
    for tid, tc in zip(tests.test_id, tests.testclass):
        for c, fx in zip(fl.testclass, fl.fix_timestamp):
            if tc == c or tc.endswith("." + c):
                out[int(tid)] = min(out.get(int(tid), np.inf), float(fx))
    return out


def iter_runs(project: str, run_idx: set[int], columns: list[str]) -> Iterator[tuple[int, dict]]:
    """Yield (run_idx, {column: array}) for the requested runs, in run order, streaming the store parts."""
    cols = sorted(set(["run_idx"] + columns))
    for f in sorted(store_dir(project).glob("part-*.parquet")):
        t = pq.read_table(f, columns=cols)
        r = t.column("run_idx").to_numpy()
        lo, hi = int(r[0]), int(r[-1])
        if not any(lo <= x <= hi for x in run_idx):
            continue
        u, starts = np.unique(r, return_index=True)
        ends = np.r_[starts[1:], len(r)]
        data = {c: t.column(c).to_numpy(zero_copy_only=False) for c in cols if c != "run_idx"}
        for ri, a, b in zip(u.tolist(), starts, ends):
            if ri in run_idx:
                yield ri, {c: v[a:b] for c, v in data.items()}


def target_masks(d: dict, start_ts: float, flaky: dict[int, float]) -> dict[str, np.ndarray]:
    """Per subset, the failing tests that count as targets."""
    fail = d["y_fail"].astype(bool)
    ids = d["test_id"]
    if flaky:
        fl = np.array([flaky.get(int(i), -np.inf) > start_ts for i in ids])
    else:
        fl = np.zeros(len(ids), bool)
    ftf = fail & d["y_ftf_asof"].astype(bool) & ~fl
    new_or_edit = d["is_new_test"].astype(bool) | d["test_file_in_diff"].astype(bool)
    return {"All": fail, "FirstFail-asof": ftf, "FirstFail-old": ftf & ~new_or_edit,
            "New/Edited": fail & new_or_edit}


def score_run(prio: np.ndarray, dur: np.ndarray, fail: np.ndarray, target: np.ndarray, rng) -> dict:
    """Order by priority (random tie-break), drop non-target failures, return APFDc / TTFF / first-in-10%."""
    o = np.lexsort((rng.random(len(prio)), prio))
    keep = ~fail | target
    o = o[keep[o]]
    d = dur[o] + DURATION_EPS
    t = target[o]
    total = d.sum()
    suffix = np.cumsum(d[::-1])[::-1]
    pos = np.flatnonzero(t)
    ap = float((suffix[pos] - d[pos] / 2).sum() / (len(pos) * total))
    ttff = float(d[: pos[0] + 1].sum())
    return {"apfdc": ap, "ttff_s": ttff, "suite_s": float(total), "first10": ttff <= 0.1 * total}


def evaluate_methods(project: str, methods: dict[str, Method], runs: pd.DataFrame, feature_cols: list[str],
                     seeds: dict[str, int] | None = None, base_seed: int = 0) -> pd.DataFrame:
    """Per-run metrics for every method and subset. `seeds[m]` = number of seeds to average (default 1)."""
    tests = pd.read_parquet(store_dir(project) / "tests.parquet")
    flaky = jira_flaky_ids(project, tests)
    meta = runs.set_index("run_idx")
    rows = []
    cols = sorted(set(EVAL_COLS + feature_cols))
    for ri, d in iter_runs(project, set(runs.run_idx.tolist()), cols):
        m = meta.loc[ri]
        masks = target_masks(d, float(m.start_ts), flaky)
        dur = d["y_duration_s"].astype(np.float64)
        fail = d["y_fail"].astype(bool)
        for name, fn in methods.items():
            k = (seeds or {}).get(name, 1)
            acc: dict[str, list] = {}
            for s in range(k):
                rng = np.random.default_rng([base_seed, s, ri])
                prio = fn(d, rng)
                for sub, tg in masks.items():
                    if not tg.any():
                        continue
                    acc.setdefault(sub, []).append(score_run(prio, dur, fail, tg, rng))
            for sub, lst in acc.items():
                rows.append({"project": project, "run_idx": ri, "pr_name": m.pr_name, "split": m.split,
                             "roll_window": m.roll_window, "method": name, "subset": sub,
                             "apfdc": float(np.mean([x["apfdc"] for x in lst])),
                             "ttff_s": float(np.mean([x["ttff_s"] for x in lst])),
                             "suite_s": lst[0]["suite_s"],
                             "first10": float(np.mean([x["first10"] for x in lst]))})
    return pd.DataFrame(rows)
