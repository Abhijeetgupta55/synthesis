"""The ML Lab: train a model live on the bundled real sample (demo_bundle/lab) and score it three ways.

Scores for every fit:
  train       the rows the model was fitted on
  validation  the held-out part of the training sample, by the chosen split:
                random  random 80% / 20% of rows (rows of one CI run can land on both sides)
                time    earliest 80% of CI runs / latest 20% (what happens in real use)
  later       later builds (valA): CI runs after the whole training period, at the real failure rate
Metrics: PR-AUC (with the base rate it should be compared with) or accuracy at threshold 0.5 (with the accuracy of
always answering 'pass'). Nothing is precomputed; every number comes from a fit made when this function runs.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
LAB = ROOT / "demo_bundle" / "lab"
LOG1P = ("hs_n_fail", "hs_days_since_last_fail", "hs_fails_last_7d", "hs_fails_last_30d", "hs_n_transitions",
         "hs_n_runs_seen", "dur_last_asof", "dur_ema_asof", "bm25_test_vs_diff", "chg_n_files", "chg_additions",
         "chg_deletions", "chg_n_top_modules", "cof_sum", "cof_count_max", "path_prefix_overlap", "name_token_overlap")


def meta() -> dict:
    return json.loads((LAB / "lab_meta.json").read_text(encoding="utf-8"))


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.read_parquet(LAB / "train_sample.parquet"), pd.read_parquet(LAB / "later_builds.parquet")


def split(tr: pd.DataFrame, kind: str, seed: int = 0) -> np.ndarray:
    """Boolean mask of validation rows inside the training sample."""
    if kind == "random":
        return np.random.default_rng(seed).random(len(tr)) < 0.2
    runs = tr[["project", "run_idx", "start_ts"]].drop_duplicates().sort_values("start_ts")
    late = runs.iloc[int(len(runs) * 0.8):]
    key = pd.MultiIndex.from_frame(tr[["project", "run_idx"]])
    return key.isin(pd.MultiIndex.from_frame(late[["project", "run_idx"]]))


def _X(df: pd.DataFrame, cols: list[str], linear: bool) -> np.ndarray:
    X = df[cols].to_numpy(np.float64)
    X = np.nan_to_num(X, nan=0.0)
    if linear:
        for j, c in enumerate(cols):
            if c in LOG1P:
                X[:, j] = np.log1p(np.maximum(X[:, j], 0))
    return X


def score(y: np.ndarray, p: np.ndarray, metric: str) -> float:
    from sklearn.metrics import average_precision_score
    if metric == "accuracy":
        return float(((p >= 0.5) == y).mean())
    return float(average_precision_score(y, p)) if y.any() else float("nan")


def train(model: str = "lgbm", groups: tuple[str, ...] = ("history", "cost", "change", "cofail"),
          split_kind: str = "time", metric: str = "pr_auc", C: float = 1.0, penalty: str = "l2",
          max_depth: int = 8, min_leaf: int = 20, num_leaves: int = 31, rounds: int = 300,
          early_stopping: bool = True, n_trees: int = 60, data=None, seed: int = 0) -> dict:
    tr, later = data if data is not None else load()
    m = meta()
    cols = [c for g in groups for c in m["groups"].get(g, [])]
    if not cols:
        raise ValueError("choose at least one feature group")
    val = split(tr, split_kind, seed)
    a, v = tr[~val], tr[val]
    ya, yv, yl = a.y_fail.to_numpy(bool), v.y_fail.to_numpy(bool), later.y_fail.to_numpy(bool)
    lin = model == "lr"
    Xa, Xv, Xl = _X(a, cols, lin), _X(v, cols, lin), _X(later, cols, lin)
    t0 = time.time()
    info: dict = {}
    if model == "lr":
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        est = make_pipeline(StandardScaler(), LogisticRegression(
            C=C, penalty=penalty, solver="liblinear" if penalty == "l1" else "lbfgs", max_iter=1000))
        est.fit(Xa, ya)
        pred = lambda X: est.predict_proba(X)[:, 1]  # noqa: E731
        coef = est[-1].coef_[0]
        info["weights"] = sorted(zip(cols, coef.tolist()), key=lambda cv: -abs(cv[1]))
        info["n_zero"] = int((np.abs(coef) < 1e-9).sum())
        info["weights_kind"] = "coefficient (standardised features)"
    elif model == "rf":
        from sklearn.ensemble import RandomForestClassifier
        est = RandomForestClassifier(n_estimators=n_trees, max_depth=max_depth or None, min_samples_leaf=min_leaf,
                                     max_features="sqrt", n_jobs=4, random_state=seed)
        est.fit(Xa, ya)
        pred = lambda X: est.predict_proba(X)[:, 1]  # noqa: E731
        info["weights"] = sorted(zip(cols, est.feature_importances_.tolist()), key=lambda cv: -cv[1])
        info["weights_kind"] = "importance (mean decrease in impurity)"
    else:
        import lightgbm as lgb
        params = dict(objective="binary", learning_rate=0.1, num_leaves=num_leaves, max_depth=max_depth or -1,
                      min_child_samples=min_leaf, verbose=-1, seed=seed, num_threads=4,
                      lambda_l2=1.0 if early_stopping else 0.0, feature_fraction=0.8 if early_stopping else 1.0)
        dtr = lgb.Dataset(Xa, ya.astype(np.float32), feature_name=cols, free_raw_data=False)
        cb, valid = [], []
        if early_stopping:
            valid = [lgb.Dataset(Xv, yv.astype(np.float32), reference=dtr)]
            cb = [lgb.early_stopping(30, verbose=False)]
        b = lgb.train(params, dtr, rounds, valid_sets=valid, callbacks=cb)
        it = b.best_iteration or rounds
        pred = lambda X: b.predict(X, num_iteration=it)  # noqa: E731
        info["rounds_used"] = int(it)
        info["weights"] = sorted(zip(cols, b.feature_importance("gain", iteration=it).tolist()), key=lambda cv: -cv[1])
        info["weights_kind"] = "importance (total gain)"
    fit_s = time.time() - t0
    pa, pv, pl = pred(Xa), pred(Xv), pred(Xl)
    ftf = later.y_ftf_asof.to_numpy(bool)
    out = {"model": model, "groups": list(groups), "split": split_kind, "metric": metric, "n_features": len(cols),
           "rows": {"train": int(len(a)), "validation": int(len(v)), "later": int(len(later))},
           "score": {"train": score(ya, pa, metric), "validation": score(yv, pv, metric),
                     "later": score(yl, pl, metric)},
           "baseline": ({"train": float(1 - ya.mean()), "validation": float(1 - yv.mean()),
                         "later": float(1 - yl.mean())} if metric == "accuracy" else
                        {"train": float(ya.mean()), "validation": float(yv.mean()), "later": float(yl.mean())}),
           "later_first_time_pr_auc": score(ftf, pl, "pr_auc") if ftf.any() else None,
           "later_first_time_base_rate": float(ftf.mean()),
           "seconds": round(time.time() - t0, 1), "fit_seconds": round(fit_s, 1), **info}
    return out


EXPERIMENTS = {
    "The accuracy trap": {
        "question": "Is 99% accuracy good here?",
        "runs": {"logistic regression, accuracy": dict(model="lr", metric="accuracy", C=1.0)}},
    "Overfitting without regularization": {
        "question": "What happens to a flexible model with no brakes?",
        "runs": {"LightGBM, no regularization": dict(model="lgbm", num_leaves=127, min_leaf=1, max_depth=0,
                                                       rounds=200, early_stopping=False),
                 "LightGBM, regularized": dict(model="lgbm", num_leaves=31, min_leaf=50, max_depth=8, rounds=300,
                                               early_stopping=True)}},
    "A random split inflates the score": {
        "question": "Does it matter how we hold out validation data?",
        "runs": {"random split": dict(model="lgbm", split_kind="random", num_leaves=127, min_leaf=1, max_depth=0,
                                      rounds=200, early_stopping=False),
                 "split by time": dict(model="lgbm", split_kind="time", num_leaves=127, min_leaf=1, max_depth=0,
                                       rounds=200, early_stopping=False)}},
    "History alone vs history + change": {
        "question": "Do features about the code change add anything to past failures?",
        "runs": {"history only": dict(model="lgbm", groups=("history",)),
                 "history + cost + change": dict(model="lgbm", groups=("history", "cost", "change"))}},
}


def takeaway(name: str, res: dict[str, dict]) -> str:
    """One-line conclusion computed from the results just obtained (not written in advance)."""
    r = list(res.values())
    if name == "The accuracy trap":
        x = r[0]
        worse = x['score']['later'] < x['baseline']['later']
        return (f"Accuracy on later builds is {x['score']['later']:.2%}; always answering 'pass' scores "
                f"{x['baseline']['later']:.2%}" + (", so the trained model is even *worse* than doing nothing"
                                                    if worse else "") +
                f". When only {1 - x['baseline']['later']:.2%} of tests fail, accuracy cannot tell a useful model "
                "from a useless one: use PR-AUC.")
    if name == "Overfitting without regularization":
        u, g = r
        return (f"Without brakes the model scores {u['score']['train']:.2f} on its own training rows but "
                f"{u['score']['later']:.3f} on later builds; regularized: {g['score']['train']:.2f} vs "
                f"{g['score']['later']:.3f}. " + ("Regularization wins where it matters." if g['score']['later'] >
                                                    u['score']['later'] else "Here regularization did not help."))
    if name == "A random split inflates the score":
        a, b = r
        return (f"The random split reports {a['score']['validation']:.3f}, the time split {b['score']['validation']:.3f}, "
                f"and later builds give {a['score']['later']:.3f}: " +
                ("a random split lets rows of the same CI run sit on both sides and promises more than the model "
                 "delivers on the future." if a['score']['validation'] > b['score']['validation'] else
                 "this time the two splits agree."))
    if name == "History alone vs history + change":
        h, c = r
        n_ftf = int(round(c['later_first_time_base_rate'] * c['rows']['later']))
        better = c['score']['later'] > h['score']['later']
        return (f"On later builds: history only {h['score']['later']:.3f}, with cost and change features "
                f"{c['score']['later']:.3f}: " + ("adding them helps on this sample." if better else
                "on this small sample they do *not* help overall; history carries most of the signal.") +
                f" On the {n_ftf} first-time failures in the later builds (no history to use): "
                f"{h['later_first_time_pr_auc']:.4f} vs {c['later_first_time_pr_auc']:.4f} "
                f"(random = {c['later_first_time_base_rate']:.4f}); too few to conclude from this sample.")
    return ""
