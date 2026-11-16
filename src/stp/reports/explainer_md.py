"""Generate reports/EXPLAINER.md (plain language, for anyone) and reports/ROADMAP.md (scope and next steps).

Numbers come from reports/results/*.json. Usage: python -m stp.reports.explainer_md
"""
from __future__ import annotations

from stp import paths
from stp.reports.error_md import _ci, get
from stp.reports.results_md import _r


def explainer() -> str:
    S, M, L, B, V, A = (_r(n) for n in ("savings", "models", "labels", "eda/B_costs", "verdict_networkx", "audit_runs"))
    if not B:
        import json
        f = paths.ROOT / "reports" / "eda_json" / "B_costs.json"
        B = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    me = S.get("methods", {})
    fx, ml = get(me, "Random", "frac_waited_macro", default=0), get(me, "lgbm", "frac_waited_macro", default=0)
    best = get(M, "best_simple_by_val", "All")
    fr = get(me, best, "frac_waited_macro", default=0)
    hours = get(B, "full", "duration_h_median", "macro", default=0)
    d = get(M, "vs_best_simple", "All", "macro10", "lgbm")
    f = get(M, "vs_best_simple", "FirstFail-old", "macro10", "lgbm")
    med = V.get("median_s", {})
    return "\n".join([
        "# smartci, explained simply", "",
        "*For anyone: no programming or machine-learning background needed. Numbers come from "
        "`reports/results/` and are regenerated with `python -m stp.reports.explainer_md`.*", "",
        "## The problem", "",
        "Software teams keep a large set of automatic checks, called **tests**, that verify the code still works. "
        "Every time someone changes the code, a system called **CI** (continuous integration) runs all the tests. "
        f"In the ten big open-source projects we studied, one full run takes about **{hours:.0f} hours** "
        "(median). The tests run in a fixed order, so if a change broke something, the test that notices is "
        f"often far down the list: typically the developer waits through **{fx:.0%}** of the whole run before "
        "the first failure appears (measured with a random order standing in for the fixed one, because the data "
        "does not record the original order).", "",
        "## The idea", "",
        "**Run the tests most likely to fail first.** Nothing is skipped; every test still runs. Only the order "
        "changes, so bad news arrives early.", "",
        "> *Like looking for lost keys:* you don't search the house room by room in a fixed order. You look first "
        "where you last had them and where you just were. smartci looks first at the tests that broke recently and "
        "the tests related to the files you just changed.", "",
        "## How it works, in three steps", "",
        "1. **Learn from the past.** We trained a machine-learning model on "
        f"{get(L, 'pooled', 'rows', default=0) / 1e6:.0f} million records of past test results (108,366 test runs "
        "of 10 Apache projects). For each test in each run it learned which clues predict a failure: did this test "
        "fail recently? Is it about the code that changed? How long does it take?",
        "2. **Predict for a new change.** When code changes, the model gives every test a chance of failing.",
        "3. **Reorder.** Tests run in order of chance-of-failing divided by running time, so a likely and quick "
        "test goes first.", "",
        "## What we found", "",
        f"- **Reordering helps enormously.** With the model, the first failure appears after {ml:.1%} of the run "
        f"instead of {fx:.0%}. On NetworkX (a popular Python library) the typical bug is caught after "
        f"{med.get('smartci', 0):.2f} seconds of testing instead of {med.get('default', 0):.0f} seconds.",
        f"- **Machine learning is only modestly better than a good simple rule.** A one-line rule such as "
        f"\"run the tests of the changed files first\" gets the first failure after {fr:.1%} of the run. On "
        f"failures that happened before, the model ties the best rule (score difference {_ci(d)}).",
        f"- **For a test failing for the very first time, \"fastest test first\" beats the model** ({_ci(f)}). "
        "The model trusts history, and a first-time failure has none. We measured this rather than assume it "
        "(RESULTS.md §4).", "",
        "That is why the tool does not just push the model. `smartci evaluate` replays a team's own past bugs and "
        f"recommends whatever works best on *their* code. For NetworkX it recommends: **{V.get('recommendation')}**.",
        "", "## Words you will hear", "",
        "- **Test suite:** all of a project's automatic tests.",
        "- **CI (continuous integration):** the server that runs the tests on every change.",
        "- **Flaky test:** a test that sometimes fails for no real reason; we exclude them from every measurement.",
        "- **APFDc:** a score from 0 to 1 for an order; 1 means every failure was found at the very start, about "
        "0.5 means a random order.",
        "- **PR-AUC:** how well a model ranks the failing tests above the passing ones. Because only "
        f"{get(L, 'pooled', 'pos_rate_fail', default=0):.2%} of test results are failures, the simpler 'accuracy' "
        "would look excellent for a model that always says 'pass'.",
        "- **Backtest:** replaying old, real bugs to see what each order would have done.", "",
        "## Common questions", "",
        "- **Does it skip tests? Can it let a bug through?** No. Every test runs. The worst case is no speed-up.",
        "- **Is it a big AI system?** No. It is a small model (gradient-boosted decision trees) that ranks a few "
        "hundred tests in a fraction of a second on a laptop.",
        "- **Does it need my data?** It learns from your own test history and past bug fixes, locally. Nothing is "
        "sent anywhere.",
        "- **What does it cost?** A few seconds of start-up per run. On very short test suites that can cost more "
        "than it saves, and the tool says so.",
        "- **Is this a real problem?** Yes. Large companies run systems like this: Facebook reported halving the "
        "cost of testing code changes with a model that predicts which tests will fail "
        "([Machalica et al., 2019](https://arxiv.org/abs/1810.05286)), and commercial tools sell predictive test "
        "selection for pytest and other frameworks. The research study our data comes from "
        "([Cheng et al., ISSTA 2024](https://mir.cs.illinois.edu/marinov/publications/ChengETAL24LongRTP.pdf)) "
        "found simple rules hard to beat, which matches what we found.", ""])


