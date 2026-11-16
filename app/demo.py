"""smartci demo (Streamlit): eight pages, offline, reading only demo_bundle/ (ML Lab and Break the code also compute live).

Run:  streamlit run app/demo.py
Every number comes from files in demo_bundle/ (built by `python -m stp.demo.build_bundle` from reports/results,
reports/figures and the smartci outputs). The 'Predict live' page runs the real packaged model (no precomputed
answers) through the same function as `smartci rank --files`.
"""
from __future__ import annotations

import io
import json
import random
from pathlib import Path

import sys

import matplotlib

if str(Path(__file__).resolve().parents[1] / "src") not in sys.path:   # works without `pip install -e .` (hosting)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
matplotlib.use("Agg")
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from stp.reports.colors import label  # noqa: E402
from stp.reports.error_md import firstfail_md, floor_md, meaning, tvm_md, verdict  # noqa: E402
from stp.reports.fmt import HEADLINE, NAME, QUESTION  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "demo_bundle"
FIGS = BUNDLE / "figures"
SUBSETS = {"All": "all failed runs", "FirstFail-asof": "first-time failures (any test)",
           "FirstFail-old": "first-time failures of existing tests", "New/Edited": "failures of new or edited tests"}


# ------------------------------------------------------------------------------------------------- data helpers
@st.cache_data
def load_json(path: str):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def R(name: str) -> dict:
    """A results JSON copied into the bundle (reports/results/<name>.json)."""
    return load_json(str(BUNDLE / "results" / f"{name}.json")) or {}


def get(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def ci(x: dict | None, d: int = 3, sign: bool = False) -> str:
    if not x or x.get("mean") is None:
        return "–"
    f = f"{{:{'+' if sign else ''}.{d}f}}"
    return f"{f.format(x['mean'])} [{f.format(x['lo'])}, {f.format(x['hi'])}]"


def fig(name: str, caption: str | None = None):
    f = FIGS / f"{name}.png"
    if f.exists():
        st.image(str(f), caption=caption, width="stretch")
    else:
        st.warning(f"Figure {name}.png is missing from demo_bundle/figures.")


def why(text: str):
    st.info(f"**Why we chose this.** {text}")


def jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def decode(rec: dict) -> dict:
    names = rec["names"]
    rec["tests"] = {n: {"duration_s": d, "fail": bool(f)} for n, d, f in zip(names, rec["duration_s"], rec["fail"])}
    for r in rec["methods"].values():
        r["order"] = [names[i] for i in r["order"]]
    return rec


def nx_backtest() -> dict:
    return load_json(str(BUNDLE / "repos" / "networkx" / "backtest.json")) or {}


# ------------------------------------------------------------------------------------------------- 1 overview
def page_overview():
    st.title(NAME)
    st.markdown("**The problem.** A CI run executes hundreds or thousands of tests in a fixed order. When a change "
                "breaks something, the failing test is often near the end, so the developer waits for most of the "
                "suite before seeing red. If we can predict which tests are likely to fail for *this* change, we can "
                "run them first: the same tests, nothing skipped, only the order changes.")
    st.subheader("What we built")
    st.graphviz_chart("""
digraph { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#f4f4f4", fontsize=10];
  lrts [label="LRTS dataset\\n108,366 CI runs\\n10 Apache projects"];
  feat [label="25 as-of features\\n(history, cost,\\nchange, co-failure)"];
  clf  [label="classifiers\\nLR · RF · LightGBM\\nvoting · stacking"];
  ord  [label="order tests by\\nP(fail) ÷ duration"];
  ev   [label="evaluate vs\\nsimple rules\\n(APFDc, CIs)"];
  exp  [label="export model"];
  tool [label="smartci\\npytest plugin + CLI"];
  nx   [label="NetworkX\\nreal bugs + mutants"];
  lrts -> feat -> clf -> ord -> ev; clf -> exp -> tool -> nx; }
""")
    L, C, M = R("labels"), R("models_classification"), R("models")
    nx = get(R("real_world"), "networkx", "backtest_summary", "all", default={})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tests that fail, per (run, test class)", f"{get(L, 'pooled', 'pos_rate_fail', default=0):.3%}",
              help="LRTS, all 104M rows: failures are rare, which shapes every modelling choice.")
    best_m = max(("lr", "rf", "lgbm", "vote", "stack"), key=lambda m: get(C, "models", m, "pr_auc", default=0))
    c2.metric("Best model PR-AUC (held-out rows)", f"{get(C, 'models', best_m, 'pr_auc', default=0):.3f}",
              help=f"{label(best_m)}; a random ranking scores the base rate, {C.get('base_rate', 0):.2%}.")
    d = get(M, "vs_best_simple", "All", "macro10", "lgbm")
    c3.metric("Model − best simple rule, all failures (APFDc)",
              (f"{d['mean']:+.3f}" + (" (tie)" if verdict(d) == "level" else "")) if d else "–",
              help=f"95% CI {ci(d, sign=True)}: {'a tie (CI includes 0)' if verdict(d) == 'level' else verdict(d)}. "
                   f"Best simple rule: {get(M, 'best_simple_by_val', 'All')}.")
    q = nx_queue_medians()
    c4.metric("NetworkX: failing file's queue position (median)",
              f"{q['default']:.0f} → {q['smartci']:.0f}" if q else "–",
              help=f"Out of {q.get('n_files')} test files, pytest's default order vs smartci, {q.get('n')} real mined "
                   "bugs. Test time and end-to-end time for each bug are on 'Break the code'.")
    st.markdown(f"**The question we tested.** {QUESTION}  \n**The answer.** {HEADLINE}")


# ------------------------------------------------------------------------------------------------- 2 ML pipeline
def tab_eda():
    L, A, B, G = R("labels"), R("eda/audit"), R("eda/B_costs"), R("gate2_reproduction")
    st.markdown("We first looked at what the data can and cannot support. Failures are rare, suites are long, and "
                "simple history rules that do well on repeat failures collapse on tests that fail for the first time.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CI runs", f"{get(A, 'runs', 'full_dataset_csv_rows', default=0):,}")
    c2.metric("(run, test class) rows", f"{get(L, 'pooled', 'rows', default=0):,}")
    c3.metric("Failure rate per row", f"{get(L, 'pooled', 'pos_rate_fail', default=0):.3%}")
    c4.metric("First-time-failure rate per row", f"{get(L, 'pooled', 'pos_rate_ftf_asof', default=0):.4%}")
    st.markdown(f"**Label imbalance.** About 1 row in {1 / get(L, 'pooled', 'pos_rate_fail', default=1):.0f} is a "
                "failure, so a model that always says 'pass' is "
                f"{get(L, 'pooled', 'always_pass_accuracy', default=0):.2%} accurate and useless.")
    fig("B_duration_cdf", "Suite durations: most runs take hours, so finding the failure early matters.")
    st.markdown(f"Median suite duration (macro over projects): "
                f"**{get(B, 'full', 'duration_h_median', 'macro', default=0):.1f} h**; median "
                f"{get(B, 'full', 'classes_per_run_median', 'macro', default=0):.0f} test classes per run.")
    fig("A_headline_all_vs_firstfail", "The paper's history rules on all failures vs first-time failures.")
    lf = get(G, "macro", "as_of")
    if lf:
        st.markdown(f"**The collapse.** 'Last failed first' scores APFDc {lf['All']['LastFail_Asc']:.3f} on all "
                    f"failures but {lf['FirstFail']['LastFail_Asc']:.3f} on first-time failures, while "
                    f"'quickest first' (QTF) goes from {lf['All']['QTF']:.3f} to {lf['FirstFail']['QTF']:.3f}. "
                    "History helps only when the failure has happened before.")
    with st.expander("More EDA figures"):
        for n in ("C_runs_per_project", "D_failure_frequency_tail", "D_first_time_failures", "G_time_to_first_failure",
                  "F_overlap_lift"):
            fig(n)
    why("Imbalance decided the metric (PR-AUC, not accuracy); long suites decided the target (time to first "
        "failure, APFDc); the first-time-failure collapse decided the hard test case we report separately.")


