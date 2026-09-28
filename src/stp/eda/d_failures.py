"""3.D Failure structure: failures per failed run, per-test failure frequency tail, first-time failures, flakiness.

first-time failure (ftf): failing test class with no failure of the same class in any strictly earlier run
(by build_timestamp) of the same (project, stage). History = all 108k runs. Because the first months of each
project have no history, ftf is inflated early on; we also report it after a burn-in (first 15% of each project's
runs by time, i.e. roughly the part a model would train on).
"""
from __future__ import annotations

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stp import paths
from stp.eda.common import GRID, PALETTE, TEXT_2, save_json, savefig, style, with_macro

RUN_KEY = ["project", "pr_name", "build_id", "stage_id"]
BURN_IN = 0.15


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    runs = pd.read_parquet(paths.RUNS_PQ)
    fails = duckdb.sql(f"SELECT * FROM read_parquet('{paths.FAILURES_PQ.as_posix()}')").df()
    # burn-in cut per project on run timestamps
    cut = runs.groupby("project").build_timestamp.quantile(BURN_IN).rename("burn_in_ts")
    runs = runs.join(cut, on="project")
    runs["after_burn_in"] = runs.build_timestamp > runs.burn_in_ts
    fails = fails.merge(runs[RUN_KEY + ["after_burn_in"]], on=RUN_KEY, how="left")
    return runs, fails


def per_run_labels(runs: pd.DataFrame, fails: pd.DataFrame) -> pd.DataFrame:
    agg = fails.groupby(RUN_KEY).agg(n_fail=("ftf", "size"), n_ftf=("ftf", "sum"),
                                     n_flaky=("is_jira_flaky", "sum")).reset_index()
    r = runs[runs.failed][RUN_KEY + ["num_fail_class", "after_burn_in", "in_paper_subset"]].merge(agg, on=RUN_KEY, how="left")
    r["has_ftf"] = r.n_ftf > 0
    r["all_ftf"] = r.n_ftf == r.n_fail
    return r


def summarize(runs: pd.DataFrame, fails: pd.DataFrame, r: pd.DataFrame) -> dict:
    fr = runs[runs.failed]
    g = fr.groupby("project").num_fail_class
    per_test = fails.groupby(["project", "testclass"]).size().rename("n").reset_index()

    def tail_stats(d):
        n = np.sort(d.n.values)[::-1]
        k1 = max(1, int(np.ceil(0.01 * len(n))))
        return pd.Series({"failing_test_classes": len(n), "share_failed_once": (n == 1).mean(),
                          "share_of_failures_top1pct_tests": n[:k1].sum() / n.sum(),
                          "share_of_failures_top10_tests": n[:10].sum() / n.sum(), "max_failures_one_test": n[0]})

    tails = per_test.groupby("project").apply(tail_stats, include_groups=False)
    fp = fails.groupby("project")
    rb = r[r.after_burn_in]
    fb = fails[fails.after_burn_in]
    out = {
        "failed_classes_per_failed_run": {
            "median": with_macro(g.median().to_dict()), "mean": with_macro(g.mean().to_dict()),
            "p90": with_macro(g.quantile(0.9).to_dict()), "share_exactly_one": with_macro(g.apply(lambda s: (s == 1).mean()).to_dict())},
        "per_test_failure_tail": {c: with_macro(tails[c].to_dict()) for c in tails.columns},
        "ftf_share_of_failures": with_macro(fp.ftf.mean().to_dict()),
        "ftf_share_of_failures_after_burn_in": with_macro(fb.groupby("project").ftf.mean().to_dict()),
        "ftf_share_of_failures_anystage_def": with_macro(fp.ftf_anystage.mean().to_dict()),
        "failed_runs_with_any_ftf": with_macro(r.groupby("project").has_ftf.mean().to_dict()),
        "failed_runs_all_ftf": with_macro(r.groupby("project").all_ftf.mean().to_dict()),
        "failed_runs_all_ftf_after_burn_in": with_macro(rb.groupby("project").all_ftf.mean().to_dict()),
        "failed_runs_with_any_ftf_after_burn_in": with_macro(rb.groupby("project").has_ftf.mean().to_dict()),
        "n_ftf_runs": r.groupby("project").has_ftf.sum().to_dict(),
        "n_ftf_runs_after_burn_in": rb.groupby("project").has_ftf.sum().to_dict(),
        "n_failure_rows": fp.size().to_dict(),
        "flaky": {
            "share_failures_jira_flaky": with_macro(fp.is_jira_flaky.mean().to_dict()),
            "share_failures_flaky_before_fix": with_macro(fp.flaky_before_fix.mean().to_dict()),
            "share_failures_flaky_after_fix": with_macro(
                fp.apply(lambda d: (d.is_jira_flaky & ~d.flaky_before_fix).mean(), include_groups=False).to_dict()),
            "share_failed_runs_only_flaky": with_macro(
                r.groupby("project").apply(lambda d: (d.n_flaky == d.n_fail).mean(), include_groups=False).to_dict()),
            "n_listed_flaky_classes_matched": fails[fails.is_jira_flaky].groupby("project").testclass.nunique().to_dict(),
            "share_ftf_rows_that_are_jira_flaky": with_macro(
                fails[fails.ftf].groupby("project").is_jira_flaky.mean().to_dict()),
        },
        "definition": __doc__,
    }
    return out


