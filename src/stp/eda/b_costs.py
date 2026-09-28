"""3.B The problem is real: test-suite durations and sizes (full processed dataset, 108k runs)."""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stp import paths
from stp.eda.common import GRID, PALETTE, TEXT_2, save_json, savefig, style, with_macro

THRESHOLDS_H = [1, 2, 6]


def summarize(runs: pd.DataFrame) -> dict:
    out = {}
    for name, d in [("full", runs), ("paper_subset", runs[runs.in_paper_subset])]:
        g = d.groupby("project")
        sec = {
            "n_runs": g.size().to_dict(),
            "duration_h_median": with_macro(g.duration_h.median().to_dict()),
            "duration_h_mean": with_macro(g.duration_h.mean().to_dict()),
            "classes_per_run_median": with_macro(g.n_classes.median().to_dict()),
            "classes_per_run_mean": with_macro(g.n_classes.mean().to_dict()),
        }
        for t in THRESHOLDS_H:
            sec[f"share_runs_over_{t}h"] = with_macro(g.duration_h.apply(lambda s: (s > t).mean()).to_dict())
        sec["pooled_share_over_2h"] = (d.duration_h > 2).mean()
        out[name] = sec
    return out


def plot(runs: pd.DataFrame) -> None:
    style()
    projects = paths.PROJECTS
    # small multiples: each project's CDF in colour, all others as grey context
    fig, axes = plt.subplots(2, 5, figsize=(13, 5), sharex=True, sharey=True)
    grid = np.logspace(-2, np.log10(max(runs.duration_h.max(), 50)), 300)
    cdfs = {p: np.searchsorted(np.sort(runs[runs.project == p].duration_h.values), grid, side="right")
            / max((runs.project == p).sum(), 1) for p in projects}
    for ax, p in zip(axes.flat, projects):
        for q in projects:
            if q != p:
                ax.plot(grid, cdfs[q], color=GRID, lw=1)
        ax.plot(grid, cdfs[p], color=PALETTE[0], lw=2)
        for t in THRESHOLDS_H:
            ax.axvline(t, color=TEXT_2, lw=0.6, ls=":")
        ax.set_xscale("log")
        ax.set_title(f"{p} (n={int((runs.project == p).sum()):,})", fontsize=9)
    for ax in axes[1]:
        ax.set_xlabel("test-suite duration (h, log)")
    for ax in axes[:, 0]:
        ax.set_ylabel("share of runs ≤ x")
    fig.suptitle("CDF of test-suite run duration per project (dotted: 1h / 2h / 6h)", fontweight="bold")
    fig.tight_layout()
    savefig(fig, "B_duration_cdf")

    fig, ax = plt.subplots(figsize=(9, 3.6))
    data = [runs[runs.project == p].n_classes.values for p in projects]
    ax.boxplot(data, tick_labels=projects, showfliers=False, patch_artist=True,
               boxprops=dict(facecolor=PALETTE[0], alpha=0.35, edgecolor=PALETTE[0]),
               medianprops=dict(color=PALETTE[0], lw=2), whiskerprops=dict(color=TEXT_2), capprops=dict(color=TEXT_2))
    ax.set_yscale("log")
    ax.set_ylabel("test classes per run (log)")
    ax.set_title("Test classes executed per run (whiskers 1.5 IQR, outliers hidden)")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    savefig(fig, "B_classes_per_run")


def run() -> dict:
    runs = pd.read_parquet(paths.RUNS_PQ)
    s = summarize(runs)
    save_json(s, "B_costs")
    plot(runs)
    return s


if __name__ == "__main__":
    import json

    print(json.dumps(run()["full"], indent=1, default=str)[:3000])
