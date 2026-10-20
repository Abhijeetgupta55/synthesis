"""Phase 2.3-2.6: evaluate every as-of baseline on the failed val + test runs and summarise with PR-clustered CIs.

Per-run results: data/processed/eval/baselines_runs/<project>.parquet (resumable per project).
Summary:         reports/results/baselines.json
  cells[split][subset][group][method] = APFDc macro + 95% CI, median minutes to first failure (test time and an
                                         approximate wall-clock), share of runs whose first failure is in the first
                                         10% of test time, n runs / PRs (flag when a project has < 30 runs)
  best_simple[subset]                  = best simple baseline, chosen on *val* macro APFDc (never on test)
  vs_best[subset][group][method]       = paired test-split difference to that baseline (CI, excludes zero?)
Groups: macro over all 10 projects, Kafka, TVM, and the 8 small projects pooled as one macro group.
Usage: python -m stp.baselines.run_baselines [--workers 3]
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import time

import numpy as np
import pandas as pd

from stp import paths
from stp.baselines import heuristics as H
from stp.evaluation.bootstrap import macro_ci, median_ci, paired_diff_ci
from stp.evaluation.harness import SUBSETS, eval_runs, evaluate_methods
from stp.features.store import store_ready
from stp.results import load_result, save_result

OUT = paths.PROCESSED / "eval" / "baselines_runs"
SMALL = [p for p in paths.PROJECTS if p not in ("kafka", "tvm")]
GROUPS = {"macro10": None, "kafka": ["kafka"], "tvm": ["tvm"], "small8": SMALL}


def wallclock_factor() -> dict[str, float]:
    """median(build_duration / summed test time) per project, capped at 1: above 1 the build is dominated by
    non-test work (compilation, setup), and test time is not compressed by parallelism."""
    r = load_result("phase0_facts")["fact3"]["median_build_duration_over_suite"]["per_project"]
    return {p: min(1.0, float(v)) for p, v in r.items()}


def project_job(p: str) -> str:
    f = OUT / f"{p}.parquet"
    if f.exists():
        return f"{p}: cached"
    t0 = time.time()
    runs = eval_runs(p, ("val", "test"))
    seeds = {m: (20 if m == "Random" else 1 if m == "Oracle" else H.TIE_SEEDS) for m in H.METHODS}
    df = evaluate_methods(p, H.METHODS, runs, H.COLUMNS, seeds, base_seed=11)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(f, index=False)
    return f"{p}: {len(runs):,} runs in {time.time() - t0:.0f}s"


def summarise(df: pd.DataFrame) -> dict:
    wc = wallclock_factor()
    df = df.copy()
    df["ttff_min"] = df.ttff_s / 60.0
    df["ttff_wall_min"] = df.ttff_min * df.project.map(wc)
    cells: dict = {}
    for split in ("val", "test"):
        for sub in SUBSETS:
            d = df[(df.split == split) & (df.subset == sub)]
            for gname, projs in GROUPS.items():
                for m in H.METHODS:
                    x = d[d.method == m]
                    if projs is not None:
                        x = x[x.project.isin(projs)]
                    if x.empty:
                        continue
                    ci = macro_ci(x, "apfdc", seed=1)
                    cells.setdefault(split, {}).setdefault(sub, {}).setdefault(gname, {})[m] = {
                        "apfdc": ci,
                        "ttff_min_median": median_ci(x, "ttff_min", n_boot=400, seed=2),
                        "ttff_wall_min_median_approx": float(x.ttff_wall_min.median()),
                        "first10_share": float(x.first10.mean()),
                        "n_runs_per_project": x.groupby("project").size().to_dict(),
                    }
    best, vs = {}, {}
    for sub in SUBSETS:
        val = cells.get("val", {}).get(sub, {}).get("macro10", {})
        cand = {m: v["apfdc"]["mean"] for m, v in val.items() if m in H.SIMPLE and v["apfdc"]["mean"] is not None}
        if not cand:
            continue
        best[sub] = max(cand, key=cand.get)
        d = df[(df.split == "test") & (df.subset == sub)]
        for gname, projs in GROUPS.items():
            for m in H.METHODS:
                if m == best[sub]:
                    continue
                vs.setdefault(sub, {}).setdefault(gname, {})[m] = paired_diff_ci(d, m, best[sub], projects=projs, seed=3)
    return {"cells": cells, "best_simple_by_val": best, "vs_best_on_test": vs, "wallclock_factor": wc,
            "groups": GROUPS, "methods": list(H.METHODS), "doc": H.__doc__}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    projects = sorted([p for p in paths.PROJECTS if store_ready(p)],
                      key=lambda p: -len(pd.read_parquet(paths.FEATURES_DIR / f"project={p}" / "runs.parquet")))
    with mp.Pool(a.workers) as pool:
        for msg in pool.imap_unordered(project_job, projects):
            print("  [baselines]", msg, flush=True)
    df = pd.concat([pd.read_parquet(OUT / f"{p}.parquet") for p in projects], ignore_index=True)
    res = summarise(df)
    res["start_order_vs_asof"] = load_result("gate2_reproduction")["macro"] if (paths.RESULTS / "gate2_reproduction.json").exists() else None
    save_result("baselines", res)
    print("best simple baseline (chosen on val):", res["best_simple_by_val"])


if __name__ == "__main__":
    main()
