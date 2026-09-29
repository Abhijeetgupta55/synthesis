"""3.C Dataset shape: runs / failed runs / builds / stages / PRs per project; temporal coverage."""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stp import paths
from stp.eda.common import PALETTE, TEXT_2, save_json, savefig, style

BUILD_KEY = ["project", "pr_name", "build_id"]


def summarize(runs: pd.DataFrame) -> dict:
    g = runs.groupby("project")
    tbl = pd.DataFrame({
        "runs": g.size(),
        "failed_runs": g.failed.sum(),
        "builds": runs[BUILD_KEY].drop_duplicates().groupby("project").size(),
        "failed_builds": runs[runs.failed][BUILD_KEY].drop_duplicates().groupby("project").size(),
        "stages": g.stage_id.nunique(),
        "prs": g.pr_name.nunique(),
        "paper_subset_runs": g.in_paper_subset.sum(),
        "first_month": g.month.min(),
        "last_month": g.month.max(),
    })
    tbl["failed_run_rate"] = tbl.failed_runs / tbl.runs
    tbl["share_of_all_runs"] = tbl.runs / tbl.runs.sum()
    tbl["share_of_paper_runs"] = tbl.paper_subset_runs / tbl.paper_subset_runs.sum()
    monthly = runs.drop_duplicates(BUILD_KEY).groupby(["project", "month"]).size().unstack("project").fillna(0)
    all_months = pd.period_range(runs.month.min(), runs.month.max(), freq="M").strftime("%Y-%m")
    monthly = monthly.reindex(all_months, fill_value=0)
    gaps = {}
    for p in paths.PROJECTS:
        s = monthly[p]
        active = s[(s.index >= tbl.loc[p, "first_month"]) & (s.index <= tbl.loc[p, "last_month"])]
        gaps[p] = {"active_span_months": len(active), "zero_build_months_inside_span": int((active == 0).sum()),
                   "zero_months": list(active[active == 0].index)}
    return {"per_project": tbl.reset_index().to_dict(orient="records"),
            "totals": tbl[["runs", "failed_runs", "builds", "failed_builds", "prs", "paper_subset_runs"]].sum().to_dict(),
            "macro_failed_run_rate": tbl.failed_run_rate.mean(),
            "pooled_failed_run_rate": tbl.failed_runs.sum() / tbl.runs.sum(),
            "monthly_gaps": gaps}, tbl, monthly


def plot(tbl: pd.DataFrame, monthly: pd.DataFrame) -> None:
    style()
    t = tbl.sort_values("runs")
    fig, ax = plt.subplots(figsize=(8, 4))
    y = np.arange(len(t))
    ax.barh(y, t.runs, color=PALETTE[0], height=0.75, label="all runs")
    ax.barh(y, t.failed_runs, color=PALETTE[1], height=0.4, label="failed runs")
    for i, (r, s) in enumerate(zip(t.runs, t.share_of_all_runs)):
        ax.text(r * 1.03, i, f"{r:,}  ({s:.1%})", va="center", fontsize=8, color=TEXT_2)
    ax.set_yticks(y, t.index)
    ax.set_xscale("log")
    ax.set_xlabel("test-suite runs (log)")
    ax.set_title("Runs per project (share of all 108k runs) — Kafka + TVM dominate")
    ax.legend(loc="lower right")
    ax.set_xlim(right=t.runs.max() * 8)
    savefig(fig, "C_runs_per_project")

    fig, ax = plt.subplots(figsize=(12, 4))
    m = monthly[paths.PROJECTS].T
    im = ax.imshow(np.log1p(m.values), aspect="auto", cmap="Blues")
    ax.set_yticks(range(len(m.index)), m.index)
    step = 3
    ax.set_xticks(range(0, len(m.columns), step), m.columns[::step], rotation=60, ha="right", fontsize=7)
    ax.grid(False)
    ax.set_title("Builds per month per project (colour = log(1+builds); white = no builds)")
    cb = fig.colorbar(im, ax=ax, shrink=0.8)
    ticks = [0, 10, 100, 1000]
    cb.set_ticks(np.log1p(ticks), labels=[str(x) for x in ticks])
    savefig(fig, "C_builds_per_month")


def run() -> dict:
    runs = pd.read_parquet(paths.RUNS_PQ)
    s, tbl, monthly = summarize(runs)
    save_json(s, "C_shape")
    plot(tbl, monthly)
    return s


if __name__ == "__main__":
    s = run()
    print(pd.DataFrame(s["per_project"]).to_string())
