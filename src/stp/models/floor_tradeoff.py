"""Phase D: a probability floor to trade recurring-failure gains against first-time-failure losses.

Ordering score with floor f: max(P, f) / (expected duration + 0.001 s), descending. f = 0 is the model's order; as
f grows every test gets the same probability and the order approaches "fastest first" (by expected duration).

Model: the tuned, calibrated LightGBM (`cal_lgbm`, as in MODELING.md). Per-row predictions are not stored, so each
failed run is scored once and every f is evaluated on that one prediction (harness rules: subsets, non-target
failures removed, seeded tie-break as in the harness with base_seed 11).

Selection rule, fixed before the test split is scored (also written to the JSON before the test step runs):
  on the VALIDATION split, among the f whose macro APFDc on All failed runs is at most 0.005 below f = 0, take the f
  with the highest macro APFDc on FirstFail-old; if none beats f = 0 on FirstFail-old, f* = 0.
Ship rule: smartci gets the floor only if f* > 0 and, on the TEST split (reported once), the paired difference
  f* − 0 on FirstFail-old has a 95% PR-clustered CI above 0 and the All mean difference is ≥ −0.005.

Usage: python -m stp.models.floor_tradeoff [--step val|test|both]   -> reports/results/floor_tradeoff.json
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from stp import paths
from stp.evaluation.bootstrap import macro_ci, paired_diff_ci
from stp.evaluation.harness import EVAL_COLS, eval_runs, iter_runs, jira_flaky_ids, score_run, target_masks
from stp.features.store import store_dir
from stp.models.common import load_model
from stp.results import load_result, save_result

GRID = [0.0, 1e-5, 3e-5, 1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1, 1.0]
SUBS = ("All", "FirstFail-asof", "FirstFail-old")
TOL_ALL = 0.005
OUT = paths.PROCESSED / "eval" / "floor_runs"


def score_split(split: str, grid: list[float]) -> pd.DataFrame:
    cal = load_model("cal_lgbm")
    cols = sorted(set(cal.entry["cols"]) | set(EVAL_COLS) | {"dur_ema_asof", "dur_last_asof"})
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for p in paths.PROJECTS:
        f = OUT / f"{split}_{p}_{len(grid)}.parquet"
        if f.exists():
            frames.append(pd.read_parquet(f))
            continue
        t0 = time.time()
        runs = eval_runs(p, (split,))
        if runs.empty:
            continue
        tests = pd.read_parquet(store_dir(p) / "tests.parquet")
        flaky = jira_flaky_ids(p, tests)
        meta = runs.set_index("run_idx")
        rows = []
        for ri, d in iter_runs(p, set(runs.run_idx.tolist()), cols):
            m = meta.loc[ri]
            masks = {k: v for k, v in target_masks(d, float(m.start_ts), flaky).items() if k in SUBS and v.any()}
            if not masks:
                continue
            dur = d["y_duration_s"].astype(np.float64)
            fail = d["y_fail"].astype(bool)
            pf = cal.predict(d)
            dexp = d["dur_ema_asof"].astype(np.float64) + 1e-3
            methods = {f"f={x:g}": -(np.maximum(pf, x) / dexp) for x in grid}
            methods["QTF"] = d["dur_last_asof"].astype(np.float64) + 1e-3
            for name, prio in methods.items():
                for sub, tg in masks.items():
                    rng = np.random.default_rng([11, 0, ri])
                    r = score_run(prio, dur, fail, tg, rng)
                    rows.append({"project": p, "run_idx": ri, "pr_name": m.pr_name, "method": name, "subset": sub,
                                 "apfdc": r["apfdc"]})
        df = pd.DataFrame(rows)
        df.to_parquet(f, index=False)
        frames.append(df)
        print(f"  [floor:{split}] {p}: {df.run_idx.nunique() if len(df) else 0} runs in {time.time() - t0:.0f}s",
              flush=True)
    return pd.concat(frames, ignore_index=True)


def curve(df: pd.DataFrame, grid) -> dict:
    out = {}
    for name in [f"f={x:g}" for x in grid] + ["QTF"]:
        out[name] = {s: macro_ci(df[(df.method == name) & (df.subset == s)])["mean"] for s in SUBS}
    return out


def choose(cv: dict, grid) -> float:
    base = cv["f=0"]
    ok = [x for x in grid if cv[f"f={x:g}"]["All"] >= base["All"] - TOL_ALL]
    best = max(ok, key=lambda x: cv[f"f={x:g}"]["FirstFail-old"])
    return best if cv[f"f={best:g}"]["FirstFail-old"] > base["FirstFail-old"] else 0.0


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="both")
    a = ap.parse_args(argv)
    try:
        res = load_result("floor_tradeoff")
        res.pop("_meta", None)
    except FileNotFoundError:
        res = {}
    res["rule"] = __doc__.split("Selection rule")[1].split("Usage:")[0].strip()
    if a.step in ("val", "both"):
        dv = score_split("val", GRID)
        cv = curve(dv, GRID)
        fstar = choose(cv, GRID)
        res.update({"grid": GRID, "val_curve": cv, "f_star": fstar,
                    "n_val_runs": {s: int(dv[dv.subset == s].run_idx.nunique()) for s in SUBS}})
        save_result("floor_tradeoff", res)        # f* is fixed on disk before the test split is scored
        print(f"  f* = {fstar:g} (chosen on validation)", flush=True)
    if a.step in ("test", "both"):
        fstar = res["f_star"]
        grid = sorted({0.0, fstar})
        dt = score_split("test", GRID)             # full grid stored for the plot; f* was fixed above
        test = {"curve": curve(dt, GRID)}
        if fstar > 0:
            test["delta_vs_f0"] = {s: paired_diff_ci(dt[dt.subset == s], f"f={fstar:g}", "f=0") for s in SUBS}
            d_old, d_all = test["delta_vs_f0"]["FirstFail-old"], test["delta_vs_f0"]["All"]
            test["ship"] = bool(d_old["lo"] > 0 and d_all["mean"] >= -TOL_ALL)
        else:
            test["ship"] = False
        test["n_test_runs"] = {s: int(dt[dt.subset == s].run_idx.nunique()) for s in SUBS}
        res["test"] = test
        del grid
        save_result("floor_tradeoff", res)
        print(f"  test: ship floor = {test['ship']}", flush=True)


if __name__ == "__main__":
    main()
