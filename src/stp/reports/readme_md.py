"""Generate README.md (every number from reports/results/*.json).

Usage: python -m stp.reports.readme_md
"""
from __future__ import annotations

from stp import paths
from stp.reports.error_md import _ci, get, verdict
from stp.reports.fmt import HEADLINE, NAME, QUESTION, table
from stp.reports.results_md import _r

REPO = "Abhijeetgupta55/synthesis"   # the GitHub repository (git remote origin), confirmed by the owner


def build() -> str:
    M, C, L, RW, MEM = _r("models"), _r("models_classification"), _r("labels"), _r("real_world"), _r("app_memory")
    nx = get(RW, "networkx", "backtest_summary", "all", default={})
    best = get(M, "best_simple_by_val", default={})

    def cell(sub, m):
        return _ci(get(M, "cells", sub, "macro10", m, "apfdc")).replace("+", "")

    word = {"better": "ML wins", "worse": "ML loses", "level": "tie"}
    rows = []
    for sub, name in (("All", "all failed runs"), ("FirstFail-old", "first-time failures of existing tests")):
        d = get(M, "vs_best_simple", sub, "macro10", "lgbm")
        rows.append([name, best.get(sub), cell(sub, best.get(sub)), cell(sub, "lgbm"), _ci(d), word[verdict(d)]])
    v = get(M, "vs_cbt_lastfail_All")
    rows.insert(1, ["all failed runs", "cbt_LastFail (paper's best history rule)", cell("All", "cbt_LastFail"),
                    cell("All", "lgbm"), _ci(v), word[verdict(v)]])
    nxm = get(RW, "networkx", "backtest_summary", "mined", default={})
    med = lambda m: get(nxm, "median_ttff_s", m, "median", default=float("nan"))  # noqa: E731
    bnx = nx.get("best_simple_baseline", "changed_files_first")
    lab = _r("lab_meta") or {}
    import json as _json
    lm = paths.ROOT / "demo_bundle" / "lab" / "lab_meta.json"
    if lm.exists():
        lab = _json.loads(lm.read_text(encoding="utf-8"))
    kp = get(M, "vs_best_simple", "All", "macro10", "stack", "per_project", default={})
    W = _r("real_prs_wins")
    wtl = lambda p: " / ".join(f"{get(W, 'projects', p, o, 'n_builds', default=0):,}" for o in ("win", "tie", "loss"))  # noqa: E731
    bt = paths.ROOT / "demo_bundle" / "repos" / "networkx" / "backtest.json"
    nq, startup = {}, 0.0
    if bt.exists():
        b = _json.loads(bt.read_text(encoding="utf-8"))
        mined = [x for x in b["bugs"] if x["kind"] == "mined" and x.get("prefix")]
        nq = {"n": len(mined), "n_files": b.get("n_test_files")}
        for m in ("default", "smartci", "changed_files_first"):
            v = sorted(len(x["prefix"][m]) for x in mined if m in x["prefix"])
            nq[m] = v[len(v) // 2] if v else None
        pr = _json.loads((bt.parent / "profile.json").read_text(encoding="utf-8"))
        o = sorted(x for x in pr.get("overhead_s") or [] if x is not None)
        startup = o[len(o) // 2] if o else 0.0
    rubric = [
        ["1 EDA", "[EDA_REPORT.md](reports/EDA_REPORT.md)", "label imbalance, suite durations, history-rule collapse"],
        ["2 Feature derivation", "[FEATURES.md](reports/FEATURES.md)", "25 as-of features, leakage tests, rejected features"],
        ["3 Classification", "[MODELING.md §1, §4](reports/MODELING.md)", "LR, random forest, LightGBM; PR-AUC"],
        ["4 Regularization", "[MODELING.md §3](reports/MODELING.md)", "L1/L2/elastic net, tree depth, early stopping"],
        ["5 Hyperparameter tuning", "[MODELING.md §3](reports/MODELING.md)", "Optuna TPE, time-ordered validation"],
        ["6 Ensembles", "[MODELING.md §6](reports/MODELING.md)", "bagging vs boosting, voting, stacking"],
        ["7 Performance analysis", "[RESULTS.md](reports/RESULTS.md)",
         "APFDc vs every baseline with CIs, error analysis, trade-off"],
    ]
    return "\n".join([
        f"# {NAME}", "",
        f"![tests](https://github.com/{REPO}/actions/workflows/tests.yml/badge.svg)", "",
        "Predict which tests will fail for a code change and run those first, so a broken change is caught in "
        "seconds instead of after the whole suite. Nothing is skipped; only the order changes.", "",
        "> **In plain words:** like looking for lost keys where you last had them instead of searching the house "
        "room by room, smartci runs first the tests most likely to catch your mistake. "
        "[Explained simply](reports/EXPLAINER.md) · [Roadmap](reports/ROADMAP.md) · "
        "[Demo script](reports/DEMO_SCRIPT.md)", "",
        "## The demo in four steps", "",
        "```powershell", "scripts\\setup_demo.ps1     # once: .venv-demo with requirements.txt",
        "scripts\\run_demo.ps1       # http://localhost:8501, offline", "```", "",
        "Linux/macOS: `scripts/setup_demo.sh` and `scripts/run_demo.sh` (or `pip install -r requirements.txt` and "
        f"`streamlit run app/demo.py`). The app needs no dataset; about {MEM.get('peak_working_set_mb', '?')} MB of memory.", "",
        f"1. **ML Lab** (live training, nothing precomputed). A real sample is bundled ({lab.get('train_sample', {}).get('rows', 0):,} "
        f"training rows, {lab.get('later_builds', {}).get('rows', 0):,} rows of later builds). Pick logistic regression, a random forest "
        "or LightGBM, the regularization, the split (random or by time), the feature groups and the metric; *Train* fits now and "
        "shows train vs validation vs later-build scores, top features and the time taken. Four guided experiments, each with a "
        "takeaway computed from the fit: the accuracy trap, overfitting without regularization, a random split inflating the "
        "score, history features alone vs with change features. Retype them: [notebooks/lab_by_hand.ipynb](notebooks/lab_by_hand.ipynb).",
        f"2. **Real PRs** (replay of a real recorded build). Held-out Apache Kafka and TVM builds, the two projects where the "
        f"stacked model beats the best simple rule (ΔAPFDc {kp.get('kafka', 0):+.3f} Kafka, {kp.get('tvm', 0):+.3f} TVM). Per build: "
        "the link to the real PR, changed files, tests and total test time; for random, fastest-first, the best simple rule and "
        "the model, the position of the first failing test, the test minutes before it and approximate wall-clock time; the "
        "model's top 10 with reasons. Win/tie/loss counts and a *Show me a loss* button. "
        f"Over all held-out builds: Kafka {wtl('kafka')}, TVM {wtl('tvm')} (won / tied / lost). The wins come from recurring "
        "failures, not flaky tests (the page shows the numbers).",
        "3. **A real GitHub pull request.** On a NetworkX fork, one workflow runs three jobs on the same commit (pytest's "
        "order, `--smartci-rule changed_files_first`, the model) and comments on the PR: the top 10 tests with probability "
        "and reasons, the failing test's queue position in each order, and each job's end-to-end time on GitHub's clock. "
        "Links: [reports/PUBLIC_RUNS.md](reports/PUBLIC_RUNS.md); steps: [HUMAN_TODO.md](HUMAN_TODO.md). On the *Break the code* "
        "page two real pytest processes run side by side with a real stopwatch (start-up included), ending in the real traceback.",
        "4. **The honest verdict.** The model helps on large projects with long history (Kafka, TVM). On a small Python repo "
        "(NetworkX) a simple rule, changed files first, is enough. On first-time failures the model loses to fastest first.", "",
        "## The numbers", "",
        f"**The question.** {QUESTION}", "", f"**The answer.** {HEADLINE}", "",
        f"On 108,366 real CI runs of 10 Apache projects (held-out test period, APFDc: 1 = failures first, 0.5 ≈ random; "
        f"95% confidence intervals):", "",
        table(["Failures", "Best simple rule", "Its APFDc", "ML (LightGBM)", "ML − rule", "Verdict"], rows), "",
        f"On NetworkX ({nq.get('n')} real past bugs put back), the failing test file sits at median queue position "
        f"{nq.get('default')} of {nq.get('n_files')} in pytest's order, {nq.get('smartci')} with smartci and "
        f"{nq.get('changed_files_first')} with changed files first; test seconds until it fails are {med('default'):.1f}, "
        f"{med('smartci'):.2f} and {med(bnx):.2f}, and every order pays the same pytest start-up on top (about "
        f"{startup:.0f} s on our laptop). Failures are rare: "
        f"{get(L, 'pooled', 'pos_rate_fail', default=0):.3%} of (run, test) pairs, so accuracy is meaningless and we "
        f"use PR-AUC (best model {max(get(C, 'models', m, 'pr_auc', default=0) for m in ('lr', 'rf', 'lgbm', 'vote', 'stack')):.3f}). "
        "Why the model loses on first-time failures: [RESULTS.md §4](reports/RESULTS.md).", "",
        "## Use smartci on your own repo", "",
        "```bash",
        f"pip install \"smartci @ git+https://github.com/{REPO}.git\"   # into the venv you test with",
        "smartci evaluate           # replays your own past bugs; verdict: smartci, a simple rule, or nothing",
        "pytest --smartci           # run your tests in smartci's order (nothing is skipped)",
        "pytest --smartci --smartci-rule changed_files_first   # or the simple rule evaluate recommended", "```", "",
        "`smartci evaluate` runs `profile` (suite twice: durations, order, flaky tests), `learn` (mine and reproduce "
        "past bug fixes) and `backtest` (replay them under every order), then prints a verdict card. On NetworkX it "
        f"recommends **{_r('verdict_networkx').get('recommendation', '?')}**: the tool says so when a simple rule is "
        "as good as the model.", "",
        "Also: `smartci compare --bug <id>` (real side-by-side pytest runs), `smartci explain`, "
        "`smartci rank --files a.py b.py` (rank for a hypothetical change), `pytest --smartci-shadow` (rank and record "
        "without reordering). The plugin does nothing unless you pass `--smartci`; if ranking fails, it keeps "
        "pytest's order. It works in git worktrees under `.smartci/` and never touches your checkout.", "",
        "## How the ML pipeline maps to the course rubric", "",
        table(["Rubric item", "Where", "What"], rubric), "",
        "One table with the key number per item: [RUBRIC_MAP.md](reports/RUBRIC_MAP.md). Viva preparation: "
        "[VIVA_NOTES.md](reports/VIVA_NOTES.md). Demo script: [DEMO_SCRIPT.md](reports/DEMO_SCRIPT.md). Audit of "
        "every claim: [AUDIT.md](reports/AUDIT.md). Every number in the reports is generated from "
        "`reports/results/*.json` by `src/stp/reports/*`.", "",
        "## Limitations", "",
        "- The model was trained on Apache CI data (9 Java/Scala projects + TVM's Python suites), never on NetworkX.",
        "- On first-time failures the model loses to \"fastest first\"; on a small Python repo a simple rule is as "
        "good as the model.",
        "- NetworkX bugs are past bugs reintroduced, or synthetic mutants; Real PRs replays add up recorded durations "
        "(LRTS does not record the real execution order, so a random order stands in for it).",
        "- The simulated-vs-real timing check (GATE 5) and the live-run recordings need mains power and are pending "
        "([REAL_WORLD.md](reports/REAL_WORLD.md), HUMAN_TODO 0).",
        "- On a suite of a few seconds, smartci's own start-up costs more than it saves.",
        "- A second repository (sympy) was attempted and not completed.", "",
        "## Data sources and licences", "",
        "- **LRTS** (Long-Running Test Suites, ISSTA 2024): CI test results of 10 Apache projects; MIT licence. Not "
        "included in this repository; `python -m stp.data.download` fetches it.",
        "- **NetworkX** (BSD-3-Clause): pinned commit, cloned to `external/networkx` for the live demo; not included.",
        "- **Apache projects** (Apache-2.0): pull-request links only.", "",
        "## Reproduce the research pipeline", "",
        "```bash", 'uv venv --python 3.11 .venv && uv pip install --python .venv -e ".[research,dev]"',
        "python -m stp.data.download && python -m stp.data.build_tables && python -m stp.data.splits",
        "python -m stp.data.build_diffs && python -m stp.features.store && python -m stp.features.verify_store",
        "python -m stp.baselines.lrts_repro && python -m stp.baselines.run_baselines",
        "python -m stp.models.pipeline && python -m stp.models.figures && python -m stp.models.error_analysis",
        "python -m stp.models.floor_tradeoff && python -m stp.models.wtl",
        "for m in baselines_md features_md modeling_md real_world_md results_md viva_md model_card presentation_md "
        "extra_figures readme_md; do python -m stp.reports.$m; done",
        "pytest", "```", "",
        "The full pipeline takes many hours and about 15 GB of disk; every stage streams per project and is resumable.",
        "", "## Layout", "",
        table(["Path", "What"], [
            ["`src/stp/`", "research pipeline: data, EDA, features, evaluation, baselines, models, reports, demo"],
            ["`src/smartci/`", "the tool: CLI, pytest plugin, scoring, packaged model (`model/`)"],
            ["`app/demo.py`, `demo_bundle/`", "the dashboard and the only data it reads"],
            ["`live_demo/`", "NetworkX live comparison, GATE 5, Phase C timing, public CI (`public_ci/`)"],
            ["`notebooks/lab_by_hand.ipynb`", "the ML Lab's four experiments in plain pandas / scikit-learn / LightGBM"],
            ["`reports/`", "generated reports, `results/*.json`, `figures/`, `demo_screenshots/`"],
            ["`data/`, `external/`", "git-ignored (LRTS data, LRTS repo, NetworkX clone)"]]), ""])


def main() -> None:
    (paths.ROOT / "README.md").write_text(build(), encoding="utf-8")
    print("wrote README.md")


if __name__ == "__main__":
    main()
