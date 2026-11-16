"""Generate reports/REAL_WORLD.md and reports/results/real_world.json from the repos' .smartci/ outputs.

Usage: python -m stp.reports.real_world_md
"""
from __future__ import annotations

import json
from pathlib import Path

from stp import paths
from stp.reports.fmt import table
from stp.results import save_result

REPOS = {"networkx": paths.ROOT / "external" / "networkx"}  # a second repo (sympy) was attempted, not completed
CAVEATS = [
    "**Mined bugs are reintroduced known bugs.** The revealing test usually arrived with the fix, so this measures "
    "*regression catching*: would the tests that guard a past fix have been run early?",
    "**The mined diff is the reverse of the fix** (only the non-test source files are restored), an approximation of "
    "the original buggy change.",
    "**Selection bias toward test-backed fixes**: only commits whose message says fix/bug/regression/issue and that "
    "touch both source and tests are candidates, and only reproducible ones are kept.",
    "**Mutants are synthetic** single-point changes; sites are drawn from covered lines, which favours the "
    "coverage-first baseline.",
    "The NetworkX mutant set (seed 42) contains **no negated-condition mutants**: that operator had a bug, found and "
    "fixed after the set was generated; the set was not regenerated so the logged seed still reproduces it.",
    "**The global model was trained on Apache CI data** (9 Java/Scala projects + TVM's Python suites), never on these "
    "repositories.",
    "**Short suites mean small absolute savings**; smartci's own start-up cost (imports, git diff, scoring) is paid on "
    "every run and is reported below. The value grows with suite length.",
    "Times in the backtest are *simulated* sums of profiled durations; GATE 5 checks them against real pytest runs.",
]