def plot(fails: pd.DataFrame, r: pd.DataFrame, s: dict) -> None:
    style()
    projects = paths.PROJECTS
    # 1) first-time failure shares
    fig, ax = plt.subplots(figsize=(10, 3.8))
    x = np.arange(len(projects) + 1)
    series = [("share of failing (run,class) rows that are first-time", s["ftf_share_of_failures_after_burn_in"], PALETTE[0]),
              ("share of failed runs with ≥1 first-time failure", s["failed_runs_with_any_ftf_after_burn_in"], PALETTE[1]),
              ("share of failed runs where ALL failures are first-time", s["failed_runs_all_ftf_after_burn_in"], PALETTE[2])]
    w = 0.27
    for i, (lab, d, c) in enumerate(series):
        vals = [d["per_project"].get(p, np.nan) for p in projects] + [d["macro"]]
        ax.bar(x + (i - 1) * w, vals, w - 0.02, color=c, label=lab)
    ax.set_xticks(x, projects + ["MACRO"])
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.set_ylim(0, 1)
    ax.set_title(f"First-time failures per project (after {int(BURN_IN*100)}% burn-in)")
    ax.legend(loc="upper left", fontsize=7.5)
    savefig(fig, "D_first_time_failures")

    # 2) rank-frequency long tail, small multiples
    fig, axes = plt.subplots(2, 5, figsize=(13, 5), sharey=False)
    per_test = fails.groupby(["project", "testclass"]).size()
    for ax, p in zip(axes.flat, projects):
        n = np.sort(per_test.loc[p].values)[::-1] if p in per_test.index.get_level_values(0) else np.array([1])
        ax.loglog(np.arange(1, len(n) + 1), n, color=PALETTE[0], lw=2)
        ax.set_title(f"{p} ({len(n):,} failing classes)", fontsize=9)
    for ax in axes[1]:
        ax.set_xlabel("test-class rank")
    for ax in axes[:, 0]:
        ax.set_ylabel("# failures")
    fig.suptitle("Per-test-class failure frequency: long tail (log-log)", fontweight="bold")
    fig.tight_layout()
    savefig(fig, "D_failure_frequency_tail")

    # 3) failed classes per failed run
    fig, ax = plt.subplots(figsize=(9, 3.4))
    data = [r[r.project == p].num_fail_class.clip(lower=1).values for p in projects]
    ax.boxplot(data, tick_labels=projects, showfliers=False, patch_artist=True,
               boxprops=dict(facecolor=PALETTE[1], alpha=0.35, edgecolor=PALETTE[1]),
               medianprops=dict(color=PALETTE[1], lw=2), whiskerprops=dict(color=TEXT_2), capprops=dict(color=TEXT_2))
    ax.set_yscale("log")
    ax.set_ylabel("failed classes (log)")
    ax.set_title("Failed test classes per failed run")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    savefig(fig, "D_failed_classes_per_run")

    # 4) flaky share
    fig, ax = plt.subplots(figsize=(9, 3.2))
    fl = s["flaky"]
    x = np.arange(len(projects) + 1)
    b = [fl["share_failures_flaky_before_fix"]["per_project"].get(p, 0) for p in projects] + [fl["share_failures_flaky_before_fix"]["macro"]]
    a = [fl["share_failures_flaky_after_fix"]["per_project"].get(p, 0) for p in projects] + [fl["share_failures_flaky_after_fix"]["macro"]]
    ax.bar(x, b, 0.7, color=PALETTE[3], label="JIRA-flaky, before fix date")
    ax.bar(x, a, 0.7, bottom=b, color=PALETTE[6], label="JIRA-flaky, after fix date")
    ax.set_xticks(x, projects + ["MACRO"])
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.set_ylabel("share of all failures")
    ax.set_title("Failures from JIRA-listed flaky test classes")
    ax.legend(fontsize=8)
    savefig(fig, "D_flaky_share")


def run() -> dict:
    runs, fails = load()
    r = per_run_labels(runs, fails)
    r.to_parquet(paths.INTERIM / "failed_run_labels.parquet", index=False)
    s = summarize(runs, fails, r)
    save_json(s, "D_failures")
    plot(fails, r, s)
    return s


if __name__ == "__main__":
    import json

    s = run()
    print(json.dumps({k: (v.get("macro") if isinstance(v, dict) and "macro" in v else None) for k, v in s.items()}, indent=1))
