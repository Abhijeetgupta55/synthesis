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
            timing = d / "profile" / f"run{k}_timing.json"
            t0 = time.time()
            r = runner.run_pytest(wt, ["-q", f"--smartci-timing={timing}", *pytest_args], junit=junit,
                                  timeout=timeout, python=python)
            t1 = time.time()
            df = history.parse_junit(wt, junit) if junit.exists() else None
            cases = history.junit_cases(junit) if junit.exists() else []
            tm = json.loads(timing.read_text(encoding="utf-8")) if timing.exists() else {}
            n_tests = sum(1 for c in cases if c["kind"] == "test")
            test_wall = (tm["end"] - tm["first_test_start"]) if tm.get("first_test_start") else None
            sum_dur = sum(c["duration_s"] for c in cases if c["kind"] == "test")
            per_test = (test_wall - sum_dur) / n_tests if test_wall and n_tests else None
            per_run.append({"start": t0, "end": t1, "elapsed_s": r.elapsed_s, "returncode": r.returncode,
                            "timed_out": r.timed_out, "frame": df, "cases": cases, "test_wall_s": test_wall,
                            "per_test_overhead_s": per_test})
            if df is not None:
                history.record(repo, junit, t0, t1, commit=sha, base=sha, changed_files=[],
                               run_id=f"profile-{sha[:8]}-{k}")
            print(f"smartci profile: run {k + 1}/{runs} {r.elapsed_s:.1f}s exit {r.returncode}", flush=True)
    finally:
        runner.remove_worktree(repo, wt)
    frames = [{x["test_file"]: x for x in r["frame"]} for r in per_run if r["frame"] is not None]
    files = sorted(set().union(*[set(f) for f in frames])) if frames else []
    dur, outc = {}, {}
    for f in files:
        vals = [fr[f] for fr in frames if f in fr]
        dur[f] = float(np.mean([v["duration_s"] for v in vals]))
        outc[f] = [bool(v["fail"]) for v in vals]
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
           # per-test framework cost (hooks, reporting) between tests, not inside JUnit durations: the simulator
           # adds it once per executed test (GATE 5 showed it matters: ~10 ms x thousands of tests)
           "test_phase_wall_s": [x["test_wall_s"] for x in per_run],
           "per_test_overhead_s": float(np.median([x["per_test_overhead_s"] for x in per_run
                                                   if x["per_test_overhead_s"] is not None] or [0.0])),
           "overhead_s": [x["elapsed_s"] - sum(v["duration_s"] for v in x["frame"]) if x["frame"] is not None
                          else None for x in per_run]}
    (d / "profile.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def load(repo: Path) -> dict:
    f = history.state_dir(repo) / "profile.json"
    if not f.exists():
        raise SystemExit("smartci: no profile yet. Run `smartci profile` first.")
    return json.loads(f.read_text(encoding="utf-8"))
