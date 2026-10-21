"""Run real pytest in isolated git worktrees.

Every command that changes code (profile on the base commit, learn's reintroduced bugs, mutants, compare) works in
a worktree under .smartci/worktrees/, never in the user's checkout. PYTHONPATH is pinned to the worktree so that an
editable install of the package under test cannot silently import the *main* checkout's code instead.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from smartci.gitdiff import git


@dataclass
class PytestRun:
    returncode: int
    elapsed_s: float
    stdout: str
    junit: Path | None
    timed_out: bool = False


def worktree(repo: Path, name: str, commit: str) -> Path:
    """(Re)create a detached worktree of `commit` at .smartci/worktrees/<name>."""
    repo = Path(repo).resolve()
    wt = repo / ".smartci" / "worktrees" / name
    if wt.exists():
        git(repo, "worktree", "remove", "--force", str(wt), check=False)
        shutil.rmtree(wt, ignore_errors=True)
    git(repo, "worktree", "prune")
    wt.parent.mkdir(parents=True, exist_ok=True)
    git(repo, "worktree", "add", "--detach", "--force", str(wt), commit)
    return wt


def remove_worktree(repo: Path, wt: Path) -> None:
    git(Path(repo), "worktree", "remove", "--force", str(wt), check=False)
    shutil.rmtree(wt, ignore_errors=True)
    git(Path(repo), "worktree", "prune", check=False)


def reset_worktree(wt: Path, commit: str) -> None:
    git(wt, "checkout", "--force", "--detach", commit)
    git(wt, "clean", "-fdq", "-e", ".smartci")


def env_for(wt: Path, extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(wt) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    env.pop("SMARTCI", None)
    env.update(extra or {})
    return env


def run_pytest(wt: Path, args: list[str], junit: Path | None = None, timeout: float | None = None,
               python: str | None = None, env_extra: dict | None = None) -> PytestRun:
    cmd = [python or sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args]
    if junit is not None:
        junit.parent.mkdir(parents=True, exist_ok=True)
        cmd += [f"--junitxml={junit}", "-o", "junit_family=xunit1"]
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, cwd=wt, env=env_for(wt, env_extra), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace")
    try:
        out, _ = p.communicate(timeout=timeout)
        return PytestRun(p.returncode, time.perf_counter() - t0, out, junit)
    except subprocess.TimeoutExpired:
        kill_tree(p.pid)
        out, _ = p.communicate()
        return PytestRun(-9, time.perf_counter() - t0, out or "", junit, timed_out=True)


def kill_tree(pid: int) -> None:
    """Kill a process and all its children. On Windows a venv's python.exe is a launcher that starts the real
    interpreter as a child; killing only the launcher would leave the test run alive (and holding memory)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
    else:
        import signal
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGKILL)


def collect_order(wt: Path, args: list[str] = (), python: str | None = None) -> tuple[list[str], list[str]]:
    """pytest's real default order: (node ids, test files in first-appearance order)."""
    r = run_pytest(wt, ["--collect-only", "-q", *args], python=python)
    nodeids = [ln.strip() for ln in r.stdout.splitlines() if "::" in ln and not ln.startswith(("=", " "))]
    files: list[str] = []
    seen = set()
    for n in nodeids:
        f = n.split("::", 1)[0].replace("\\", "/")
        if f not in seen:
            seen.add(f)
            files.append(f)
    return nodeids, files
