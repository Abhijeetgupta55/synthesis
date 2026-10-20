"""Phase 3.10: export the shipped model to models/global/ in a self-contained, pickle-free format.

  models/global/model.txt            LightGBM booster (text format), chosen by the TVM-transfer evidence
  models/global/model_coldstart.txt  LightGBM booster without history / co-failure features (new repos)
  models/global/calibration.json     isotonic calibrators as (x_thresholds, y_values) for np.interp
  models/global/schema.json          feature names in model order, dtypes, defaults for missing values, version,
                                     training data range, headline metrics
  models/global/MODEL_CARD.md        intended use, limits, training data
`smartci.scoring` loads these with lightgbm + numpy only; tests/test_export.py checks that scoring works with
no LRTS file present.
"""
from __future__ import annotations

import json
import time

import numpy as np

from stp import paths
from stp.features.schema import FEATURES
from stp.models.common import load_model
from stp.models.prep import defaults
from stp.results import git_sha, load_result

OUT = paths.ROOT / "models" / "global"
VERSION = "0.1.0"


def iso_to_json(iso) -> dict:
    return {"x": np.asarray(iso.X_thresholds_, float).tolist(), "y": np.asarray(iso.y_thresholds_, float).tolist()}


def export(main_variant: str, coldstart_variant: str = "var_coldstart") -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    main = load_model(main_variant)
    cold = load_model(coldstart_variant)
    main.booster.save_model(str(OUT / "model.txt"), num_iteration=main.best_iteration)
    cold.booster.save_model(str(OUT / "model_coldstart.txt"), num_iteration=cold.best_iteration)
    calib = {"model": iso_to_json(main.iso), "model_coldstart": iso_to_json(cold.iso)}
    (OUT / "calibration.json").write_text(json.dumps(calib), encoding="utf-8")
    dfl = defaults()
    splits = load_result("splits")
    schema = {
        "version": VERSION, "exported": time.strftime("%Y-%m-%d %H:%M:%S"), "git_sha": git_sha(),
        "main_variant": main_variant,
        "features": [{"name": c, "dtype": FEATURES[c]["dtype"], "default": dfl.get(c, 0.0)} for c in main.cols],
        "features_coldstart": [{"name": c, "dtype": FEATURES[c]["dtype"], "default": dfl.get(c, 0.0)}
                               for c in cold.cols],
        "ordering": "priority = calibrated P(fail) / (expected duration + 0.001 s), descending",
        "training_data": {"source": "LRTS (ISSTA 2024), 10 Apache projects; 9 Java/Scala + TVM (Python/pytest)",
                          "split": "build-level chronological 70/15/15; model trained on train builds only",
                          "date_ranges": splits["date_range"]},
    }
    (OUT / "schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
    return schema