def _read(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def repo_section(name: str, repo: Path) -> tuple[str, dict]:
    sd = repo / ".smartci"
    bt, ls, pr = _read(sd / "backtest.json"), _read(sd / "learn_summary.json"), _read(sd / "profile.json")
    g5 = _read(paths.RESULTS / f"gate5_{repo.name}.json")
    ad = _read(sd / "adapter.json")
    head = ""
    try:
        import subprocess
        head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        pass
    n_mut = sum(1 for _ in open(sd / "mutants.jsonl", encoding="utf-8")) if (sd / "mutants.jsonl").exists() else 0
    summary = {"pinned_sha": head, "learn": ls, "n_mutants": n_mut, "adapter": ad,
               "backtest_summary": bt["summary"] if bt else None, "gate5": g5,
               "profile": {k: pr[k] for k in ("suite_test_time_s", "run_elapsed_s", "overhead_s", "flaky",
                                              "failing_on_base")} if pr else None}
    s = [f"## {name}", "", f"Pinned commit `{head[:12]}`. "]
    if pr:
        s.append(f"Profile: {len(pr['durations'])} test files, {pr['suite_test_time_s']:.0f} s summed test time, "
                 f"full runs took {', '.join(f'{x:.0f}' for x in pr['run_elapsed_s'])} s; pytest start-up overhead "
                 f"{min(x for x in pr['overhead_s'] if x is not None):.1f} s; flaky files {len(pr['flaky'])}, failing on "
                 f"base {len(pr['failing_on_base'])}.")
    if ls:
        s.append("")
        s.append(f"Mined bugs: {ls['n_candidates']} candidate fix commits → **{ls['n_kept']} reproducible bugs**; "
                 f"excluded {ls['n_excluded']} ({', '.join(f'{k} {v}' for k, v in ls['exclusions'].items())}); "
                 f"{ls['could_not_run_in_current_env']} could not run in the current pinned environment.")
    s.append(f"Mutants kept (killed by ≥ 1 existing test): {n_mut}.")
    if ad:
        s.append("Per-repo adapter: " + (f"fitted on {ad['n_adapt_bugs']} older bugs, evaluated on the newer "
                                         f"{ad['n_eval_bugs']}" if ad.get("fitted") else f"not fitted ({ad.get('reason')})")
                 + ".")
    s.append("")
    if bt:
        for kind, v in bt["summary"].items():
            s.append(f"### Backtest: {kind} (n = {v['n']})")
            s.append("")
            rows = []
            for m, x in sorted(v["median_ttff_s"].items(), key=lambda kv: kv[1]["median"]):
                w = v["vs_smartci"].get(m)
                rows.append([m, f"{x['median']:.2f} [{x['lo']:.2f}, {x['hi']:.2f}]", f"{v['mean_apfdc'][m]:.3f}",
                             "–" if not w else f"{w['win']}/{w['tie']}/{w['loss']}",
                             "–" if not w else f"{w['median_time_ratio_smartci_over_baseline']:.2f} "
                                               f"[{w['ratio_ci'][0]:.2f}, {w['ratio_ci'][1]:.2f}]"])
            s.append(table(["Ordering", "Median s to 1st failure [95% CI]", "Mean APFDc", "smartci W/T/L",
                            "smartci ÷ baseline (median) [CI]"], rows))
            s.append("")
            s.append(f"Best simple baseline: **{v['best_simple_baseline']}**. {v['recommendation']}")
            loss = v["vs_smartci"].get(v["best_simple_baseline"], {}).get("losses", [])
            if loss:
                s.append(f"Losses vs {v['best_simple_baseline']} ({len(loss)}): " + ", ".join(x[:12] for x in loss))
            s.append("")
        s.append(f"Every bug with its commit link: `{repo.relative_to(paths.ROOT).as_posix()}/.smartci/backtest.md` "
                 "(also in `demo_bundle/repos/`).")
        s.append("")
    if g5:
        rows = [[r["kind"], r["id"][:14], f"{r['default_sim_s']:.2f}", "–" if r["default_real_s"] is None else
                 f"{r['default_real_s']:.2f}", f"{r['smartci_sim_s']:.2f}",
                 "–" if r["smartci_real_s"] is None else f"{r['smartci_real_s']:.2f}",
                 "✔" if r["default_pass"] and r["smartci_pass"] else "✘",
                 "–" if r.get("smartci_elapsed_s") is None else f"{r['default_elapsed_s']:.1f} / {r['smartci_elapsed_s']:.1f}"]
                for r in g5["runs"]]
        s += [f"### Simulation vs real pytest (GATE 5, seed {g5['seed']})", "",
              table(["Kind", "Bug", "default sim s", "default real s", "smartci sim s", "smartci real s", "pass",
                     "end-to-end s (default / smartci)"], rows), "",
              *([f"**Conditions:** {g5['conditions']}", ""] if g5.get("conditions") else []),
              f"Rule: {g5['rule']}; measured overhead {g5['measured_overhead_s']:.2f} s. "
              f"**GATE 5: {'PASS' if g5['gate5_pass'] else 'FAIL'}** ({g5['n_pass']}/{g5['n_checks']} checks). "
              "End-to-end seconds include pytest start-up and smartci's scoring cost.", ""]
    return "\n".join(s), summary


def main() -> None:
    parts, js = [], {}
    for name, repo in REPOS.items():
        if (repo / ".smartci").exists():
            t, j = repo_section(name, repo)
            parts.append(t)
            js[name] = j
    text = ["# REAL_WORLD", "", "Generated by `python -m stp.reports.real_world_md` from each repository's `.smartci/` "
            "outputs and `reports/results/gate5_*.json`. Do not edit by hand.", "",
            "smartci never skips a test; it only reorders test files. Every number below comes from real pytest runs "
            "of the repository (durations, failing tests) — see the caveats at the end.", ""] + parts + \
           ["## A second repository", "", "A second repository (sympy, a documented subset of its suite) was attempted. Bug mining ran, but profiling, the adapter and the backtest were not completed, so no sympy result is reported anywhere in this project.", "", "## Caveats", ""] + [f"- {c}" for c in CAVEATS] + [""]
    (paths.ROOT / "reports" / "REAL_WORLD.md").write_text("\n".join(text), encoding="utf-8")
    save_result("real_world", js)
    print("wrote reports/REAL_WORLD.md")


if __name__ == "__main__":
    main()
