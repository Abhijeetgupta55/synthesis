"""3.E Change data: size of the change per build, availability of line-level patches, changed-file extensions.

A "build" is (project, pr_name, build_id, trunk_sha, build_head_sha); the change is GitHub's compare of
trunk_sha...build_head_sha, exactly as LRTS used it.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stp import paths
from stp.eda.common import PALETTE, TEXT_2, save_json, savefig, style, with_macro


def summarize(ch: pd.DataFrame, cf: pd.DataFrame) -> dict:
    ch = ch.copy()
    ch["lines"] = ch.additions + ch.deletions
    found = ch[ch.compare_found]
    g = found.groupby("project")
    cf = cf.copy()
    cf["ext"] = cf.filename.str.extract(r"(\.[A-Za-z0-9_+-]+)$")[0].str.lower().fillna("(none)")
    top_overall = cf.ext.value_counts(normalize=True).head(15)
    top_pp = {p: d.ext.value_counts(normalize=True).head(5).round(4).to_dict() for p, d in cf.groupby("project")}
    return {
        "builds": ch.groupby("project").size().to_dict(),
        "compare_found_share": with_macro(ch.groupby("project").compare_found.mean().to_dict()),
        "files_per_build_median": with_macro(g.n_files.median().to_dict()),
        "files_per_build_p90": with_macro(g.n_files.quantile(0.9).to_dict()),
        "lines_per_build_median": with_macro(g.lines.median().to_dict()),
        "lines_per_build_p90": with_macro(g.lines.quantile(0.9).to_dict()),
        "share_builds_with_patch_text": with_macro(g.has_patch.mean().to_dict()),
        "share_builds_with_diff_file": with_macro(ch.groupby("project").has_diff_file.mean().to_dict()),
        "share_changed_files_with_patch": with_macro(cf.groupby("project").has_patch.mean().to_dict()),
        "share_builds_with_zero_files": with_macro(g.apply(lambda d: (d.n_files == 0).mean(), include_groups=False).to_dict()),
        "share_builds_over_300_files": with_macro(g.apply(lambda d: (d.n_files >= 300).mean(), include_groups=False).to_dict()),
        "commits_per_build_median": with_macro(g.n_commits.median().to_dict()),
        "authors_per_build_median": with_macro(g.n_authors.median().to_dict()),
        "top_extensions_overall": top_overall.round(4).to_dict(),
        "top_extensions_per_project": top_pp,
    }


def plot(ch: pd.DataFrame, s: dict) -> None:
    style()
    ch = ch[ch.compare_found].copy()
    ch["lines"] = ch.additions + ch.deletions
    projects = paths.PROJECTS
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8))
    for ax, col, lab, c in [(axes[0], "n_files", "changed files per build", PALETTE[0]),
                            (axes[1], "lines", "changed lines per build", PALETTE[2])]:
        data = [ch[ch.project == p][col].clip(lower=1).values for p in projects]
        ax.boxplot(data, tick_labels=projects, showfliers=False, patch_artist=True,
                   boxprops=dict(facecolor=c, alpha=0.35, edgecolor=c), medianprops=dict(color=c, lw=2),
                   whiskerprops=dict(color=TEXT_2), capprops=dict(color=TEXT_2))
        ax.set_yscale("log")
        ax.set_title(lab + " (log, outliers hidden)")
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    savefig(fig, "E_change_size")

    top = pd.Series(s["top_extensions_overall"]).head(12)[::-1]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.barh(top.index, top.values, color=PALETTE[0])
    for i, v in enumerate(top.values):
        ax.text(v, i, f" {v:.1%}", va="center", fontsize=8, color=TEXT_2)
    ax.set_xlabel("share of changed-file entries (pooled)")
    ax.set_title("Most common changed-file extensions")
    savefig(fig, "E_extensions")


def run() -> dict:
    ch = pd.read_parquet(paths.CHANGES_PQ)
    cf = pd.read_parquet(paths.CHANGED_FILES_PQ, columns=["project", "filename", "has_patch"])
    s = summarize(ch, cf)
    save_json(s, "E_changes")
    plot(ch, s)
    return s


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=1, default=str)[:4000])
