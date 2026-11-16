"""One colour per ordering method, used by every generated figure and every page of the demo app.

Equivalent names (LRTS baseline vs smartci backtest name) share a colour: QTF = fastest_first,
cbt_LastFail ~ recently_failed_first, ChangedOrNewFirst = changed_files_first, lgbm = smartci.
"""
from __future__ import annotations

COLORS = {
    "default": "#7f7f7f", "Random": "#b8b8b8", "random": "#b8b8b8",
    "QTF": "#e8a200", "fastest_first": "#e8a200",
    "cbt_LastFail": "#2a78d6", "recently_failed_first": "#2a78d6",
    "LastFail": "#86b6ea", "LastFail_tiesShort": "#a9c8ec", "FailCount": "#55718c", "cbt_BM25": "#3fb0bf",
    "ChangedOrNewFirst": "#1a9e6e", "changed_files_first": "#1a9e6e",
    "coverage_first": "#6a4fb5",
    "lr": "#c08ad9", "rf": "#7c9a3a", "vote": "#f08c8c", "stack": "#a5141b",
    "lgbm": "#e34948", "smartci": "#e34948", "smartci (LightGBM)": "#e34948", "lgbm_p": "#f2a1a0",
    "Oracle": "#111111",
}
LABELS = {"lgbm": "LightGBM", "lr": "logistic regression", "rf": "random forest", "vote": "soft voting",
          "stack": "stacking", "QTF": "QTF (fastest first)", "cbt_LastFail": "cbt_LastFail (recent failures, cheap)",
          "ChangedOrNewFirst": "changed or new first", "lgbm_p": "LightGBM, probability only"}


def color(m: str) -> str:
    return COLORS.get(m, "#e87ba4")


def label(m: str) -> str:
    return LABELS.get(m, m)
