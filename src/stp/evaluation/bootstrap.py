"""PR-clustered bootstrap for macro averages and paired differences.

Stages and rebuilds of one PR share code and flakiness, so runs are not independent. Each bootstrap replicate
resamples PRs (with replacement) independently inside every project, recomputes each project's mean over the
runs of the drawn PRs, then averages projects (macro). Paired differences resample the per-run difference
(method A − method B on the same runs), so the correlation between methods is kept.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

N_BOOT = 2000


def _project_boot(values: np.ndarray, clusters: np.ndarray, n_boot: int, rng) -> np.ndarray:
    """n_boot bootstrap means of `values` resampling `clusters`."""
    codes, uniq = pd.factorize(clusters)
    k = len(uniq)
    sums = np.bincount(codes, weights=values, minlength=k)
    cnts = np.bincount(codes, minlength=k).astype(np.float64)
    w = rng.multinomial(k, np.full(k, 1.0 / k), size=n_boot).astype(np.float64)
    return (w @ sums) / np.maximum(w @ cnts, 1e-12)


def macro_ci(df: pd.DataFrame, value: str = "apfdc", projects: list[str] | None = None, n_boot: int = N_BOOT,
             seed: int = 0, alpha: float = 0.05) -> dict:
    """Macro mean over projects (mean of per-project run means) with a PR-clustered percentile CI."""
    rng = np.random.default_rng(seed)
    d = df if projects is None else df[df.project.isin(projects)]
    d = d.dropna(subset=[value])
    if d.empty:
        return {"mean": None, "lo": None, "hi": None, "n_runs": 0, "n_prs": 0, "n_projects": 0, "small_n": True}
    per, boots = {}, []
    for p, g in d.groupby("project"):
        per[p] = float(g[value].mean())
        boots.append(_project_boot(g[value].to_numpy(np.float64), g.pr_name.to_numpy(), n_boot, rng))
    b = np.mean(boots, axis=0)
    n_runs = len(d)
    return {"mean": float(np.mean(list(per.values()))), "lo": float(np.quantile(b, alpha / 2)),
            "hi": float(np.quantile(b, 1 - alpha / 2)), "n_runs": int(n_runs), "n_prs": int(d.pr_name.nunique()),
            "n_projects": len(per), "small_n": bool(min(d.groupby("project").size()) < 30), "per_project": per}


def paired_diff_ci(df: pd.DataFrame, a: str, b: str, value: str = "apfdc", projects: list[str] | None = None,
                   n_boot: int = N_BOOT, seed: int = 0) -> dict:
    """CI of macro(mean_a − mean_b) on the runs both methods were scored on (rows keyed by project, run_idx)."""
    key = ["project", "run_idx", "pr_name"]
    x = df[df.method == a][key + [value]].merge(df[df.method == b][key + [value]], on=key, suffixes=("_a", "_b"))
    x["diff"] = x[f"{value}_a"] - x[f"{value}_b"]
    r = macro_ci(x, "diff", projects, n_boot, seed)
    r["excludes_zero"] = r["lo"] is not None and (r["lo"] > 0 or r["hi"] < 0)
    return r


def median_ci(df: pd.DataFrame, value: str, n_boot: int = 1000, seed: int = 0, alpha: float = 0.05) -> dict:
    """Median of `value` over runs (pooled within the frame) with a PR-clustered percentile CI."""
    d = df.dropna(subset=[value])
    if d.empty:
        return {"median": None, "lo": None, "hi": None, "n_runs": 0}
    rng = np.random.default_rng(seed)
    codes, uniq = pd.factorize(d.pr_name)
    order = np.argsort(codes, kind="stable")
    vals = d[value].to_numpy(np.float64)[order]
    starts = np.r_[0, np.cumsum(np.bincount(codes, minlength=len(uniq)))]
    meds = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, len(uniq), len(uniq))
        idx = np.concatenate([np.arange(starts[c], starts[c + 1]) for c in pick])
        meds[i] = np.median(vals[idx])
    return {"median": float(np.median(vals)), "lo": float(np.quantile(meds, alpha / 2)),
            "hi": float(np.quantile(meds, 1 - alpha / 2)), "n_runs": int(len(d))}
