"""Measure before building the ML Lab: do the Lab's lessons show up on a small sample?

On ~300k rows sampled from data/processed/train/train.parquet (negative-sampled training rows) we train logistic
regression and LightGBM, each without and with regularization, and report PR-AUC on:
  (a) random 80/20 split of the sample (rows of one CI run can land on both sides),
  (b) valA: time-later validation runs, unsampled (the real failure rate),
  (c) time 80/20 split of the sample: train on the earliest 80% of runs, test on the latest 20%.
(c) has the same sampling as (a), so (a) vs (c) isolates the effect of a random split; (b) also differs in
base rate, because train.parquet keeps every failure but at most 200 passing tests per run. PR-AUC grows with the
base rate, so each result is also given as lift = PR-AUC / base rate.

Usage: python -m stp.models.lab_check   -> reports/results/lab_check.json
"""
from __future__ import annotations

import time

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from stp import paths
from stp.models.common import load_model
from stp.models.prep import matrix
from stp.results import save_result

N = 300_000
SEED = 0
TRAIN = paths.PROCESSED / "train" / "train.parquet"
VALA = paths.PROCESSED / "train" / "valA.parquet"


def load_sample(cols):
    t = pq.read_table(TRAIN, columns=cols + ["y_fail", "run_idx", "project", "start_ts"]).to_pandas()
    rng = np.random.default_rng(SEED)
    return t.iloc[np.sort(rng.choice(len(t), N, replace=False))].reset_index(drop=True)


def models(params_lgbm):
    unreg_lgb = dict(objective="binary", learning_rate=0.1, num_leaves=1024, min_child_samples=1, lambda_l1=0.0,
                     lambda_l2=0.0, feature_fraction=1.0, bagging_fraction=1.0, bagging_freq=0, max_depth=-1,
                     verbose=-1, seed=SEED, num_threads=4)
    reg_lgb = {**params_lgbm, "objective": "binary", "verbose": -1, "seed": SEED, "num_threads": 4}
    return {"lr_unregularized": ("lr", dict(penalty=None)),
            "lr_regularized": ("lr", dict(penalty="l1", C=0.001, solver="liblinear")),
            "lgbm_unregularized": ("lgbm", (unreg_lgb, 400, False)),
            "lgbm_regularized": ("lgbm", (reg_lgb, 1000, True))}


def fit_predict(kind, spec, Xtr, ytr, Xs: dict):
    if kind == "lr":
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, **spec))
        m.fit(Xtr, ytr)
        return {k: m.predict_proba(X)[:, 1] for k, X in Xs.items()} | {"train": m.predict_proba(Xtr)[:, 1]}, None
    params, rounds, early = spec
    # early stopping uses a slice of the *training* rows (latest 10% by order), never the evaluation sets
    cut = int(len(Xtr) * 0.9)
    dtr = lgb.Dataset(Xtr[:cut] if early else Xtr, ytr[:cut] if early else ytr)
    cb = []
    valid = []
    if early:
        valid = [lgb.Dataset(Xtr[cut:], ytr[cut:], reference=dtr)]
        cb = [lgb.early_stopping(50, verbose=False)]
    b = lgb.train(params, dtr, rounds, valid_sets=valid, callbacks=cb)
    it = b.best_iteration or rounds
    return {k: b.predict(X, num_iteration=it) for k, X in Xs.items()} | {"train": b.predict(Xtr, num_iteration=it)}, it


def main() -> None:
    t0 = time.time()
    cols = load_model("cal_lgbm").entry["cols"]
    params = load_model("lgbm")["params"]
    s = load_sample(cols)
    va = pq.read_table(VALA, columns=cols + ["y_fail"]).to_pandas()
    rng = np.random.default_rng(SEED)
    rand_test = rng.random(len(s)) < 0.2
    runs = s[["run_idx", "project", "start_ts"]].drop_duplicates().sort_values("start_ts")
    late = set(map(tuple, runs.iloc[int(len(runs) * 0.8):][["project", "run_idx"]].to_numpy()))
    time_test = np.array([(p, r) in late for p, r in zip(s.project, s.run_idx)])
    y = s.y_fail.to_numpy(bool)
    yv = va.y_fail.to_numpy(bool)
    out = {"n_sample": len(s), "seed": SEED, "features": cols, "splits": {}, "doc": __doc__.strip()}
    for split, test in (("random_80_20", rand_test), ("time_80_20", time_test)):
        for name, (kind, spec) in models(params).items():
            lin = kind == "lr"
            Xtr = matrix(s[~test], cols, lin)
            Xte = matrix(s[test], cols, lin)
            Xva = matrix(va, cols, lin)
            t1 = time.time()
            p, it = fit_predict(kind, spec, Xtr, y[~test], {"test": Xte, "valA": Xva})
            r = {"train": average_precision_score(y[~test], p["train"]),
                 "test": average_precision_score(y[test], p["test"]),
                 "valA": average_precision_score(yv, p["valA"]),
                 "seconds": round(time.time() - t1, 1), "best_iteration": it,
                 "base_rate": {"train": float(y[~test].mean()), "test": float(y[test].mean()),
                               "valA": float(yv.mean())}}
            r["lift"] = {k: r[k] / r["base_rate"][k] for k in ("train", "test", "valA")}
            out["splits"].setdefault(split, {})[name] = r
            print(f"{split:13s} {name:20s} train {r['train']:.3f}  test {r['test']:.3f}  valA {r['valA']:.3f}  "
                  f"(lift {r['lift']['test']:.0f}x / {r['lift']['valA']:.0f}x)  {r['seconds']} s", flush=True)
    out["seconds_total"] = round(time.time() - t0, 1)
    save_result("lab_check", out)


if __name__ == "__main__":
    main()
