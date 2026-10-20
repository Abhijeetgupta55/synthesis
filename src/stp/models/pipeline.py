"""Phase 3 orchestrator. Each stage is skipped when its output exists (resumable after a sleep/crash).

  data     training sample (K=200), valA / valB (time halves of val), testC
  scope    choose all-stage (h_) vs same-stage (hs_) history on valB PR-AUC with a default LightGBM
  lr, rf   grids + regularisation figures (tune_linear_rf)
  lgbm     Optuna + regularisation curves + refit (tune_lgbm)
  calib    isotonic / Platt per model on valB, soft vote, stacking
  cls      classification metrics on testC
  domain   APFDc / TTFF on all failed test runs, models vs baselines

Usage: python -m stp.models.pipeline [--stages data,scope,...] [--trials 60]
"""
from __future__ import annotations

import argparse
import json
import time

import lightgbm as lgb
import numpy as np

from stp import paths
from stp.models import data as D
from stp.models.common import MODEL_DIR, TRAIN_DIR, has_model, load
from stp.models.prep import columns
from stp.results import load_result, save_result

STAGES = ["data", "scope", "lr", "rf", "lgbm", "calib", "cls", "domain"]


def stage_data() -> None:
    if not (TRAIN_DIR / "train.parquet").exists():
        st = D.build_training_sample("train", K=200, max_failed_runs=6000, passing_frac=0.1)
        save_result("train_sample", {"K": 200, "max_failed_runs_per_project": 6000, "passing_frac": 0.1,
                                     "per_project": st, "doc": D.__doc__})
    for name, split, part in (("valA", "val", "first"), ("valB", "val", "second"), ("testC", "test", None)):
        if not (TRAIN_DIR / f"{name}.parquet").exists():
            st = D.build_calibration_set(name, run_frac=0.25, max_runs=600, split=split, part=part,
                                         seed={"valA": 101, "valB": 102, "testC": 103}[name])
            save_result(f"set_{name}", {"per_project": st, "run_frac": 0.25, "max_runs": 600, "split": split,
                                        "part": part})


def stage_scope() -> dict:
    """Default LightGBM on each history scope; pick by valB PR-AUC (valA early-stops)."""
    if (paths.RESULTS / "scope_choice.json").exists():
        return load_result("scope_choice")
    from stp.models.common import subsample_rows
    from stp.models.tune_lgbm import BASE
    rows = subsample_rows("train", 1_000_000, 5)
    res = {}
    for scope in ("h", "hs", "both"):
        cols = columns(scope=None if scope == "both" else scope)
        X, m = load("train", cols, ["y_fail", "weight"], rows=rows)
        Xa, ma = load("valA", cols, ["y_fail"])
        Xb, mb = load("valB", cols, ["y_fail"])
        w = m.weight.to_numpy()
        dtr = lgb.Dataset(X, m.y_fail.to_numpy(np.float32), weight=w / w.mean(), params={"max_bin": 127})
        dva = lgb.Dataset(Xa, ma.y_fail.to_numpy(np.float32), reference=dtr)
        b = lgb.train({**BASE, "num_leaves": 63, "learning_rate": 0.05, "min_child_samples": 100}, dtr, 1500,
                      valid_sets=[dva], callbacks=[lgb.early_stopping(100, first_metric_only=True, verbose=False)])
        from sklearn.metrics import average_precision_score
        res[scope] = {"n_features": len(cols), "valA_pr_auc": float(b.best_score["valid_0"]["average_precision"]),
                      "valB_pr_auc": float(average_precision_score(mb.y_fail, b.predict(Xb))),
                      "best_iteration": int(b.best_iteration)}
        print(f"  [scope] {scope}: {res[scope]}", flush=True)
    choice = max(("h", "hs"), key=lambda s: res[s]["valB_pr_auc"])
    out = {"results": res, "choice": choice,
           "rule": "pick the single-scope variant with the higher valB PR-AUC; 'both' is reported for reference"}
    save_result("scope_choice", out)
    return out


def main_cols() -> list[str]:
    return columns(scope=load_result("scope_choice")["choice"])


def stage_lr():
    if not has_model("lr"):
        from stp.models.tune_linear_rf import tune_lr
        tune_lr(main_cols())


def stage_rf():
    if not has_model("rf"):
        from stp.models.tune_linear_rf import tune_rf
        tune_rf(main_cols())


def stage_lgbm(trials: int):
    if not has_model("lgbm"):
        from stp.models.tune_lgbm import run
        run(main_cols(), trials)


def stage_calib():
    if not has_model("stack"):
        from stp.baselines import heuristics as H
        from stp.models.calibrate import fit_all
        out = fit_all(H.COLUMNS + ["test_id"])
        save_result("calibration", out)


def stage_cls():
    if not (paths.RESULTS / "models_classification.json").exists():
        from stp.models.evaluate import classification
        save_result("models_classification", classification(main_cols()))


def stage_domain():
    from stp.models.evaluate import domain_eval, model_methods
    methods, cols = model_methods()
    df = domain_eval(methods, cols, "main")
    (MODEL_DIR / "domain_main_done.json").write_text(json.dumps({"rows": len(df)}))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", default=",".join(STAGES))
    ap.add_argument("--trials", type=int, default=60)
    a = ap.parse_args()
    for s in a.stages.split(","):
        t0 = time.time()
        print(f"[pipeline] stage {s}", flush=True)
        {"data": stage_data, "scope": stage_scope, "lr": stage_lr, "rf": stage_rf,
         "lgbm": lambda: stage_lgbm(a.trials), "calib": stage_calib, "cls": stage_cls, "domain": stage_domain}[s]()
        print(f"[pipeline] stage {s} done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
