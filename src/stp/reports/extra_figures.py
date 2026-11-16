"""Figures that fill the rubric gaps found in the audit (AUDIT.md A5), drawn from results JSON only.

  cls_models.png          classification: PR-AUC, ROC-AUC and precision / recall at the top 10 / 50 / 100 per model
  ens_vs_base.png         ensembles vs their base models: PR-AUC (rows) and APFDc on all failed runs (ordering)
  perf_apfdc_forest.png   APFDc with 95% CIs for every baseline and model, All vs FirstFail-old
  error_firstfail.png     error analysis: time spent before a first-time failure, and on what (RESULTS.md §4.1)
  tradeoff_floor.png      Phase D: APFDc on All vs FirstFail-old as the probability floor grows (if computed)

Usage: python -m stp.reports.extra_figures
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from stp import paths  # noqa: E402
from stp.reports.colors import color, label  # noqa: E402
from stp.reports.results_md import _r, get  # noqa: E402

FIG = paths.ROOT / "reports" / "figures"
MODELS = ["lr", "rf", "lgbm", "vote", "stack"]


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=130)
    plt.close(fig)
    print(f"  wrote reports/figures/{name}")


def cls_models():
    c = _r("models_classification")
    if not c:
        return
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    x = np.arange(len(MODELS))
    for ax, key, title in ((axes[0], "pr_auc", "PR-AUC (primary)"), (axes[1], "roc_auc", "ROC-AUC")):
        v = [get(c, "models", m, key) for m in MODELS]
        ax.bar(x, v, color=[color(m) for m in MODELS])
        for i, y in enumerate(v):
            ax.text(i, y, f"{y:.3f}", ha="center", va="bottom", fontsize=8)
        ax.set_xticks(x, [label(m) for m in MODELS], rotation=25, ha="right", fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].axhline(c["base_rate"], color="#444", ls=":", lw=1)
    axes[0].text(len(MODELS) - 0.5, c["base_rate"], f"random = base rate {c['base_rate']:.2%}", fontsize=7,
                 ha="right", va="bottom")
    ax = axes[2]
    ks = [10, 50, 100]
    for m in MODELS:
        at = get(c, "models", m, "at_k", "macro")
        ax.plot(ks, [at[f"r@{k}"] for k in ks], marker="o", color=color(m), label=label(m))
    ax.set_xticks(ks)
    ax.set_xlabel("top k test classes of a failed run")
    ax.set_ylabel("recall: share of the run's failures in the top k")
    ax.set_title("Recall at the top k (macro over projects)", fontsize=10)
    ax.legend(fontsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"Classification on held-out test rows (testC, {c['n_rows']:,} rows). Always predicting 'pass' "
                 f"is {c['always_pass_accuracy']:.2%} accurate and useless, so accuracy is not reported.", fontsize=9)
    _save(fig, "cls_models.png")


def ens_vs_base():
    c, M = _r("models_classification"), _r("models")
    if not c or not M:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    x = np.arange(len(MODELS))
    v = [get(c, "models", m, "pr_auc") for m in MODELS]
    axes[0].bar(x, v, color=[color(m) for m in MODELS])
    axes[0].set_ylim(min(v) * 0.9, max(v) * 1.05)
    axes[0].set_title("PR-AUC on test rows (y-axis zoomed)", fontsize=10)
    cells = [get(M, "cells", "All", "macro10", m, "apfdc") for m in MODELS]
    mean = [x_["mean"] for x_ in cells]
    err = [[x_["mean"] - x_["lo"] for x_ in cells], [x_["hi"] - x_["mean"] for x_ in cells]]
    axes[1].bar(x, mean, yerr=err, capsize=3, color=[color(m) for m in MODELS])
    axes[1].set_ylim(min(x_["lo"] for x_ in cells) - 0.02, max(x_["hi"] for x_ in cells) + 0.01)
    axes[1].set_title("APFDc, all failed test runs, 95% CI (y-axis zoomed)", fontsize=10)
    for ax, vals in ((axes[0], v), (axes[1], mean)):
        for i, y in enumerate(vals):
            ax.text(i, y, f"{y:.3f}", ha="center", va="bottom", fontsize=8)
        ax.set_xticks(x, [label(m) for m in MODELS], rotation=25, ha="right", fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Bagging (random forest), boosting (LightGBM), and the two ensembles built from all three", fontsize=9)
    _save(fig, "ens_vs_base.png")


def perf_forest():
    M = _r("models")
    if not M:
        return
    subs = ["All", "FirstFail-old"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    methods = ["Random", "FailCount", "LastFail", "cbt_BM25", "QTF", "ChangedOrNewFirst", "cbt_LastFail", "lr", "rf",
               "vote", "stack", "lgbm"]
    for ax, s in zip(axes, subs):
        best = get(M, "best_simple_by_val", s)
        for i, m in enumerate(methods):
            a = get(M, "cells", s, "macro10", m, "apfdc")
            if not a:
                continue
            ax.errorbar(a["mean"], i, xerr=[[a["mean"] - a["lo"]], [a["hi"] - a["mean"]]], fmt="o", color=color(m),
                        capsize=3, ms=6 if m in (best, "lgbm") else 4)
            ax.text(a["hi"] + 0.005, i, f"{a['mean']:.3f}", va="center", fontsize=7)
        ax.set_title(f"{s} (best simple rule on validation: {best})", fontsize=10)
        ax.set_xlabel("APFDc, test split, macro over 10 projects (1 = failures first)")
        ax.grid(axis="x", alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_yticks(range(len(methods)), [label(m) for m in methods], fontsize=8)
    fig.suptitle("Every baseline and model with 95% PR-clustered bootstrap CIs", fontsize=10)
    _save(fig, "perf_apfdc_forest.png")


def error_firstfail():
    e = get(_r("error_analysis"), "firstfail_old", "macro")
    if not e:
        return
    fig, ax = plt.subplots(figsize=(8, 2.8))
    for i, (m, name) in enumerate((("model", "lgbm"), ("QTF", "QTF"))):
        tot = e[f"{m}|time_share_before_target"]
        prev = tot * e[f"{m}|prev_failed_share_of_time_before"]
        ax.barh(i, prev, color=color(name))
        ax.barh(i, tot - prev, left=prev, color=color(name), alpha=0.35)
        ax.text(tot, i, f"  {tot:.1%} of suite time", va="center", fontsize=8)
    ax.set_yticks([0, 1], ["LightGBM", "QTF"])
    ax.invert_yaxis()
    ax.set_xlabel("share of suite time spent before the first-time failure is reached "
                  "(dark = on tests that had failed before)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Why the model loses on first-time failures (RESULTS.md §4.1)", fontsize=10)
    _save(fig, "error_firstfail.png")


def tradeoff():
    F = _r("floor_tradeoff")
    if not F or "val_curve" not in F:
        return
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    for split, cv, style in (("validation", F["val_curve"], "-o"), ("test", get(F, "test", "curve"), "--s")):
        if not cv:
            continue
        pts = [(k, v) for k, v in cv.items() if k.startswith("f=")]
        ax.plot([v["All"] for _, v in pts], [v["FirstFail-old"] for _, v in pts], style, color=color("lgbm"),
                alpha=1 if split == "validation" else 0.5, label=f"LightGBM with floor f ({split})")
        for k, v in pts:
            if split == "validation":
                ax.annotate(k, (v["All"], v["FirstFail-old"]), fontsize=6, xytext=(3, 3), textcoords="offset points")
        q = cv.get("QTF")
        if q:
            ax.plot(q["All"], q["FirstFail-old"], "D", color=color("QTF"), alpha=1 if split == "validation" else 0.5,
                    label=f"QTF ({split})")
    ax.set_xlabel("APFDc, all failed runs")
    ax.set_ylabel("APFDc, first-time failures of existing tests")
    ax.set_title(f"Trade-off from a probability floor (f* = {F.get('f_star'):g}, chosen on validation)", fontsize=9)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    _save(fig, "tradeoff_floor.png")


def main():
    for f in (cls_models, ens_vs_base, perf_forest, error_firstfail, tradeoff):
        f()


if __name__ == "__main__":
    main()
