"""Phase 3.5-3.6 for LightGBM: Optuna TPE search, regularisation evidence, refit with early stopping.

Search: 60 TPE trials on 500k training rows and a fixed 300k-row subsample of valA (whole runs in both), objective =
valA PR-AUC (LightGBM's average_precision), each trial capped at 1,000 rounds, early-stopped (50 rounds patience) and
pruned by a median pruner on the intermediate PR-AUC. (A first attempt with the full 1.2M valA rows took ~20 min per
trial, because AP is recomputed every round.)
Space: num_leaves, max_depth, min_child_samples, lambda_l1, lambda_l2, feature_fraction, bagging_fraction /
bagging_freq, learning_rate. The best configuration is refitted on the full negative-sampled training data,
again early-stopped on valA. The top-5 configurations are also scored on valA APFDc (domain metric).
Regularisation figure: train vs valA log-loss and PR-AUC by boosting round, tuned vs an unregularised config.

Outputs: data/processed/models/lgbm.pkl, reports/results/tune_lgbm.json, reports/figures/reg_lgbm_*.png,
tune_lgbm_*.png
"""
from __future__ import annotations

import time

import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd

from stp.eda.common import PALETTE, savefig, style
from stp.evaluation.metrics import apfdc
from stp.models.common import train_weight, load, n_rows, save_model, subsample_rows
from stp.results import save_result

UNREG = {"num_leaves": 255, "max_depth": -1, "min_child_samples": 1, "min_sum_hessian_in_leaf": 1e-6,
         "lambda_l1": 0.0, "lambda_l2": 0.0, "feature_fraction": 1.0, "bagging_fraction": 1.0, "bagging_freq": 0,
         "learning_rate": 0.1}
BASE = {"objective": "binary", "metric": ["average_precision", "binary_logloss"], "verbosity": -1,
        "num_threads": 4, "seed": 0, "feature_pre_filter": False, "max_bin": 127}


def space(trial: optuna.Trial) -> dict:
    p = {"num_leaves": trial.suggest_int("num_leaves", 7, 255, log=True),
         "max_depth": trial.suggest_categorical("max_depth", [-1, 4, 6, 8, 12]),
         "min_child_samples": trial.suggest_int("min_child_samples", 10, 3000, log=True),
         "lambda_l1": trial.suggest_float("lambda_l1", 1e-8, 10.0, log=True),
         "lambda_l2": trial.suggest_float("lambda_l2", 1e-8, 10.0, log=True),
         "feature_fraction": trial.suggest_float("feature_fraction", 0.4, 1.0),
         "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
         "bagging_freq": trial.suggest_categorical("bagging_freq", [0, 1, 5]),
         "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.2, log=True)}
    return p


def run_apfdc(frame: pd.DataFrame, p: np.ndarray) -> float:
    """Mean APFDc over the failed runs of an unsampled frame, ordering by p / expected duration."""
    f = frame.assign(prio=-(p / (frame.dur_ema_asof.to_numpy() + 1e-3)))
    vals = []
    for (_, _), g in f.groupby(["project", "run_idx"]):
        if g.y_fail.any():
            o = np.argsort(g.prio.to_numpy(), kind="stable")
            vals.append((g.project.iloc[0], apfdc(g.y_duration_s.to_numpy()[o], g.y_fail.to_numpy()[o])))
    v = pd.DataFrame(vals, columns=["project", "a"])
    return float(v.groupby("project").a.mean().mean())


TUNE_TRAIN_ROWS = 500_000
TUNE_VAL_ROWS = 300_000      # whole valA runs; AP is computed every round, so the full 1.2M rows cost ~20 min/trial
MAX_ROUNDS, PATIENCE = 1000, 50


def tune(cols: list[str], n_trials: int = 60, sub_rows: int = TUNE_TRAIN_ROWS, seed: int = 0) -> dict:
    rows = subsample_rows("train", sub_rows, seed)
    X, m = load("train", cols, ["y_fail", "weight"], rows=rows)
    vrows = subsample_rows("valA", TUNE_VAL_ROWS, seed + 1)
    Xv, mv = load("valA", cols, ["y_fail", "project", "run_idx", "y_duration_s", "dur_ema_asof"], rows=vrows)
    w = m.weight.to_numpy()
    dtr = lgb.Dataset(X, m.y_fail.to_numpy(np.float32), weight=train_weight(w), free_raw_data=False,
                      params={"max_bin": 127, "feature_pre_filter": False})
    dva = lgb.Dataset(Xv, mv.y_fail.to_numpy(np.float32), reference=dtr)

    def objective(trial):
        params = {**BASE, **space(trial)}
        t0 = time.time()

        def prune_cb(env):
            if env.iteration % 25 == 0:
                ap = [r[2] for r in env.evaluation_result_list if r[1] == "average_precision"][0]
                trial.report(ap, env.iteration)
                if trial.should_prune():
                    raise optuna.TrialPruned()

        b = lgb.train(params, dtr, num_boost_round=MAX_ROUNDS, valid_sets=[dva], valid_names=["valA"],
                      callbacks=[lgb.early_stopping(PATIENCE, first_metric_only=True, verbose=False), prune_cb])
        trial.set_user_attr("best_iteration", int(b.best_iteration))
        trial.set_user_attr("seconds", time.time() - t0)
        return float(b.best_score["valA"]["average_precision"])

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed),
                                pruner=optuna.pruners.MedianPruner(n_startup_trials=8, n_warmup_steps=50))
    study.optimize(objective, n_trials=n_trials, callbacks=[lambda s, t: print(
        f"  [optuna] trial {t.number:2d} {t.state.name:8s} value {t.value if t.value is not None else float('nan'):.4f}"
        f"  best {s.best_value:.4f}", flush=True)])
    trials = [{"number": t.number, "state": t.state.name, "value": t.value, "params": t.params,
               "best_iteration": t.user_attrs.get("best_iteration")} for t in study.trials]
    done = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    top5 = sorted(done, key=lambda t: -t.value)[:5]
    top5_out = []
    for t in top5:
        params = {**BASE, **t.params}
        b = lgb.train(params, dtr, num_boost_round=t.user_attrs["best_iteration"] or 100)
        pv = b.predict(Xv)
        top5_out.append({"number": t.number, "val_pr_auc": t.value, "val_apfdc_macro": run_apfdc(mv, pv),
                         "params": t.params})
        print(f"  [optuna] top trial {t.number}: PR-AUC {t.value:.4f}  valA APFDc {top5_out[-1]['val_apfdc_macro']:.4f}")
    try:
        imp = optuna.importance.get_param_importances(study)
    except Exception as e:  # noqa: BLE001
        imp = {"error": str(e)}
    figs(study)
    return {"study": study, "trials": trials, "top5": top5_out, "param_importance": imp, "dtr": dtr, "dva": dva,
            "train_rows": int(len(rows)), "val_rows": int(len(vrows))}


