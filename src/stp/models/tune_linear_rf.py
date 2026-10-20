"""Phase 3.5-3.6 for the two sklearn models: regularisation evidence + grid/random search, selected on valA PR-AUC.

Logistic regression (standardised, log1p features; sampling weights):
  penalties L2, L1, Elastic-Net (l1_ratio 0.5) x C in a log grid. Shows validation PR-AUC vs C per penalty and
  which coefficients L1 sets to exactly zero as C shrinks (embedded feature selection).
Random forest (bagging):
  random search over max_depth, min_samples_leaf, max_features; a depth sweep with the train/valA PR-AUC gap
  shows how depth limits overfitting.
Both are fitted on whole-run subsamples of train (LR 500k rows, RF 400k rows): saga and deep forests on the full sample
would not fit the
RAM/time budget; the subsample is documented in MODELING.md. The chosen configuration is then refitted on a larger
subsample (`refit_rows`).

Outputs: data/processed/models/{lr,rf}.pkl, reports/results/tune_lr.json, tune_rf.json, reports/figures/reg_lr_*.png,
reg_rf_depth.png
"""
from __future__ import annotations

import time

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from stp.eda.common import PALETTE, savefig, style
from stp.models.common import train_weight, load, n_rows, save_model, subsample_rows
from stp.results import save_result

C_GRID = [1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0]


def lr_model(penalty: str, C: float):
    kw = {"l2": dict(penalty="l2", solver="lbfgs"), "l1": dict(penalty="l1", solver="saga"),
          "elasticnet": dict(penalty="elasticnet", solver="saga", l1_ratio=0.5)}[penalty]
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=300, tol=1e-3, **kw))


def tune_lr(cols: list[str], sub_rows: int = 500_000, refit_rows: int = 1_500_000, seed: int = 0) -> dict:
    import matplotlib.pyplot as plt

    rows = subsample_rows("train", sub_rows, seed)
    X, m = load("train", cols, ["y_fail", "weight"], linear=True, rows=rows)
    Xv, mv = load("valA", cols, ["y_fail"], linear=True)
    y, w, yv = m.y_fail.to_numpy(bool), m.weight.to_numpy(), mv.y_fail.to_numpy(bool)
    w = train_weight(w)
    res, coefs = [], {}
    for pen in ("l2", "l1", "elasticnet"):
        for C in C_GRID:
            t0 = time.time()
            mdl = lr_model(pen, C).fit(X, y, logisticregression__sample_weight=w)
            pv = mdl.predict_proba(Xv)[:, 1]
            pt = mdl.predict_proba(X)[:, 1]
            coef = mdl[-1].coef_[0]
            r = {"penalty": pen, "C": C, "val_pr_auc": float(average_precision_score(yv, pv)),
                 "train_pr_auc_weighted": float(average_precision_score(y, pt)),
                 "n_zero_coef": int((np.abs(coef) < 1e-10).sum()), "seconds": time.time() - t0}
            coefs[f"{pen}|{C}"] = dict(zip(cols, coef.tolist()))
            res.append(r)
            print(f"  [lr] {pen:10s} C={C:<7g} valA PR-AUC {r['val_pr_auc']:.4f}  zero coefs {r['n_zero_coef']}  "
                  f"{r['seconds']:.0f}s", flush=True)
    best = max(res, key=lambda r: r["val_pr_auc"])
    style()
    fig, ax = plt.subplots(figsize=(6, 3.6))
    for i, pen in enumerate(("l2", "l1", "elasticnet")):
        rr = [r for r in res if r["penalty"] == pen]
        ax.plot([r["C"] for r in rr], [r["val_pr_auc"] for r in rr], marker="o", color=PALETTE[i], label=pen.upper())
    ax.set_xscale("log")
    ax.set_xlabel("C (inverse regularisation strength)")
    ax.set_ylabel("valA PR-AUC")
    ax.set_title("Logistic regression: validation PR-AUC vs regularisation")
    ax.legend()
    savefig(fig, "reg_lr_C")
    # L1 path: which coefficients reach exactly zero
    fig, ax = plt.subplots(figsize=(7, 4.2))
    l1 = np.array([[coefs[f"l1|{C}"][c] for c in cols] for C in C_GRID])
    order = np.argsort(-np.abs(l1[-1]))
    for k, j in enumerate(order[:12]):
        ax.plot(C_GRID, l1[:, j], marker=".", color=PALETTE[k % len(PALETTE)], label=cols[j], lw=1.5)
    ax.axhline(0, color="#999", lw=0.8)
    ax.set_xscale("log")
    ax.set_xlabel("C")
    ax.set_ylabel("standardised coefficient")
    ax.set_title("L1 path: coefficients driven to zero as C shrinks (top 12 at largest C)")
    ax.legend(fontsize=6, ncols=2)
    savefig(fig, "reg_lr_l1_path")
    del X
    rows2 = subsample_rows("train", refit_rows, seed + 1)
    X2, m2 = load("train", cols, ["y_fail", "weight"], linear=True, rows=rows2)
    w2 = m2.weight.to_numpy()
    final = lr_model(best["penalty"], best["C"]).fit(X2, m2.y_fail.to_numpy(bool),
                                                      logisticregression__sample_weight=train_weight(w2))
    save_model({"model": final, "cols": cols, "linear": True}, "lr")
    zero_by_C = {str(C): [c for c in cols if abs(coefs[f"l1|{C}"][c]) < 1e-10] for C in C_GRID}
    out = {"grid": res, "best": best, "coefficients": coefs, "l1_zeroed_by_C": zero_by_C,
           "final_coefficients": dict(zip(cols, final[-1].coef_[0].tolist())),
           "train_rows_grid": int(len(rows)), "train_rows_refit": int(len(rows2)), "n_train_total": n_rows("train")}
    save_result("tune_lr", out)
    return out


