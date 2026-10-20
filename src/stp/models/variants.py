"""Phase 3.8 ablations and 3.9 Python transfer: LightGBM variants with the tuned parameters.

Ablations (cumulative feature groups, same data and parameters, early stopping on valA):
  A history   B + cost   C + change relatedness   D + co-failure (= the full model)
Transfer to TVM (Python/pytest suites):
  jvm9_to_tvm  train on the 9 JVM projects only
  tvm_only     train on TVM only
  all_to_tvm   train on all 10 projects
  The model to ship is the variant with the best TVM valB PR-AUC (then confirmed on TVM test).
Each variant is calibrated (isotonic) on valB rows of its own evaluation projects.
"""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pyarrow.parquet as pq
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score

from stp import paths
from stp.models.common import train_weight, TRAIN_DIR, has_model, load, load_model, save_model
from stp.models.prep import columns, matrix

ABLATIONS = {"A_history": ["history"], "B_cost": ["history", "cost"], "C_change": ["history", "cost", "change"],
             "D_cofail": ["history", "cost", "change", "cofail"]}
JVM9 = [p for p in paths.PROJECTS if p != "tvm"]
TRANSFER = {"jvm9_to_tvm": JVM9, "tvm_only": ["tvm"], "all_to_tvm": paths.PROJECTS}


class Variant:
    def __init__(self, booster, cols, iso, best_iteration):
        self.booster, self.cols, self.iso, self.best_iteration = booster, cols, iso, best_iteration

    def raw(self, d):
        return self.booster.predict(matrix(d, self.cols), num_iteration=self.best_iteration)

    def predict(self, d):
        r = self.raw(d)
        return self.iso.predict(r) + 1e-9 * r  # isotonic is a step function; +1e-9*raw breaks its plateaus by the raw score (calibration unchanged, ranking kept)


def _rows_for(name: str, projects: list[str]) -> np.ndarray:
    p = pq.read_table(TRAIN_DIR / f"{name}.parquet", columns=["project"]).column(0).to_numpy(zero_copy_only=False)
    return np.flatnonzero(np.isin(p, projects))


def train_variant(name: str, cols: list[str], train_projects: list[str], eval_projects: list[str] | None = None,
                  max_rows: int | None = None) -> dict:
    if has_model(f"var_{name}"):
        return load_model(f"var_{name}_info")
    params = load_model("lgbm")["params"]
    rows = _rows_for("train", train_projects)
    if max_rows and len(rows) > max_rows:
        rows = np.sort(np.random.default_rng(0).choice(rows, max_rows, replace=False))
    X, m = load("train", cols, ["y_fail", "weight"], rows=rows)
    ev = eval_projects or train_projects
    Xa, ma = load("valA", cols, ["y_fail"], rows=_rows_for("valA", train_projects))
    w = m.weight.to_numpy()
    dtr = lgb.Dataset(X, m.y_fail.to_numpy(np.float32), weight=train_weight(w), params={"max_bin": 127})
    dva = lgb.Dataset(Xa, ma.y_fail.to_numpy(np.float32), reference=dtr)
    b = lgb.train(params, dtr, 3000, valid_sets=[dva],
                  callbacks=[lgb.early_stopping(100, first_metric_only=True, verbose=False)])
    del X, dtr
    Xb, mb = load("valB", cols, ["y_fail"], rows=_rows_for("valB", ev))
    rb = b.predict(Xb, num_iteration=b.best_iteration)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(rb, mb.y_fail.to_numpy(bool))
    v = Variant(b, cols, iso, int(b.best_iteration))
    save_model(v, f"var_{name}")
    Xt, mt = load("testC", cols, ["y_fail", "y_ftf_asof"], rows=_rows_for("testC", ev))
    rt = b.predict(Xt, num_iteration=b.best_iteration)
    pt = iso.predict(rt) + 1e-9 * rt
    info = {"name": name, "cols": cols, "train_projects": train_projects, "eval_projects": ev,
            "train_rows": int(len(rows)), "best_iteration": int(b.best_iteration),
            "valB_pr_auc": float(average_precision_score(mb.y_fail, rb)),
            "testC_pr_auc": float(average_precision_score(mt.y_fail, pt)),
            "testC_pr_auc_ftf": float(average_precision_score(mt.y_ftf_asof, pt)) if mt.y_ftf_asof.any() else None}
    save_model(info, f"var_{name}_info")
    print(f"  [variant] {info}", flush=True)
    return info


def run_ablations(scope: str) -> dict:
    out = {}
    for name, groups in ABLATIONS.items():
        out[name] = train_variant(f"abl_{name}", columns(groups, scope), paths.PROJECTS)
    return out


def run_transfer(scope: str) -> dict:
    cols = columns(scope=scope)
    return {name: train_variant(f"tr_{name}", cols, projs, ["tvm"]) for name, projs in TRANSFER.items()}


def run_coldstart(scope: str) -> dict:
    """Cold start: a brand-new repo has no CI history, so the outcome-history and co-failure groups are left out.
    Cost stays (smartci `profile` measures durations before the first prioritised run) and so does change
    relatedness, which needs only the diff and the test names."""
    cols = columns(["cost", "change"], scope)
    return train_variant("coldstart", cols, paths.PROJECTS)
