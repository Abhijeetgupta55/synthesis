"""smartci command line.

  smartci profile        measure the suite twice on the clean base commit (durations, default order, flaky files)
  smartci learn          mine test-backed bug fixes from history; fit the per-repo adapter when there are enough
  smartci backtest       simulated time-to-first-failure on held-out bugs vs simple baselines (receipts + URLs)
  smartci compare        real side-by-side pytest runs for one bug (default order vs --smartci)
  smartci explain        why the top tests are ranked where they are
  plus: rank, record, coverage-map, mutate, report (shadow mode)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _repo(a) -> Path:
    return Path(a.repo).resolve()


def cmd_profile(a):
    from smartci import profile
    p = profile.profile(_repo(a), a.base, a.runs, a.pytest_args, python=a.python)
    print(f"smartci profile: {len(p['durations'])} test files, {p['suite_test_time_s']:.1f} s summed test time, "
          f"{len(p['flaky'])} flaky, {len(p['failing_on_base'])} failing on base; "
          f"start-up overhead ~{min(x for x in p['overhead_s'] if x is not None):.1f} s")


def cmd_coverage(a):
    from smartci import coverage_map
    print(json.dumps(coverage_map.build(_repo(a), a.base, a.pytest_args, python=a.python), indent=1))


def cmd_learn(a):
    from smartci import learn
    s = learn.learn(_repo(a), a.since, a.max, a.timeout, a.python)
    print(json.dumps(s, indent=1))
    from smartci import profile as prof
    if (prof.history.state_dir(_repo(a)) / "profile.json").exists():
        print(json.dumps(learn.rebase(_repo(a), a.timeout, a.python), indent=1))
    print(json.dumps(learn.fit_adapter(_repo(a)), indent=1))


def cmd_mutate(a):
    from smartci import mutate
    print(json.dumps(mutate.generate(_repo(a), a.n, a.seed, a.timeout, a.python, a.max_attempts), indent=1))


def cmd_backtest(a):
    from smartci import backtest
    from smartci.history import state_dir
    backtest.run(_repo(a), a.set)
    print((state_dir(_repo(a)) / "backtest.md").read_text(encoding="utf-8"))


def cmd_compare(a):
    from smartci import compare
    compare.print_result(compare.compare(_repo(a), a.bug, a.mode, a.python, a.pytest_args))


def _collect(repo: Path, python: str | None, args: list[str]) -> list[str]:
    from smartci import runner
    return runner.collect_order(repo, args, python)[1]


def cmd_rank(a):
    from smartci import gitdiff
    from smartci.scoring import score, stable_order
    repo = _repo(a)
    files = _collect(repo, a.python, a.pytest_args)
    diff = gitdiff.compute(repo, a.base)
    sc = score(repo, files, diff.change)
    print(f"change: {len(diff.change.files)} files vs {a.base or gitdiff.default_base(repo)}; model {sc[0].model if sc else '-'}")
    for r, i in enumerate(stable_order(sc)[: a.top], 1):
        s = sc[i]
        print(f"{r:3d}. {s.test_file:60s} p={s.p_fail:.4f}  ~{s.expected_duration:.2f}s")


def cmd_explain(a):
    from smartci import explain
    repo = _repo(a)
    for e in explain.explain(repo, _collect(repo, a.python, a.pytest_args), a.base, a.top):
        print(f"{e['rank']:2d}. {e['test_file']}  (p={e['p_fail']:.3f}, ~{e['expected_duration_s']:.2f}s)")
        for r in e["reasons"]:
            print(f"      - {r}")


def cmd_record(a):
    from smartci import history
    rid = history.record(_repo(a), Path(a.junit), float(a.start), float(a.end or time.time()), a.commit, a.base)
    print(f"smartci: recorded run {rid}")


def cmd_report(a):
    from smartci import shadow
    r = shadow.report(_repo(a))
    print(r.get("message", f"smartci report: {r['n_failing_runs']} failing shadow runs recorded so far"))
    print(json.dumps(r["vs"], indent=1))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="smartci", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="git repository (default: current directory)")
    ap.add_argument("--python", default=None, help="python to run pytest with (default: this interpreter)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        p = sub.add_parser(name, **kw)
        p.set_defaults(fn=fn)
        p.add_argument("pytest_args", nargs="*", help="extra pytest arguments (after --)")
        return p

    p = add("profile", cmd_profile, help="measure the suite on the clean base")
    p.add_argument("--base", default=None)
    p.add_argument("--runs", type=int, default=2)
    p = add("coverage-map", cmd_coverage, help="map test files to covered source lines")
    p.add_argument("--base", default=None)
    p = add("learn", cmd_learn, help="mine test-backed bug fixes")
    p.add_argument("--since", default=None)
    p.add_argument("--max", type=int, default=None)
    p.add_argument("--timeout", type=float, default=600)
    p = add("mutate", cmd_mutate, help="generate killed mutants")
    p.add_argument("--n", type=int, default=300)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("--max-attempts", type=int, default=None)
    p = add("backtest", cmd_backtest, help="simulate held-out bugs")
    p.add_argument("--set", choices=["mined", "mutants", "both"], default="both")
    p = add("compare", cmd_compare, help="real default-vs-smartci pytest runs for one bug")
    p.add_argument("--bug", required=True)
    p.add_argument("--mode", choices=["sequential", "side-by-side"], default="sequential")
    for name, fn in (("rank", cmd_rank), ("explain", cmd_explain)):
        p = add(name, fn, help=f"{name} test files for the current change")
        p.add_argument("--base", default=None)
        p.add_argument("--top", type=int, default=10)
    p = add("record", cmd_record, help="ingest a JUnit XML run into .smartci/history")
    p.add_argument("--junit", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", default=None)
    p.add_argument("--commit", default=None)
    p.add_argument("--base", default=None)
    add("report", cmd_report, help="summarise shadow-mode receipts")
    a = ap.parse_args(argv)
    a.fn(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
