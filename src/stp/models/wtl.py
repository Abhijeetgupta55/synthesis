"""Win / tie / loss counts of the models against the simple rules, per held-out test run (from stored per-run APFDc).

A run is a tie when |APFDc(model) − APFDc(rule)| < 0.001 (e.g. both put the failing test first). Counts are pooled
over all test-split failed runs of the subset and also given per project; macro means with CIs are in models.json.

Usage: python -m stp.models.wtl   -> reports/results/wtl.json
"""
from __future__ import annotations

import pandas as pd

from stp import paths
from stp.results import load_result, save_result

TIE = 0.001
EVAL = paths.PROCESSED / "eval"


def main() -> None:
    m = pd.concat([pd.read_parquet(f) for f in (EVAL / "models_runs").glob("main_*.parquet")], ignore_index=True)
    b = pd.concat([pd.read_parquet(f) for f in (EVAL / "baselines_runs").glob("*.parquet")], ignore_index=True)
    b = b[b.split == "test"]
    best = load_result("models")["best_simple_by_val"]
    key = ["project", "run_idx", "subset"]
    out = {"tie_threshold": TIE, "subsets": {}}
    for sub in ("All", "FirstFail-asof", "FirstFail-old", "New/Edited"):
        out["subsets"][sub] = {}
        for model in ("lgbm", "stack"):
            for rule in sorted({best[sub], "cbt_LastFail", "QTF", "ChangedOrNewFirst"}):
                x = m[(m.method == model) & (m.subset == sub)][key + ["apfdc"]].merge(
                    b[(b.method == rule) & (b.subset == sub)][key + ["apfdc"]], on=key, suffixes=("_m", "_r"))
                d = x.apfdc_m - x.apfdc_r
                per = {p: {"win": int((g > TIE).sum()), "tie": int((g.abs() <= TIE).sum()), "loss": int((g < -TIE).sum())}
                       for p, g in d.groupby(x.project)}
                out["subsets"][sub][f"{model}|{rule}"] = {"win": int((d > TIE).sum()), "tie": int((d.abs() <= TIE).sum()),
                                                         "loss": int((d < -TIE).sum()), "n": int(len(d)),
                                                         "per_project": per}
    save_result("wtl", out)
    print("wrote reports/results/wtl.json")


if __name__ == "__main__":
    main()
