"""smartci demo (Streamlit): six pages, offline, reading only demo_bundle/.

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
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from stp.reports.colors import color, label  # noqa: E402
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


def race(lanes: dict[str, list[tuple[str, float, bool]]], title: str, unit: str = "s"):
    """Horizontal lanes: each test (or file) is a segment; a lane stops at its first failure (red)."""
    fig_, ax = plt.subplots(figsize=(9, 0.7 + 0.55 * len(lanes)))
    scale = 60.0 if unit == "min" else 1.0
    for y, (name, segs) in enumerate(lanes.items()):
        t = 0.0
        for _, d, f in segs:
            ax.barh(y, d / scale, left=t / scale, color="#d62728" if f else color(name), edgecolor="white",
                    linewidth=0.3, height=0.6)
            t += d
            if f:
                ax.text(t / scale, y, f"  {t / scale:.2f} {unit}", va="center", fontsize=8)
                break
    ax.set_yticks(range(len(lanes)), [label(n) for n in lanes])
    ax.invert_yaxis()
    ax.set_xlabel(f"time until the first failure is reported ({unit}; tests run one after another; red = failing)")
    ax.set_title(title, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    st.pyplot(fig_)
    plt.close(fig_)


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
    bt = nx_backtest()
    if bt:
        bugs = [b for b in bt["bugs"] if b["kind"] == "mined" and b.get("prefix")]
        med = sorted(b["ttff_s"]["default"] for b in bugs)[len(bugs) // 2]
        b = min(bugs, key=lambda x: abs(x["ttff_s"]["default"] - med))
        fails = set(b["failing_files"])
        lanes = {m: [(f, d, f in fails) for f, d in b["prefix"][m]] for m in ("default", "smartci") if m in b["prefix"]}
        race(lanes, f"A real NetworkX bug (\"{b['title'][:70]}\"): pytest's order vs smartci's order")
        st.caption("Real measured test-file durations of NetworkX; the failing file is the real one. The lanes are replayed "
                   "from those durations (see 'Race replay' for every bug and how to re-run it for real).")
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
    md, ms = get(nx, "median_ttff_s", "default", "median"), get(nx, "median_ttff_s", "smartci", "median")
    c4.metric("NetworkX: median s to first failure", f"{md:.1f} s → {ms:.2f} s" if md else "–",
              help=f"pytest's default order vs smartci, {nx.get('n')} bugs (real mined bugs + synthetic mutants); "
                   "changed-files-first does about as well (see Results).")
    st.markdown(f"**The question we tested.** {QUESTION}  \n**The answer.** {HEADLINE}")
    st.markdown("""
