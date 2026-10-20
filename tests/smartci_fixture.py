"""Helpers for the smartci tests: a tiny git repo with a test-backed bug fix, and a tiny model in export format."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

OPS_GOOD = '''def add(a, b):
    return a + b


def sub(a, b):
    return a - b


def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
'''
OPS_BUG = OPS_GOOD.replace("    return a - b", "    return b - a")
STATS = '''def mean(xs):
    return sum(xs) / len(xs)


def total(xs):
    s = 0
    for x in xs:
        s = s + x
    return s
'''
TEST_OPS_V1 = '''from calc.ops import add, clamp


def test_add():
    assert add(2, 3) == 5


def test_clamp():
    assert clamp(5, 0, 3) == 3
    assert clamp(-1, 0, 3) == 0
'''
TEST_OPS_V2 = TEST_OPS_V1.replace("from calc.ops import add, clamp", "from calc.ops import add, clamp, sub") + '''

def test_sub():
    assert sub(5, 3) == 2
'''
TEST_STATS = '''import time

from calc.stats import mean, total


def test_mean():
    time.sleep(0.3)
    assert mean([1, 2, 3]) == 2


def test_total():
    assert total([1, 2, 3]) == 6
'''
TEST_MISC = '''import time


def test_slow_unrelated():
    time.sleep(0.6)
    assert True
'''


def sh(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def make_repo(root: Path) -> dict:
    repo = root / "fixture_repo"
    (repo / "calc").mkdir(parents=True)
    (repo / "tests").mkdir()
    sh(root, "init", "-q", "-b", "main", str(repo))
    sh(repo, "config", "user.email", "t@example.com")
    sh(repo, "config", "user.name", "t")
    (repo / "calc" / "__init__.py").write_text("")
    (repo / "calc" / "ops.py").write_text(OPS_BUG)
    (repo / "calc" / "stats.py").write_text(STATS)
    (repo / "tests" / "test_misc.py").write_text(TEST_MISC)
    (repo / "tests" / "test_ops.py").write_text(TEST_OPS_V1)
    (repo / "tests" / "test_stats.py").write_text(TEST_STATS)
    (repo / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-qm", "initial calc package")
    (repo / "calc" / "ops.py").write_text(OPS_GOOD)
    (repo / "tests" / "test_ops.py").write_text(TEST_OPS_V2)
    sh(repo, "add", "-A")
    sh(repo, "commit", "-qm", "Fix sub argument order (bug #12)")
    fix = sh(repo, "rev-parse", "HEAD").strip()
    (repo / "README.md").write_text("calc\n")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-qm", "docs")
    return {"repo": repo, "fix_sha": fix}


def make_model(d: Path) -> Path:
    """A tiny LightGBM in export format: risk rises with test_file_in_diff / path overlap / recent failures."""
    import lightgbm as lgb

    from stp.features.schema import FEATURES, feature_names
    from stp.models.prep import defaults

    d.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    cols = feature_names(scope="h")
    cold = feature_names(["cost", "change"], "h")
    dfl = defaults()
    for name, cs in (("model", cols), ("model_coldstart", cold)):
        n = 4000
        X = rng.random((n, len(cs))).astype(np.float32)
        j = {c: i for i, c in enumerate(cs)}
        z = -4 + 3 * X[:, j["path_prefix_overlap"]] + 2 * X[:, j["name_token_overlap"]]
        if "h_fails_last_7d" in j:
            z += 2 * X[:, j["h_fails_last_7d"]]
        y = rng.random(n) < 1 / (1 + np.exp(-z))
        b = lgb.train({"objective": "binary", "verbosity": -1, "num_leaves": 7}, lgb.Dataset(X, y), 30)
        b.save_model(str(d / f"{name}.txt"))
    (d / "calibration.json").write_text(json.dumps({k: {"x": [0.0, 1.0], "y": [0.0, 1.0]}
                                                    for k in ("model", "model_coldstart")}))
    sch = {"version": "test", "features": [{"name": c, "dtype": FEATURES[c]["dtype"], "default": dfl[c]} for c in cols],
           "features_coldstart": [{"name": c, "dtype": FEATURES[c]["dtype"], "default": dfl[c]} for c in cold]}
    (d / "schema.json").write_text(json.dumps(sch))
    return d
