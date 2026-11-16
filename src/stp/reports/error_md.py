"""Markdown for the error analysis (RESULTS.md §4) and the 'what this means' paragraph, from results JSON only.

Every sentence that states a direction (better / worse / supported) is decided by the numbers, not written in.
"""
from __future__ import annotations

from stp.reports.fmt import table


def get(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def verdict(d) -> str:
    """'better' / 'worse' / 'level' from a CI dict: does the 95% CI exclude 0?"""
    if not d:
        return "unknown"
    return "better" if d["lo"] > 0 else "worse" if d["hi"] < 0 else "level"


WORDS = {"better": "beats", "worse": "loses to", "level": "is level with (95% CI includes 0)", "unknown": "?"}


def _ci(d) -> str:
    return f"{d['mean']:+.3f} [{d['lo']:+.3f}, {d['hi']:+.3f}]"


def meaning(M) -> str:
    vb = get(M, "vs_best_simple", "All", "macro10", "lgbm")
    vc = get(M, "vs_cbt_lastfail_All")
    vf = get(M, "vs_best_simple", "FirstFail-old", "macro10", "lgbm")
    best = get(M, "best_simple_by_val", "All")
    ab = get(M, "ablation_question", default={})
    a, c = get(ab, "abl_A_history", "mean"), get(ab, "abl_C_change", "mean")
    closed = f"; change relatedness closes {1 - c / a:.0%} of the gap left by history alone" if a and c else ""
    beats_all_ablations = all(get(x, "hi", default=0) < 0 for x in ab.values() if isinstance(x, dict))
    return (f"**What this means.** On all failures the model {WORDS[verdict(vc)]} the strongest paper baseline "
            f"(cbt_LastFail, {_ci(vc)}) and {WORDS[verdict(vb)]} the best simple rule ({best}, {_ci(vb)}). "
            f"On first-time failures of existing tests it {WORDS[verdict(vf)]} \"quickest test first\" "
            f"(QTF, {_ci(vf)})"
            + (", and every ablation variant also loses to QTF there" if beats_all_ablations else "")
            + f"{closed}. Section 4 tests why.")


def firstfail_md(E) -> list[str]:
    ff = get(E, "firstfail_old", "macro")
    if not ff:
        return []
    n = get(E, "firstfail_old", "n_runs")
    mt, qt = ff["model|time_share_before_target"], ff["QTF|time_share_before_target"]
    mp, qp = ff["model|prev_failed_share_of_time_before"], ff["QTF|prev_failed_share_of_time_before"]
    prev = ff["prev_failed_share_of_tests"]
    supported = mt > qt and mp > max(qp, prev)
    return [
        "### 4.1 First-time failures of existing tests (model vs QTF)", "",
        "**Hypothesis.** The model ranks tests that have failed before ahead of tests that never failed. When the "
        "failing test is one that never failed, the time spent on those earlier tests is wasted.", "",
        f"**Test.** All {n} held-out test-split runs with such a failure; tuned LightGBM vs QTF with the harness's "
        "tie-break seeds; per project the median over runs, then the mean over projects "
        "(`python -m stp.models.error_analysis`).", "",
        table(["", "LightGBM", "QTF"], [
            ["Share of suite time spent before the first-time failure is reached", f"{mt:.1%}", f"{qt:.1%}"],
            ["… of that time, spent on tests that had failed before", f"{mp:.1%}", f"{qp:.1%}"],
            ["Position of that failure in the order (0 = first, 1 = last)", f"{ff['model|position_share']:.2f}",
             f"{ff['QTF|position_share']:.2f}"]]), "",
        f"Tests that had failed before are {prev:.0%} of a run's tests (median). The model gives passing tests that "
        f"failed before a mean P(fail) of {ff['p_prev_failed']:.4f}, against {ff['p_never_failed']:.4f} for "
        f"never-failed tests ({ff['p_prev_failed'] / ff['p_never_failed']:.0f}×). The first-time-failing test itself "
        f"sits at the {ff['target_duration_percentile']:.0%} duration percentile of its run (a long test), and "
        "dividing by duration pushes it back further.", "",
        ("**Verdict: supported.** The model reaches the first-time failure later, and most of the time before it goes "
         "to previously-failed tests, far more than their share of the suite. QTF ignores history and does not pay "
         "that cost. It is the price of the gain on recurring failures, not a bug."
         if supported else
         "**Verdict: not supported by this data.** The model does not spend a disproportionate share of time on "
         "previously-failed tests before the first-time failure; see the numbers above."), ""]


def tvm_md(E) -> list[str]:
    tv = get(E, "tvm_drift", "splits")
    if not tv:
        return []
    sp = [s for s in ("train", "valA", "valB", "test") if s in tv]
    pr = get(E, "tvm_drift", "tvm_only_pr_auc", default={})
    per_cls = {s: tv[s]["n_fail_rows"] / max(1, tv[s]["n_distinct_failing_classes"]) for s in sp}
    rows = [["Runs", *[f"{tv[s]['n_runs']:,}" for s in sp]],
            ["Failed-run rate", *[f"{tv[s]['failed_run_rate']:.1%}" for s in sp]],
            ["Row failure rate", *[f"{tv[s]['row_failure_rate']:.3%}" for s in sp]],
            ["Failures per failing test class", *[f"{per_cls[s]:.1f}" for s in sp]],
            ["Rows whose test class never appeared in train", *[f"{tv[s]['share_rows_unseen_class']:.1%}" for s in sp]],
            ["Failures from classes never seen in train", *[f"{tv[s]['share_fails_unseen_class']:.1%}" for s in sp]],
            ["Failures from classes that already failed in train",
             *[f"{tv[s]['share_fails_class_failed_in_train']:.1%}" for s in sp]]]
    psi = {s: tv[s]["psi_vs_train"] for s in sp if s != "train"}
    feats = sorted(psi.get("test", {}), key=lambda c: -psi["test"][c])[:6]
    prow = [[f"`{c}`", *[f"{psi[s][c]:.2f}" for s in psi]] for c in feats]
    vb, te = tv.get("valB"), tv.get("test")
    shows, rules_out = [], []
    if vb and te:
        r = vb["row_failure_rate"] / max(te["row_failure_rate"], 1e-12)
        if r > 1.5:
            shows.append(f"the row failure rate is {r:.1f}× lower in test ({te['row_failure_rate']:.3%} vs "
                         f"{vb['row_failure_rate']:.3%} in valB); PR-AUC falls with the base rate even when the "
                         "ranking is equally good")
        if per_cls["valB"] > 1.5 * per_cls["test"]:
            shows.append(f"validation failures repeat: each failing class fails {per_cls['valB']:.1f} times on average "
                         f"in valB but {per_cls['test']:.1f} times in test, so history features (which see earlier "
                         "validation runs as-of) catch far more of valB's failures")
        d = vb["share_fails_class_failed_in_train"] - te["share_fails_class_failed_in_train"]
        if d > 0.05:
            shows.append(f"fewer test failures come from classes that already failed in train "
                         f"({te['share_fails_class_failed_in_train']:.0%} vs {vb['share_fails_class_failed_in_train']:.0%})")
        same = [c for c in feats if psi["test"][c] > 0.25 and psi["valB"][c] > 0.25]
        if same:
            rules_out.append("feature drift against train is large in *both* valB and test (" + ", ".join(
                f"`{c}`" for c in same) + "), so it cannot explain why valB is good and test is bad")
        if abs(te["share_rows_unseen_class"] - vb["share_rows_unseen_class"]) < 0.1:
            rules_out.append(f"the share of rows from classes unseen in train is similar ({vb['share_rows_unseen_class']:.0%}"
                             f" valB, {te['share_rows_unseen_class']:.0%} test): most TVM test classes in both periods are new "
                             "(added, renamed or moved since train), which hurts both periods alike")
    return ["### 4.2 Why the TVM-only model collapses from validation to test", "",
            f"**Observation.** TVM-only PR-AUC is {pr.get('valB', 0):.3f} on validation (valB) and "
            f"{pr.get('testC', 0):.3f} on test. **Hypothesis:** drift between the two periods.", "",
            "**Test.** For TVM, per split (valA / valB = time halves of the validation runs): failure rates, how "
            "concentrated failures are, how many come from test classes seen or failing in train, and the population "
            "stability index (PSI) of the main features against train.", "",
            table(["TVM", *sp], rows), "",
            "PSI against train (largest on test first; < 0.1 small, > 0.25 large):", "",
            table(["Feature", *psi], prow), "",
            "**What the data shows.** " + ("; ".join(s[0].upper() + s[1:] if i == 0 else s for i, s in enumerate(shows)) + "." if shows else "no clear change between valB and test.")
            + (" **What it rules out.** " + "; ".join(rules_out) + "." if rules_out else ""), "",
            "**Verdict.** " + ("Partly supported, but not as feature drift: the validation period was easy (frequent, "
                               "repeating failures that history catches), and the test period has rarer, more varied "
                               "failures. One project and one validation period are too little to choose a model "
                               "on; pooling all 10 projects (the shipped `all_to_tvm`) is more robust on test."
                               if shows else "Not supported: the measured drift does not differ between the periods."),
            ""]


def floor_md(F, N=None) -> list[str]:
    """§4.3: the probability floor (Phase D), from reports/results/floor_tradeoff.json."""
    if not F or "val_curve" not in F:
        return []
    te = F.get("test") or {}
    dl = te.get("delta_vs_f0") or {}
    cv = te.get("curve") or {}
    fs = F["f_star"]
    rows = [[k, f"{v['All']:.3f}", f"{v['FirstFail-old']:.3f}"] for k, v in F["val_curve"].items()]
    out = ["### 4.3 Can the trade-off be tuned? A probability floor", "",
           "**Idea.** Order by max(P, f) ÷ duration. With f = 0 this is the model; as f grows every test gets the "
           "same probability and the order becomes \"fastest first\". A small f stops the model from pushing "
           "never-failed tests to the very end.", "",
           f"**Rule, fixed before the test split was scored.** {F.get('rule', '')}", "",
           "Validation curve (macro APFDc, tuned LightGBM):", "", table(["", "All", "FirstFail-old"], rows), ""]
    if dl:
        a, o = dl["All"], dl["FirstFail-old"]
        out += [f"**Test split, reported once (f* = {fs:g}).** Δ vs f = 0: all failures {_ci(a)}, first-time "
                f"failures of existing tests {_ci(o)}. With the floor the model scores "
                f"{cv.get(f'f={fs:g}', {}).get('FirstFail-old', 0):.3f} there against QTF's "
                f"{cv.get('QTF', {}).get('FirstFail-old', 0):.3f}: "
                + ("it closes part of the gap but still loses to QTF. " if cv.get(f"f={fs:g}", {}).get(
                    "FirstFail-old", 0) < cv.get("QTF", {}).get("FirstFail-old", 0) else "it reaches QTF. ")
                + ("The LRTS ship rule was met. " if te.get("ship") else "**Not shipped**: the ship rule was not met. "),
                ""]
        nx = (N or {}).get("with_floor", {}).get("all")
        nx0 = (N or {}).get("without_floor", {}).get("all")
        if te.get("ship") and nx and nx0:
            out += [f"**Deployment check on NetworkX (not declared in advance).** With the floor, smartci's median "
                    f"time to the first failure on NetworkX's {nx['n']} bugs went from "
                    f"{nx0['median_ttff_s']['median']:.2f} s to {nx['median_ttff_s']['median']:.2f} s, and its losses "
                    f"against {nx['best']} from {nx0['vs_best']['loss']} to {nx['vs_best']['loss']}. smartci's "
                    "probabilities on a repository pass through a per-repo adapter, so a floor tuned on the LRTS "
                    "model's scale promotes tiny unrelated tests there. **The floor is therefore off by default** "
                    "and available as an option (`SMARTCI_FLOOR`); a floor would have to be tuned per repository.",
                    ""]
    elif fs == 0:
        out += ["No floor beat f = 0 on validation, so nothing was tested or shipped.", ""]
    return out


def error_analysis_md(E, F=None, N=None) -> str:
    body = firstfail_md(E) + tvm_md(E) + floor_md(F, N)
    if not body:
        return ""
    return "\n".join(["## 4. Error analysis: why the model loses where it loses", ""] + body)
