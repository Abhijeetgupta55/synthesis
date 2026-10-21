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
from stp.models.common import train_weight, MODEL_DIR, TRAIN_DIR, has_model, load
from stp.models.prep import columns
from stp.results import load_result, save_result

STAGES = ["data", "labels", "scope", "univariate", "lr", "rf", "lgbm", "calib", "cls", "domain", "variants",
          "abl_domain", "summary", "interpret", "export"]


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
        dtr = lgb.Dataset(X, m.y_fail.to_numpy(np.float32), weight=train_weight(w), params={"max_bin": 127})
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


def stage_labels():
    if not (paths.RESULTS / "labels.json").exists():
        from stp.models.labels import main as m
        m()


def stage_univariate():
    if not (paths.RESULTS / "univariate.json").exists():
        from stp.models.univariate import main as m
        m()


def stage_variants():
    from stp.models import variants as V
    scope = load_result("scope_choice")["choice"]
    abl = V.run_ablations(scope)
    tr = V.run_transfer(scope)
    cold = V.run_coldstart(scope)
    save_result("ablations", {"variants": abl})
    save_result("transfer", transfer_decision(tr))
    save_result("coldstart", cold)


def transfer_decision(tr: dict) -> dict:
    """Declared rule: choose the variant with the best TVM valB PR-AUC, then confirm on TVM testC. If the chosen
    variant is worse on testC than the pooled all-projects variant, confirmation has failed and the pooled variant is
    shipped instead. That fallback uses test information; it is disclosed, and the shipped model's unbiased evaluation
    is on repositories no model has seen (Phase 5)."""
    chosen = max(tr, key=lambda k: tr[k]["valB_pr_auc"])
    confirmed = chosen == "all_to_tvm" or tr[chosen]["testC_pr_auc"] >= tr["all_to_tvm"]["testC_pr_auc"]
    return {"variants": tr, "chosen": chosen, "confirmed_on_test": bool(confirmed),
            "shipped": chosen if confirmed else "all_to_tvm",
            "rule": transfer_decision.__doc__.strip()}


def stage_abl_domain():
    from stp.models.evaluate import domain_eval, variant_methods
    from stp.models.variants import ABLATIONS
    methods, cols = variant_methods({f"abl_{k}": f"var_abl_{k}" for k in ABLATIONS})
    domain_eval(methods, cols, "abl")


def stage_summary():
    from stp.models.summary import main as m
    m()


def stage_interpret():
    if not (paths.RESULTS / "interpret.json").exists():
        from stp.models.interpret import main as m
        m()


def stage_export():
    from stp.models.export import export
    tr = load_result("transfer")
    shipped = tr.get("shipped") or transfer_decision(tr["variants"])["shipped"]
    export(f"var_tr_{shipped}")
    from stp.reports.model_card import main as card
    card()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", default=",".join(STAGES))
    ap.add_argument("--trials", type=int, default=60)
    a = ap.parse_args()
    for s in a.stages.split(","):
        t0 = time.time()
        print(f"[pipeline] stage {s}", flush=True)
        {"data": stage_data, "labels": stage_labels, "scope": stage_scope, "univariate": stage_univariate,
         "lr": stage_lr, "rf": stage_rf, "lgbm": lambda: stage_lgbm(a.trials), "calib": stage_calib, "cls": stage_cls,
         "domain": stage_domain, "variants": stage_variants, "abl_domain": stage_abl_domain,
         "summary": stage_summary, "interpret": stage_interpret, "export": stage_export}[s]()
        print(f"[pipeline] stage {s} done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
