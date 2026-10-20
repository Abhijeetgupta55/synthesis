"""Phase 3.8: performance analysis of models vs baselines on the held-out test split.

Ordering policy for every model: priority = calibrated P(fail) / expected duration (dur_ema_asof), descending
(VIVA_NOTES: adjacent-swap argument). 'lgbm_p' orders by probability alone, for comparison.

Classification metrics (testC = all rows of a random subset of test runs, unsampled):
  PR-AUC (primary), ROC-AUC, Brier before/after calibration, reliability curves, Precision@k / Recall@k per failed
  run (k = 10, 50, 100), F1 and confusion matrix at the threshold that maximises F1 on valB.
Domain metrics: stp.evaluation.harness on *all* failed test runs, same subsets and bootstrap as the baselines.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_curve

from stp import paths
from stp.baselines import heuristics as H
from stp.evaluation.harness import eval_runs, evaluate_methods
from stp.features.store import store_ready
from stp.models.calibrate import BASE_MODELS, logit
from stp.models.common import cls_metrics, load, load_model, per_project_pr_auc

EVAL_OUT = paths.PROCESSED / "eval" / "models_runs"


def model_methods(extra: dict | None = None) -> tuple[dict, list[str]]:
    """Harness methods for every calibrated model + ensembles; returns (methods, store columns needed)."""
    cal = {m: load_model(f"cal_{m}") for m in BASE_MODELS}
    stack, vote = load_model("stack"), load_model("vote")
    cols = sorted(set(sum((c.entry["cols"] for c in cal.values()), [])) | set(H.COLUMNS))
    eps = 1e-3

    def mk(fn):
        def method(d, rng):
            p = fn(d, rng)
            return -(p / (d["dur_ema_asof"].astype(np.float64) + eps))
        return method

    def run_feats(d, rng):
        n = len(d["test_id"])
        pr = H.cbt_lastfail(d, rng)
        o = np.lexsort((rng.random(n), pr))
        r = np.empty(n)
        r[o] = np.arange(n) / max(1, n - 1)
        flag = (d["test_file_in_diff"].astype(bool) | d["is_new_test"].astype(bool)).astype(float)
        return r, flag

    methods = {f"{m}": mk(lambda d, rng, m=m: cal[m].predict(d)) for m in BASE_MODELS}
    methods["vote"] = mk(lambda d, rng: vote.predict(d))
    methods["stack"] = mk(lambda d, rng: stack.predict(d, *run_feats(d, rng)))
    methods["lgbm_p"] = lambda d, rng: -cal["lgbm"].predict(d)
    for k, fn in (extra or {}).items():
        methods[k] = fn
    return methods, cols


def domain_eval(methods: dict, cols: list[str], tag: str, splits=("test",), workers_note: str = "") -> pd.DataFrame:
    EVAL_OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for p in paths.PROJECTS:
        if not store_ready(p):
            continue
        f = EVAL_OUT / f"{tag}_{p}.parquet"
        if f.exists():
            frames.append(pd.read_parquet(f))
            continue
        t0 = time.time()
        runs = eval_runs(p, splits)
        df = evaluate_methods(p, methods, runs, cols, {m: 1 for m in methods}, base_seed=11)
        df.to_parquet(f, index=False)
        frames.append(df)
        print(f"  [domain:{tag}] {p}: {len(runs):,} runs in {time.time() - t0:.0f}s", flush=True)
    return pd.concat(frames, ignore_index=True)


def classification(cols_needed: list[str]) -> dict:
    """Classification metrics on testC for each base model, the ensembles, and the always-pass classifier."""
    cal = {m: load_model(f"cal_{m}") for m in BASE_MODELS}
    stack, vote = load_model("stack"), load_model("vote")
    _, tc = load("testC", [cols_needed[0]], sorted(set(cols_needed) | set(H.COLUMNS) | {"y_fail", "y_ftf_asof",
                                                                                          "project", "run_idx"}))
    _, vb = load("valB", [cols_needed[0]], sorted(set(cols_needed) | set(H.COLUMNS) | {"y_fail", "project", "run_idx"}))
    from stp.models.calibrate import run_level
    y = tc.y_fail.to_numpy(bool)
    proj = tc.project.to_numpy()
    rank, flag = run_level(tc)
    rank_b, flag_b = run_level(vb)
    preds = {}
    raw = {}
    for m in BASE_MODELS:
        raw[m] = cal[m].raw(tc)
        preds[m] = cal[m].predict(tc)
        preds[f"{m}_platt"] = cal[m].predict(tc, "platt")
    preds["vote"] = vote.predict(tc)
    preds["stack"] = stack.predict(tc, rank, flag)
    pb = {m: cal[m].predict(vb) for m in BASE_MODELS}
    pb["vote"] = vote.predict(vb)
    pb["stack"] = stack.predict(vb, rank_b, flag_b)
    out = {"n_rows": int(len(y)), "n_pos": int(y.sum()), "base_rate": float(y.mean()),
           "always_pass_accuracy": float(1 - y.mean()), "models": {}}
    for m, p in preds.items():
        r = cls_metrics(y, p)
        r["pr_auc_per_project"] = per_project_pr_auc(y, p, proj)
        r["pr_auc_macro"] = float(np.mean(list(r["pr_auc_per_project"].values())))
        base = m.split("_")[0]
        if m in BASE_MODELS:
            r["brier_raw"] = cls_metrics(y, np.clip(raw[m], 0, 1))["brier"]
        if m in pb:
            yb = vb.y_fail.to_numpy(bool)
            pr, rc, th = precision_recall_curve(yb, pb[m])
            f1 = 2 * pr * rc / np.maximum(pr + rc, 1e-12)
            t = float(th[int(np.argmax(f1[:-1]))]) if len(th) else 0.5
            yhat = p >= t
            r["threshold_from_valB"] = t
            r["f1_test"] = float(f1_score(y, yhat))
            r["confusion_test"] = confusion_matrix(y, yhat).tolist()
            r["accuracy_test"] = float((yhat == y).mean())
        r["ftf_pr_auc"] = cls_metrics(tc.y_ftf_asof.to_numpy(bool), p)["pr_auc"]
        r["at_k"] = at_k(tc, p)
        out["models"][m] = r
        del base
    out["reliability"] = reliability(y, {m: raw[m] for m in BASE_MODELS}, {m: preds[m] for m in BASE_MODELS})
    out["error_corr"] = error_correlation(y, {m: preds[m] for m in BASE_MODELS + ["vote", "stack"]})
    return out


def at_k(frame: pd.DataFrame, p: np.ndarray, ks=(10, 50, 100)) -> dict:
    res = {f"p@{k}": [] for k in ks} | {f"r@{k}": [] for k in ks}
    projs = []
    for (pj, _), idx in frame.groupby(["project", "run_idx"]).indices.items():
        y = frame.y_fail.to_numpy(bool)[idx]
        if not y.any():
            continue
        o = np.argsort(-p[idx], kind="stable")
        for k in ks:
            top = y[o[:k]].sum()
            res[f"p@{k}"].append(top / k)
            res[f"r@{k}"].append(top / y.sum())
        projs.append(pj)
    df = pd.DataFrame(res)
    df["project"] = projs
    g = df.groupby("project").mean()
    return {"macro": g.mean().to_dict(), "per_project": g.to_dict(orient="index"), "n_failed_runs": int(len(df))}


def reliability(y, raw: dict, cal: dict, bins: int = 10) -> dict:
    out = {}
    for kind, preds in (("raw", raw), ("calibrated", cal)):
        for m, p in preds.items():
            q = np.quantile(p, np.linspace(0, 1, bins + 1))
            q = np.unique(q)
            idx = np.clip(np.searchsorted(q, p, side="right") - 1, 0, len(q) - 2)
            out[f"{m}|{kind}"] = {"mean_pred": [float(p[idx == b].mean()) for b in range(len(q) - 1) if (idx == b).any()],
                                  "frac_pos": [float(y[idx == b].mean()) for b in range(len(q) - 1) if (idx == b).any()]}
    return out


def error_correlation(y, preds: dict) -> dict:
    names = list(preds)
    E = np.column_stack([y.astype(float) - preds[m] for m in names])
    C = np.corrcoef(E, rowvar=False)
    L = np.column_stack([logit(preds[m]) for m in names])
    R = pd.DataFrame(L).rank().corr(method="pearson").to_numpy()
    return {"names": names, "residual_corr": C.tolist(), "rank_corr": R.tolist()}
