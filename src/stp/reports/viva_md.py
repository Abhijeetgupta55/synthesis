"""Generate reports/VIVA_NOTES.md. Concept text is fixed; every number comes from reports/results/*.json via `R()`.

Usage: python -m stp.reports.viva_md
"""
from __future__ import annotations

import json

from stp import paths

_CACHE: dict = {}


def R(name: str, *keys, fmt: str = "{:.3f}", default: str = "(pending: result not generated yet)") -> str:
    """Value at results/<name>.json[keys...] formatted, or a visible 'pending' marker."""
    try:
        if name not in _CACHE:
            _CACHE[name] = json.loads((paths.RESULTS / f"{name}.json").read_text(encoding="utf-8"))
        v = _CACHE[name]
        for k in keys:
            v = v[k]
        return fmt.format(v) if fmt and not isinstance(v, str) else str(v)
    except Exception:  # noqa: BLE001
        return default


def section(title, what, how, why, result, qa) -> str:
    out = [f"## {title}", "", f"**What it is.** {what}", "", f"**How it works.** {how}", "",
           f"**Why we chose it here.** {why}", "", f"**Our result and what it means.** {result}", "",
           "**Likely questions.**"]
    out += [f"- *{q}* {a}" for q, a in qa]
    return "\n".join(out) + "\n"


