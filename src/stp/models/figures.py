"""Phase 3 figures from results JSON + the baselines' rolling-origin summary.

  figures/calibration_reliability.png   reliability curves (raw vs isotonic) per base model, testC
  figures/ensemble_error_corr.png       residual-correlation matrix of base models and ensembles
  results/rolling_origin_baselines.json baselines on every 30-day window of the last 30% of each project (val+test):
                                        macro APFDc per subset, pooled over windows (no fitting needed, so every
                                        window is a true out-of-time evaluation)
Usage: python -m stp.models.figures
"""
from __future__ import annotations

import glob

import numpy as np
import pandas as pd

from stp import paths
from stp.eda.common import PALETTE, savefig, style
from stp.evaluation.bootstrap import macro_ci
from stp.results import load_result, save_result


def reliability_fig() -> None:
    import matplotlib.pyplot as plt

    c = load_result("models_classification")["reliability"]
    style()
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True)
    for ax, m in zip(axes, ("lr", "rf", "lgbm")):
        for i, kind in enumerate(("raw", "calibrated")):
            r = c.get(f"{m}|{kind}")
            if r:
                ax.plot(r["mean_pred"], r["frac_pos"], marker="o", color=PALETTE[i], label=kind)
        lim = max(max(c[f"{m}|raw"]["mean_pred"]), max(c[f"{m}|raw"]["frac_pos"]))
        ax.plot([0, lim], [0, lim], "--", color="#999", lw=1)
        ax.set_xscale("symlog", linthresh=1e-3)
        ax.set_yscale("symlog", linthresh=1e-3)
        ax.set_title(m.upper())
        ax.set_xlabel("mean predicted P(fail)")
    axes[0].set_ylabel("observed failure rate")
    axes[0].legend()
    fig.suptitle("Reliability on testC (deciles of prediction): raw vs isotonic-calibrated on valB")
    savefig(fig, "calibration_reliability")


def error_corr_fig() -> None:
    import matplotlib.pyplot as plt

    e = load_result("models_classification")["error_corr"]
    C = np.array(e["residual_corr"])
    style()
    fig, ax = plt.subplots(figsize=(4.8, 4))
    im = ax.imshow(C, cmap="Blues", vmin=0.9, vmax=1)
    ax.set_xticks(range(len(e["names"])), e["names"])
    ax.set_yticks(range(len(e["names"])), e["names"])
    ax.grid(False)
    for i in range(len(C)):
        for j in range(len(C)):
            ax.text(j, i, f"{C[i, j]:.2f}", ha="center", va="center", fontsize=8,
                    color="white" if C[i, j] > 0.97 else "black")
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("Residual (y − p) correlation, testC")
    savefig(fig, "ensemble_error_corr")


def rolling_baselines() -> dict:
    fs = sorted(glob.glob(str(paths.PROCESSED / "eval" / "baselines_runs" / "*.parquet")))
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d = d[d.roll_window.notna()]
    out = {"n_runs_by_subset": d[d.method == "Random"].groupby("subset").size().to_dict(), "cells": {}}
    for sub, g in d.groupby("subset"):
        for m, x in g.groupby("method"):
            out["cells"].setdefault(sub, {})[m] = macro_ci(x, "apfdc", n_boot=500, seed=7)
        best = max((m for m in out["cells"][sub] if m not in ("Oracle", "Random")),
                   key=lambda m: out["cells"][sub][m]["mean"])
        out.setdefault("best", {})[sub] = best
    out["doc"] = __doc__
    save_result("rolling_origin_baselines", out)
    return out


def main() -> None:
    reliability_fig()
    error_corr_fig()
    r = rolling_baselines()
    print("rolling-origin best baseline by subset:", r["best"], r["n_runs_by_subset"])


if __name__ == "__main__":
    main()