def roadmap() -> str:
    return "\n".join([
        "# ROADMAP: where smartci can go", "",
        "*What exists today, what would make it production-grade, and the research questions it opens. Written for "
        "the team and for anyone judging the project's scope.*", "",
        "## Today", "",
        "- A study on 108,366 real CI runs: leak-free features, five classifiers, ensembles, calibration, honest "
        "comparison with every simple rule, error analysis (RESULTS.md).",
        "- `smartci`: an installable pytest plugin and CLI. `smartci evaluate` replays a repository's own past "
        "bugs and recommends the model, a simple rule (`--smartci-rule`), or nothing. Shadow mode records "
        "rankings without changing anything. Every run writes an auditable receipt.",
        "- A dashboard that runs offline, including a live model page and a guided demo.", "",
        "## Next: production-grade (weeks)", "",
        "1. **Shadow mode in CI first.** Install the GitHub Action (`action.yml`) in shadow mode for a few weeks. "
        "It ranks every run without changing the order and records outcomes. That builds the history the full "
        "model needs (today NetworkX runs on the cold-start model because it has almost no recorded CI history) "
        "and gives a before/after measurement on real pull requests.",
        "2. **Test-level ordering.** Today smartci reorders whole test files. Ordering individual tests inside a "
        "file would help large files.",
        "3. **Parallel CI.** Most CI splits tests across machines. Putting the likeliest failures in every "
        "machine's first slot turns the same idea into wall-clock savings.",
        "4. **Per-repository tuning.** The probability floor that helped first-time failures on the research data "
        "hurt on NetworkX (RESULTS.md §4.3); tune such settings per repository with `smartci evaluate`.",
        "5. **Flaky-test signal.** Flag tests whose outcome changes without a code change, and keep them out of "
        "training and out of the 'likely to fail' list.", "",
        "## Later: bigger bets (months)", "",
        "- **Safe test selection.** Run only the top-ranked tests on every change and the full suite nightly, as "
        "Facebook does ([Machalica et al.](https://arxiv.org/abs/1810.05286)). This saves machine time, not just "
        "waiting time, but it can delay finding a bug, so it needs a measured safety bound per repository.",
        "- **Other languages.** The research data is mostly Java; a JUnit/Gradle front end would reuse the same "
        "model and features.",
        "- **Learning online.** Update the per-repository adapter after every CI run instead of from mined bugs.",
        "- **In the editor.** Show \"tests most likely affected by your edit\" before the developer even pushes.", "",
        "## Open research questions", "",
        "- First-time failures: which signals (code coverage, semantic similarity of code and test, change type) "
        "beat 'fastest first' where history is silent?",
        "- When does ML stop being worth it? A cost model that includes the tool's own start-up, suite length and "
        "failure rate would tell a team in advance.",
        "- Combining rules and models: a learned switch that picks the model or a rule per change, rather than "
        "per repository.", ""])


def main() -> None:
    (paths.ROOT / "reports" / "EXPLAINER.md").write_text(explainer(), encoding="utf-8")
    (paths.ROOT / "reports" / "ROADMAP.md").write_text(roadmap(), encoding="utf-8")
    print("wrote reports/EXPLAINER.md and reports/ROADMAP.md")


if __name__ == "__main__":
    main()
