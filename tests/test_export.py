"""The exported model (models/global and the packaged copy in smartci/model) must load and score with no LRTS file
present, and the numpy evaluator used by the plugin must agree with lightgbm exactly."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
GLOBAL = ROOT / "models" / "global"


@pytest.mark.skipif(not (GLOBAL / "schema.json").exists(), reason="model not exported yet")
def test_scores_without_lrts(tmp_path):
    d = tmp_path / "model"
    shutil.copytree(GLOBAL, d)
    code = f"""
import json, sys
sys.modules['stp.paths'] = None          # any import of the LRTS path config would fail loudly
from smartci.scoring import GlobalModel
m = GlobalModel(r'{d}')
rows = [{{}} , {{'test_file_in_diff': 1, 'path_prefix_overlap': 1.0, 'name_token_overlap': 3}}]
for which in ('model', 'model_coldstart'):
    p = m.calibrate(m.raw(rows, which), which)
    assert all(0 <= x <= 1 for x in p), p
print(json.dumps({{'ok': True}}))
"""
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True,
                       env={"PATH": "", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
                            "PYTHONPATH": str(ROOT / "src")})
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout.strip().splitlines()[-1])["ok"]


@pytest.mark.skipif(not (GLOBAL / "model.txt").exists(), reason="model not exported yet")
def test_numpy_evaluator_matches_lightgbm():
    import lightgbm as lgb

    from smartci.treemodel import TextModel

    sch = json.loads((GLOBAL / "schema.json").read_text())
    for name, key in (("model", "features"), ("model_coldstart", "features_coldstart")):
        n = len(sch[key])
        rng = np.random.default_rng(0)
        X = rng.random((2000, n)) * rng.choice([0, 1, 10, 1000], size=(2000, n))
        X[rng.random((2000, n)) < 0.5] = 0
        a = TextModel(GLOBAL / f"{name}.txt").predict(X)
        b = lgb.Booster(model_file=str(GLOBAL / f"{name}.txt")).predict(X)
        assert np.abs(a - b).max() < 1e-12


@pytest.mark.skipif(not (GLOBAL / "schema.json").exists(), reason="model not exported yet")
def test_packaged_copy_matches_global():
    pkg = ROOT / "src" / "smartci" / "model"
    for f in ("model.txt", "model_coldstart.txt", "calibration.json", "schema.json"):
        assert (pkg / f).read_bytes() == (GLOBAL / f).read_bytes(), f
