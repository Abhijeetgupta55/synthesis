"""`smartci coverage-map`: which test files execute which source lines, measured on the base commit.

Runs the suite once under coverage.py with dynamic contexts (one context per test function) in a worktree of the
base commit. Contexts ('pkg.tests.test_x.TestCls.test_y') are resolved to test files. Output:
.smartci/coverage_map.json = {"base_sha": ..., "tests": [test files], "lines": {source_file: {line: [test idx]}}}.
Used for the `covers_changed_lines` signal, the coverage-first baseline, and to pick mutation sites (mutate.py).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from smartci import history, runner
from smartci.gitdiff import changed_lines, default_base, git


def build(repo: Path, base: str | None = None, pytest_args: list[str] = (), timeout: float = 14400,
          python: str | None = None) -> dict:
    repo = Path(repo).resolve()
    d = history.smartci_dir(repo)
    sha = git(repo, "rev-parse", base or default_base(repo)).strip()
    wt = runner.worktree(repo, "coverage", sha)
    try:
        rc = wt / ".smartci_coveragerc"
        data = wt / ".smartci_coverage"
        rc.write_text("[run]\ndynamic_context = test_function\nrelative_files = True\n"
                      f"data_file = {data.as_posix()}\nsource = .\nomit =\n    */tests/*\n    */test_*.py\n",
                      encoding="utf-8")
        import subprocess
        import sys
        t0 = time.time()
        cmd = [python or sys.executable, "-m", "coverage", "run", f"--rcfile={rc}", "-m", "pytest", "-q",
               "-p", "no:cacheprovider", f"--rootdir={wt}", *pytest_args]
        r = subprocess.run(cmd, cwd=wt, env=runner.env_for(wt), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        elapsed = time.time() - t0
        print(f"smartci coverage-map: suite under coverage {elapsed:.0f}s (exit {r.returncode})", flush=True)
        import coverage
        cd = coverage.CoverageData(basename=str(data))
        cd.read()
        cache: dict = {}
        idx = test_module_index(wt)
        tests: list[str] = []
        tidx: dict[str, int] = {}
        lines: dict[str, dict[str, list[int]]] = {}
        for mf in cd.measured_files():
            rel = Path(mf)
            if rel.is_absolute():
                try:
                    rel = rel.relative_to(wt)
                except ValueError:
                    continue
            rel_s = rel.as_posix()
            by_line = cd.contexts_by_lineno(mf)
            out: dict[str, list[int]] = {}
            for ln, ctxs in by_line.items():
                ids = set()
                for c in ctxs:
                    if not c:
                        continue
                    f = _context_file(idx, c, cache)
                    if f is None:
                        continue
                    if f not in tidx:
                        tidx[f] = len(tests)
                        tests.append(f)
                    ids.add(tidx[f])
                if ids:
                    out[str(ln)] = sorted(ids)
            if out:
                lines[rel_s] = out
    finally:
        runner.remove_worktree(repo, wt)
    res = {"base_sha": sha, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "elapsed_s": elapsed, "tests": tests,
           "lines": lines}
    (d / "coverage_map.json").write_text(json.dumps(res), encoding="utf-8")
    return {"base_sha": sha, "n_source_files": len(lines), "n_test_files": len(tests), "elapsed_s": elapsed}


def test_module_index(wt: Path) -> dict[str, str]:
    """Every dotted-module suffix of every test file -> file. pytest imports a test module under a name that depends
    on rootdir / packages ('test_ops' or 'tests.test_ops' or 'pkg.tests.test_ops'), and coverage's context uses it."""
    idx: dict[str, str] = {}
    for f in wt.rglob("*.py"):
        rel = f.relative_to(wt).as_posix()
        if rel.startswith(".") or "/." in rel:
            continue
        name = f.name
        if not (name.startswith("test_") or name.endswith("_test.py")):
            continue
        parts = rel[:-3].split("/")
        for k in range(len(parts)):
            idx.setdefault(".".join(parts[k:]), rel)
    return idx


def _context_file(idx: dict[str, str], ctx: str, cache: dict) -> str | None:
    """'pkg.tests.test_x.TestCls.test_y' or 'test_x.test_y' -> its test file (longest module prefix known)."""
    if ctx in cache:
        return cache[ctx]
    parts = ctx.split(".")
    found = None
    for k in range(len(parts) - 1, 0, -1):
        found = idx.get(".".join(parts[:k]))
        if found:
            break
    cache[ctx] = found
    return found


def load(repo: Path) -> dict | None:
    f = history.state_dir(repo) / "coverage_map.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def covering_tests(cmap: dict, patch_by_file: dict[str, str]) -> dict[str, int]:
    """test file -> number of changed (new-side) source lines it covers."""
    out: dict[str, int] = {}
    for f, patch in patch_by_file.items():
        m = cmap["lines"].get(f)
        if not m:
            continue
        for ln in changed_lines(patch):
            for t in m.get(str(ln), ()):
                name = cmap["tests"][t]
                out[name] = out.get(name, 0) + 1
    return out
