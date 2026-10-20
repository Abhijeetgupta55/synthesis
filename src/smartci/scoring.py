"""Score the collected test files of a repo for the current change.

Model: the exported global model (smartci/model/, copied from models/global/ by `python -m stp.models.export`).
The cold-start variant (no outcome-history / co-failure features) is used while the repo has fewer than
MIN_HISTORY_RUNS finished recorded runs. An optional per-repo adapter (smartci learn) rescales the global logit.
Output per test file: calibrated P(fail), expected duration, priority = P / (duration + 0.001), and the inputs
needed to explain the rank.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from smartci.history import History, state_dir
from stp.features.change import Change, bm25_scores, change_features, change_size_features

import os

# $SMARTCI_MODEL_DIR overrides the packaged model (used by the tests with a tiny synthetic model)
MODEL_DIR = Path(os.environ.get("SMARTCI_MODEL_DIR") or Path(__file__).resolve().parent / "model")
MIN_HISTORY_RUNS = 5
DEFAULT_DURATION = 1.0


@dataclass
class Scored:
    test_file: str
    p_fail: float
    expected_duration: float
    priority: float
    features: dict
    model: str
    contributions: dict = field(default_factory=dict)


class GlobalModel:
    def __init__(self, model_dir: Path | None = None):
        from smartci.treemodel import TextModel

        self.dir = Path(model_dir or os.environ.get("SMARTCI_MODEL_DIR") or MODEL_DIR)
        self.schema = json.loads((self.dir / "schema.json").read_text(encoding="utf-8"))
        cal = json.loads((self.dir / "calibration.json").read_text(encoding="utf-8"))
        # numpy evaluator: the plugin must not pay lightgbm's (scikit-learn's) import time on every session
        self.trees = {k: TextModel(self.dir / f"{k}.txt") for k in ("model", "model_coldstart")}
        self._boosters: dict = {}
        self.cal = {k: (np.asarray(v["x"]), np.asarray(v["y"])) for k, v in cal.items()}
        self.cols = {"model": [f["name"] for f in self.schema["features"]],
                     "model_coldstart": [f["name"] for f in self.schema["features_coldstart"]]}
        self.defaults = {f["name"]: f["default"] for f in self.schema["features"] + self.schema["features_coldstart"]}
        self.version = self.schema["version"]

    def matrix(self, rows: list[dict], which: str) -> np.ndarray:
        cols = self.cols[which]
        return np.array([[float(r.get(c, self.defaults[c])) for c in cols] for r in rows], dtype=np.float32)

    def raw(self, rows: list[dict], which: str) -> np.ndarray:
        """Uncalibrated P(fail) from the tree ensemble (what the calibrator was fitted on)."""
        return self.trees[which].predict(self.matrix(rows, which))

    def calibrate(self, raw: np.ndarray, which: str) -> np.ndarray:
        x, y = self.cal[which]
        return np.interp(raw, x, y)

    def contributions(self, rows: list[dict], which: str) -> list[dict]:
        """Per-feature contributions in log-odds (LightGBM's built-in TreeSHAP)."""
        import lightgbm as lgb  # only `smartci explain` needs exact TreeSHAP

        if which not in self._boosters:
            self._boosters[which] = lgb.Booster(model_file=str(self.dir / f"{which}.txt"))
        c = self._boosters[which].predict(self.matrix(rows, which), pred_contrib=True)
        cols = self.cols[which]
        return [dict(zip(cols + ["_bias"], map(float, r))) for r in c]


def load_adapter(repo: Path) -> dict | None:
    f = state_dir(repo) / "adapter.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def apply_adapter(p: np.ndarray, adapter: dict | None, cov: np.ndarray | None = None) -> np.ndarray:
    if not adapter or not adapter.get("fitted"):
        return p
    z = np.log(np.clip(p, 1e-7, 1 - 1e-7) / (1 - np.clip(p, 1e-7, 1 - 1e-7)))
    z2 = adapter["intercept"] + adapter["coef_logit"] * z
    if adapter.get("uses_coverage") and cov is not None:
        z2 = z2 + adapter["coef_cov"] * cov
    return 1 / (1 + np.exp(-z2))


def feature_rows(repo: Path, test_files: list[str], change: Change, t: float | None = None,
                 stop: frozenset[str] = frozenset(), history: History | None = None) -> list[dict]:
    """All model features for each test file: history (as-of t), cost, change relatedness, co-failure."""
    t = time.time() if t is None else t
    hist = history or History(repo)
    hrows = hist.features(test_files, change.files, t)
    size = change_size_features(change, stop)
    bm = bm25_scores(test_files, change, stop)
    out = []
    for f, h, b in zip(test_files, hrows, bm):
        out.append({**h, **change_features(f, change, stop), **size, "bm25_test_vs_diff": b})
    return out


def score(repo: Path, test_files: list[str], change: Change, t: float | None = None, model: GlobalModel | None = None,
          stop: frozenset[str] | None = None, explain: bool = False,
          covering: dict[str, int] | None = None) -> list[Scored]:
    """`covering` (test file -> changed lines it covers, from a coverage map) feeds the adapter when it uses it."""
    repo = Path(repo)
    t = time.time() if t is None else t
    stop = stop if stop is not None else frozenset({repo.resolve().name.lower().replace("-", "")})
    model = model or GlobalModel()
    hist = History(repo)
    rows = feature_rows(repo, test_files, change, t, stop, hist)
    which = "model" if hist.n_finished(t) >= MIN_HISTORY_RUNS else "model_coldstart"
    p = model.calibrate(model.raw(rows, which), which)
    cov = None if covering is None else np.array([float(covering.get(f, 0) > 0) for f in test_files])
    p = apply_adapter(p, load_adapter(repo), cov)
    dur = np.array([r["dur_ema_asof"] if r["dur_source"] > 0 else _profile_duration(repo, f)
                    for r, f in zip(rows, test_files)], dtype=float)
    prio = p / (dur + 1e-3)
    contrib = model.contributions(rows, which) if explain else [{} for _ in rows]
    return [Scored(f, float(pi), float(di), float(qi), r, which, c)
            for f, pi, di, qi, r, c in zip(test_files, p, dur, prio, rows, contrib)]


_PROFILE: dict[str, dict] = {}


def _profile_duration(repo: Path, test_file: str) -> float:
    key = str(Path(repo).resolve())
    if key not in _PROFILE:
        f = state_dir(repo) / "profile.json"
        _PROFILE[key] = json.loads(f.read_text(encoding="utf-8"))["durations"] if f.exists() else {}
    d = _PROFILE[key].get(test_file)
    if d is None:
        vals = list(_PROFILE[key].values())
        return float(np.median(vals)) if vals else DEFAULT_DURATION
    return float(d)


def stable_order(scored: list[Scored]) -> list[int]:
    """Indices by descending priority; ties keep the original (pytest collection) order."""
    return sorted(range(len(scored)), key=lambda i: (-scored[i].priority, i))

