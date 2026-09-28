"""Shared helpers for EDA sections: JSON output, figure style, per-project + macro summaries."""
from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from stp import paths  # noqa: E402

# Categorical palette (fixed order, never cycled). Past 8 series we use small multiples.
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"


def style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": TEXT_2, "xtick.color": TEXT_2, "ytick.color": TEXT_2,
        "text.color": TEXT, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "axes.titlesize": 11,
        "axes.titleweight": "bold", "font.size": 9, "legend.frameon": False, "lines.linewidth": 2,
        "figure.dpi": 110,
    })


def savefig(fig, name: str) -> Path:
    paths.FIGURES.mkdir(parents=True, exist_ok=True)
    out = paths.FIGURES / f"{name}.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else round(f, 6)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def save_json(obj, name: str) -> Path:
    paths.EDA_JSON.mkdir(parents=True, exist_ok=True)
    out = paths.EDA_JSON / f"{name}.json"
    out.write_text(json.dumps(_clean(obj), indent=2), encoding="utf-8")
    return out


def load_json(name: str) -> dict:
    return json.loads((paths.EDA_JSON / f"{name}.json").read_text(encoding="utf-8"))


def with_macro(per_project: dict[str, float]) -> dict:
    """{project: value} -> {'per_project': ..., 'macro': mean of non-null project values}."""
    vals = [v for v in per_project.values() if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return {"per_project": per_project, "macro": float(np.mean(vals)) if vals else None}
