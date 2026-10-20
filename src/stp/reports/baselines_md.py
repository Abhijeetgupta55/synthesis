"""Generate reports/BASELINES.md from reports/results/{gate2_reproduction,baselines,leakage_*}.json.

Usage: python -m stp.reports.baselines_md
"""
from __future__ import annotations

from stp import paths
from stp.reports.fmt import ci, diff_ci, f3, pct, sgn, table
from stp.results import load_result

TECH_MAP = {"QTF": "QTF", "LastFail_Asc": "LastFail", "FailCount_Desc": "FailCount", "cbt_LastFail_Asc": "cbt_LastFail",
            "Random": "Random"}
SUBSETS = ["All", "FirstFail-asof", "FirstFail-old", "New/Edited"]
GROUP_LABEL = {"macro10": "Macro (10)", "kafka": "Kafka", "tvm": "TVM", "small8": "Small-8 macro"}


def gate2_section(g: dict) -> str:
    rows = []
    for key, v in g["gate"].items():
        var, tech = key.split("|")
        rows.append([var, tech, f3(v["target"]), f"{v['ours']:.4f}", sgn(v["diff"], 4), "PASS" if v["pass"] else "FAIL",
                     f"{v['as_of']:.4f}", sgn(v["as_of"] - v["ours"], 4)])
    for var in ("All", "FirstFail"):
        r = g["macro"]["start_order"][var]["Random"]
        rows.append([var, "Random", "–", f"{r:.4f}", "–", "–", f"{g['macro']['as_of'][var]['Random']:.4f}", "–"])
    n = g["n_runs"]["start_order"]
    s = ["## 1. Reproduction of the paper's baselines (GATE 2)", "",
         "Our harness, LRTS's own start-order history features, the paper subset (stages with > 50 runs), 10 tie-break "
         "seeds per run, macro APFDc_uniqueBug over projects. Target = paper value (`docs/PROMPT.md`, fact 7). "
         "The last two columns re-run *the same features* with the as-of rule (a run only sees runs that had finished "
         "when it started).", "",
         table(["Variant", "Technique", "Target", "Ours (start order)", "Diff", "±0.005", "Ours (as-of)",
                "As-of − start order"], rows), "",
         f"Evaluated runs: All {n['All']['QTF']:,}, FirstFail {n['FirstFail']['QTF']:,} "
         f"(paper: {g['paper_n_runs']['All']['QTF']:,} and {g['paper_n_runs']['FirstFail']['QTF']:,}). "
         f"**GATE 2: {'PASS' if g['gate_pass'] else 'FAIL'}.**", ""]
    return "\n".join(s)


def asof_section(b: dict) -> str:
    cells = b["cells"]["test"]
    methods = b["methods"]
    out = ["## 2. As-of baselines on our held-out test split", "",
           "All baselines use only as-of features (`stp/baselines/heuristics.py`). Failed runs of the build-level test "
           "split. Cells: macro APFDc with a 95% PR-clustered bootstrap CI; † = some project has < 30 runs. "
           "The best simple baseline per subset is chosen on **validation**, never on test.", ""]
    for sub in SUBSETS:
        if sub not in cells:
            continue
        best = b["best_simple_by_val"].get(sub)
        out.append(f"### {sub}  (best simple baseline on val: **{best}**)")
        out.append("")
        rows = []
        for m in methods:
            row = [m + (" ★" if m == best else "")]
            for gname in ("macro10", "kafka", "tvm", "small8"):
                row.append(ci(cells[sub].get(gname, {}).get(m, {}).get("apfdc")))
            c = cells[sub].get("macro10", {}).get(m, {})
            med = c.get("ttff_min_median", {})
            row.append("–" if med.get("median") is None else f"{med['median']:.1f}")
            row.append(pct(c.get("first10_share")))
            rows.append(row)
        out.append(table(["Method", "Macro (10)", "Kafka", "TVM", "Small-8 macro", "Median min to 1st failure",
                          "1st failure in first 10%"], rows))
        k = cells[sub].get("macro10", {}).get("Random", {}).get("n_runs_per_project", {})
        out.append("")
        out.append("Runs per project: " + ", ".join(f"{p} {n}" for p, n in sorted(k.items())))
        vs = b["vs_best_on_test"].get(sub, {}).get("macro10", {})
        if vs:
            out.append("")
            out.append(f"Paired difference to {best} on test (macro, 95% CI, * = excludes 0): " + "; ".join(
                f"{m} {diff_ci(v)}" for m, v in vs.items() if m not in ("Random",)))
        out.append("")
    return "\n".join(out)


