"""smartci demo (Streamlit). Reads only demo_bundle/ and, optionally, a .smartci/ folder you point it at.

Run:  streamlit run app/demo.py
Every number on these pages comes from files: demo_bundle/ (built by `python -m stp.demo.build_bundle` from
reports/results and the smartci outputs) or the .smartci/ folder of a repository you choose.
"""
from __future__ import annotations

import io
import json
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "demo_bundle"
# one colour per method, used on every page
COLORS = {"default": "#7f7f7f", "Random": "#b0b0b0", "random": "#b0b0b0", "QTF": "#eda100",
          "fastest_first": "#eda100", "cbt_LastFail": "#2a78d6", "recently_failed_first": "#2a78d6",
          "ChangedOrNewFirst": "#1baf7a", "changed_files_first": "#1baf7a", "coverage_first": "#4a3aa7",
          "smartci": "#e34948", "smartci (LightGBM)": "#e34948", "Oracle": "#0b0b0b"}


def color(m: str) -> str:
    return COLORS.get(m, "#e87ba4")


@st.cache_data
def load_json(path: str):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def race(lanes: dict[str, list[tuple[str, float, bool]]], title: str, unit: str = "s"):
    """Horizontal lanes: each test (or file) is a segment; the run stops at the first failure (red)."""
    fig, ax = plt.subplots(figsize=(9, 0.6 + 0.55 * len(lanes)))
    scale = 60.0 if unit == "min" else 1.0
    for y, (name, segs) in enumerate(lanes.items()):
        t = 0.0
        for test, d, f in segs:
            ax.barh(y, d / scale, left=t / scale, color="#e34948" if f else color(name), edgecolor="white",
                    linewidth=0.3, height=0.6)
            t += d
            if f:
                ax.text(t / scale, y, f"  {t / scale:.2f} {unit}", va="center", fontsize=8)
                break
    ax.set_yticks(range(len(lanes)), list(lanes))
    ax.invert_yaxis()
    ax.set_xlabel(f"time until the first failure is reported ({unit}, tests run one after another)")
    ax.set_title(title, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    st.pyplot(fig)
    plt.close(fig)


# ------------------------------------------------------------------------------------------------- pages
def page_repo():
    st.header("Try it on a real repo")
    st.write("Each row is a real bug: a past bug fix of the repository with its source reverted (mined), or a "
             "seeded mutant. Durations are the repository's real measured test times; the failing tests are the "
             "real ones. Re-run any row live with the command shown below it.")
    repos = sorted(p.name for p in (BUNDLE / "repos").glob("*")) if (BUNDLE / "repos").exists() else []
    choice = st.selectbox("Repository", repos + ["(a .smartci folder on this machine)"])
    if choice.startswith("("):
        folder = st.text_input("Path to the repository's .smartci folder")
        d = Path(folder) if folder else None
    else:
        d = BUNDLE / "repos" / choice
    if not d or not (d / "backtest.json").exists():
        st.info("No backtest.json there yet. Run `smartci profile`, `smartci learn`, `smartci backtest` first.")
        return
    bt = load_json(str(d / "backtest.json"))
    st.caption(f"profile base {bt['profile_base_sha'][:10]} · {bt['n_test_files']} test files · "
               f"{bt['suite_test_time_s']:.0f} s summed test time · simulated from real durations")
    for kind, s in bt["summary"].items():
        with st.expander(f"Summary: {kind} (n = {s['n']}), best simple baseline: {s['best_simple_baseline']}",
                         expanded=kind == "all"):
            rows = [{"ordering": m, "median s to 1st failure": v["median"], "95% CI": f"[{v['lo']:.2f}, {v['hi']:.2f}]",
                     "mean APFDc": s["mean_apfdc"][m],
                     "smartci W/T/L": "" if m not in s["vs_smartci"] else
                     "{win}/{tie}/{loss}".format(**s["vs_smartci"][m])} for m, v in s["median_ttff_s"].items()]
            st.dataframe(pd.DataFrame(rows).sort_values("median s to 1st failure"), hide_index=True)
            st.write(f"**Recommendation:** {s['recommendation']}")
    bugs = pd.DataFrame([{"kind": b["kind"], "id": b["id"], "title": b["title"], "url": b.get("url"),
                          "failing tests": b["n_failing_tests"], "default s": b["ttff_s"]["default"],
                          "smartci s": b["ttff_s"]["smartci"]} for b in bt["bugs"]])
    st.dataframe(bugs, hide_index=True, column_config={"url": st.column_config.LinkColumn("commit")})
    pick = st.selectbox("Race one bug", bugs.id.tolist())
    b = next(x for x in bt["bugs"] if x["id"] == pick)
    best = bt["summary"]["all"]["best_simple_baseline"]
    fails = set(b["failing_files"])
    lanes = {m: [(f, d_, f in fails) for f, d_ in b["prefix"][m]] for m in ("default", best, "smartci")
             if m in b.get("prefix", {})}
    race(lanes, f"{b['kind']} {pick[:12]}: files run until the first failure")
    st.code(f"smartci compare --bug {pick}", language="bash")
    st.caption("This runs real `pytest -x` twice (default order and --smartci) in two git worktrees and prints "
               "both outputs and the elapsed seconds.")


def page_lrts():
    st.header("The 108k-build study (LRTS)")
    idx = load_json(str(BUNDLE / "lrts" / "index.json")) or []
    if not idx:
        st.warning("demo_bundle/lrts is missing: run `python -m stp.demo.build_bundle`.")
        return
    if "seed" not in st.session_state:
        st.session_state.seed = 7
    c1, c2 = st.columns([1, 3])
    if c1.button("Random build"):
        st.session_state.seed = random.SystemRandom().randrange(10**6)
    rng = random.Random(st.session_state.seed)
    c2.write(f"seed **{st.session_state.seed}** (the same seed always shows the same build)")
    projects = sorted({x["project"] for x in idx})
    proj = st.selectbox("Project", ["(any)"] + projects)
    pool = [x for x in idx if proj == "(any)" or x["project"] == proj]
    item = pool[rng.randrange(len(pool))]
    rec = load_json(str(BUNDLE / item["file"]))
    st.subheader(f"{rec['project']} · {rec['pr_name']} · build {rec['build_id']} · stage {rec['stage_id']}")
    st.write(f"{rec['n_tests']} test classes, {rec['n_fail']} failing, summed test time "
             f"{rec['suite_s'] / 60:.0f} min, started {rec['start']} (held-out test split).")
    if rec.get("pr_url"):
        st.markdown(f"[Open the real Apache pull request]({rec['pr_url']})")
    lanes = {}
    for m, r in rec["methods"].items():
        lanes[m] = [(t, rec["tests"][t]["duration_s"], rec["tests"][t]["fail"]) for t in r["order"]]
    race(lanes, "Each lane runs the same tests in a different order", unit="min")
    st.dataframe(pd.DataFrame([{"method": m, "APFDc": r["apfdc"], "minutes to 1st failure": r["ttff_s"] / 60}
                               for m, r in rec["methods"].items()]), hide_index=True)
    m = st.selectbox("Full ordered list for", list(rec["methods"]))
    order = rec["methods"][m]["order"]
    df = pd.DataFrame({"rank": range(1, len(order) + 1), "test class": order,
                       "duration s": [rec["tests"][t]["duration_s"] for t in order],
                       "failed": [rec["tests"][t]["fail"] for t in order]})
    df["running total min"] = df["duration s"].cumsum() / 60
    st.dataframe(df, hide_index=True, height=300)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.download_button("Download CSV", buf.getvalue(), file_name=f"{rec['project']}_{rec['pr_name']}_{m}.csv")
    st.code(f"python -m stp.demo.verify --project {rec['project']} --pr {rec['pr_name']} --build {rec['build_id']} "
            f"--stage {rec['stage_id']}", language="bash")
    st.caption("Recomputes every number above from the raw LRTS test_class.csv.zip and prints MATCH / MISMATCH.")
    st.session_state.last_rec = rec


def page_why():
    st.header("Why this test?")
    rec = st.session_state.get("last_rec")
    if not rec:
        st.info("Open a build on 'The 108k-build study' first.")
        return
    st.write(f"Top 10 of smartci's ranking for {rec['project']} {rec['pr_name']} build {rec['build_id']}: the three "
             "largest contributions (SHAP, log-odds) behind each probability.")
    plain = {"hs_fail_rate": "failure rate in this stage", "hs_days_since_last_fail": "days since its last failure",
             "hs_fails_last_7d": "failures in the last 7 days", "dur_ema_asof": "its usual duration",
             "dur_last_asof": "its last duration", "hs_n_runs_seen": "how often it ran before",
             "cof_sum": "past failures when these files changed", "cof_max": "past failures when these files changed",
             "name_token_overlap": "name words shared with the change", "bm25_test_vs_diff": "match with the diff text",
             "test_file_in_diff": "its own file is in the change", "path_prefix_overlap": "package overlap with the change"}
    for r in rec["smartci_reasons"]:
        st.markdown(f"**{r['test']}** · P(fail) = {r['p_fail']:.4f}  {'❌ failed' if rec['tests'][r['test']]['fail'] else ''}")
        for t in r["top"]:
            direction = "raises" if t["shap"] > 0 else "lowers"
            st.write(f"- {plain.get(t['feature'], t['feature'])} = {t['value']:.3g} {direction} the risk "
                     f"({t['shap']:+.2f})")


def page_scoreboard():
    st.header("Scoreboard")
    sb = load_json(str(BUNDLE / "scoreboard.json")) or {}
    if not sb:
        st.warning("demo_bundle/scoreboard.json missing.")
        return
    m = sb.get("models", {})
    st.subheader("Ordering quality on the held-out test split (macro APFDc, 95% PR-clustered CI)")
    rows = []
    for sub, groups in m.get("cells", {}).items():
        c = groups.get("macro10", {})
        best = m["best_simple_by_val"].get(sub)
        for meth in ("lgbm", "stack", best, "cbt_LastFail", "QTF"):
            if meth in c:
                a = c[meth]["apfdc"]
                rows.append({"subset": sub, "method": meth, "APFDc": a["mean"], "lo": a["lo"], "hi": a["hi"],
                             "best simple (val)": meth == best})
    st.dataframe(pd.DataFrame(rows).drop_duplicates(["subset", "method"]), hide_index=True)
    st.write("Model vs cbt_LastFail on All:", m.get("vs_cbt_lastfail_All", {}).get("mean"),
             "CI", [m.get("vs_cbt_lastfail_All", {}).get("lo"), m.get("vs_cbt_lastfail_All", {}).get("hi")])
    c = sb.get("models_classification", {})
    if c:
        st.subheader("Classification (testC, unsampled)")
        st.dataframe(pd.DataFrame([{"model": k, "PR-AUC": v["pr_auc"], "ROC-AUC": v["roc_auc"], "Brier": v["brier"]}
                                   for k, v in c["models"].items()]), hide_index=True)
        st.caption(f"Base rate {c['base_rate']:.4%}; always-'pass' accuracy {c['always_pass_accuracy']:.2%}.")
    f = sb.get("phase0_facts", {}).get("fact1", {})
    if f:
        st.subheader("The leakage finding")
        st.write(f"In the paper's data, the 'previous run' had not finished for "
                 f"{f['share_prev_run_unfinished_at_start']['macro']:.1%} of runs (macro), and "
                 f"{f['share_last_outcome_fail_rows_from_unfinished_run']['macro']:.1%} of 'last outcome = fail' values "
                 "come from unfinished runs. Every feature here is as-of; "
                 f"{sb.get('leakage_bruteforce', {}).get('n_match')}/{sb.get('leakage_bruteforce', {}).get('n_runs')} "
                 "random runs recomputed by brute force match.")
    t = sb.get("transfer", {})
    if t:
        st.subheader("Python transfer (TVM)")
        st.dataframe(pd.DataFrame([{"variant": k, "TVM valB PR-AUC": v["valB_pr_auc"], "TVM test PR-AUC": v["testC_pr_auc"]}
                                   for k, v in t["variants"].items()]), hide_index=True)
        st.write(f"Chosen by validation: {t['chosen']}; confirmed on test: {t.get('confirmed_on_test')}; "
                 f"shipped: {t.get('shipped')}.")


def page_honesty():
    st.header("Honesty")
    st.markdown("""
- **Real:** LRTS test durations and outcomes (108,366 CI runs, 10 Apache projects); NetworkX / sympy test durations
  (measured by `smartci profile`), their failing tests, and every `smartci compare` run.
- **Simulated:** race lanes and backtest times add up *measured* durations in a given order (tests one after another).
  `smartci compare` checks the simulation against real pytest runs (REAL_WORLD.md, GATE 5).
- **Mined bugs are reintroduced known bugs:** the revealing test usually came with the fix, so this measures
  regression catching; the bug diff is the reverse of the fix; there is selection bias toward test-backed fixes.
- **Mutants are synthetic** and drawn from covered lines, which favours the coverage-first baseline.
- **The model was trained on Apache CI data** (9 Java/Scala projects + TVM's Python suites).
- **Where a simple rule wins, we say so**: on LRTS first-time failures QTF beats every model; see the Scoreboard.
- Short suites mean small absolute savings; smartci's own start-up cost (a few seconds) is real.
- Data licences: LRTS (MIT), NetworkX (BSD-3-Clause), sympy (BSD-3-Clause), Apache projects (Apache-2.0).
- Reports: `reports/RESULTS.md`, `MODELING.md`, `BASELINES.md`, `REAL_WORLD.md`, `VIVA_NOTES.md`.
""")


PAGES = {"Try it on a real repo": page_repo, "The 108k-build study": page_lrts, "Why this test?": page_why,
         "Scoreboard": page_scoreboard, "Honesty": page_honesty}


def main():
    st.set_page_config(page_title="smartci demo", layout="wide")
    page = st.sidebar.radio("Page", list(PAGES))
    PAGES[page]()
    meta = load_json(str(BUNDLE / "meta.json")) or {}
    st.sidebar.caption(f"results version {meta.get('git_sha', '?')} · generated {meta.get('generated', '?')}")


main()