def tab_features():
    U, FM = R("univariate"), R("features_meta")
    st.markdown("Every feature is computed **as-of**: a run sees only results of runs that had *finished* when it "
                "started. The 25 model features come in four groups.")
    groups = {}
    for name, m in (FM.get("features") or {}).items():
        groups.setdefault(m["group"], []).append(name)
    st.table(pd.DataFrame([{"group": g, "what it captures": (FM.get("asof") or {}).get(g, ""),
                            "# features": len(v)} for g, v in groups.items()]))
    rows = []
    for name, m in (U.get("features") or {}).items():
        base = name.split("_", 1)[1] if name.startswith(("h_", "hs_")) else name
        doc = (FM.get("doc") or {}).get(base, ["", ""])
        rows.append({"feature": name, "group": get(FM, "features", name, "group", default=""),
                     "single-feature PR-AUC": m["pr_auc"], "on first-time failures": m["pr_auc_ftf"],
                     "mutual information": m["mutual_info"], "meaning": doc[0]})
    if rows:
        st.markdown(f"**Measured signal of each feature alone** (training sample; random = "
                    f"{U.get('base_rate_weighted', 0):.4f}). Note how history features carry no signal for "
                    "first-time failures.")
        st.dataframe(pd.DataFrame(rows).sort_values("single-feature PR-AUC", ascending=False), hide_index=True,
                     height=320)
    fig("features_univariate")
    st.markdown("**Rejected features**")
    for a, b in FM.get("rejected") or []:
        st.markdown(f"- **{a}**: {b}")
    why("Each group answers a different question: has it failed before (history), how expensive is it (cost), "
        "is it related to this change (change), and did it fail when these files changed before (co-failure).")


def tab_classification():
    C = R("models_classification")
    st.markdown("Three classifiers predict P(this test fails in this run): logistic regression (linear, "
                "interpretable), random forest (bagging of trees) and LightGBM (boosted trees). All are trained on "
                "older builds and tested on newer ones.")
    fig("cls_models")
    rows = [{"model": label(m), "PR-AUC": get(C, "models", m, "pr_auc"), "ROC-AUC": get(C, "models", m, "roc_auc"),
             "Brier": get(C, "models", m, "brier"), "accuracy at best-F1 threshold": get(C, "models", m, "accuracy_test"),
             "F1": get(C, "models", m, "f1_test")} for m in ("lr", "rf", "lgbm")]
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.markdown(f"**Why accuracy is the wrong metric.** On these test rows only {C.get('base_rate', 0):.2%} fail, so "
                f"always predicting 'pass' is {C.get('always_pass_accuracy', 0):.2%} accurate and finds no failure. "
                "PR-AUC measures how well the failures are ranked above the passes, and a random ranking scores "
                "the base rate.")
    why("LR is the transparent baseline, RF tests bagging, LightGBM tests boosting; PR-AUC is the primary metric "
        "because positives are rare.")


def tab_regularization():
    LR, RF, GB = R("tune_lr"), R("tune_rf"), R("tune_lgbm")
    st.markdown("Regularization stops a model from memorising its training data. We controlled it differently "
                "for each model and chose the strength on validation data, never on test data.")
    c1, c2 = st.columns(2)
    with c1:
        fig("reg_lr_C", "Logistic regression: validation PR-AUC across strengths C (small C = strong penalty).")
    with c2:
        fig("reg_lr_l1_path", "L1 sets coefficients to exactly zero as the penalty grows.")
    z = LR.get("l1_zeroed_by_C") or {}
    if z:
        st.dataframe(pd.DataFrame([{"C": k, "coefficients set to zero by L1": len(v)} for k, v in z.items()]),
                     hide_index=True)
    b = LR.get("best") or {}
    st.markdown(f"Chosen: **{b.get('penalty')}**, C = {b.get('C')}, validation PR-AUC {b.get('val_pr_auc', 0):.3f}, "
                f"{b.get('n_zero_coef')} coefficients at zero.")
    c1, c2 = st.columns(2)
    with c1:
        fig("reg_rf_depth", "Random forest: deeper trees fit training data better but stop helping validation.")
    with c2:
        fig("reg_lgbm_curves", "LightGBM: train vs validation PR-AUC by boosting round, unregularised vs tuned.")
    rb = RF.get("best") or {}
    st.markdown(f"Random forest chosen depth {rb.get('max_depth')}, min samples per leaf {rb.get('min_samples_leaf')}: "
                f"train PR-AUC {rb.get('train_pr_auc_weighted', 0):.3f} vs validation {rb.get('val_pr_auc', 0):.3f}. "
                f"LightGBM uses L1 = {get(GB, 'best_params', 'lambda_l1', default=0):.4f}, "
                f"L2 = {get(GB, 'best_params', 'lambda_l2', default=0):.3f}, feature and row subsampling, and early "
                f"stopping (best round {GB.get('refit_best_iteration')}).")
    why("The gap between train and validation curves is the overfitting we are controlling; the unregularised "
        "LightGBM curve shows validation PR-AUC falling while training PR-AUC climbs.")


def tab_tuning():
    GB = R("tune_lgbm")
    st.markdown(f"LightGBM was tuned with Optuna (TPE, {len(GB.get('trials', []))} trials) on "
                f"{GB.get('train_rows_tuning', 0):,} training rows, scored by validation PR-AUC, with early stopping "
                f"(patience {GB.get('patience_tuning')}) and pruning of poor trials.")
    c1, c2 = st.columns(2)
    with c1:
        fig("tune_lgbm_history", "Trial history: best validation PR-AUC so far.")
    with c2:
        fig("tune_lgbm_importance", "Which hyperparameters mattered.")
    fig("tune_lgbm_slice")
    st.markdown("**Best parameters**")
    st.dataframe(pd.DataFrame([GB.get("best_params") or {}]), hide_index=True)
    st.markdown(f"Best validation PR-AUC {GB.get('best_value', 0):.3f}; refit on {GB.get('train_rows_refit', 0):,} rows.")
    why("Validation is split by time (validation builds come after training builds, test builds after validation), "
        "because a model is always used on future builds; a random split would leak the future into training.")


