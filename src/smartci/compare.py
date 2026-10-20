"""`smartci compare --bug <fix_sha | mutant_id | working-tree>`: real pytest runs, default order vs smartci.

Two git worktrees are put into the same bug state (a mined bug: the fix commit with its source files restored from
the parent; a mutant: the base commit with the mutation applied; working-tree: a copy of the current uncommitted
diff). Then `pytest -x -p no:cacheprovider` runs in one and `pytest -x -p no:cacheprovider --smartci` in the other.
Both runs carry the plugin in shadow/active mode, so each writes a receipt with the moment its first failure was
reported. Printed: both pytest outputs, the FAILED line, real elapsed seconds.
Modes: sequential (default; accurate timings) or side-by-side (two concurrent processes, for show; CPU contention
inflates both times).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from smartci import history, learn, mutate, receipts, runner
from smartci.gitdiff import git


def prepare(repo: Path, bug: str, wt: Path) -> dict:
    """Put worktree `wt` into the state of `bug`; return metadata (expected failing node ids if known)."""
    bugs = {b["fix_sha"]: b for b in learn.load_bugs(repo)}
    muts = {m["mutant_id"]: m for m in mutate.load_mutants(repo)}
    match = [k for k in bugs if k.startswith(bug)]
    if bug == "working-tree":
        diff = git(repo, "diff", "--binary", "HEAD")
        runner.reset_worktree(wt, git(repo, "rev-parse", "HEAD").strip())
        _apply(wt, diff)
        return {"kind": "working-tree", "expected": None}
    if match:
        b = bugs[match[0]]
        runner.reset_worktree(wt, b["fix_sha"])
        _apply(wt, b["source_diff"])
        return {"kind": "mined", "id": b["fix_sha"], "expected": b["failing_nodeids"], "title": b["subject"]}
    if bug in muts:
        m = muts[bug]
        runner.reset_worktree(wt, m["base_sha"])
        _apply(wt, m["diff"])
        return {"kind": "mutant", "id": bug, "expected": m["failing_nodeids"]}
    raise SystemExit(f"smartci compare: unknown bug '{bug}' (fix sha prefix, mutant id, or 'working-tree')")


def _apply(wt: Path, diff: str) -> None:
    if not diff.strip():
        return
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8", newline="\n") as fh:
        fh.write(diff if diff.endswith("\n") else diff + "\n")
        name = fh.name
    git(wt, "apply", "--whitespace=nowarn", name)
    Path(name).unlink(missing_ok=True)


def _cmd(python: str, smart: bool, extra: list[str], timing: Path) -> list[str]:
    c = [python, "-m", "pytest", "-x", "-p", "no:cacheprovider", "-q"]
    # the default run only records when its first failure appears; it pays no scoring cost
    c += ["--smartci", "--smartci-base", "HEAD"] if smart else [f"--smartci-timing={timing}"]
    return c + extra


FAILED_RE = re.compile(r"^(FAILED|ERROR) .*$", re.M)


def compare(repo: Path, bug: str, mode: str = "sequential", python: str | None = None,
            pytest_args: list[str] = (), timeout: float = 3600) -> dict:
    repo = Path(repo).resolve()
    sdir = history.smartci_dir(repo)
    python = python or sys.executable
    wts = {"default": runner.worktree(repo, "cmp_default", "HEAD"),
           "smartci": runner.worktree(repo, "cmp_smartci", "HEAD")}
    meta = {k: prepare(repo, bug, w) for k, w in wts.items()}["default"]
    res = {"bug": bug, **meta, "mode": mode, "runs": {}}
    env = {"SMARTCI_DIR": str(sdir)}
    try:
        procs = {}
        for name, wt in wts.items():
            cmd = _cmd(python, name == "smartci", list(pytest_args), sdir / f"timing_{name}.json")
            t0 = time.perf_counter()
            if mode == "side-by-side":
                procs[name] = (subprocess.Popen(cmd, cwd=wt, env=runner.env_for(wt, env), stdout=subprocess.PIPE,
                                                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                                errors="replace"), t0, wt)
            else:
                r = subprocess.run(cmd, cwd=wt, env=runner.env_for(wt, env), capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=timeout)
                res["runs"][name] = _summ(r.stdout + r.stderr, r.returncode, time.perf_counter() - t0, repo, wt)
        for name, (p, t0, wt) in procs.items():
            out, _ = p.communicate(timeout=timeout)
            res["runs"][name] = _summ(out, p.returncode, time.perf_counter() - t0, repo, wt)
    finally:
        for wt in wts.values():
            runner.remove_worktree(repo, wt)
    d, s = res["runs"]["default"], res["runs"]["smartci"]
    res["speedup_elapsed"] = d["elapsed_s"] / s["elapsed_s"] if s["elapsed_s"] else None
    out = sdir / "compare"
    out.mkdir(exist_ok=True)
    (out / f"{bug.replace('/', '_')[:60]}_{int(time.time())}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


def _summ(stdout: str, rc: int, elapsed: float, repo: Path, wt: Path) -> dict:
    sdir = history.state_dir(repo)
    rec_path = None
    rec: dict = {}
    timing = sdir / f"timing_{'default' if wt.name == 'cmp_default' else 'smartci'}.json"
    if wt.name == "cmp_default" and timing.exists():
        rec = json.loads(timing.read_text(encoding="utf-8"))
        timing.unlink()
    else:
        for f in sorted((sdir / "receipts").glob("*.json"), reverse=True):
            r = receipts.read(f)
            if Path(r.get("repo", "")) == wt.resolve():
                rec_path, rec = f, r
                break
    ff = rec.get("first_failure") or {}
    m = FAILED_RE.findall(stdout)
    lines = FAILED_RE.search(stdout)
    return {"returncode": rc, "elapsed_s": elapsed, "failed_line": lines.group(0) if lines else None,
            "first_failure_after_s": ff.get("elapsed_s"), "first_failure_nodeid": ff.get("nodeid"),
            "receipt": str(rec_path) if rec_path else None, "stdout_tail": "\n".join(stdout.splitlines()[-25:]),
            "n_failed_lines": len(m)}


def print_result(res: dict) -> None:
    print(f"\n=== smartci compare: {res['kind']} {res.get('id', res['bug'])}  ({res['mode']}) ===")
    for name in ("default", "smartci"):
        r = res["runs"][name]
        print(f"\n--- {name}: pytest -x {'--smartci' if name == 'smartci' else '(default order)'} ---")
        print(r["stdout_tail"])
    print("\n=== result ===")
    for name in ("default", "smartci"):
        r = res["runs"][name]
        ff = "–" if r["first_failure_after_s"] is None else f"{r['first_failure_after_s']:.2f}s"
        print(f"{name:8s} elapsed {r['elapsed_s']:7.2f}s   first failure after {ff}   {r['failed_line'] or 'no failure'}")
    if res["speedup_elapsed"]:
        print(f"elapsed ratio default / smartci = {res['speedup_elapsed']:.2f}x")
    if res["mode"] == "side-by-side":
        print("note: side-by-side runs share the CPU, so both times are inflated; use sequential mode for timing.")
