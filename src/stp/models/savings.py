"""How much waiting each ordering saves, from the stored per-run results (held-out test split, all failed runs).

For every failed run we know, per ordering, the time until the first failing test finishes (TTFF) and the summed
suite time. From those: the share of the suite a developer waits through before the first failure, the share of
failed runs whose first failure appears in the first 10% of the suite, and minutes waited. 'Random' stands in for
a fixed order that ignores the change, because LRTS does not record the real execution order.
Aggregation: per project median (or mean for the 10% share), then the mean over the 10 projects (macro), as in
the rest of the study. The dashboard's savings calculator multiplies these shares by the user's own suite length.

Usage: python -m stp.models.savings   -> reports/results/savings.json
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from stp import paths
from stp.results import load_result, save_result

EVAL = paths.PROCESSED / "eval"
METHODS = ["Random", "QTF", "cbt_LastFail", "ChangedOrNewFirst", "lgbm", "stack", "Oracle"]


def main() -> None:
    m = pd.concat([pd.read_parquet(f) for f in (EVAL / "models_runs").glob("main_*.parquet")], ignore_index=True)
    b = pd.concat([pd.read_parquet(f) for f in (EVAL / "baselines_runs").glob("*.parquet")], ignore_index=True)
    b = b[b.split == "test"]
    d = pd.concat([m, b], ignore_index=True)
    d = d[(d.subset == "All") & d.method.isin(METHODS)].copy()
    d["frac"] = d.ttff_s / d.suite_s
    out = {"n_runs": int(d[d.method == "lgbm"].run_idx.size), "methods": {}}
    for meth, g in d.groupby("method"):
        per = g.groupby("project").agg(frac_median=("frac", "median"), first10=("first10", "mean"),
                                        ttff_min_median=("ttff_s", lambda s: float(np.median(s)) / 60),
                                        suite_min_median=("suite_s", lambda s: float(np.median(s)) / 60))
        out["methods"][meth] = {"frac_waited_macro": float(per.frac_median.mean()),
                                "share_first_failure_in_first_10pct_macro": float(per.first10.mean()),
                                "ttff_min_median_macro": float(per.ttff_min_median.mean()),
                                "suite_min_median_macro": float(per.suite_min_median.mean()),
                                "per_project": per.round(4).to_dict(orient="index")}
    fx = load_result("phase0_facts")
    out["median_build_hours"] = fx["fact1"]["build_duration"]["med_build_duration_s"] / 3600
    out["note"] = ("frac = time to the first failure / summed suite time. 'Random' approximates a fixed order. "
                   "Summed test time is not wall-clock time when tests run in parallel; the shares still apply.")
    save_result("savings", out)
    for k, v in out["methods"].items():
        print(f"{k:18s} waited {v['frac_waited_macro']:.1%} of the suite; first failure in first 10%: "
              f"{v['share_first_failure_in_first_10pct_macro']:.0%}")


if __name__ == "__main__":
    main()
