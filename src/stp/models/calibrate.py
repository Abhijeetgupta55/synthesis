"""Phase 3.2 / 3.7: calibration of every base model on valB, soft voting and stacking.

Calibration. Negative sampling (and class imbalance) distort predicted probabilities even with inverse-probability
weights, so each base model gets a monotone map fitted on *unsampled* valB rows: isotonic regression (main) and
Platt scaling (logistic on the logit, comparison). Ranking within a run is unchanged by isotonic up to ties, but the
p / duration ordering rule needs probabilities on a true scale.

Ensembles (inputs = calibrated base probabilities):
  soft voting  mean of the calibrated probabilities of LR, RF and LightGBM
  stacking     logistic-regression meta-learner fitted on valB with inputs
               [logit p_LR, logit p_RF, logit p_LGBM, cbt_LastFail rank within the run (0 = first, 1 = last),
                ChangedOrNewFirst indicator]
valB is used for both calibration and the stacker; both are low-capacity models (a monotone step function and a
5-input linear model), and test stays untouched.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from stp.baselines import heuristics as H
from stp.models.common import load, load_model, save_model
from stp.models.prep import matrix

BASE_MODELS = ["lr", "rf", "lgbm"]
TIE = 1e-9   # see Calibrated.predict


def raw_predict(entry: dict, X_raw: dict | pd.DataFrame) -> np.ndarray:
    X = matrix(X_raw, entry["cols"], entry.get("linear", False))
    m = entry["model"]
    if hasattr(m, "predict_proba"):
        return m.predict_proba(X)[:, 1]
    return m.predict(X, num_iteration=entry.get("best_iteration"))


def logit(p):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p))


class Calibrated:
    def __init__(self, entry: dict, iso: IsotonicRegression, platt: LogisticRegression):
        self.entry, self.iso, self.platt = entry, iso, platt

    def raw(self, d) -> np.ndarray:
        return raw_predict(self.entry, d)

    def predict(self, d, method: str = "isotonic") -> np.ndarray:
        r = self.raw(d)
        if method == "raw":
            return r
        if method == "platt":
            return self.platt.predict_proba(logit(r)[:, None])[:, 1]
        return self.iso.predict(r) + TIE * r  # isotonic is a step function; +1e-9*raw breaks its plateaus by the raw score (calibration unchanged, ranking kept)


def run_level(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """cbt_LastFail rank in [0, 1] within each run and the ChangedOrNewFirst indicator, for a full-run frame."""
    rank = np.zeros(len(frame))
    rng = np.random.default_rng(0)
    for _, idx in frame.groupby(["project", "run_idx"]).indices.items():
        d = {c: frame[c].to_numpy()[idx] for c in H.COLUMNS + ["test_id"]}
        pr = H.cbt_lastfail(d, rng)
        o = np.lexsort((rng.random(len(idx)), pr))
        r = np.empty(len(idx))
        r[o] = np.arange(len(idx)) / max(1, len(idx) - 1)
        rank[idx] = r
    flag = (frame.test_file_in_diff.to_numpy(bool) | frame.is_new_test.to_numpy(bool)).astype(float)
    return rank, flag


class Stacker:
    def __init__(self, members: dict[str, Calibrated], meta: LogisticRegression):
        self.members, self.meta = members, meta

    def features(self, d, rank, flag) -> np.ndarray:
        cols = [logit(self.members[m].predict(d)) for m in BASE_MODELS]
        return np.column_stack(cols + [rank, flag])

    def predict(self, d, rank, flag) -> np.ndarray:
        return self.meta.predict_proba(self.features(d, rank, flag))[:, 1]


class SoftVote:
    def __init__(self, members: dict[str, Calibrated]):
        self.members = members

    def predict(self, d) -> np.ndarray:
        return np.mean([self.members[m].predict(d) for m in BASE_MODELS], axis=0)


def fit_all(extra_cols: list[str]) -> dict:
    """Fit calibrators for every base model on valB, then the stacker; persist them."""
    cols_needed = sorted(set(sum((load_model(m)["cols"] for m in BASE_MODELS), [])) | set(extra_cols))
    _, vb = load("valB", [cols_needed[0]], cols_needed + ["y_fail", "project", "run_idx"])
    y = vb.y_fail.to_numpy(bool)
    cal = {}
    out = {}
    for m in BASE_MODELS:
        e = load_model(m)
        r = raw_predict(e, vb)
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(r, y)
        platt = LogisticRegression(C=1e6, max_iter=1000).fit(logit(r)[:, None], y)
        cal[m] = Calibrated(e, iso, platt)
        save_model(cal[m], f"cal_{m}")
        out[m] = {"valB_mean_raw": float(r.mean()), "valB_base_rate": float(y.mean())}
    rank, flag = run_level(vb)
    st = Stacker(cal, LogisticRegression(C=1.0, max_iter=2000))
    st.meta.fit(st.features(vb, rank, flag), y)
    save_model(st, "stack")
    save_model(SoftVote(cal), "vote")
    out["stack_coef"] = dict(zip([f"logit_{m}" for m in BASE_MODELS] + ["cbt_lastfail_rank", "changed_or_new"],
                                 st.meta.coef_[0].tolist()))
    out["stack_intercept"] = float(st.meta.intercept_[0])
    return out
