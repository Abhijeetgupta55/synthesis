"""`smartci evaluate`: one command that answers "should my team use smartci, a simple rule, or nothing?"

Steps (each reuses an existing command; finished steps are reused unless --fresh):
  1. profile   run the suite twice on the clean base: durations, pytest's order, flaky tests
  2. learn     mine past test-backed bug fixes, reproduce them, rebase them onto today's code, fit the adapter
  3. mutate    optional (--mutants N): seed N synthetic bugs that existing tests catch
  4. backtest  replay every held-out bug under pytest's order, simple rules and smartci (measured durations)
Then it prints a verdict card and writes it to .smartci/verdict.md.

The verdict is decided by the numbers only: smartci is recommended when it wins more bugs than it loses against the
best simple rule *and* its median time to the first failure is not worse; otherwise the best simple rule is.
With fewer than MIN_BUGS bugs the card says the evidence is too thin.
"""
from __future__ import annotations

import json
from pathlib import Path

MIN_BUGS = 10


def verdict(bt: dict) -> dict:
    s = bt["summary"].get("all") or next(iter(bt["summary"].values()))
    best = s["best_simple_baseline"]
    med = {k: v["median"] for k, v in s["median_ttff_s"].items()}
    w = s["vs_smartci"].get(best, {"win": 0, "tie": 0, "loss": 0})
    n = s["n"]
    if n < MIN_BUGS:
        choice, why = "not enough evidence", f"only {n} reproducible bugs (need {MIN_BUGS}); add `--mutants 100`"
    elif w["win"] > w["loss"] and med["smartci"] <= med[best]:
        choice, why = "smartci", f"smartci wins {w['win']} bugs and loses {w['loss']} against {best}"
    else:
        choice, why = best, (f"{best} is as good or better here (smartci wins {w['win']}, ties {w['tie']}, loses "
                             f"{w['loss']}); a simple rule is easier to run")
    speedup = med["default"] / med[choice] if choice in med and med[choice] > 0 else None
    ov = [x for x in (bt.get("profile_overhead_s") or []) if x is not None]
    return {"n_bugs": n, "best_simple_rule": best, "median_s": med, "vs_best": {k: w[k] for k in ("win", "tie", "loss")},
            "recommendation": choice, "why": why, "speedup_vs_default": speedup,
            "suite_test_time_s": bt["suite_test_time_s"], "n_test_files": bt["n_test_files"],
            "startup_s": min(ov) if ov else None}


def card(v: dict, repo: Path) -> str:
    med = v["median_s"]
    lines = [f"# smartci verdict for {repo.name}", "",
             f"Suite: {v['n_test_files']} test files, {v['suite_test_time_s']:.0f} s of test time. "
             f"Evidence: {v['n_bugs']} reproducible bugs replayed with measured durations.", "",
             "Median seconds until the first failing test is reported:", ""]
    for k in ("default", v["best_simple_rule"], "smartci"):
        lines.append(f"  {('pytest default order' if k == 'default' else k):28s} {med.get(k, float('nan')):9.2f} s")
    lines += ["", f"smartci vs {v['best_simple_rule']}: {v['vs_best']['win']} wins / {v['vs_best']['tie']} ties / "
                  f"{v['vs_best']['loss']} losses", "",
              f"RECOMMENDATION: {v['recommendation']}  ({v['why']})"]
    if v["recommendation"] in med:
        su = v.get("startup_s")
        lines.append(f"Expected: the first failure after about {med[v['recommendation']]:.2f} s of test time instead "
                     f"of {med['default']:.2f} s." + (f" pytest's own start-up and collection (measured {su:.0f} s) "
                                                     "comes on top for every order." if su else ""))
    rec = v["recommendation"]
    if rec == "smartci":
        use = "pytest --smartci"
    elif rec == "not enough evidence":
        use = "collect more evidence first"
    elif rec in ("changed_files_first", "fastest_first", "coverage_first", "recently_failed_first"):
        use = f"pytest --smartci --smartci-rule {rec}"
    else:
        use = "keep pytest's order"
    lines += [f"How to use it: {use}", "", "Nothing is ever skipped: every option only changes the order."]
    return "\n".join(lines)


def evaluate(repo: Path, since: str | None = None, max_bugs: int | None = None, mutants: int = 0,
             fresh: bool = False, python: str | None = None, timeout: float = 600, log=print) -> dict:
    from smartci import backtest, learn, mutate, profile
    from smartci.history import state_dir

    repo = Path(repo).resolve()
    sd = state_dir(repo)
    if fresh or not (sd / "profile.json").exists():
        log("[1/4] profile: running the suite twice ...")
        profile.profile(repo, None, 2, [], python=python)
    else:
        log("[1/4] profile: reusing .smartci/profile.json")
    if fresh or not (sd / "bugs.jsonl").exists():
        log("[2/4] learn: mining past bug fixes ...")
        learn.learn(repo, since, max_bugs, timeout, python)
        learn.rebase(repo, timeout, python)
    else:
        log("[2/4] learn: reusing .smartci/bugs.jsonl")
    learn.fit_adapter(repo)
    if mutants and (fresh or not (sd / "mutants.jsonl").exists()):
        log(f"[3/4] mutate: seeding {mutants} synthetic bugs ...")
        mutate.generate(repo, mutants, 42, 300, python, None)
    else:
        log("[3/4] mutate: " + ("reusing .smartci/mutants.jsonl" if (sd / "mutants.jsonl").exists() else "skipped"))
    log("[4/4] backtest: replaying every held-out bug ...")
    bt = backtest.run(repo, "both")
    bt["profile_overhead_s"] = json.loads((sd / "profile.json").read_text(encoding="utf-8")).get("overhead_s")
    v = verdict(bt)
    text = card(v, repo)
    (sd / "verdict.md").write_text(text + "\n", encoding="utf-8")
    (sd / "verdict.json").write_text(json.dumps(v, indent=1), encoding="utf-8")
    log("")
    log(text)
    return v
