"""smartci: diff parsing, LRTS/smartci feature parity, plugin ordering + receipts, and the profile -> learn ->
backtest -> compare harness on a tiny fixture repo created in a temp dir."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from smartci import gitdiff, history, receipts
from smartci.gitdiff import changed_lines, parse_unified
from stp.features.change import Change, bm25_scores, change_features
from stp.features.cofail import RunRecord, cofail_features
from stp.features.history import Event, history_features
from tests.smartci_fixture import make_model, make_repo, sh

DIFF = """diff --git a/pkg/a.py b/pkg/a.py
index 1..2 100644
--- a/pkg/a.py
+++ b/pkg/a.py
@@ -1,3 +1,4 @@
 x = 1
-y = 2
+y = 3
+z = 4
 w = 5
diff --git a/old/name.py b/new/name.py
similarity index 90%
rename from old/name.py
rename to new/name.py
diff --git a/img.png b/img.png
Binary files a/img.png and b/img.png differ
diff --git a/gone.py b/gone.py
deleted file mode 100644
--- a/gone.py
+++ /dev/null
@@ -1 +0,0 @@
-print(1)
"""


def test_parse_unified_handles_renames_binary_deletes():
    recs = {r["path"]: r for r in parse_unified(DIFF)}
    assert recs["pkg/a.py"]["added"] == 2 and recs["pkg/a.py"]["deleted"] == 1
    assert recs["new/name.py"]["old_path"] == "old/name.py"
    assert recs["img.png"]["binary"] and recs["img.png"]["patch"] == ""
    assert "gone.py" in recs and recs["gone.py"]["deleted"] == 1
    assert changed_lines(recs["pkg/a.py"]["patch"]) == {2, 3}


def test_feature_parity_lrts_vs_smartci_on_same_inputs(tmp_path):
    """The LRTS store and smartci call the same pure functions; same inputs must give the same values."""
    evs = [Event(0, 0.0, 10.0, "default", True, 1.5), Event(1, 20.0, 30.0, "default", False, 2.5)]
    ch = Change(files=["calc/ops.py"], additions=1, deletions=1, token_counts={"ops": 2, "sub": 1})
    recs = [RunRecord(0, 10.0, frozenset({"calc/ops.py"}), frozenset({"tests/test_ops.py"})),
            RunRecord(1, 30.0, frozenset({"calc/stats.py"}), frozenset())]
    # smartci path: the history object built from a recorded .smartci history
    repo = tmp_path / "r"
    (repo / ".git" / "info").mkdir(parents=True)
    d = history.smartci_dir(repo)
    rows = [{"run_id": f"r{i}", "start_ts": e.start, "end_ts": e.end, "stage": "default",
             "test_file": "tests/test_ops.py", "duration_s": e.duration, "fail": e.fail} for i, e in enumerate(evs)]
    (d / "history.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    runs = [{"run_id": "r0", "start_ts": 0.0, "end_ts": 10.0, "commit": "", "base": "", "files": ["calc/ops.py"]},
            {"run_id": "r1", "start_ts": 20.0, "end_ts": 30.0, "commit": "", "base": "", "files": ["calc/stats.py"]}]
    (d / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in runs))
    got = history.History(repo).features(["tests/test_ops.py"], ch.files, t=35.0)[0]
    ref = history_features(evs, 35.0, "default")
    for k, v in ref.items():
        if not k.startswith("_"):
            assert got[k] == v, k
    ref_c = cofail_features("tests/test_ops.py", ch.files, recs, 35.0)
    for k, v in ref_c.items():
        assert got[k] == v, k
    cf = change_features("tests/test_ops.py", ch)
    assert cf["name_token_overlap"] == 1 and cf["path_prefix_overlap"] == 0.0
    assert bm25_scores(["tests/test_ops.py", "tests/test_stats.py"], ch)[0] > 0


@pytest.fixture(scope="module")
def fx(tmp_path_factory):
    root = tmp_path_factory.mktemp("smartci")
    info = make_repo(root)
    model = make_model(root / "model")
    import os
    os.environ["SMARTCI_MODEL_DIR"] = str(model)
    yield info
    os.environ.pop("SMARTCI_MODEL_DIR", None)


def _pytest(repo: Path, *args: str, env_extra=None) -> subprocess.CompletedProcess:
    import os
    env = dict(os.environ, PYTHONPATH=str(repo), **(env_extra or {}))
    return subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args], cwd=repo, env=env,
                          capture_output=True, text=True)


def test_plugin_inactive_by_default(fx):
    r = _pytest(fx["repo"], "-q")
    assert "smartci:" not in r.stdout and r.returncode == 0


def test_plugin_reorders_stably_and_writes_valid_receipt(fx):
    repo = fx["repo"]
    (repo / "calc" / "ops.py").write_text((repo / "calc" / "ops.py").read_text().replace("return a - b", "return b - a"))
    try:
        r = _pytest(repo, "-v", "--smartci", "--smartci-base", "HEAD")
        assert "smartci: 3 test files ranked" in r.stdout, r.stdout
        order = [ln.split("::")[0] for ln in r.stdout.splitlines()
                 if ln.startswith("tests/") and ("PASSED" in ln or "FAILED" in ln)]
        files = list(dict.fromkeys(order))
        assert sorted(files) == ["tests/test_misc.py", "tests/test_ops.py", "tests/test_stats.py"]  # nothing skipped
        assert files[0] == "tests/test_ops.py"           # the file related to the change runs first
        assert len(order) == 6                           # every test ran
        # within a file pytest's order is kept
        ops = [ln.split("::")[1].split()[0] for ln in r.stdout.splitlines() if ln.startswith("tests/test_ops.py::")]
        assert ops == ["test_add", "test_clamp", "test_sub"]
        rec = receipts.read(receipts.latest(repo))
        assert receipts.validate(rec) == []
        assert rec["first_failure"]["nodeid"] == "tests/test_ops.py::test_sub"
        assert rec["results"]["tests/test_ops.py"]["outcome"] == "failed"
    finally:
        sh(repo, "checkout", "--", "calc/ops.py")


def test_profile_learn_backtest_compare(fx):
    from smartci import backtest, compare, learn, profile

    repo = fx["repo"]
    p = profile.profile(repo, runs=2)
    assert p["default_order"] == ["tests/test_misc.py", "tests/test_ops.py", "tests/test_stats.py"]
    assert p["durations"]["tests/test_misc.py"] > 0.5 and not p["flaky"]
    s = learn.learn(repo, max_n=5)
    assert s["n_kept"] == 1, s
    bug = learn.load_bugs(repo)[0]
    assert bug["fix_sha"] == fx["fix_sha"] and bug["failing_nodeids"] == ["tests/test_ops.py::test_sub"]
    assert "calc/ops.py" in bug["source_files"]
    assert not (history.state_dir(repo) / "adapter.json").exists()     # < 20 bugs: no adapter
    bt = backtest.run(repo, "mined")
    row = bt["bugs"][0]
    # default order runs test_misc (0.6 s) first; smartci should put test_ops first
    assert row["ttff_s"]["smartci"] < row["ttff_s"]["default"]
    assert row["ttff_s"]["fastest_first"] >= 0
    assert (history.state_dir(repo) / "backtest.md").exists()
    res = compare.compare(repo, fx["fix_sha"][:10])
    d, sm = res["runs"]["default"], res["runs"]["smartci"]
    assert d["failed_line"] and sm["failed_line"] and "test_sub" in sm["failed_line"]
    assert sm["first_failure_after_s"] < d["first_failure_after_s"]
    # simulation vs reality, GATE 5 rule: |real - simulated| <= 10% of simulated + measured pytest overhead
    ovh = min(x for x in p["overhead_s"] if x is not None)
    assert abs(sm["first_failure_after_s"] - row["ttff_s"]["smartci"]) <= 0.1 * row["ttff_s"]["smartci"] + ovh
    assert abs(d["first_failure_after_s"] - row["ttff_s"]["default"]) <= 0.1 * row["ttff_s"]["default"] + ovh
    # worktrees cleaned up, user's checkout untouched
    assert not any((repo / ".smartci" / "worktrees").glob("*")) if (repo / ".smartci" / "worktrees").exists() else True
    assert sh(repo, "status", "--porcelain").strip() == ""


def test_mutate_on_fixture(fx):
    from smartci import coverage_map, mutate

    repo = fx["repo"]
    cm = coverage_map.build(repo)
    assert cm["n_source_files"] >= 2
    out = mutate.generate(repo, n=3, seed=1, timeout=60, max_attempts=30)
    muts = mutate.load_mutants(repo)
    assert out["kept"] == len(muts) >= 1
    m = muts[0]
    assert m["failing_nodeids"] and m["diff"].startswith("diff --git")
    _ = time
    _ = np
    _ = gitdiff


def test_mutation_operators():
    from smartci.mutate import apply, sites
    src = "def f(x):\n    if x > 1 and x < 5:\n        return x + 1\n    return 0\n"
    ops = {s[4] for s in sites(src, {2, 3, 4})}
    assert ops == {"compare", "boolop", "constant", "return", "arith", "negate"}
    neg = [apply(src, s) for s in sites(src, {2}) if s[4] == "negate"][0]
    assert "if not (x > 1 and x < 5):" in neg