def tab_ensembles():
    C, M, CAL = R("models_classification"), R("models"), R("calibration")
    st.markdown("Random forest is **bagging** (many trees on resampled data, averaged); LightGBM is **boosting** "
                "(trees added one by one to fix earlier errors). We also combined all three: **soft voting** "
                "averages their probabilities, **stacking** learns weights with a small logistic regression.")
    fig("ens_vs_base")
    rows = [{"model": label(m), "PR-AUC": get(C, "models", m, "pr_auc"),
             "APFDc all failures [95% CI]": ci(get(M, "cells", "All", "macro10", m, "apfdc")),
             "APFDc first-time failures of existing tests": ci(get(M, "cells", "FirstFail-old", "macro10", m, "apfdc"))}
            for m in ("lr", "rf", "lgbm", "vote", "stack")]
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    fig("ensemble_error_corr", "Correlation of the models' errors: high correlation means they make the same mistakes.")
    ec = C.get("error_corr") or {}
    if ec:
        n = ec["names"]
        i, j = n.index("lgbm"), n.index("rf")
        st.markdown(f"The residuals of LightGBM and random forest correlate at {ec['residual_corr'][i][j]:.2f}: the "
                    "models share the same signal (mostly history), so combining them adds little.")
    if CAL.get("stack_coef"):
        st.caption("Stacking weights: " + ", ".join(f"{k} {v:+.2f}" for k, v in CAL["stack_coef"].items()))
    why("Ensembles help when members make different errors. Here they do not, which is itself a result we can "
        "explain from the error-correlation matrix.")


def tab_performance():
    C, M = R("models_classification"), R("models")
    st.markdown("Performance has two levels: how well the model **ranks rows** (classification metrics) and how "
                "early the resulting **order finds failures** (APFDc: 1 = failures first, 0.5 ≈ random).")
    at = get(C, "models", "lgbm", "at_k", "macro", default={})
    st.dataframe(pd.DataFrame([{"k": k, "precision@k": at.get(f"p@{k}"), "recall@k": at.get(f"r@{k}")}
                               for k in (10, 50, 100)]), hide_index=True)
    st.caption("LightGBM, per failed run, macro over projects: the top 10 test classes contain about half of a "
               "run's failures.")
    fig("calibration_reliability", "Calibration: predicted probability vs observed failure rate, before and after "
        "isotonic calibration.")
    fig("perf_apfdc_forest")
    rows = []
    for sub in SUBSETS:
        best = get(M, "best_simple_by_val", sub)
        d = get(M, "vs_best_simple", sub, "macro10", "lgbm")
        rows.append({"subset": SUBSETS[sub], "best simple rule": best,
                     "rule APFDc": ci(get(M, "cells", sub, "macro10", best, "apfdc")),
                     "LightGBM APFDc": ci(get(M, "cells", sub, "macro10", "lgbm", "apfdc")),
                     "Δ [95% CI]": ci(d, sign=True), "verdict": {"better": "model wins", "worse": "model loses",
                                                                "level": "tie"}.get(verdict(d), "?")})
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    fig("shap_global", "What drives the model (SHAP): history features dominate.")
    why("APFDc is the measure the LRTS paper uses, so our baselines are comparable with published numbers; CIs "
        "resample pull requests, because builds of one PR are not independent.")


def page_pipeline():
    st.header("The ML pipeline: seven rubric items")
    st.caption("Each tab: what was done, the figure, the key numbers, and why we chose it. Numbers come from "
               "reports/results; figures from reports/figures.")
    tabs = st.tabs(["1 EDA", "2 Features", "3 Classification", "4 Regularization", "5 Tuning", "6 Ensembles",
                    "7 Performance"])
    for t, fn in zip(tabs, (tab_eda, tab_features, tab_classification, tab_regularization, tab_tuning, tab_ensembles,
                            tab_performance)):
        with t:
            fn()


# ------------------------------------------------------------------------------------------------- 3 predict live
@st.cache_resource
def _live():
    from stp.demo import live
    return live


@st.cache_data(show_spinner="Scoring every NetworkX test file with the packaged model…")
def _rank(files: tuple[str, ...], additions: int, deletions: int):
    live = _live()
    rows = live.live_rank(list(files), additions, deletions)
    return rows, live.baselines(rows)


def page_predict():
    st.header("Predict live")
    st.markdown("Pick up to five NetworkX source files you might change. The app builds a change from those paths, "
                "computes the features with smartci's own functions, scores every NetworkX test file with the real "
                "packaged model, and ranks them. Nothing on this page is precomputed.")
    st.warning("The change contains **file paths only, no patch text**. Without a patch, line-level coverage and the "
               "diff's words are unavailable; the change size uses the median of NetworkX's own bug fixes unless "
               "you set it.")
    live = _live()
    meta = live.meta()
    from smartci.whatif import typical_size
    ta, td = typical_size(live.LIVE)
    files = st.multiselect("NetworkX source files (1–5)", meta["sources"], max_selections=5,
                           default=["networkx/algorithms/flow/maxflow.py"])
    c1, c2 = st.columns(2)
    add = c1.number_input("lines added", 0, 5000, ta)
    dele = c2.number_input("lines removed", 0, 5000, td)
    if not files:
        st.info("Pick at least one file.")
        return
    rows, base = _rank(tuple(files), int(add), int(dele))
    model = rows[0]["model"] if rows else "-"
    st.caption(f"Model used: `{model}`" + (" (cold start: fewer than 5 recorded CI runs for NetworkX, so the "
                                          "history and co-failure features are not used)" if model == "model_coldstart"
                                          else "") + ". A per-repo adapter, fitted on older NetworkX bugs, rescales "
               "the probability and adds the coverage signal.")
    left, right = st.columns([3, 2])
    with left:
        st.subheader("smartci's order")
        df = pd.DataFrame([{"rank": r["rank"], "test file": r["test_file"].replace("networkx/", ""),
                            "P(fail)": r["p_fail"], "expected s": r["expected_duration_s"], "priority": r["priority"],
                            "covers change": r["covers_change"], "top reasons": " · ".join(r["reasons"])}
                           for r in rows])
        st.dataframe(df, hide_index=True, height=420,
                     column_config={"P(fail)": st.column_config.NumberColumn(format="%.4f"),
                                    "priority": st.column_config.NumberColumn(format="%.4f"),
                                    "expected s": st.column_config.NumberColumn(format="%.2f")})
        st.caption("priority = P(fail) ÷ (expected seconds + 0.001): a likely-failing quick test goes first.")
    with right:
        st.subheader("Simple rules, same change")
        n = st.slider("show the first", 5, 30, 10)
        st.markdown("**changed files first**")
        st.dataframe(pd.DataFrame({"rank": range(1, n + 1), "test file": [t.replace("networkx/", "") for t in
                                                                          base["changed_files_first"][:n]]}),
                     hide_index=True)
        st.markdown("**fastest first**")
        st.dataframe(pd.DataFrame({"rank": range(1, n + 1), "test file": [t.replace("networkx/", "") for t in
                                                                          base["fastest_first"][:n]]}),
                     hide_index=True)
    st.markdown("**Same scores from the command line** (the test suite checks they are equal):")
    st.code(live.command(files, int(add), int(dele)), language="bash")


