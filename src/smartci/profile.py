"""`smartci profile`: measure the suite on the clean base commit.

Runs the full suite `runs` times (default 2) in a worktree of the base commit with --junitxml. Records:
  durations      mean per-file duration over the runs (seconds, JUnit test times summed per file)
  default_order  pytest's real collection order (files in first-appearance order) and node ids
  flaky          files whose outcome differed between runs  -> excluded from every benchmark
  failing_on_base files that failed in every run on the clean base -> excluded too (they reveal nothing about a change)
  overhead_s     pytest start-up overhead: wall time minus summed test time, per run
Both runs are also recorded as history (they finished before anything we will score).
Output: .smartci/profile.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from smartci import history, runner
from smartci.gitdiff import default_base, git


def profile(repo: Path, base: str | None = None, runs: int = 2, pytest_args: list[str] = (), timeout: float = 7200,
            python: str | None = None) -> dict:
    repo = Path(repo).resolve()
    d = history.smartci_dir(repo)
    base = base or default_base(repo)
    sha = git(repo, "rev-parse", base).strip()
    wt = runner.worktree(repo, "profile", sha)
    try:
        nodeids, order = runner.collect_order(wt, list(pytest_args), python)
        per_run = []
        for k in range(runs):
            junit = d / "profile" / f"run{k}.xml"
            t0 = time.time()
            r = runner.run_pytest(wt, ["-q", *pytest_args], junit=junit, timeout=timeout, python=python)
            t1 = time.time()
            df = history.parse_junit(wt, junit) if junit.exists() else None
            cases = history.junit_cases(junit) if junit.exists() else []
            per_run.append({"start": t0, "end": t1, "elapsed_s": r.elapsed_s, "returncode": r.returncode,
                            "timed_out": r.timed_out, "frame": df, "cases": cases})
            if df is not None:
                history.record(repo, junit, t0, t1, commit=sha, base=sha, changed_files=[],
                               run_id=f"profile-{sha[:8]}-{k}")
            print(f"smartci profile: run {k + 1}/{runs} {r.elapsed_s:.1f}s exit {r.returncode}", flush=True)
    finally:
        runner.remove_worktree(repo, wt)
    frames = [x["frame"] for x in per_run if x["frame"] is not None]
    files = sorted(set().union(*[set(f.test_file) for f in frames])) if frames else []
    dur, outc = {}, {}
    for f in files:
        vals = [fr.set_index("test_file").loc[f] for fr in frames if f in set(fr.test_file)]
        dur[f] = float(np.mean([v.duration_s for v in vals]))
        outc[f] = [bool(v.fail) for v in vals]
    nd: dict[str, list[float]] = {}
    nfail: dict[str, list[bool]] = {}
    for x in per_run:
        for c in x.get("cases", []):
            if c["kind"] == "test":
                nd.setdefault(c["nodeid"], []).append(c["duration_s"])
                nfail.setdefault(c["nodeid"], []).append(c["failed"])
    flaky = sorted(f for f, o in outc.items() if len(set(o)) > 1 or len(o) < len(frames))
    failing = sorted(f for f, o in outc.items() if o and all(o) and len(o) == len(frames))
    out = {"base": base, "base_sha": sha, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "runs": runs,
           "pytest_args": list(pytest_args), "durations": dur, "default_order": order, "nodeids": nodeids,
           "nodeid_durations": {k: float(np.mean(v)) for k, v in nd.items()},
           "flaky_nodeids": sorted(k for k, v in nfail.items() if len(set(v)) > 1),
           "flaky": flaky, "failing_on_base": failing,
           "suite_test_time_s": float(sum(dur.values())),
           "run_elapsed_s": [x["elapsed_s"] for x in per_run],
           "overhead_s": [x["elapsed_s"] - float(x["frame"].duration_s.sum()) if x["frame"] is not None else None
                          for x in per_run]}
    (d / "profile.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def load(repo: Path) -> dict:
    f = history.state_dir(repo) / "profile.json"
    if not f.exists():
        raise SystemExit("smartci: no profile yet. Run `smartci profile` first.")
    return json.loads(f.read_text(encoding="utf-8"))