def gap_section(g: dict) -> str:
    rows = []
    for var in ("All", "FirstFail"):
        for t in ("QTF", "LastFail_Asc", "FailCount_Desc", "cbt_LastFail_Asc"):
            a, b = g["macro"]["start_order"][var][t], g["macro"]["as_of"][var][t]
            rows.append([var, t, f"{a:.4f}", f"{b:.4f}", sgn(b - a, 4)])
    return "\n".join(["## 3. Start order vs as-of, same features, same runs (the leak effect)", "",
                      table(["Variant", "Technique", "Start order (paper)", "As-of", "Δ"], rows), ""])


def explain(g: dict, b: dict) -> str:
    f = load_result("phase0_facts")["fact1"]
    d_all = g["macro"]["as_of"]["All"]["cbt_LastFail_Asc"] - g["macro"]["start_order"]["All"]["cbt_LastFail_Asc"]
    d_lf = g["macro"]["as_of"]["All"]["LastFail_Asc"] - g["macro"]["start_order"]["All"]["LastFail_Asc"]
    best = b["best_simple_by_val"]
    return "\n".join([
        "## 4. In plain words", "",
        f"- **The paper's history baselines peek at results that did not exist yet.** In LRTS, a run's \"previous "
        f"outcome\" is taken from the previous run *by start time*. For {pct(f['share_prev_run_unfinished_at_start']['macro'])} "
        f"of runs (macro; Kafka {pct(f['share_prev_run_unfinished_at_start']['per_project']['kafka'])}) that previous run "
        f"was still running, and {pct(f['share_last_outcome_fail_rows_from_unfinished_run']['macro'])} of the "
        f"\"last outcome = fail\" values come from such an unfinished run.",
        f"- **How much it matters.** Making exactly the same baselines respect finish times changes macro APFDc by "
        f"{sgn(d_lf, 4)} for LastFail and {sgn(d_all, 4)} for cbt_LastFail (All). A small macro change can hide "
        "larger per-project effects; see `gate2_reproduction.json` → per_project.",
        f"- **Best simple rule by subset (chosen on validation):** " + ", ".join(f"{s}: {m}" for s, m in best.items())
        + ". These are the numbers a model must beat.", ""])


def main() -> None:
    g = load_result("gate2_reproduction")
    b = load_result("baselines")
    lb = load_result("leakage_bruteforce") if (paths.RESULTS / "leakage_bruteforce.json").exists() else None
    head = ["# BASELINES", "",
            "Generated by `python -m stp.reports.baselines_md` from `reports/results/gate2_reproduction.json` and "
            "`reports/results/baselines.json`. Do not edit by hand.", ""]
    if lb:
        head.append(f"Feature store leakage check: {lb['n_match']}/{lb['n_runs']} random real runs recomputed by brute "
                    f"force match exactly ({lb['n_rows_checked']:,} rows).")
        head.append("")
    text = "\n".join(head) + "\n" + gate2_section(g) + "\n" + asof_section(b) + "\n" + gap_section(g) + "\n" + explain(g, b)
    (paths.ROOT / "reports" / "BASELINES.md").write_text(text, encoding="utf-8")
    print("wrote reports/BASELINES.md")


if __name__ == "__main__":
    main()