# ------------------------------------------------------------------------------------------------- 5 results
def page_results():
    st.header("Results: where ML wins and where it loses")
    M, W = R("models"), R("wtl")
    st.markdown(meaning(M))
    rows = []
    for sub in SUBSETS:
        best = get(M, "best_simple_by_val", sub)
        d = get(M, "vs_best_simple", sub, "macro10", "lgbm")
        w = get(W, "subsets", sub, f"lgbm|{best}", default={})
        rows.append({"subset": SUBSETS[sub], "best simple rule (chosen on validation)": best,
                     "rule APFDc": ci(get(M, "cells", sub, "macro10", best, "apfdc")),
                     "LightGBM APFDc": ci(get(M, "cells", sub, "macro10", "lgbm", "apfdc")),
                     "Δ [95% CI]": ci(d, sign=True),
                     "verdict": {"better": "ML wins", "worse": "ML loses", "level": "tie"}.get(verdict(d), "?"),
                     "runs won / tied / lost": f"{w.get('win')} / {w.get('tie')} / {w.get('loss')}" if w else "–"})
    st.subheader("LRTS scoreboard (held-out test period, macro over 10 projects)")
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.caption("Win/tie/loss counts are pooled over runs (Kafka has most runs); the Δ and its CI are macro over "
               "projects, so the two can point in different directions. A tie is |ΔAPFDc| < "
               f"{W.get('tie_threshold', 0.001)}.")
    fig("perf_apfdc_forest")
    bt = get(R("real_world"), "networkx", "backtest_summary", default={})
    if bt:
        st.subheader("NetworkX (real repository, smartci tool)")
        su = nx_startup_s()
        for kind, s in bt.items():
            q = nx_queue_medians(None if kind == "all" else kind)
            st.markdown(f"**{kind}** (n = {s['n']}): best simple rule **{s['best_simple_baseline']}**. "
                        f"{s['recommendation']}")
            st.dataframe(pd.DataFrame([{"order": label(m),
                                        "failing file's queue position (median)": q.get(m),
                                        "test s until it fails, median [95% CI]":
                                        f"{v['median']:.2f} [{v['lo']:.2f}, {v['hi']:.2f}]",
                                        "end-to-end s (+ measured start-up)": round(v["median"] + su, 1),
                                        "mean APFDc": s["mean_apfdc"].get(m),
                                        "smartci wins / ties / losses": "–" if m not in s["vs_smartci"] else
                                        "{win} / {tie} / {loss}".format(**s["vs_smartci"][m])}
                                       for m, v in sorted(s["median_ttff_s"].items(), key=lambda kv: kv[1]["median"])]),
                         hide_index=True)
    E = R("error_analysis")
    st.subheader("Why the model loses where it loses")
    fig("error_firstfail")
    st.markdown("\n".join(firstfail_md(E)))
    with st.expander("Why the TVM-only model collapsed from validation to test"):
        st.markdown("\n".join(tvm_md(E)))
    F = R("floor_tradeoff")
    if F.get("val_curve"):
        st.subheader("Can the trade-off be tuned? A probability floor")
        fig("tradeoff_floor")
        st.markdown("\n".join(floor_md(F, R("floor_networkx"))[2:]))
    v = R("verdict_networkx")
    if v:
        st.subheader("What `smartci evaluate` tells the NetworkX team")
        med = v["median_s"]
        st.code("\n".join([
            f"Evidence: {v['n_bugs']} reproducible bugs, {v['n_test_files']} test files",
            f"Median seconds of testing until the first failure:",
            f"  pytest default order   {med['default']:8.2f} s",
            f"  {v['best_simple_rule']:22s} {med[v['best_simple_rule']]:8.2f} s",
            f"  smartci                {med['smartci']:8.2f} s",
            f"smartci vs {v['best_simple_rule']}: {v['vs_best']['win']} wins / {v['vs_best']['tie']} ties / "
            f"{v['vs_best']['loss']} losses",
            f"RECOMMENDATION: {v['recommendation']}",
            f"pytest start-up and collection ({v['startup_s']:.0f} s) comes on top for every order"
            if v.get("startup_s") else ""]), language="text")
        st.caption("The tool recommends the simple rule when the model does not clearly win, and can run it: "
                   f"`pytest --smartci --smartci-rule {v['recommendation']}`.")
    st.subheader("What a team should actually use")
    st.success("On a small Python repository like NetworkX, a simple rule (changed files first, or coverage first) "
               "is enough: it reaches the first failure about as fast as the model. On long suites with recurring "
               "failures, the model adds a modest gain over the best simple rule. For tests failing for the first "
               "time, 'fastest first' is better than the model. In every case, any of these orders beats pytest's "
               "default order by a wide margin.")


# ------------------------------------------------------------------------------------------------- 6 limits
def page_limits():
    st.header("Limits and honesty")
    st.markdown("""
**Real**
- LRTS test durations and outcomes: 108,366 CI runs of 10 Apache projects.
- NetworkX test durations (measured by `smartci profile`), the failing tests of each bug, and every `smartci compare` run.
- The 'Predict live' page runs the real packaged model now.

**Replayed (simulated from real measurements)**
- Every race lane adds up *measured* durations in a given order, as if tests run one after another.
- NetworkX lanes include pytest's per-test overhead but not start-up and collection.
- `smartci compare` checks this against real pytest runs (GATE 5). The last check was measured on battery, with a
  throttled CPU, and failed; it is pending a re-run on mains power (REAL_WORLD.md).

**Caveats, one line each**
- Mined NetworkX bugs are past bugs reintroduced; the revealing test usually came with the fix (regression catching).
- Mutants are synthetic one-line changes, drawn from covered lines, which favours coverage-first.
- The model was trained on Apache CI data (9 Java/Scala projects + TVM's Python suites), never on NetworkX.
- The headline LightGBM numbers are the tuned model; smartci ships the all-projects variant (disclosed choice).
- The TVM-only variant looked best on validation and collapsed on test; it was not shipped.
- LRTS has test-class granularity and no execution order; 'default' there is a random order.
- Models are evaluated at one time origin; small projects have few test runs, so only the macro is interpreted.
- On a ~1 s suite, smartci's own start-up (imports, git diff, scoring) can cost more than it saves.
- A second repository (sympy) was attempted and not completed; no result from it is shown.

**Data licences.** LRTS (MIT), NetworkX (BSD-3-Clause), Apache projects (Apache-2.0).

**Reports.** `reports/RESULTS.md`, `MODELING.md`, `FEATURES.md`, `BASELINES.md`, `REAL_WORLD.md`, `AUDIT.md`,
`VIVA_NOTES.md`.
""")




# ------------------------------------------------------------------------------------------------- NetworkX helpers
def nx_profile() -> dict:
    return load_json(str(BUNDLE / "repos" / "networkx" / "profile.json")) or {}


