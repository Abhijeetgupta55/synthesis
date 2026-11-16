"""The app's 'Predict live' page and the smartci command line give the same scores for the same input.

Needs only the committed demo_bundle (no LRTS data, no NetworkX clone).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from stp.demo import live

CASES = [["networkx/algorithms/flow/maxflow.py"],
         ["networkx/algorithms/shortest_paths/weighted.py", "networkx/classes/graph.py"]]

pytestmark = pytest.mark.skipif(not (live.LIVE / "live_meta.json").exists(), reason="demo_bundle/live not built")


@pytest.mark.parametrize("files", CASES)
def test_app_scores_equal_cli(files):
    app = live.live_rank(files)
    env = {k: v for k, v in os.environ.items() if k != "SMARTCI_DIR"}
    cmd = [sys.executable, "-m", "smartci.cli", "--repo", str(live.LIVE), "rank", "--files", *files,
           "--at", repr(live.meta()["as_of"]), "--json"]
    out = subprocess.run(cmd, capture_output=True, text=True, env=env, check=True, cwd=live.ROOT)
    cli = json.loads(out.stdout.strip().splitlines()[-1])
    assert [r["test_file"] for r in app] == [r["test_file"] for r in cli]
    for a, c in zip(app, cli):
        assert a["p_fail"] == pytest.approx(c["p_fail"], rel=1e-12, abs=1e-15)
        assert a["priority"] == pytest.approx(c["priority"], rel=1e-12, abs=1e-15)
    assert len(app) > 0


def test_change_related_tests_rank_high():
    rows = live.live_rank(["networkx/algorithms/flow/maxflow.py"])
    top = [r["test_file"] for r in rows[:3]]
    assert any("flow/tests/" in t for t in top), top
    assert all(r["reasons"] for r in rows[:10])
