"""Phase 3.8 summary: models vs baselines on the test split -> reports/results/models.json.

Inputs: per-run domain results of the models (data/processed/eval/models_runs/<tag>_<project>.parquet) and of the
baselines (data/processed/eval/baselines_runs/<project>.parquet), both from stp.evaluation.harness on the same failed
test runs and subsets.
Outputs per subset and group (macro10 / kafka / tvm / small8): APFDc macro with PR-clustered CI, median minutes to
first failure, first-in-10% share, and paired differences of each model to the best simple baseline (chosen on val
in baselines.json). Also: ablations (A→D) on FirstFail-old, regime-shift sensitivity (macro without the Kafka and
TVM test windows), and leave-one-project-out macro differences (does one project drive the result?).
"""
from __future__ import annotations

import glob

import numpy as np
import pandas as pd

from stp import paths
from stp.baselines.run_baselines import GROUPS, wallclock_factor
from stp.evaluation.bootstrap import macro_ci, median_ci, paired_diff_ci
from stp.evaluation.harness import SUBSETS
from stp.results import load_result, save_result

EV = paths.PROCESSED / "eval"


def load_runs(tag: str) -> pd.DataFrame:
    fs = sorted(glob.glob(str(EV / "models_runs" / f"{tag}_*.parquet")))
    return pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True) if fs else pd.DataFrame()


def baselines_test() -> pd.DataFrame:
    fs = sorted(glob.glob(str(EV / "baselines_runs" / "*.parquet")))
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    return d[d.split == "test"]


def cells(df: pd.DataFrame, methods: list[str]) -> dict:
    wc = wallclock_factor()
    df = df.assign(ttff_min=df.ttff_s / 60.0)
    out: dict = {}
    for sub in SUBSETS:
        d = df[df.subset == sub]
        for g, projs in GROUPS.items():
            for m in methods:
                x = d[d.method == m]
                if projs is not None:
                    x = x[x.project.isin(projs)]
                if x.empty:
                    continue
                out.setdefault(sub, {}).setdefault(g, {})[m] = {
                    "apfdc": macro_ci(x, "apfdc", seed=1),
                    "ttff_min_median": median_ci(x, "ttff_min", n_boot=300, seed=2),
                    "ttff_wall_min_median_approx": float((x.ttff_min * x.project.map(wc)).median()),
                    "first10_share": float(x.first10.mean())}
    return out


def paired(df: pd.DataFrame, models: list[str], ref_by_subset: dict[str, str]) -> dict:
    out: dict = {}
    for sub in SUBSETS:
        ref = ref_by_subset.get(sub)
        if ref is None:
            continue
        d = df[df.subset == sub]
        for g, projs in GROUPS.items():
            for m in models:
                out.setdefault(sub, {}).setdefault(g, {})[m] = paired_diff_ci(d, m, ref, projects=projs, seed=3)
    return out


def leave_one_out(df: pd.DataFrame, model: str, ref: str, sub: str) -> dict:
    d = df[df.subset == sub]
    out = {}
    for p in sorted(d.project.unique()):
        r = paired_diff_ci(d[d.project != p], model, ref, n_boot=500, seed=4)
        out[p] = {"mean": r["mean"], "lo": r["lo"], "hi": r["hi"]}
    return out


def regime(df: pd.DataFrame, model: str, refs: dict[str, str]) -> dict:
    """Macro difference to each subset's best simple baseline, with and without the Kafka/TVM test windows."""
    out = {}
    for sub in ("All", "FirstFail-asof", "FirstFail-old"):
        ref = refs[sub]
        d = df[df.subset == sub]
        out[sub] = {"with": paired_diff_ci(d, model, ref, n_boot=500, seed=5),
                    "without_kafka_tvm": paired_diff_ci(d[~d.project.isin(["kafka", "tvm"])], model, ref,
                                                        n_boot=500, seed=5)}
    return out


def main(main_model: str = "lgbm") -> dict:
    b = baselines_test()
    bl = load_result("baselines")
    best = bl["best_simple_by_val"]
    m = load_runs("main")
    ab = load_runs("abl")
    df = pd.concat([b, m, ab], ignore_index=True)
    models = sorted(set(m.method)) if not m.empty else []
    abl = sorted(set(ab.method)) if not ab.empty else []
    methods = sorted(set(b.method)) + models + abl
    res = {"cells": cells(df, methods), "best_simple_by_val": best, "models": models, "ablations": abl,
           "vs_best_simple": paired(df, models + abl, best)}
    if main_model in models:
        res["leave_one_project_out"] = {s: leave_one_out(df, main_model, best[s], s)
                                        for s in ("All", "FirstFail-asof", "FirstFail-old") if s in best}
        res["regime_shift"] = regime(df, main_model, best)
        res["vs_cbt_lastfail_All"] = paired_diff_ci(df[df.subset == "All"], main_model, "cbt_LastFail", seed=6)
        fo = res["vs_best_simple"].get("FirstFail-old", {}).get("macro10", {})
        res["ablation_question"] = {
            "question": "does C (change) or D (co-failure) beat the best baseline on FirstFail-old with a CI "
                        "excluding zero?",
            **{k: fo.get(k) for k in abl}}
        hl = {}
        for s in ("All", "FirstFail-asof", "FirstFail-old", "New/Edited"):
            c = res["cells"].get(s, {}).get("macro10", {})
            if main_model in c and best.get(s) in c:
                hl[f"APFDc {s} ({main_model} vs {best[s]})"] = (
                    f"{c[main_model]['apfdc']['mean']:.3f} vs {c[best[s]]['apfdc']['mean']:.3f}")
        res["headline"] = hl
    save_result("models", res)
    return res


if __name__ == "__main__":
    main()
    _ = np