def figs(study) -> None:
    import matplotlib.pyplot as plt
    from optuna.visualization.matplotlib import plot_param_importances, plot_slice

    style()
    vals = [t.value for t in study.trials if t.value is not None]
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.plot(range(len(vals)), vals, "o", color=PALETTE[0], ms=4, label="completed trial")
    ax.plot(range(len(vals)), np.maximum.accumulate(vals), color=PALETTE[1], label="best so far")
    ax.set_xlabel("completed trial")
    ax.set_ylabel("valA PR-AUC")
    ax.set_title("Optuna TPE search history (LightGBM)")
    ax.legend()
    savefig(fig, "tune_lgbm_history")
    try:
        ax = plot_param_importances(study)
        savefig(ax.figure, "tune_lgbm_importance")
        axs = plot_slice(study)
        f = axs[0].figure if hasattr(axs, "__len__") else axs.figure
        f.set_size_inches(18, 3.5)
        savefig(f, "tune_lgbm_slice")
    except Exception as e:  # noqa: BLE001
        print("  [optuna] plot failed:", e)


def regularisation_curves(cols, best_params: dict, dtr, dva) -> dict:
    import matplotlib.pyplot as plt

    out = {}
    for name, p in (("unregularised", UNREG), ("tuned", best_params)):
        rec: dict = {}
        lgb.train({**BASE, **p}, dtr, num_boost_round=600, valid_sets=[dtr, dva], valid_names=["train", "valA"],
                  callbacks=[lgb.record_evaluation(rec)])
        out[name] = {k: {m: v[::10] for m, v in d.items()} for k, d in rec.items()}
    style()
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    for ax, metric, lab in ((axes[0], "binary_logloss", "log-loss"), (axes[1], "average_precision", "PR-AUC")):
        for i, name in enumerate(("unregularised", "tuned")):
            for ls, part in (("-", "train"), ("--", "valA")):
                y = out[name][part][metric]
                ax.plot(np.arange(len(y)) * 10, y, ls, color=PALETTE[i], label=f"{name} · {part}")
        ax.set_xlabel("boosting round")
        ax.set_ylabel(lab)
        ax.legend(fontsize=7)
    axes[0].set_title("Train vs validation log-loss")
    axes[1].set_title("Train vs validation PR-AUC")
    savefig(fig, "reg_lgbm_curves")
    return out


def run(cols: list[str], n_trials: int = 60) -> dict:
    t = tune(cols, n_trials)
    best = t["study"].best_params
    curves = regularisation_curves(cols, best, t["dtr"], t["dva"])
    del t["dtr"]
    # refit on the full training sample with early stopping on valA
    X, m = load("train", cols, ["y_fail", "weight"])
    Xv, mv = load("valA", cols, ["y_fail"])
    w = m.weight.to_numpy()
    dtr = lgb.Dataset(X, m.y_fail.to_numpy(np.float32), weight=train_weight(w), params={"max_bin": 127})
    dva = lgb.Dataset(Xv, mv.y_fail.to_numpy(np.float32), reference=dtr)
    rec: dict = {}
    b = lgb.train({**BASE, **best}, dtr, num_boost_round=3000, valid_sets=[dva], valid_names=["valA"],
                  callbacks=[lgb.early_stopping(100, first_metric_only=True, verbose=False), lgb.record_evaluation(rec)])
    save_model({"model": b, "cols": cols, "linear": False, "params": {**BASE, **best},
                "best_iteration": int(b.best_iteration)}, "lgbm")
    out = {"trials": t["trials"], "top5": t["top5"], "best_params": best, "best_value": t["study"].best_value,
           "param_importance": t["param_importance"], "train_rows_tuning": t["train_rows"],
           "val_rows_tuning": t["val_rows"], "max_rounds_tuning": MAX_ROUNDS, "patience_tuning": PATIENCE,
           "train_rows_refit": n_rows("train"), "refit_best_iteration": int(b.best_iteration),
           "refit_valA_pr_auc": float(b.best_score["valA"]["average_precision"]),
           "curves": curves, "space": "see stp/models/tune_lgbm.py::space", "unregularised_params": UNREG,
           "gain_importance": dict(zip(cols, b.feature_importance("gain").tolist()))}
    save_result("tune_lgbm", out)
    return out