def nx_profile_order() -> list[str]:
    return nx_profile().get("default_order", [])


def nx_startup_s() -> float:
    """Median measured pytest start-up + collection on this laptop (profile runs: wall time minus test time)."""
    o = sorted(x for x in nx_profile().get("overhead_s") or [] if x is not None)
    return float(o[len(o) // 2]) if o else 0.0


def nx_queue_medians(kind: str | None = "mined") -> dict:
    """Median queue position of the first failing test file per order (= length of the stored order prefix)."""
    bt = nx_backtest()
    bugs = [b for b in bt.get("bugs", []) if b.get("prefix") and (kind is None or b["kind"] == kind)]
    if not bugs:
        return {}
    out = {"n": len(bugs), "n_files": bt.get("n_test_files")}
    for m in bugs[0]["prefix"]:
        v = sorted(len(b["prefix"][m]) for b in bugs if m in b["prefix"])
        out[m] = v[len(v) // 2]
    return out


# ------------------------------------------------------------------------------------------------- 0 start here
def page_start():
    M = R("models")
    st.title("smartci")
    st.markdown("### Run the tests most likely to fail first, so a broken change turns red sooner.")
    st.markdown("""
**The idea in everyday words.** You have lost your keys. You don't search the house room by room in a fixed order:
you look first where you last had them. smartci does the same for software tests: when code changes, it runs first
the tests related to that change or that broke recently. **Every test still runs; only the order changes.**
""")
    st.markdown("""
**How to walk through this demo**
1. **ML Lab**: train logistic regression, a random forest or LightGBM *now*, on real CI rows, and see the four
   lessons that shaped the project (accuracy trap, overfitting, random-split leakage, which features matter).
2. **Real PRs**: replays of real recorded Apache Kafka and TVM builds the model never saw: where the first failing
   test sat in each order, how many test minutes came before it, and the model's top 10 with reasons. Losses included.
3. **Break the code**: a real NetworkX bug put back into today's code; two real pytest processes, a real stopwatch.
4. **Results** and **Limits and honesty**: the full scoreboard and every caveat.
""")
    d = get(M, "vs_best_simple", "All", "macro10", "stack")
    f = get(M, "vs_best_simple", "FirstFail-old", "macro10", "lgbm")
    kp = get(d or {}, "per_project", default={})
    st.subheader("The honest verdict")
    st.markdown(f"""
1. **The model helps on large projects with long history.** On held-out Kafka and TVM builds the stacked model beats
   the best simple rule (ΔAPFDc {kp.get('kafka', 0):+.3f} on Kafka, {kp.get('tvm', 0):+.3f} on TVM; macro over all
   ten projects {ci(d, sign=True)}).
2. **On a small Python repository, a simple rule is enough.** On NetworkX, 'changed files first' finds the failing
   test about as early as the model (see *Break the code* and *Results*).
3. **It loses on first-time failures.** For tests that have never failed before, 'fastest first' beats the model
   ({ci(f, sign=True)} APFDc). `smartci evaluate` tells each team which order wins on *their* code.
""")
    with st.expander("For the technical audience: the pipeline and four headline numbers"):
        page_overview()


# ------------------------------------------------------------------------------------------------- ML Lab
@st.cache_resource(show_spinner="Loading the bundled real sample…")
def _lab():
    from stp.demo import lab
    return lab, lab.load()


MODEL_NAMES = {"lr": "Logistic regression", "rf": "Random forest", "lgbm": "LightGBM"}
SPLIT_NAMES = {"time": "by time (earliest 80% of CI runs → train, latest 20% → validation)",
               "random": "random (80% / 20% of rows, ignoring time)"}
METRIC_NAMES = {"pr_auc": "PR-AUC", "accuracy": "accuracy"}


def _lab_scores(res: dict) -> pd.DataFrame:
    rows = []
    for k, name in (("train", "train (rows it learned from)"), ("validation", "validation (held out, chosen split)"),
                    ("later", "later builds (after all training data)")):
        s, b = res["score"][k], res["baseline"][k]
        rows.append({"data": name, "rows": res["rows"][k], METRIC_NAMES[res["metric"]]: s,
                     ("always 'pass' scores" if res["metric"] == "accuracy" else "random ranking scores"): b,
                     **({"× better than random": s / b if b else None} if res["metric"] == "pr_auc" else {})})
    return pd.DataFrame(rows)


def _lab_show(res: dict):
    st.dataframe(_lab_scores(res), hide_index=True)
    gap = res["score"]["train"] - res["score"]["validation"]
    st.caption(f"Fitted in **{res['fit_seconds']:.1f} s** ({res['seconds']:.1f} s with scoring) on this machine · "
               f"{res['n_features']} features · train − validation gap {gap:+.3f}"
               + (f" · {res['rounds_used']} boosting rounds used" if "rounds_used" in res else "")
               + (f" · {res['n_zero']} coefficients exactly zero" if res.get("n_zero") else "")
               + ". Later builds keep the real failure rate (unsampled), so compare them with their own random line.")
    w = pd.DataFrame(res["weights"][:12], columns=["feature", "value"])
    if res["model"] == "lr":
        w["direction"] = ["raises risk" if v > 0 else "lowers risk" if v < 0 else "dropped (0)" for v in w.value]
        w["size"] = w.value.abs()
    else:
        w["size"] = w.value
    st.markdown(f"**Top features** ({res['weights_kind']})")
    st.dataframe(w, hide_index=True, column_config={
        "size": st.column_config.ProgressColumn("size", min_value=0.0, max_value=float(w["size"].max() or 1.0),
                                                format="%.3g"),
        "value": st.column_config.NumberColumn(format="%.4g")})


def page_lab():
    st.header("ML Lab: train a model now")
    lab, data = _lab()
    m = lab.meta()
    ts, lb = m["train_sample"], m["later_builds"]
    st.markdown(f"Everything on this page is fitted **when you press the button**; nothing is precomputed. The data is "
                f"a real sample bundled with the app: **{ts['rows']:,} training rows** ({ts['failure_rate']:.2%} "
                f"fail; passing tests were sampled down, as in our training set) and **{lb['rows']:,} rows of "
                f"{lb['runs']} later CI builds** ({lb['failure_rate']:.2%} fail, the real rate). One row = one test "
                "class in one CI run of a real Apache project; the label is whether it failed.")
    tab_exp, tab_free = st.tabs(["Four guided experiments", "Train your own"])
    with tab_exp:
        for name, e in lab.EXPERIMENTS.items():
            st.subheader(name)
            st.markdown(f"*{e['question']}*  ·  runs: " + " vs ".join(f"**{k}**" for k in e["runs"]))
            key = f"exp_{name}"
            if st.button("Run this experiment", key=f"btn_{name}"):
                with st.spinner("Training…"):
                    st.session_state[key] = {k: lab.train(data=data, **v) for k, v in e["runs"].items()}
            res = st.session_state.get(key)
            if res:
                for k, r in res.items():
                    st.markdown(f"**{k}**")
                    st.dataframe(_lab_scores(r), hide_index=True)
                st.success("**Takeaway (computed from the fit you just ran).** " + lab.takeaway(name, res))
                st.caption("Total time: " + ", ".join(f"{k} {r['seconds']:.1f} s" for k, r in res.items()))
            st.divider()
    with tab_free:
        c1, c2, c3 = st.columns(3)
        model = c1.radio("Model", list(MODEL_NAMES), format_func=MODEL_NAMES.get)
        split = c2.radio("Validation split", list(SPLIT_NAMES), format_func=SPLIT_NAMES.get)
        metric = c3.radio("Metric", list(METRIC_NAMES), format_func=METRIC_NAMES.get)
        st.markdown("**Feature groups**")
        gc = st.columns(4)
        groups = tuple(g for g, col in zip(m["groups"], gc) if col.checkbox(f"{g} ({len(m['groups'][g])})", True,
                                                                           key=f"grp_{g}"))
        st.markdown("**Regularization**")
        kw: dict = {}
        r1, r2, r3, r4 = st.columns(4)
        if model == "lr":
            kw["penalty"] = r1.radio("Penalty", ["l2", "l1"], format_func=str.upper)
            kw["C"] = r2.select_slider("C (smaller = stronger penalty)",
                                       [0.0001, 0.001, 0.01, 0.1, 1.0, 10.0, 100.0], value=1.0)
        elif model == "rf":
            kw["n_trees"] = r1.slider("Trees", 10, 150, 60, 10)
            kw["max_depth"] = r2.slider("Max depth (0 = unlimited)", 0, 30, 12)
            kw["min_leaf"] = r3.slider("Min rows per leaf", 1, 200, 20)
        else:
            kw["num_leaves"] = r1.slider("Leaves per tree", 4, 255, 31)
            kw["max_depth"] = r2.slider("Max depth (0 = unlimited)", 0, 16, 8)
            kw["min_leaf"] = r3.slider("Min rows per leaf", 1, 200, 20)
            kw["rounds"] = r4.slider("Boosting rounds (max)", 50, 600, 300, 50)
            kw["early_stopping"] = r4.checkbox("Early stopping on validation (+ L2 1.0, 80% features)", True)
        if not groups:
            st.warning("Choose at least one feature group.")
        elif st.button("Train", type="primary"):
            with st.spinner(f"Training {MODEL_NAMES[model]}…"):
                res = lab.train(model=model, groups=groups, split_kind=split, metric=metric, data=data, **kw)
            st.session_state.lab_last = res
            st.session_state.setdefault("lab_log", []).append(
                {"model": MODEL_NAMES[model], "split": split, "metric": metric, "groups": "+".join(groups),
                 "settings": ", ".join(f"{k}={v}" for k, v in kw.items()), "train": res["score"]["train"],
                 "validation": res["score"]["validation"], "later builds": res["score"]["later"],
                 "seconds": res["seconds"]})
        if st.session_state.get("lab_last"):
            _lab_show(st.session_state.lab_last)
        if st.session_state.get("lab_log"):
            st.markdown("**Your fits this session**")
            st.dataframe(pd.DataFrame(st.session_state.lab_log), hide_index=True)
    st.caption("Retype the same four experiments yourself: `notebooks/lab_by_hand.ipynb` (pandas, scikit-learn, "
               "LightGBM). The bigger measurement behind this page: `reports/results/lab_check.json`.")


# ------------------------------------------------------------------------------------------------- Real PRs
ORDER_LABEL = {"random": "Random order (stands in for a fixed order)", "fastest_first": "Fastest first (QTF)",
               "best_rule": "Best simple rule: changed or new tests first", "model": "Model (stacking)"}


def _wins_text(W: dict) -> str:
    k, t = get(W, "projects", "kafka", default={}), get(W, "projects", "tvm", default={})
    if not k or not t:
        return ""
    s = lambda d, o, f: d.get(o, {}).get(f, 0)  # noqa: E731
    return (
        "**Do the model's wins come from recurring or flaky failures?** Checked on every held-out failed build of "
        f"both projects ({sum(v['n_builds'] for v in k.values()):,} Kafka, {sum(v['n_builds'] for v in t.values())} "
        "TVM). **Recurring, not flaky.** "
        f"{s(k, 'win', 'share_builds_with_a_recurring_failure'):.0%} of Kafka wins and "
        f"{s(t, 'win', 'share_builds_with_a_recurring_failure'):.0%} of TVM wins contain a test that had failed "
        "before; builds where every failing test is on the known-flaky list are only "
        f"{s(k, 'win', 'share_builds_only_known_flaky_failures'):.0%} (Kafka) and "
        f"{s(t, 'win', 'share_builds_only_known_flaky_failures'):.0%} (TVM) of wins. Known-flaky tests make up "
        f"{s(k, 'win', 'share_known_flaky'):.0%} of failing tests in Kafka wins and "
        f"{s(k, 'loss', 'share_known_flaky'):.0%} in Kafka losses, so flakiness does not separate wins from losses. "
        "But losses are recurring too "
        f"({s(k, 'loss', 'share_recurring'):.0%} Kafka, {s(t, 'loss', 'share_recurring'):.0%} TVM): history is "
        "what lets the model win at all, not a guarantee that it wins. On TVM, "
        f"{s(t, 'win', 'share_first_time'):.0%} of failing tests in winning builds were first-time failures; the "
        "model won those builds by finding a recurring failure in the same build early.")


def page_real_prs():
    st.header("Real PRs: held-out Apache Kafka and TVM builds")
    st.info("**Replay of a real recorded build.** Every number comes from the build's recorded test durations and "
            "outcomes in the LRTS dataset; nothing is animated or re-run. The model never saw these builds (they are "
            "from the held-out test period). Kafka and TVM are the two projects where the model beats the best "
            "simple rule.")
    idx = load_json(str(BUNDLE / "real_prs" / "index.json")) or []
    if not idx:
        st.warning("demo_bundle/real_prs is missing (python -m stp.demo.build_real_prs).")
        return
    M, W = R("models"), R("real_prs_wins")
    d = get(M, "vs_best_simple", "All", "macro10", "stack", "per_project", default={})
    cols = st.columns(4)
    for c, p in zip(cols[:2], ("kafka", "tvm")):
        w = get(W, "projects", p, default={})
        c.metric(f"{p}: model − best rule (APFDc, all held-out builds)", f"{d.get(p, 0):+.3f}",
                 help="From reports/results/models.json (vs_best_simple → All → stack).")
        cols[2 + (p == "tvm")].metric(f"{p}: builds won / tied / lost",
                                      " / ".join(f"{w.get(o, {}).get('n_builds', 0):,}" for o in ("win", "tie", "loss")),
                                      help="Every held-out failed build; tie = |ΔAPFDc| < 0.001.")
    st.markdown(_wins_text(W))
    st.divider()

    def pick(outcome: str):
        st.session_state.rp_seed = random.SystemRandom().randrange(10 ** 6)
        st.session_state.rp_outcome = outcome

    st.session_state.setdefault("rp_seed", 7)
    st.session_state.setdefault("rp_outcome", "any")
    c1, c2, c3, c4 = st.columns([1, 1, 1.2, 2])
    c1.button("Random build", on_click=pick, args=("any",))
    c2.button("Show me a loss", on_click=pick, args=("loss",))
    proj = c3.selectbox("Project", ["any", "kafka", "tvm"], key="rp_project")
    c4.selectbox("Outcome vs best simple rule", ["any", "win", "tie", "loss"], key="rp_outcome")
    pool = [x for x in idx if proj in ("any", x["project"]) and st.session_state.rp_outcome in ("any", x["outcome"])]
    if not pool:
        st.warning("No bundled build matches.")
        return
    i0 = random.Random(st.session_state.rp_seed).randrange(len(pool))
    i = st.selectbox(f"Build ({len(pool)} match; random pick with seed {st.session_state.rp_seed})", range(len(pool)),
                     index=i0, format_func=lambda k: f"[{pool[k]['outcome']}] {pool[k]['project']} {pool[k]['pr_name']} "
                                                     f"build {pool[k]['build_id']} · {pool[k]['stage_id']}")
    rec = load_json(str(BUNDLE / pool[i]["file"]))
    names, dur, fail = rec["names"], rec["duration_s"], rec["fail"]
    st.subheader(f"{rec['project']} · {rec['pr_name']} · build {rec['build_id']} · {rec['stage_id']}")
    st.markdown(f"[Open the real Apache pull request]({rec['pr_url']}) · started {rec['start']} · "
                f"outcome **{rec['outcome']}** (model − best rule ΔAPFDc {rec['delta_vs_best_rule']:+.3f})")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Test classes", f"{rec['n_tests']:,}")
    k2.metric("Failing", rec["n_fail"])
    k3.metric("Total test time", f"{rec['suite_min']:.0f} min")
    k4.metric("Changed files", rec["n_changed_files"])
    with st.expander(f"Changed files in this PR ({rec['n_changed_files']})"):
        st.code("\n".join(rec["changed_files"]) or "(no diff recorded)", language="text")
    rows = []
    for k, lab_ in ORDER_LABEL.items():
        o = rec["orders"][k]
        rows.append({"order": lab_, "first failing test at position": f"{o['first_fail_position']} of {rec['n_tests']}",
                     "test min before it": o["test_min_before"], "test min until it fails": o["test_min_until"],
                     "≈ wall-clock min until it fails": o["wall_min_approx"], "APFDc (all failures)": o["apfdc"]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, column_config={
        c: st.column_config.NumberColumn(format="%.1f") for c in ("test min before it", "test min until it fails",
                                                                  "≈ wall-clock min until it fails")}
        | {"APFDc (all failures)": st.column_config.NumberColumn(format="%.3f")})
    st.caption(f"Test minutes add up the recorded durations in each order, one test after another. Wall-clock ≈ test "
               f"minutes × {rec['wallclock_factor']:.2f}, {rec['project']}'s median ratio of recorded build time to "
               "summed test time (its CI runs tests in parallel). APFDc scores how early *all* failures come, not "
               "just the first; win/tie/loss is decided on APFDc. LRTS does not record the real execution order, so "
               "a random order stands in for it.")
    st.markdown("**The model's top 10 tests, with reasons**")
    st.dataframe(pd.DataFrame([{"rank": r + 1, "test class": t["test"], "really failed?": "❌ yes" if t["failed"] else "",
                                "why the model put it here": " · ".join(t["reasons"])}
                               for r, t in enumerate(rec["model_top10"])]), hide_index=True)
    st.caption("Reasons are the three largest SHAP contributions of the stack's LightGBM member, written as sentences.")
    with st.expander("Full order for one method"):
        k = st.selectbox("Order", list(ORDER_LABEL), format_func=ORDER_LABEL.get)
        order = rec["orders"][k]["order"]
        df = pd.DataFrame({"position": range(1, len(order) + 1), "test class": [names[j] for j in order],
                           "duration s": [dur[j] for j in order], "failed": [bool(fail[j]) for j in order]})
        df["running total min"] = df["duration s"].cumsum() / 60
        st.dataframe(df, hide_index=True, height=260)
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        st.download_button("Download CSV", buf.getvalue(), file_name=f"{rec['project']}_{rec['pr_name']}_{k}.csv")
    st.markdown("**Recompute every number above from the raw LRTS file** (needs the LRTS download):")
    st.code(f"python -m stp.demo.verify --bundle real_prs --project {rec['project']} --pr {rec['pr_name']} "
            f"--build {rec['build_id']} --stage {rec['stage_id']}", language="bash")


# ------------------------------------------------------------------------------------------------- Break the code
def _lane_table(res: dict) -> pd.DataFrame:
    rows = []
    for name, ln in res["lanes"].items():
        rows.append({"process": "pytest's own order" if name == "default" else
                     f"smartci ({res.get('rule') or 'model'})",
                     "failing test file's queue position": (f"{ln['queue_position']} of {ln['n_test_files']}"
                                                            if ln.get("queue_position") else "–"),
                     "test s until it fails": ln.get("test_time_to_first_failure_s"),
                     "end-to-end s (launch → exit, incl. start-up)": ln.get("end_to_end_s"),
                     "exit code": ln.get("returncode"), "first failure": ln.get("first_failure") or "none"})
    return pd.DataFrame(rows)


def _show_run(res: dict, live_run):
    st.markdown(f"**{res.get('mode')}** run on {res.get('date')} · NetworkX `{(res.get('networkx_head') or '')[:10]}`"
                + (f" · saved as `{res['saved_as']}`" if res.get("saved_as") else ""))
    st.dataframe(_lane_table(res), hide_index=True, column_config={
        c: st.column_config.NumberColumn(format="%.2f") for c in ("test s until it fails",
                                                                  "end-to-end s (launch → exit, incl. start-up)")})
    cols = st.columns(2)
    for c, (name, ln) in zip(cols, res["lanes"].items()):
        with c:
            st.markdown(f"**{name}** · `{ln['command']}`")
            st.code(live_run.traceback_of(ln["lines"])[-6000:], language="text")
            with st.expander("Full log with timestamps (s since launch)"):
                st.code("\n".join(f"{t:8.2f}  {x}" for t, x in ln["lines"]), language="text")
    if res.get("smartci_top10"):
        ff = (res["lanes"].get("default", {}).get("first_failure") or "").split("::")[0]
        st.markdown("**smartci's top 10 for this change**")
        st.dataframe(pd.DataFrame([{"rank": r["rank"], "test file": r["test_file"], "P(fail)": r["p_fail"],
                                    "fails?": "❌ yes" if r["test_file"] == ff else "",
                                    "reasons": " · ".join(r["reasons"])} for r in res["smartci_top10"]]),
                     hide_index=True)


def _live_section(pick: str, b: dict):
    from stp.demo import live_run
    st.markdown("#### Step 4 · Run it for real: two pytest processes, a real stopwatch")
    recs = sorted((BUNDLE / "recordings").glob("*.json"), reverse=True) if (BUNDLE / "recordings").exists() else []
    if live_run.available():
        c1, c2, c3 = st.columns(3)
        mode = c1.radio("Mode", ["side-by-side", "sequential"],
                        help="side-by-side: both at once (they share the CPU, so both are slower); sequential: "
                             "pytest's order first, then smartci (cleaner timings).")
        rule = c2.selectbox("smartci lane orders by", ["model", "changed_files_first"])
        top = "/".join(b["failing_files"][0].split("/")[:2])
        subset = c3.selectbox("Tests", ["full suite", top], help="A subset makes collection shorter.")
        st.caption(f"Measured start-up (Python, imports, collecting ~10,000 tests) on this laptop: about "
                   f"{nx_startup_s():.0f} s per process. It is inside the stopwatch, for both lanes.")
        if st.button("▶ Start both pytest runs", type="primary"):
            started = __import__("time").time()
            meta, lanes, ctx = live_run.setup(pick, None if rule == "model" else rule,
                                              None if subset == "full suite" else subset)
            holders = {k: st.columns(1)[0].empty() for k in lanes}
            groups = [["default", "smartci"]] if mode == "side-by-side" else [["default"], ["smartci"]]
            try:
                for g in groups:
                    for k in g:
                        lanes[k].start()
                    while True:
                        done = all(lanes[k].drain() for k in g)
                        for k, ln in lanes.items():
                            tail = "\n".join(x for _, x in ln.lines[-12:])
                            state = ("waiting" if ln.t0 is None else
                                     f"exited ({ln.rc})" if ln.rc is not None else "running")
                            holders[k].code(f"[{k}] {state} · stopwatch {ln.elapsed():7.1f} s\n{tail}", language="text")
                        if done:
                            break
                        __import__("time").sleep(0.25)
            finally:
                for ln in lanes.values():
                    if ln.proc and ln.proc.poll() is None:
                        from smartci.runner import kill_tree
                        kill_tree(ln.proc.pid)
            st.session_state[f"live_{pick}"] = live_run.finish(meta, lanes, ctx, started, mode)
        if st.session_state.get(f"live_{pick}"):
            _show_run(st.session_state[f"live_{pick}"], live_run)
        return
    st.warning("The NetworkX clone is not on this machine, so the live run is not possible here. Below are "
               "**recordings of real runs** made with the same code on the authors' laptop (full logs included)."
               if recs else "The NetworkX clone is not on this machine and no recording is bundled yet. Record one "
               "with `python -m stp.demo.live_run --bug <id>` on a machine with the clone (see README).")
    if recs:
        f = st.selectbox("Recording", recs, format_func=lambda p: p.name)
        _show_run(load_json(str(f)), live_run)


def page_break():
    st.header("Break the code: a guided demo")
    st.markdown("A real bug from NetworkX's history is put back into today's code. The model has **never seen this "
                "bug**. Step through it.")
    bt = nx_backtest()
    bugs = {b["id"]: b for b in bt.get("bugs", []) if b["kind"] == "mined" and b.get("prefix")}
    meta = {b["fix_sha"]: b for b in jsonl(BUNDLE / "repos" / "networkx" / "bugs.jsonl")}
    ids = [i for i in bugs if i in meta]
    if not ids:
        st.warning("No mined NetworkX bugs in the bundle.")
        return
    su = nx_startup_s()

    def outcome(i):
        p = bugs[i]["prefix"]
        s, r = len(p.get("smartci", [])), len(p.get("changed_files_first", []))
        w = "smartci earlier" if s < r else "simple rule earlier" if r < s else "tie"
        return f"[{w}: queue position smartci {s}, rule {r}, pytest {len(p['default'])}] {bugs[i]['title'][:70]}"

    ids = sorted(ids, key=lambda i: bugs[i]["ttff_s"]["smartci"])
    st.caption("Every held-out real bug is listed with its outcome, including the ones smartci loses.")
    pick = st.selectbox("Choose a bug", ids, index=len(ids) // 2, format_func=outcome)
    b, m = bugs[pick], meta[pick]
    st.markdown(f"#### Step 1 · The change\nSomeone edits **{', '.join(m['source_files'])}** and, without noticing, "
                f"brings back the bug fixed in [this commit]({b.get('url')}): *{b['title']}*.")
    diff = m["source_diff"]
    st.code("\n".join(diff.splitlines()[:40]) + ("\n…" if len(diff.splitlines()) > 40 else ""), language="diff")
    st.markdown("#### Step 2 · Ask the model which tests to run first")
    adds = sum(1 for x in diff.splitlines() if x.startswith("+") and not x.startswith("+++"))
    dels = sum(1 for x in diff.splitlines() if x.startswith("-") and not x.startswith("---"))
    if st.toggle("Run the model now", value=False, key=f"run_{pick}"):
        rows, base = _rank(tuple(m["source_files"]), adds, dels)
        fails = set(b["failing_files"])
        st.dataframe(pd.DataFrame([{"rank": r["rank"], "test file": r["test_file"].replace("networkx/", ""),
                                    "really fails?": "❌ yes" if r["test_file"] in fails else "",
                                    "chance of failing": r["p_fail"], "why": " · ".join(r["reasons"])}
                                   for r in rows[:10]]), hide_index=True,
                     column_config={"chance of failing": st.column_config.NumberColumn(format="%.3f")})
        st.caption("This page sees only the changed file names (no patch text).")
    else:
        st.info("Turn on **Run the model now**: the real model scores all NetworkX test files for this change.")
    st.markdown("#### Step 3 · Where did the truly failing test land? (backtest on measured test times)")
    tt = b["ttff_s"]
    res = pd.DataFrame([{"order": lab_, "failing file's queue position": f"{len(b['prefix'][k])} of {bt.get('n_test_files')}",
                         "test s until it fails": tt.get(k), "≈ end-to-end s (+ measured start-up)": tt.get(k, 0) + su}
                        for k, lab_ in (("default", "pytest's normal order"),
                                        ("changed_files_first", "changed files first (simple rule)"),
                                        ("smartci", "smartci (full code change)")) if k in b["prefix"]])
    st.dataframe(res, hide_index=True, column_config={c: st.column_config.NumberColumn(format="%.1f") for c in
                                                      ("test s until it fails", "≈ end-to-end s (+ measured start-up)")})
    st.caption(f"Test seconds replay NetworkX's measured per-test durations in each order; end-to-end adds the "
               f"measured start-up of ~{su:.0f} s. Step 4 measures all three for real.")
    _live_section(pick, b)


PAGES = {"Start here": page_start, "ML Lab": page_lab, "Real PRs": page_real_prs,
         "Break the code (guided demo)": page_break, "The ML pipeline": page_pipeline, "Predict live": page_predict,
         "Results": page_results, "Limits and honesty": page_limits}


def main():
    st.set_page_config(page_title="smartci", layout="wide")
    page = st.sidebar.radio("Page", list(PAGES))
    PAGES[page]()
    meta = load_json(str(BUNDLE / "meta.json")) or {}
    foot = f"results version {meta.get('git_sha', '?')} · bundle built {meta.get('generated', '?')}"
    st.sidebar.caption(foot)
    st.divider()
    st.caption(foot + " · every number on this page is read from demo_bundle/ or computed live")


main()
