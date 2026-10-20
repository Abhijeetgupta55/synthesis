"""Feature schema: names, groups, dtypes and defaults. Single source of truth for the store, models and smartci.

Groups (used by the Phase 3 ablations A → D):
  history      as-of outcome history (two scopes: h_ all-stage, hs_ same-stage)
  cost         as-of duration estimates
  change       relatedness between the test and the change under test
  cofail       as-of co-failure memory between changed files and the test
  reserved     columns kept for a future model (always NaN now)
Columns that are *not* features (keys, labels, evaluation-only values) are listed separately; models must never
read them. tests/test_leakage.py checks that every feature column is in FEATURES and no label is.
"""
from __future__ import annotations

from stp.features.history import HISTORY_STATS

_HIST_DTYPES = {"n_fail": "int32", "days_since_last_fail": "float32", "fails_last_7d": "int32",
                "fails_last_30d": "int32", "last_outcome": "bool", "n_transitions": "int32", "n_runs_seen": "int32",
                "fail_rate": "float32"}

FEATURES: dict[str, dict] = {}
for _scope in ("h", "hs"):
    for _k in HISTORY_STATS:
        FEATURES[f"{_scope}_{_k}"] = {"group": "history", "dtype": _HIST_DTYPES[_k], "scope": _scope}
FEATURES["is_new_test"] = {"group": "history", "dtype": "bool", "scope": "h"}
FEATURES["h_last_fail_same_stage"] = {"group": "history", "dtype": "bool", "scope": "h"}
for _k in ("dur_last_asof", "dur_ema_asof"):
    FEATURES[_k] = {"group": "cost", "dtype": "float32"}
FEATURES["dur_source"] = {"group": "cost", "dtype": "int8"}
for _k, _t in [("test_file_in_diff", "bool"), ("same_top_module", "bool"), ("path_prefix_overlap", "float32"),
               ("name_token_overlap", "int16"), ("bm25_test_vs_diff", "float32"), ("chg_n_files", "int32"),
               ("chg_additions", "int32"), ("chg_deletions", "int32"), ("chg_n_top_modules", "int16"),
               ("has_change_data", "bool")]:
    FEATURES[_k] = {"group": "change", "dtype": _t}
for _k, _t in [("cof_max", "float32"), ("cof_sum", "float32"), ("cof_count_max", "int32")]:
    FEATURES[_k] = {"group": "cofail", "dtype": _t}
FEATURES["semantic_sim"] = {"group": "reserved", "dtype": "float32"}

KEYS = ["run_idx", "test_id"]
LABELS = ["y_fail", "y_ftf_asof", "y_ftf_asof_ss"]
EVAL_ONLY = ["y_duration_s"]     # the test's real duration in *this* run: evaluation cost, never a feature

GROUPS = ["history", "cost", "change", "cofail"]


def feature_names(groups: list[str] | None = None, scope: str | None = None) -> list[str]:
    """Model input columns in fixed order. scope='h' keeps only all-stage history, 'hs' only same-stage."""
    out = []
    for name, m in FEATURES.items():
        if m["group"] == "reserved":
            continue
        if groups is not None and m["group"] not in groups:
            continue
        if scope is not None and m.get("scope") not in (None, scope) and name not in ("is_new_test",):
            continue
        out.append(name)
    return out
