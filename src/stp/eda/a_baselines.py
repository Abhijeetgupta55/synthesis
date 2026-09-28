"""3.A Motivation: reproduce the LRTS paper's TCP baselines from the eval_outcome files in the LRTS repo.

Protocol (mirrors LRTS analysis_paper/analysis_utils.py::agg_project_wise_data):
  * drop stages with <= 50 runs in dataset.csv (paper's `filter_stages`);
  * per run, average over random seeds; per project, average over runs;
  * macro = mean over projects.  ML_* rows only exist for the ML test split (paper does the same).
"""
from __future__ import annotations

import pandas as pd

from stp import paths
from stp.eda.common import PALETTE, TEXT_2, save_json, savefig, style

VARIANTS = {
    "d_nofilter": "All",
    "d_jira_stageunique_freqfail": "DeConf",
    "d_first_jira_stageunique": "FirstFail",
}
TECHNIQUES = [
    "Random", "QTF", "LastFail_Asc", "FailCount_Desc", "TestFile_FailFreq", "IR_GitDiff",
    "IR_GitDiff_tfidf", "ML_f1", "ML_f3", "ML_fall", "cbt_LastFail_Asc", "cbt_FailCount_Desc",
    "cbt_IR_GitDiff", "cbt_ML_fall",
]
HEADLINE = ["Random", "QTF", "cbt_LastFail_Asc", "cbt_IR_GitDiff", "cbt_ML_fall"]
KEY = ["project", "pr_name", "build_id", "stage_id"]
METRIC = "APFDc_uniqueBug"


def paper_stages() -> dict[str, set[str]]:
    ds = pd.read_csv(paths.LRTS_DATASET_CSV, usecols=["project", "stage_id"])
    n = ds.groupby(["project", "stage_id"]).size()
    keep = n[n > 50].reset_index()
    return {p: set(g.stage_id) for p, g in keep.groupby("project")}


def load_per_run(stage_filter: bool = True) -> pd.DataFrame:
    """One row per (variant, technique, run): seed-averaged APFDc_uniqueBug."""
    stages = paper_stages()
    frames = []
    for var in VARIANTS:
        for proj in paths.PROJECTS:
            for tcp in TECHNIQUES:
                f = paths.LRTS_EVAL_OUTCOME / var / proj / f"{tcp}.csv.zip"
                if not f.exists():
                    print(f"  MISSING {f}")
                    continue
                d = pd.read_csv(f, usecols=KEY + ["seed", METRIC], dtype={"stage_id": str})
                if stage_filter:
                    d = d[d.stage_id.isin(stages.get(proj, set()))]
                d = d.groupby(KEY, as_index=False)[METRIC].mean()
                d["variant"], d["tcp"] = var, tcp
                frames.append(d)
    return pd.concat(frames, ignore_index=True)


def summarize(per_run: pd.DataFrame) -> dict:
    out = {}
    for var, label in VARIANTS.items():
        d = per_run[per_run.variant == var]
        means = d.groupby(["tcp", "project"])[METRIC].mean().unstack("project")
        nruns = d.groupby(["tcp", "project"]).size().unstack("project")
        out[label] = {
            "mean_apfdc": {t: {**{p: means.loc[t].get(p) for p in paths.PROJECTS},
                               "macro": means.loc[t].mean()} for t in TECHNIQUES if t in means.index},
            "n_runs": {t: {**{p: nruns.loc[t].get(p) for p in paths.PROJECTS},
                           "total": nruns.loc[t].sum()} for t in TECHNIQUES if t in nruns.index},
        }
    return out


def plot_headline(summary: dict) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    style()
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = np.arange(len(HEADLINE))
    w = 0.38
    for i, (label, color) in enumerate([("All", PALETTE[0]), ("FirstFail", PALETTE[1])]):
        vals = [summary[label]["mean_apfdc"][t]["macro"] for t in HEADLINE]
        bars = ax.bar(x + (i - 0.5) * w, vals, w - 0.03, color=color, label=f"LRTS-{label}")
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.3f}", ha="center", fontsize=8, color=TEXT_2)
    ax.set_xticks(x, HEADLINE)
    ax.set_ylim(0, 1)
    ax.set_ylabel("APFDc (uniqueBug), macro over projects")
    ax.set_title("History-based ranking collapses on first-time failures")
    ax.legend(loc="upper left", ncols=2)
    n_ml = summary["FirstFail"]["n_runs"]["cbt_ML_fall"]["total"]
    n_all = summary["FirstFail"]["n_runs"]["Random"]["total"]
    fig.text(0.01, -0.04, f"Paper protocol (stages with >50 runs). cbt_ML_fall is scored only on the paper's ML test split "
             f"({n_ml} of {n_all} FirstFail runs), so it is not directly comparable.", fontsize=7, color=TEXT_2)
    savefig(fig, "A_headline_all_vs_firstfail")

    # full heatmap-ish table figure: technique x variant (macro)
    fig, ax = plt.subplots(figsize=(6.5, 5))
    labels = list(VARIANTS.values())
    mat = np.array([[summary[l]["mean_apfdc"].get(t, {}).get("macro", np.nan) for l in labels] for t in TECHNIQUES])
    im = ax.imshow(mat, cmap="Blues", vmin=0.2, vmax=1.0, aspect="auto")
    ax.set_xticks(range(len(labels)), labels)
    ax.set_yticks(range(len(TECHNIQUES)), TECHNIQUES)
    ax.grid(False)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, f"{mat[i, j]:.3f}", ha="center", va="center", fontsize=8,
                    color="white" if mat[i, j] > 0.7 else "black")
    ax.set_title("Macro APFDc by technique and dataset variant")
    fig.colorbar(im, ax=ax, shrink=0.8)
    savefig(fig, "A_macro_table")


def run() -> dict:
    per_run = load_per_run(stage_filter=True)
    paths.INTERIM.mkdir(parents=True, exist_ok=True)
    per_run.to_parquet(paths.BASELINES_PQ, index=False)
    summary = summarize(per_run)
    # sensitivity: without the paper's >50-runs-per-stage filter
    nofilt = summarize(load_per_run(stage_filter=False))
    summary["sensitivity_no_stage_filter_macro"] = {
        l: {t: nofilt[l]["mean_apfdc"][t]["macro"] for t in HEADLINE} for l in VARIANTS.values()}
    summary["protocol"] = __doc__
    save_json(summary, "A_baselines")
    plot_headline(summary)
    return summary


if __name__ == "__main__":
    s = run()
    for label in VARIANTS.values():
        print(f"\n== {label}")
        for t in TECHNIQUES:
            m = s[label]["mean_apfdc"].get(t)
            if m:
                print(f"  {t:22s} macro={m['macro']:.3f}  n_runs={s[label]['n_runs'][t]['total']}")
