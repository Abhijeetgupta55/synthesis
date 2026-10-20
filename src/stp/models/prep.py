"""Model input matrices from feature-store columns.

Trees (RF, LightGBM) take the raw features: monotone transforms do not change their splits.
Logistic regression gets log1p on heavy-tailed counts/durations/sizes (a linear model in log space captures
"each doubling adds the same risk", which is what the EDA's lift tables show) and is standardised afterwards
(sklearn StandardScaler inside the LR pipeline), so that the L1/L2 penalty treats all coefficients on one scale.

Project identity is deliberately NOT a feature: the exported model has to score repositories it has never seen
(smartci), and a project id would let a pooled model memorise per-project base rates instead of learning
transferable signals.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from stp.features.schema import FEATURES, feature_names

LOG1P = {
    "h_n_fail", "h_fails_last_7d", "h_fails_last_30d", "h_n_transitions", "h_n_runs_seen", "h_days_since_last_fail",
    "hs_n_fail", "hs_fails_last_7d", "hs_fails_last_30d", "hs_n_transitions", "hs_n_runs_seen",
    "hs_days_since_last_fail", "dur_last_asof", "dur_ema_asof", "chg_n_files", "chg_additions", "chg_deletions",
    "chg_n_top_modules", "name_token_overlap", "bm25_test_vs_diff", "cof_sum", "cof_count_max",
}


def columns(groups: list[str] | None = None, scope: str | None = None) -> list[str]:
    return feature_names(groups, scope)


def matrix(df: pd.DataFrame | dict, cols: list[str], linear: bool = False) -> np.ndarray:
    X = np.empty((len(df[cols[0]]), len(cols)), dtype=np.float32)
    for j, c in enumerate(cols):
        v = np.asarray(df[c], dtype=np.float64)
        if linear and c in LOG1P:
            v = np.log1p(np.maximum(v, 0))
        X[:, j] = v
    return X


def defaults() -> dict:
    """Value to use when a feature is missing at scoring time (cold start / unknown): the 'no evidence' value."""
    d = {}
    for c, m in FEATURES.items():
        if c.endswith("days_since_last_fail"):
            d[c] = 9999.0
        elif c.endswith("fail_rate"):
            d[c] = 0.0025
        elif m["dtype"] == "bool":
            d[c] = 0.0
        else:
            d[c] = 0.0
    d["is_new_test"] = 1.0
    d["dur_source"] = 0.0
    d["has_change_data"] = 1.0
    return d