def rf_model(max_depth, min_samples_leaf, max_features, n_estimators=150, seed=0):
    return RandomForestClassifier(n_estimators=n_estimators, max_depth=max_depth, min_samples_leaf=min_samples_leaf,
                                  max_features=max_features, n_jobs=4, random_state=seed, max_samples=0.5)


def tune_rf(cols: list[str], sub_rows: int = 400_000, n_random: int = 10, seed: int = 0) -> dict:
    import matplotlib.pyplot as plt

    rows = subsample_rows("train", sub_rows, seed + 7)
    X, m = load("train", cols, ["y_fail", "weight"], rows=rows)
    Xv, mv = load("valA", cols, ["y_fail"])
    y, w, yv = m.y_fail.to_numpy(bool), m.weight.to_numpy(), mv.y_fail.to_numpy(bool)
    w = train_weight(w)
    rng = np.random.default_rng(seed)
    # depth is capped and leaves hold >= 5 samples: fully grown trees on 10^5-10^6 rows would need GBs of RAM
    space = {"max_depth": [6, 10, 14, 18], "min_samples_leaf": [5, 20, 100, 400],
             "max_features": ["sqrt", 0.3, 0.6]}
    trials = []

    def fit_eval(cfg, n_est=100):
        t0 = time.time()
        mdl = rf_model(cfg["max_depth"], cfg["min_samples_leaf"], cfg["max_features"], n_est, seed).fit(X, y, sample_weight=w)
        pv = mdl.predict_proba(Xv)[:, 1]
        pt = mdl.predict_proba(X)[:, 1]
        r = {**{k: (v if v is not None else "none") for k, v in cfg.items()},
             "val_pr_auc": float(average_precision_score(yv, pv)),
             "train_pr_auc_weighted": float(average_precision_score(y, pt)),
             "seconds": time.time() - t0}
        print(f"  [rf] {cfg} valA {r['val_pr_auc']:.4f} train {r['train_pr_auc_weighted']:.4f} {r['seconds']:.0f}s",
              flush=True)
        return mdl, r

    for _ in range(n_random):
        cfg = {k: v[int(rng.integers(len(v)))] for k, v in space.items()}
        trials.append(fit_eval(cfg)[1])
    depth = []
    for dpt in [4, 6, 8, 10, 14, 18, 24]:
        depth.append(fit_eval({"max_depth": dpt, "min_samples_leaf": 5, "max_features": "sqrt"}, 40)[1])
    best = max(trials, key=lambda r: r["val_pr_auc"])
    style()
    fig, ax = plt.subplots(figsize=(6, 3.6))
    xs = [str(r["max_depth"]) for r in depth]
    ax.plot(xs, [r["train_pr_auc_weighted"] for r in depth], marker="o", color=PALETTE[0], label="train (weighted)")
    ax.plot(xs, [r["val_pr_auc"] for r in depth], marker="o", color=PALETTE[1], label="valA")
    ax.set_xlabel("max_depth (min_samples_leaf=5, max_features=sqrt, 40 trees)")
    ax.set_ylabel("PR-AUC")
    ax.set_title("Random forest: train/validation gap grows with depth")
    ax.legend()
    savefig(fig, "reg_rf_depth")
    cfg = {k: (None if best[k] == "none" else best[k]) for k in ("max_depth", "min_samples_leaf", "max_features")}
    final, _ = fit_eval(cfg, 200)
    save_model({"model": final, "cols": cols, "linear": False}, "rf")
    out = {"trials": trials, "depth_sweep": depth, "best": best, "space": {k: [str(x) for x in v] for k, v in space.items()},
           "train_rows": int(len(rows)), "n_estimators_final": 200,
           "feature_importance_mdi": dict(zip(cols, final.feature_importances_.tolist()))}
    save_result("tune_rf", out)
    return out