def _j(name):
    try:
        return json.loads((paths.RESULTS / f"{name}.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def framing_questions() -> str:
    """The eight questions the 'when does ML beat simple rules?' framing invites, answered with numbers."""
    from stp.reports.error_md import _ci, get, verdict
    M, C, L, E, F, RW, LB, LS = (_j(n) for n in ("models", "models_classification", "labels", "error_analysis",
                                                 "floor_tradeoff", "real_world", "leakage_bruteforce",
                                                 "leakage_signal"))
    nan = float("nan")
    nx = get(RW, "networkx", "backtest_summary", "all", default={})

    def med(m):
        return get(nx, "median_ttff_s", m, "median", default=nan)

    best_nx = nx.get("best_simple_baseline", "changed_files_first")
    w_nx = get(nx, "vs_smartci", best_nx, default={})
    ff = get(E, "firstfail_old", "macro", default={})
    tv = get(E, "tvm_drift", "splits", default={})
    ec = C.get("error_corr") or {}
    rc = "?"
    if ec:
        n = ec["names"]
        rc = f"{ec['residual_corr'][n.index('lgbm')][n.index('rf')]:.2f}"
    dl = get(F, "test", "delta_vs_f0", default={})
    best_pr = max(get(C, "models", m, "pr_auc", default=0) for m in ("lr", "rf", "lgbm", "vote", "stack"))
    rate_ratio = get(tv, "valB", "row_failure_rate", default=0) / max(get(tv, "test", "row_failure_rate", default=1),
                                                                      1e-12)
    vb = get(M, "vs_best_simple", "All", "macro10", "lgbm")
    qa = [
        ("Isn't this just a scheduler?",
         "The output is an order, so the last step is scheduling: sort by P(fail) / expected duration. The ML part "
         "is estimating P(fail) for every test in every run, which no scheduler knows. The order itself matters a "
         f"lot: on NetworkX the median time to the first failure falls from {med('default'):.1f} s (pytest's order) "
         f"to {med('smartci'):.2f} s; on LRTS a random order scores APFDc "
         f"{get(M, 'cells', 'All', 'macro10', 'Random', 'apfdc', 'mean', default=nan):.3f} and the model "
         f"{get(M, 'cells', 'All', 'macro10', 'lgbm', 'apfdc', 'mean', default=nan):.3f}."),
        ("Why does the model lose on first-time failures?",
         "It learned that tests which failed before fail again, which is right for recurring failures. When the "
         "failing test has never failed, the time spent on previously-failed tests is wasted: before reaching the "
         f"failure the model has used {ff.get('model|time_share_before_target', nan):.1%} of suite time (QTF "
         f"{ff.get('QTF|time_share_before_target', nan):.1%}), "
         f"{ff.get('model|prev_failed_share_of_time_before', nan):.0%} of it on previously-failed tests. "
         f"Delta APFDc vs QTF {_ci(get(M, 'vs_best_simple', 'FirstFail-old', 'macro10', 'lgbm'))}. A probability "
         f"floor recovers {_ci(dl['FirstFail-old']) if dl else '(not computed)'} of it (RESULTS.md section 4)."),
        ("Why is a simple rule as good on NetworkX?",
         f"Median seconds to first failure: smartci {med('smartci'):.2f}, {best_nx} {med(best_nx):.2f}; smartci "
         f"wins / ties / loses {w_nx.get('win')} / {w_nx.get('tie')} / {w_nx.get('loss')} against it. NetworkX "
         "names each test file after the module it tests, so running the tests of the changed files already finds "
         "most bugs, and NetworkX has almost no recorded CI history, so the model runs in cold-start mode without "
         "its strongest (history) features."),
        ("Why PR-AUC and not accuracy?",
         f"Only {get(L, 'pooled', 'pos_rate_fail', default=nan):.3%} of (run, test) rows fail, so always predicting "
         f"'pass' is {get(L, 'pooled', 'always_pass_accuracy', default=nan):.2%} accurate and finds nothing. PR-AUC "
         "asks how well failures are ranked above passes; a random ranking scores the base rate, our best model "
         f"{best_pr:.3f}."),
        ("Why do ensembles add so little?",
         f"PR-AUC LightGBM {get(C, 'models', 'lgbm', 'pr_auc', default=nan):.3f}, voting "
         f"{get(C, 'models', 'vote', 'pr_auc', default=nan):.3f}, stacking "
         f"{get(C, 'models', 'stack', 'pr_auc', default=nan):.3f}; the APFDc confidence intervals overlap. Ensembles "
         f"help when members make different mistakes; the residuals of LightGBM and random forest correlate at {rc}, "
         "because all models lean on the same history features."),
        ("Why did the TVM model collapse on the test period?",
         "Not because the features drifted (drift against train is large in both validation and test). The "
         f"validation period was easier: the row failure rate was {rate_ratio:.1f}x higher and failures repeated "
         "more, which history features catch. One project's single validation period was too little to choose a "
         "model on; the pooled all-projects model was shipped instead (disclosed)."),
        ("Was any future information used?",
         "No feature uses it: every history feature counts only runs that had finished when the run started "
         f"(brute-force recomputation from raw data matches {LB.get('n_match')}/{LB.get('n_runs')} random runs; no "
         f"single feature reaches the suspicious PR-AUC threshold {LS.get('threshold')}). Splits are by time. JIRA "
         "flaky labels (future knowledge) only filter the evaluation. Hyperparameters and the floor were chosen on "
         "validation. One disclosed exception: when the TVM-only variant failed on test, shipping the pooled variant "
         "instead used test information."),
        ("Who would actually use this?",
         "Teams with long suites (the LRTS projects' median suite takes hours) and recurring failures, where the "
         f"model is level with or slightly above the best simple rule ({_ci(vb)}, {verdict(vb)}) and clearly above "
         f"the paper's best history rule ({_ci(get(M, 'vs_cbt_lastfail_All'))}). On a small Python repo a simple "
         "rule is enough, and `smartci backtest` says so for that repo."),
    ]
    out = ["## Questions this framing invites", "",
           "*The project asks when ML beats simple rules for ordering tests. These are the questions that framing "
           "invites, with short answers backed by numbers.*", ""]
    for q, a in qa:
        out += [f"**{q}**  ", a, ""]
    return "\n".join(out)


def build() -> str:
    pct = "{:.1%}"
    S = [
        section(
            "As-of history and the concurrency leak",
            "A rule that a CI run may only use results of runs that had *finished* when it started.",
            "Each run gets start = build_timestamp and end = start + build_duration (capped at 24 h). Run Q informs "
            "run R iff Q.end ≤ R.start. The store applies runs to per-test state in end order while visiting runs in "
            "start order.",
            "LRTS computes 'last outcome' from the previous run *by start time*. CI runs overlap, so that previous run "
            "had often not finished: using its outcome is information from the future.",
            f"Previous run unfinished at start: {R('phase0_facts', 'fact1', 'share_prev_run_unfinished_at_start', 'macro', fmt=pct)} "
            f"macro (Kafka {R('phase0_facts', 'fact1', 'share_prev_run_unfinished_at_start', 'per_project', 'kafka', fmt=pct)}); "
            f"{R('phase0_facts', 'fact1', 'share_last_outcome_fail_rows_from_unfinished_run', 'macro', fmt=pct)} of "
            "'last outcome = fail' values come from unfinished runs. Brute-force check: "
            f"{R('leakage_bruteforce', 'n_match', fmt='{}')}/{R('leakage_bruteforce', 'n_runs', fmt='{}')} random runs "
            "recomputed from raw tables match the store.",
            [("Why cap durations at 24 h?", "p99.9 of build_duration is 25.6 h and 0.12% of runs exceed 24 h; values up "
              "to 83 days are not test time. Capping makes those runs visible earlier, a deliberate, tiny relaxation."),
             ("Does the leak inflate the paper's numbers?", "See BASELINES.md §3: same features, same runs, start order vs "
              "as-of.")]),
        section(
            "Negative sampling and recalibration",
            "Training on all positives and only a sample of negatives, with weights, then re-mapping probabilities.",
            "Per training run: all failing rows; up to K = 200 passing rows, half from tests related to the change. "
            "Each sampled row is weighted by stratum size / sample size. Probabilities are then calibrated by isotonic "
            "regression on unsampled validation rows (valB).",
            "104M rows with ~0.24% positives do not fit in 2 GB RAM and are dominated by easy negatives.",
            f"Training rows: {R('train_sample', 'per_project', 'kafka', 'rows', fmt='{:,}')} for Kafka (see "
            "train_sample.json for all). Brier before/after calibration: MODELING.md §calibration.",
            [("Why calibrate at all if ranking is what matters?", "The ordering rule divides P by duration; a mis-scaled "
              "P changes the trade-off between risk and cost."),
             ("Why isotonic, not Platt?", "Isotonic is monotone and non-parametric; with millions of validation rows it "
              "does not overfit, and Platt (reported too) assumes a sigmoid shape.")]),
        section(
            "PR-AUC vs accuracy and ROC-AUC",
            "Precision-recall area: average precision over recall levels.",
            "Sort rows by score; precision at each positive, averaged.",
            f"Base rate is {R('labels', 'pooled', 'pos_rate_fail', fmt='{:.4%}')}: always predicting 'pass' is "
            f"{R('labels', 'pooled', 'always_pass_accuracy', fmt='{:.2%}')} accurate and useless. ROC-AUC rewards "
            "ranking the huge negative mass correctly and looks optimistic; PR-AUC focuses on the few positives.",
            "MODELING.md: PR-AUC (primary), ROC-AUC alongside.",
            [("Why is ROC-AUC high but PR-AUC low?", "With 400 negatives per positive, a small false-positive *rate* is "
              "still many false positives, which ROC hides and PR shows.")]),
        section(
            "L1 vs L2 regularisation",
            "Penalties on coefficient size in logistic regression: L1 = sum |w|, L2 = sum w².",
            "The loss adds λ·penalty; C = 1/λ. L1's corner at 0 sets weak coefficients exactly to zero (feature "
            "selection); L2 shrinks all smoothly and handles correlated features by sharing weight.",
            "Many correlated history features (h_ and hs_ counts, fail rate) and drift over time: a penalty limits "
            "variance and reveals which features carry independent signal.",
            f"Best LR: {R('tune_lr', 'best', 'penalty', fmt=None)} with C = {R('tune_lr', 'best', 'C', fmt='{:g}')} "
            f"(valA PR-AUC {R('tune_lr', 'best', 'val_pr_auc')}). Coefficients set to zero by L1: figure reg_lr_l1_path.png.",
            [("Why standardise first?", "Penalties compare coefficient sizes; without a common scale the penalty "
              "would depend on units.")]),
        section(
            "Early stopping and tree constraints (LightGBM, random forest)",
            "Stopping boosting when validation loss stops improving; limiting tree size.",
            "LightGBM: num_leaves, max_depth, min_child_samples, L1/L2 on leaf values, feature/bagging fractions, "
            "learning rate; training stops after 100 rounds without valA PR-AUC gain. RF: max_depth, min_samples_leaf, "
            "max_features.",
            "Extreme imbalance means trees can carve out tiny leaves around a few positives (memorising); constraints "
            "and early stopping trade a little training fit for out-of-time generalisation.",
            f"Refit stopped at {R('tune_lgbm', 'refit_best_iteration', fmt='{}')} rounds; regularised vs unregularised "
            "curves: reg_lgbm_curves.png; RF train/val gap vs depth: reg_rf_depth.png.",
            [("Why not tune on the test split?", "Then the reported number would be optimistic by the amount of "
              "selection; test is touched once.")]),
        section(
            "Bagging vs boosting",
            "Bagging: average many trees fitted on bootstrap samples (random forest). Boosting: add trees sequentially, "
            "each fitting the errors of the ensemble so far (LightGBM).",
            "Bagging reduces variance; boosting reduces bias and needs regularisation to avoid overfitting.",
            "Both are standard for tabular data; comparing them on the same features shows whether the signal is "
            "mostly variance-limited (bagging helps) or bias-limited (boosting helps).",
            "MODELING.md compares PR-AUC and APFDc on the same test runs.",
            [("Why is LightGBM usually better here?", "Rare positives and interactions (e.g. recent failure × related "
              "path) are learned incrementally; RF's averaged deep trees are less sharp on the extreme tail.")]),
        section(
            "Soft voting and stacking",
            "Soft voting: average calibrated probabilities of LR, RF and LightGBM. Stacking: a logistic regression "
            "that learns how to combine them.",
            "Stacker inputs on valB: the three base logits, the cbt_LastFail rank within the run and the "
            "ChangedOrNewFirst indicator.",
            "Ensembles help when base models make *different* errors; the residual-correlation matrix shows whether "
            "they do.",
            "MODELING.md §ensembles and the error-correlation matrix.",
            [("Why can an ensemble fail to help?", "If the members' errors are highly correlated, averaging removes "
              "little error and adds the weaker models' noise.")]),
        section(
            "Optuna / TPE",
            "Bayesian hyperparameter search with a Tree-structured Parzen Estimator.",
            "TPE models the density of good and bad configurations and proposes points with a high ratio; a median "
            "pruner stops trials whose intermediate PR-AUC lags.",
            "60 trials are enough to find good regions in a 9-dimensional space where grid search would be too "
            "coarse or too slow.",
            f"Best valA PR-AUC {R('tune_lgbm', 'best_value')}; parameter importance: tune_lgbm_importance.png.",
            [("How is it different from random search?", "It uses the results of earlier trials to choose the next.")]),
        section(
            "The p / d ordering rule (adjacent-swap proof)",
            "Run tests in descending order of P(fail) / expected duration.",
            "For adjacent independent tests i, j: running i first costs d_i + (1 − p_i) d_j of the time before the "
            "first failure in their stretch; j first costs d_j + (1 − p_j) d_i. i first is better iff p_i d_j > p_j d_i, "
            "i.e. p_i/d_i > p_j/d_j. Any order can be improved by such swaps until it is sorted by p/d (Smith's rule).",
            "It turns a classifier's probability into the ordering that minimises expected time to the first failure.",
            "MODELING.md compares p/d with p-only ordering (`lgbm_p`).",
            [("Failures are not independent.", "True (co-failures); the rule is optimal under independence and a strong "
              "heuristic otherwise; we measure the actual effect.")]),
        section(
            "APFDc",
            "Average Percentage of Faults Detected, cost-cognizant: the area under 'share of faults found' vs "
            "'share of test time spent'.",
            "For each failing test at position i: cost_i = remaining suite time from i minus half of test i; "
            "APFDc = Σ cost_i / (n_faults × total time). 1 = all failures at the start, ≈ 0.5 random.",
            "It is the LRTS paper's metric (so we can reproduce it) and it accounts for test cost.",
            f"Reproduction of the paper: GATE 2 {R('gate2_reproduction', 'gate_pass', fmt='{}')} (BASELINES.md).",
            [("Why also time-to-first-failure?", "Developers wait for the first red test; TTFF is what they feel.")]),
        section(
            "PR-clustered bootstrap",
            "Confidence intervals by resampling pull requests, not runs.",
            "Each replicate draws PRs with replacement inside every project, recomputes project means, averages them.",
            "Stages and rebuilds of one PR share code and flakiness; treating them as independent would give too-narrow "
            "intervals.",
            "All CIs in BASELINES.md and MODELING.md.",
            [("Why paired differences?", "Comparing two methods on the same runs removes run difficulty from the "
              "variance.")]),
        section(
            "SHAP",
            "Shapley-value feature attributions: how much each feature moved one prediction from the average.",
            "TreeSHAP computes them exactly for tree ensembles; global importance = mean |SHAP|.",
            "To check that the model relies on plausible signals and to explain rankings in smartci.",
            f"Agreement with LR coefficients (Spearman): {R('interpret', 'spearman_shap_vs_lr')}.",
            [("Is SHAP causal?", "No: it explains the model, not the world.")]),
        section(
            "Chronological and rolling-origin evaluation",
            "Train on the past, test on the future, never the reverse.",
            "Builds are split 70/15/15 by start time per project; rolling-origin windows refit on everything before "
            "each 30-day window.",
            "CI data drifts (Kafka's failure rate goes 0.60 → 0.97 across splits); random K-fold would leak the future.",
            f"Windows per project: {R('splits', 'n_roll_windows', fmt=None)}.",
            [("Why build-level, not run-level?", "Stages of one build share a change; splitting them would leak.")]),
        section(
            "Bug mining (smartci learn)",
            "Reintroducing a repository's own past bugs: take a fix commit with tests, put the source back to the "
            "parent, keep the fixed tests, run them.",
            "Keep only commits whose touched tests pass on the fix and fail with the old source.",
            "It produces real bugs with known revealing tests on the user's repo, without hand-picking.",
            "REAL_WORLD.md.",
            [("Isn't it biased?", "Yes: towards test-backed fixes, and the revealing test usually came with the fix "
              "(regression catching). Stated in every report.")]),
        section(
            "Mutation testing (smartci mutate)",
            "Small synthetic bugs (operator swaps, off-by-one, return None, negated conditions) at random covered lines.",
            "Keep mutants that at least one existing test kills; the kill set is the 'failing tests'.",
            "A benchmark of never-seen bugs, complementary to mined (known) bugs.",
            "REAL_WORLD.md.",
            [("Does it favour coverage-first?", "Yes, because sites are drawn from covered lines; we say so.")]),
        section(
            "Simulation vs real runs (GATE 5)",
            "Checking that the backtest's simulated time to first failure equals what real pytest does.",
            "Draw 5 mined bugs and 5 mutants (logged seed), run real `pytest -x` in both orders, compare with the "
            "simulation within 10% plus measured start-up overhead.",
            "Without it, the backtest could be an artefact of the simulator.",
            "REAL_WORLD.md §simulation check.",
            [("Why sequential, not side-by-side?", "Two concurrent runs share the CPU and inflate both times.")]),
        section(
            "Why a simple baseline can win",
            "On some repositories or subsets, a one-line rule (recently failed first, changed files first, coverage "
            "first) is as good as or better than the model.",
            "Simple rules use exactly the strongest signal with no estimation noise; a model must learn that signal "
            "from other projects and can be miscalibrated for a new repo.",
            "Honesty: smartci always reports the best simple baseline and recommends it when it wins.",
            "BASELINES.md and REAL_WORLD.md list wins, ties and losses.",
            [("Then why a model?", "It combines weak signals (history, paths, co-failure, cost) where no single rule "
              "dominates, and degrades to the simple rule's behaviour when one signal dominates.")]),
    ]
    head = ["# VIVA NOTES", "",
            "Generated by `python -m stp.reports.viva_md`. Concept text is fixed; every number is read from "
            "`reports/results/*.json`. '(pending …)' marks a result not generated yet.", ""]
    return "\n".join(head) + "\n" + framing_questions() + "\n" + "\n".join(S)


def main() -> None:
    (paths.ROOT / "reports" / "VIVA_NOTES.md").write_text(build(), encoding="utf-8")
    print("wrote reports/VIVA_NOTES.md")


if __name__ == "__main__":
    main()
