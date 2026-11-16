"""Real side-by-side pytest runs on NetworkX for the dashboard ('Break the code') and for recordings.

Two git worktrees of external/networkx are put into the same buggy state (a mined bug, a mutant, or the user's own
uncommitted edit) with smartci.compare.prepare. Then two real pytest processes run:
  default  pytest -x in pytest's own order        (records when its first failure is reported)
  smartci  pytest -x --smartci (or --smartci-rule) (ranks, reorders, writes a receipt)
Every output line is captured with the wall-clock time since the process was launched, so the stopwatch includes
Python start-up, imports, collection and (for smartci) scoring. At the end each lane reports:
  queue position  where its first failing test file sat in its own order (out of all test files)
  test time       seconds from the first test's start to the first failure (from the receipt / timing file)
  end-to-end      wall-clock seconds from launch to exit
A recording (all lines with timestamps, both commands, dates, the git state) is saved as JSON.

Modes: 'side-by-side' runs both at once (as in the dashboard; they share the CPU, so both are slower) and
'sequential' runs default, then smartci (accurate timings; used for recordings).
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NX = ROOT / "external" / "networkx"
NX_PY = NX / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
REC_DIR = ROOT / "demo_bundle" / "recordings"


def available() -> bool:
    return NX_PY.exists() and (NX / ".smartci" / "profile.json").exists()


class Lane:
    def __init__(self, name: str, cmd: list[str], cwd: Path, env: dict):
        self.name, self.cmd, self.cwd, self.env = name, cmd, cwd, env
        self.lines: list[tuple[float, str]] = []
        self.q: queue.Queue = queue.Queue()
        self.t0 = self.t_end = None
        self.rc = None
        self.proc = None

    def start(self):
        self.t0 = time.perf_counter()
        self.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.proc = subprocess.Popen(self.cmd, cwd=self.cwd, env=self.env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            self.q.put((time.perf_counter() - self.t0, line.rstrip("\n")))
        self.proc.wait()
        self.rc = self.proc.returncode
        self.t_end = time.perf_counter()
        self.q.put(None)

    def drain(self) -> bool:
        """Move queued lines into self.lines; True once the process has exited and all output is read."""
        done = False
        while True:
            try:
                x = self.q.get_nowait()
            except queue.Empty:
                break
            if x is None:
                done = True
            else:
                self.lines.append(x)
        return done or (self.rc is not None and self.q.empty())

    def elapsed(self) -> float:
        return ((self.t_end or time.perf_counter()) - self.t0) if self.t0 else 0.0


def setup(bug: str, rule: str | None = None, subset: str | None = None):
    """Prepare the two worktrees and lanes (not started). Returns (meta, lanes, context for finish())."""
    from smartci import compare, history, runner
    repo = NX.resolve()
    sdir = history.smartci_dir(repo)
    wts = {"default": runner.worktree(repo, "cmp_default", "HEAD"), "smartci": runner.worktree(repo, "cmp_smartci", "HEAD")}
    meta = {k: compare.prepare(repo, bug, w) for k, w in wts.items()}["default"]
    diff = subprocess.run(["git", "-C", str(wts["default"]), "diff", "--no-color", "HEAD"], capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout
    for f in sdir.glob("timing_*.json"):
        f.unlink()
    base = [str(NX_PY), "-u", "-m", "pytest", "-x", "-p", "no:cacheprovider", "--rootdir=.", "--color=no"]
    extra = [subset] if subset else []
    smart = ["--smartci", "--smartci-base", "HEAD"] + (["--smartci-rule", rule] if rule else [])
    cmds = {"default": base + [f"--smartci-timing={sdir / 'timing_default.json'}"] + extra,
            "smartci": base + smart + extra}
    env = {"SMARTCI_DIR": str(sdir), "PYTHONUNBUFFERED": "1"}
    lanes = {k: Lane(k, cmds[k], wts[k], runner.env_for(wts[k], env)) for k in ("default", "smartci")}
    return {**meta, "diff": diff, "rule": rule, "subset": subset}, lanes, {"repo": repo, "wts": wts, "sdir": sdir}


def finish(meta: dict, lanes: dict[str, Lane], ctx: dict, started: float, mode: str, save: bool = True) -> dict:
    """Read receipts / timing files, compute queue positions, save the recording, remove the worktrees."""
    from smartci import receipts, runner
    sdir, repo = ctx["sdir"], ctx["repo"]
    res = {"bug": meta.get("id") or meta.get("bug") or "working-tree", "kind": meta.get("kind"),
           "title": meta.get("title"), "expected_failing": meta.get("expected"), "rule": meta.get("rule"),
           "subset": meta.get("subset"), "mode": mode, "date": time.strftime("%Y-%m-%d %H:%M:%S"),
           "networkx_head": subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                                           text=True).stdout.strip(), "diff": meta.get("diff", ""), "lanes": {}}
    rec = None
    for f in sorted((sdir / "receipts").glob("*.json"), reverse=True):
        if f.stat().st_mtime < started:
            break
        r = receipts.read(f)
        if Path(r.get("repo", "")).resolve() == ctx["wts"]["smartci"].resolve():
            rec = r
            res["receipt"] = f.name
            break
    timing = sdir / "timing_default.json"
    tim = json.loads(timing.read_text(encoding="utf-8")) if timing.exists() else {}
    files_default = (rec or {}).get("original_order") or []
    files_smart = [x["test_file"] for x in (rec or {}).get("ranking", [])]
    for name, lane in lanes.items():
        ff = (rec if name == "smartci" else tim).get("first_failure") or {}
        f = (ff.get("nodeid") or "").split("::")[0].replace("\\", "/")
        order = files_smart if name == "smartci" else files_default
        failed = [ln for _, ln in lane.lines if ln.startswith(("FAILED ", "ERROR "))]
        res["lanes"][name] = {
            "command": " ".join(Path(c).name if i == 0 else c for i, c in enumerate(lane.cmd)),
            "started_at": getattr(lane, "started_at", None), "returncode": lane.rc,
            "end_to_end_s": lane.elapsed(), "test_time_to_first_failure_s": ff.get("elapsed_s"),
            "first_failure": ff.get("nodeid"), "failed_line": failed[0] if failed else None,
            "queue_position": order.index(f) + 1 if f in order else None, "n_test_files": len(order) or None,
            "lines": [[round(t, 3), ln] for t, ln in lane.lines]}
    if rec:
        from smartci.explain import top_from_receipt
        res["smartci_top10"] = top_from_receipt(rec, 10)
        res["model_variant"] = rec.get("model_variant")
    for w in ctx["wts"].values():
        runner.remove_worktree(repo, w)
    if save:
        REC_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{str(res['bug']).replace('/', '_')[:40]}_{mode}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        (REC_DIR / name).write_text(json.dumps(res), encoding="utf-8")
        res["saved_as"] = f"demo_bundle/recordings/{name}"
    return res


def run(bug: str, mode: str = "sequential", rule: str | None = None, subset: str | None = None,
        on_tick=None, save: bool = True) -> dict:
    """Headless run (recordings, tests). on_tick(lanes) is called about 4x per second."""
    started = time.time()
    meta, lanes, ctx = setup(bug, rule, subset)
    order = [["default", "smartci"]] if mode == "side-by-side" else [["default"], ["smartci"]]
    try:
        for group in order:
            for k in group:
                lanes[k].start()
            while not all(lanes[k].drain() for k in group):
                if on_tick:
                    on_tick(lanes)
                time.sleep(0.25)
    finally:
        for ln in lanes.values():
            if ln.proc and ln.proc.poll() is None:
                from smartci.runner import kill_tree
                kill_tree(ln.proc.pid)
    return finish(meta, lanes, ctx, started, mode, save)


def traceback_of(lines: list) -> str:
    """The failure section pytest prints after -x stops (from the '= FAILURES =' banner to the summary)."""
    text = [ln if isinstance(ln, str) else ln[1] for ln in lines]
    start = next((i for i, x in enumerate(text) if "FAILURES" in x and x.startswith("=")), None)
    if start is None:
        start = next((i for i, x in enumerate(text) if "ERRORS" in x and x.startswith("=")), None)
    return "\n".join(text[start:]) if start is not None else "\n".join(text[-40:])


def main(argv=None) -> int:
    """Record real runs:  python -m stp.demo.live_run --bug <id> [--mode sequential] [--rule changed_files_first]"""
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bug", action="append", help="bug id (fix sha or mutant id); repeatable. Default: 3 seeded "
                    "held-out mined bugs from the backtest")
    ap.add_argument("--mode", choices=["sequential", "side-by-side"], default="sequential")
    ap.add_argument("--rule", default=None)
    ap.add_argument("--subset", default=None)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    if not available():
        print("NetworkX clone or its .smartci profile is missing (see README: setup_demo)")
        return 1
    bugs = a.bug
    if not bugs:
        import random
        bt = json.loads((NX / ".smartci" / "backtest.json").read_text(encoding="utf-8"))
        mined = sorted(b["id"] for b in bt["bugs"] if b["kind"] == "mined")
        bugs = random.Random(a.seed).sample(mined, min(3, len(mined)))
    for bug in bugs:
        print(f"[live_run] {bug} ({a.mode}) ...", flush=True)
        r = run(bug, a.mode, a.rule, a.subset)
        for k, ln in r["lanes"].items():
            print(f"  {k:8s} queue position {ln['queue_position']}/{ln['n_test_files']}  test "
                  f"{ln['test_time_to_first_failure_s']} s  end-to-end {ln['end_to_end_s']:.1f} s  exit {ln['returncode']}")
        print("  saved", r.get("saved_as"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
