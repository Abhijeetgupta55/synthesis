"""Generate README.md (every number from reports/results/*.json).

Usage: python -m stp.reports.readme_md
"""
from __future__ import annotations

from stp import paths
from stp.reports.error_md import _ci, get, verdict
from stp.reports.fmt import HEADLINE, NAME, QUESTION, table
from stp.reports.results_md import _r

OWNER = "OWNER"   # replaced by the students after creating the GitHub repository (HUMAN_TODO)


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
    med = lambda m: get(nx, "median_ttff_s", m, "median", default=float("nan"))  # noqa: E731
    bnx = nx.get("best_simple_baseline", "changed_files_first")
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
        f"![tests](https://github.com/{OWNER}/smart-ci-tcp/actions/workflows/tests.yml/badge.svg)", "",
        "Predict which tests will fail for a code change and run those first, so a broken change is caught in "
        "seconds instead of after the whole suite. Nothing is skipped; only the order changes.", "",
        "> **In plain words:** like looking for lost keys where you last had them instead of searching the house "
        "room by room, smartci runs first the tests most likely to catch your mistake. "
        "[Explained simply](reports/EXPLAINER.md) · [Roadmap](reports/ROADMAP.md) · "
        "[Demo script](reports/DEMO_SCRIPT.md)", "",
        "![The dashboard's start page](reports/demo_screenshots/01_start_here.png)", "",
        "## The result, honestly", "",
        f"**The question.** {QUESTION}", "", f"**The answer.** {HEADLINE}", "",
        f"On 108,366 real CI runs of 10 Apache projects (held-out test period, APFDc: 1 = failures first, 0.5 ≈ random; "
        f"95% confidence intervals):", "",
        table(["Failures", "Best simple rule", "Its APFDc", "ML (LightGBM)", "ML − rule", "Verdict"], rows), "",
        f"On NetworkX ({nx.get('n')} bugs: real past bugs and synthetic mutants), the median time to the first failure "
        f"is {med('default'):.1f} s in pytest's default order, {med('smartci'):.2f} s with smartci and "
        f"{med(bnx):.2f} s with {bnx.replace('_', ' ')}. Failures are rare: "
        f"{get(L, 'pooled', 'pos_rate_fail', default=0):.3%} of (run, test) pairs, so accuracy is meaningless and we "
        f"use PR-AUC (best model {max(get(C, 'models', m, 'pr_auc', default=0) for m in ('lr', 'rf', 'lgbm', 'vote', 'stack')):.3f}). "
        "Why the model loses on first-time failures: [RESULTS.md §4](reports/RESULTS.md).", "",
        "## Run the demo", "",
        "```powershell", "scripts\\setup_demo.ps1     # once: .venv-demo with requirements.txt",
        "scripts\\run_demo.ps1       # http://localhost:8501, fully offline", "```", "",
        "Linux/macOS: `scripts/setup_demo.sh` and `scripts/run_demo.sh`. Or simply `pip install -r requirements.txt` "
        "and `streamlit run app/demo.py`. The app reads only `demo_bundle/` (committed); it needs no dataset. "
        f"Memory: about {MEM.get('peak_working_set_mb', '?')} MB. Seven pages: Start here (the idea, an animated race "
        "on a real bug, a savings calculator), Break the code (a guided demo on a real NetworkX bug the model never "
        "saw), The ML pipeline (one tab per rubric item), Predict live (the real model ranks NetworkX tests for files "
        "you pick), Race replay, Results, Limits and honesty. Screenshots of every page: [`reports/demo_screenshots/`](reports/demo_screenshots).", "",
        "## Use smartci on your own repo", "",
        "```bash",
        f"pip install \"smartci @ git+https://github.com/{OWNER}/smart-ci-tcp.git\"   # into the venv you test with",
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
        "- NetworkX bugs are past bugs reintroduced, or synthetic mutants; race lanes replay measured durations.",
        "- The simulated-vs-real timing check (GATE 5) was measured on battery and failed; it is pending a re-run on "
        "mains power ([REAL_WORLD.md](reports/REAL_WORLD.md)).",
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
            ["`live_demo/`", "NetworkX live comparison, GATE 5, Phase C timing script"],
            ["`reports/`", "generated reports, `results/*.json`, `figures/`, `demo_screenshots/`"],
            ["`data/`, `external/`", "git-ignored (LRTS data, LRTS repo, NetworkX clone)"]]), ""])


def main() -> None:
    (paths.ROOT / "README.md").write_text(build(), encoding="utf-8")
    print("wrote README.md")


if __name__ == "__main__":
    main()