**Pages**
- **The ML pipeline**: the seven course rubric items, one tab each, with figures and numbers.
- **Predict live**: pick NetworkX files you would change; the real model ranks the tests now.
- **Race replay**: three orders racing to the first failure, on real NetworkX bugs and real Apache builds.
- **Results**: where ML wins, where it loses, and why.
- **Limits and honesty**: what is simulated, what is real, and the caveats.
""")


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


# ------------------------------------------------------------------------------------------------- 4 race replay
def _race_networkx():
    bt = nx_backtest()
    if not bt:
        st.warning("demo_bundle/repos/networkx/backtest.json is missing.")
        return
    best = bt["summary"]["all"]["best_simple_baseline"]
    bugs = [b for b in bt["bugs"] if b.get("prefix")]
    if "nx_seed" not in st.session_state:
        st.session_state.nx_seed = 5
    c1, c2 = st.columns([1, 3])
    if c1.button("Random bug"):
        st.session_state.nx_seed = random.SystemRandom().randrange(10 ** 6)
    c2.write(f"seed **{st.session_state.nx_seed}** (the same seed always picks the same bug)")
    labels = [f"[{b['kind']}] {b['title'][:80]}" for b in bugs]
    i0 = random.Random(st.session_state.nx_seed).randrange(len(bugs))
    i = st.selectbox("Bug", range(len(bugs)), index=i0, format_func=lambda k: labels[k])
    b = bugs[i]
    fails = set(b["failing_files"])
    lanes = {m: [(f, d, f in fails) for f, d in b["prefix"][m]] for m in ("default", best, "smartci")
             if m in b["prefix"]}
    race(lanes, f"{b['kind']} {b['id'][:12]}: test files run until the first failure")
    st.caption(f"**Replayed** from NetworkX test-file durations measured by `smartci profile` "
               f"({bt['n_test_files']} files, {bt['suite_test_time_s']:.0f} s summed). The failing tests are real. "
               "Per-test pytest overhead is included; pytest start-up and collection are not.")
    t = b["ttff_s"]
    st.dataframe(pd.DataFrame([{"order": label(m), "seconds to first failure": t.get(m)}
                               for m in ("default", best, "smartci", "fastest_first", "coverage_first", "random")
                               if t.get(m) is not None]), hide_index=True)
    if b.get("url"):
        st.markdown(f"[Open the fix commit on GitHub]({b['url']})")
    st.markdown("**Run this race for real** (both lanes really run pytest; needs the NetworkX clone, see README):")
    st.code(f"cd external\\networkx\n.venv\\Scripts\\smartci compare --bug {b['id']}", language="powershell")


def _race_lrts():
    idx = load_json(str(BUNDLE / "lrts" / "index.json")) or []
    if not idx:
        st.warning("demo_bundle/lrts is missing.")
        return
    if "seed" not in st.session_state:
        st.session_state.seed = 7
    c1, c2 = st.columns([1, 3])
    if c1.button("Random build"):
        st.session_state.seed = random.SystemRandom().randrange(10 ** 6)
    c2.write(f"seed **{st.session_state.seed}** (the same seed always shows the same build)")
    projects = sorted({x["project"] for x in idx})
    proj = st.selectbox("Project", ["(any)"] + projects)
    pool = [x for x in idx if proj == "(any)" or x["project"] == proj]
    item = pool[random.Random(st.session_state.seed).randrange(len(pool))]
    rec = decode(load_json(str(BUNDLE / item["file"])))
    st.subheader(f"{rec['project']} · {rec['pr_name']} · build {rec['build_id']} · stage {rec['stage_id']}")
    st.write(f"{rec['n_tests']} test classes, {rec['n_fail']} failing, summed test time "
             f"{rec['suite_s'] / 60:.0f} min, started {rec['start']} (held-out test period).")
    if rec.get("pr_url"):
        st.markdown(f"[Open the real Apache pull request]({rec['pr_url']})")
    lanes = {m: [(t, rec["tests"][t]["duration_s"], rec["tests"][t]["fail"]) for t in r["order"]]
             for m, r in rec["methods"].items() if m != "Oracle"}
    race(lanes, "The same tests in different orders", unit="min")
    st.caption("**Replayed** from the real durations and outcomes in LRTS (no live run). 'Random' stands in for a "
               "fixed order, because LRTS does not record the execution order.")
    st.dataframe(pd.DataFrame([{"order": label(m), "APFDc": r["apfdc"], "minutes to first failure": r["ttff_s"] / 60}
                               for m, r in rec["methods"].items()]), hide_index=True)
    with st.expander("Why did smartci rank its top tests first?"):
        for r in rec.get("smartci_reasons", []):
            st.markdown(f"**{r['test']}** · P(fail) = {r['p_fail']:.4f} "
                        f"{'(failed)' if rec['tests'][r['test']]['fail'] else ''}")
            for x in r["top"]:
                st.write(f"- `{x['feature']}` = {x['value']:.3g} {'raises' if x['shap'] > 0 else 'lowers'} the risk "
                         f"({x['shap']:+.2f} log-odds)")
    m = st.selectbox("Full ordered list for", list(rec["methods"]))
    order = rec["methods"][m]["order"]
    df = pd.DataFrame({"rank": range(1, len(order) + 1), "test class": order,
                       "duration s": [rec["tests"][t]["duration_s"] for t in order],
                       "failed": [rec["tests"][t]["fail"] for t in order]})
    df["running total min"] = df["duration s"].cumsum() / 60
    st.dataframe(df, hide_index=True, height=260)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.download_button("Download CSV", buf.getvalue(), file_name=f"{rec['project']}_{rec['pr_name']}_{m}.csv")
    st.markdown("**Verify every number above from the raw LRTS file** (needs the LRTS download):")
    st.code(f"python -m stp.demo.verify --project {rec['project']} --pr {rec['pr_name']} --build {rec['build_id']} "
            f"--stage {rec['stage_id']}", language="bash")


def page_race():
    st.header("Race replay")
    src = st.radio("Source", ["NetworkX bugs", "LRTS held-out builds"], horizontal=True)
    _race_networkx() if src == "NetworkX bugs" else _race_lrts()


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
        for kind, s in bt.items():
            st.markdown(f"**{kind}** (n = {s['n']}): best simple rule **{s['best_simple_baseline']}**. "
                        f"{s['recommendation']}")
            st.dataframe(pd.DataFrame([{"order": label(m), "median s to first failure [95% CI]":
                                        f"{v['median']:.2f} [{v['lo']:.2f}, {v['hi']:.2f}]",
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


PAGES = {"Overview": page_overview, "The ML pipeline": page_pipeline, "Predict live": page_predict,
         "Race replay": page_race, "Results": page_results, "Limits and honesty": page_limits}


def main():
    st.set_page_config(page_title="smartci", layout="wide")
    page = st.sidebar.radio("Page", list(PAGES))
    PAGES[page]()
    meta = load_json(str(BUNDLE / "meta.json")) or {}
    foot = f"results version {meta.get('git_sha', '?')} · bundle built {meta.get('generated', '?')}"
    st.sidebar.caption(foot)
    st.divider()
    st.caption(foot + " · every number on this page is read from demo_bundle/")


main()
