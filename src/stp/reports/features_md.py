"""Generate reports/FEATURES.md from the schema, the feature docstrings and reports/results/univariate.json.

Usage: python -m stp.reports.features_md
"""
from __future__ import annotations

from stp import paths
from stp.features.schema import FEATURES
from stp.reports.fmt import table
from stp.results import load_result

ASOF = {
    "history": "computed only from runs whose end ≤ this run's start (streaming state applied in end order)",
    "cost": "durations of finished runs only; this run's own durations are evaluation-only (`y_duration_s`)",
    "change": "uses only the change (diff vs trunk) and the names of the tests in this run, known at start",
    "cofail": "counts only finished runs (end ≤ start) where a file changed and the test failed",
}
DOC = {
    "n_fail": ("# failures of the test in finished runs", "Tests that failed before fail again (EDA §D heavy tail)."),
    "days_since_last_fail": ("days since the start of the most recent known failure; 9999 if none",
                             "Failures cluster in time (EDA §D/§G: LastFail is the strongest paper baseline)."),
    "fails_last_7d": ("# failures that became known in the last 7 days", "Recent instability."),
    "fails_last_30d": ("# failures that became known in the last 30 days", "Medium-term instability."),
    "last_outcome": ("outcome in the most recently finished run containing the test", "LRTS 'last outcome', as-of."),
    "n_transitions": ("# pass↔fail flips in the finished history", "Flaky / unstable tests flip."),
    "n_runs_seen": ("# finished runs containing the test", "Confidence of the other history features."),
    "fail_rate": ("(n_fail + 20·0.0025) / (n_runs + 20)", "Smoothed failure propensity; robust for short histories."),
    "is_new_test": ("never seen in a finished run", "EDA §D: new tests are 4.9% of first-time failures."),
    "h_last_fail_same_stage": ("the most recent known failure happened in this stage",
                               "Lets the all-stage scope tell environment-specific failures apart."),
    "dur_last_asof": ("duration in the latest finished run (same stage, else any stage, else run median)",
                      "Cost: cheap tests first maximises failures found per minute."),
    "dur_ema_asof": ("EMA (α 0.3) of durations, same fallback chain", "A smoother expected cost; the p/d denominator."),
    "dur_source": ("2 same-stage, 1 other stage, 0 fallback", "How much to trust the duration."),
    "test_file_in_diff": ("the test's own file is in the change (exact mapping)",
                          "EDA fact 2: 8.3% of first-time failures have their own file edited."),
    "same_top_module": ("the test's top module equals a changed file's top module", "Coarse locality."),
    "path_prefix_overlap": ("longest common package prefix with any changed file, / test path length",
                            "Fine locality; language-agnostic."),
    "name_token_overlap": ("# tokens shared by test path and changed paths", "EDA §F: lift 1.8× / 3.0× / 5.9× at k=1/2/3."),
    "bm25_test_vs_diff": ("BM25 of test tokens vs diff tokens (paths + patch text); IDF over the run's tests",
                          "IR_GitDiff is the paper's best change-aware baseline on FirstFail."),
    "chg_n_files": ("# changed files", "Large changes break more (EDA §E)."),
    "chg_additions": ("# added lines", "Change size."),
    "chg_deletions": ("# deleted lines", "Change size."),
    "chg_n_top_modules": ("# distinct top modules touched", "Change breadth."),
    "has_change_data": ("the change was found in the compare data", "Missing-data indicator."),
    "cof_max": ("max over changed files of cof(f,x)/(nchg(f)+1), directory backoff for unseen files",
                "Learned file→test dependencies beyond names (co-failure memory)."),
    "cof_sum": ("sum of the same scores over changed files", "Several weakly linked files add up."),
    "cof_count_max": ("max raw co-failure count over changed files", "Explanations quote it."),
    "semantic_sim": ("reserved, always NaN", "Future Tier-2 embedding similarity."),
}
REJECTED = [
    ("author / commit counts", "median 1 author and 2 commits per build (EDA §E): almost no variance"),
    ("JIRA flaky flags", "future knowledge (fix dates lie after the runs); used only to filter evaluation"),
    ("current-run duration", "leakage: known only after the test ran; kept as `y_duration_s` for evaluation"),
    ("project id", "the exported model must score unseen repositories; a project id would memorise per-project base "
                   "rates. Pooled models therefore get no project id (per-project behaviour is analysed instead)"),
]


def _base(name: str) -> str:
    for pre in ("h_", "hs_"):
        if name.startswith(pre) and name[len(pre):] in DOC:
            return name[len(pre):]
    return name


def main() -> None:
    u = load_result("univariate")
    uf = u["features"]
    rows = []
    for c, m in FEATURES.items():
        d, hyp = DOC.get(_base(c), ("", ""))
        s = uf.get(c, {})
        top_lift = max((b["lift"] or 0) for b in s.get("lift_by_bin", [{"lift": 0}])) if s else None
        rows.append([f"`{c}`", m["group"], m.get("scope", ""), d, hyp,
                     "–" if not s else f"{s['pr_auc']:.4f}", "–" if not s else f"{s['pr_auc_ftf']:.4f}",
                     "–" if not s else f"{s['mutual_info']:.5f}", "–" if top_lift is None else f"{top_lift:.1f}×"])
    pairs = u["redundant_pairs_abs_rho_gt_0.9"]
    text = ["# FEATURES", "",
            "Generated by `python -m stp.reports.features_md` from `stp/features/schema.py` and "
            "`reports/results/univariate.json`. Do not edit by hand.", "",
            "## As-of guarantees by group", "",
            *[f"- **{g}**: {t}" for g, t in ASOF.items()],
            "", "Enforced by `tests/test_leakage.py` (synthetic overlap + brute-force recomputation of random real runs).",
            "", "## Definitions and univariate signal (training sample, weighted to the population)", "",
            f"Base rate (weighted): {u['base_rate_weighted']:.5f}; {u['n_rows']:,} rows, {u['n_pos']:,} positives. "
            "PR-AUC is oriented (the better of the feature and its negative); 'max lift' = highest P(fail | bin) / "
            "P(fail) over 10 quantile bins.", "",
            table(["Feature", "Group", "Scope", "Definition", "Hypothesis / evidence", "PR-AUC (fail)",
                   "PR-AUC (first-time)", "MI", "Max lift"], rows), "",
            "Figures: `figures/features_univariate.png`, `figures/features_corr.png`.", "",
            "## Correlation and redundancy", "",
            f"{len(pairs)} pairs with |Spearman ρ| > 0.9:", "",
            table(["A", "B", "ρ"], [[p["a"], p["b"], f"{p['rho']:.3f}"] for p in pairs]) if pairs else "(none)", "",
            "Handling: trees are unaffected in accuracy (they pick one of the pair per split), but importance is shared "
            "between the two, so SHAP is reported by *group* as well. For logistic regression, the h_/hs_ duplicates are "
            "resolved by the history-scope choice (only one scope enters the model, chosen on validation: "
            "`scope_choice.json`), and the L2/L1 penalties handle the remaining collinearity (L1 keeps one of a "
            "correlated pair, L2 splits weight).", "",
            "## Rejected features", "",
            *[f"- **{a}**: {b}" for a, b in REJECTED], ""]
    (paths.ROOT / "reports" / "FEATURES.md").write_text("\n".join(text), encoding="utf-8")
    print("wrote reports/FEATURES.md")


if __name__ == "__main__":
    main()
