"""Shared Phase 3 plumbing: datasets on disk, memory-lean loading, model persistence, metrics.

Data roles (all time-respecting; test is touched only by the final evaluation):
  train      negative-sampled rows of training runs (stp.models.data.build_training_sample)
  train_sub  a fixed 1M-row subsample of train (by run) for the expensive grids (LR, RF, Optuna)
  valA       unsampled rows of a random subset of the *earlier* half of each project's validation runs:
             hyperparameter selection and early stopping
  valB       same for the *later* half: calibration, stacking meta-learner, history-scope choice, thresholds
  testC      unsampled rows of a random subset of test runs: classification metrics (PR-AUC, ROC, Brier, ...)
Domain metrics (APFDc, time to first failure) use *all* failed test runs through stp.evaluation.harness.
"""
from __future__ import annotations

import json
import pickle

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from stp import paths
from stp.models.prep import matrix

TRAIN_DIR = paths.PROCESSED / "train"
MODEL_DIR = paths.PROCESSED / "models"
FIG = paths.FIGURES


def load(name: str, cols: list[str], extra: list[str] = (), linear: bool = False, rows: np.ndarray | None = None):
    """(X float32, frame of `extra` columns) from data/processed/train/<name>.parquet, column by column."""
    f = TRAIN_DIR / f"{name}.parquet"
    pf = pq.ParquetFile(f)
    n = pf.metadata.num_rows
    if rows is None:
        rows = np.arange(n)
    X = np.empty((len(rows), len(cols)), np.float32)
    for j, c in enumerate(cols):
        v = pq.read_table(f, columns=[c]).column(0).to_numpy(zero_copy_only=False)[rows]
        X[:, j] = matrix({c: v}, [c], linear)[:, 0]
    meta = pd.DataFrame({c: pq.read_table(f, columns=[c]).column(0).to_numpy(zero_copy_only=False)[rows]
                         for c in extra})
    return X, meta


def n_rows(name: str) -> int:
    return pq.ParquetFile(TRAIN_DIR / f"{name}.parquet").metadata.num_rows


def subsample_rows(name: str, n_target: int, seed: int = 0) -> np.ndarray:
    """Row indices of whole runs, drawn at random until about n_target rows (keeps per-run structure)."""
    f = TRAIN_DIR / f"{name}.parquet"
    t = pq.read_table(f, columns=["project", "run_idx"]).to_pandas()
    key = t.project.astype(str) + ":" + t.run_idx.astype(str)
    codes, uniq = pd.factorize(key)
    sizes = np.bincount(codes)
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(uniq))
    keep = order[: int(np.searchsorted(np.cumsum(sizes[order]), n_target)) + 1]
    mask = np.isin(codes, keep)
    return np.flatnonzero(mask)


def save_model(obj, name: str) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODEL_DIR / f"{name}.pkl", "wb") as fh:
        pickle.dump(obj, fh)


def load_model(name: str):
    with open(MODEL_DIR / f"{name}.pkl", "rb") as fh:
        return pickle.load(fh)


def has_model(name: str) -> bool:
    return (MODEL_DIR / f"{name}.pkl").exists()


def cls_metrics(y, p, w=None) -> dict:
    y = np.asarray(y, bool)
    if y.sum() == 0 or y.all():
        return {"pr_auc": None, "roc_auc": None, "brier": None, "base_rate": float(y.mean())}
    return {"pr_auc": float(average_precision_score(y, p, sample_weight=w)),
            "roc_auc": float(roc_auc_score(y, p, sample_weight=w)),
            "brier": float(brier_score_loss(y, np.clip(p, 0, 1), sample_weight=w)),
            "base_rate": float(np.average(y, weights=w)), "n": int(len(y)), "n_pos": int(y.sum())}


def per_project_pr_auc(y, p, project) -> dict:
    out = {}
    for pj in np.unique(project):
        m = project == pj
        if y[m].sum() > 0:
            out[str(pj)] = float(average_precision_score(y[m], p[m]))
    return out


def dump(name: str, obj) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    (MODEL_DIR / f"{name}.json").write_text(json.dumps(obj, indent=2, default=float), encoding="utf-8")
