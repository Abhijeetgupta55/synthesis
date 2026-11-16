"""Generate reports/AUDIT.md (Phase A of docs/PROMPT_FINISH.md) from results files only.

Inputs: reports/results/audit_runs.json (scripts/audit_runs.py), audit_spotcheck.json (scripts/audit_spotcheck.py),
and the study's results JSON. Claimed values are the ones docs/PROMPT_FINISH.md states; each is compared with the
value regenerated from JSON at the same precision.

Usage: python -m stp.reports.audit_md
"""
from __future__ import annotations

import json

import numpy as np

from stp import paths
from stp.reports.fmt import table
from stp.reports.results_md import _r, get

FIG = paths.ROOT / "reports" / "figures"


def _ci(x):
    return f"{x['mean']:+.3f} [{x['lo']:+.3f}, {x['hi']:+.3f}]"


def _apfdc(M, sub, m):
    return get(M, "cells", sub, "macro10", m, "apfdc", "mean")


def claims() -> list[tuple[str, str, str, str]]:
    """(claim, value stated in the prompt, value regenerated from JSON, source)."""
    L, C, M, T, RW = _r("labels"), _r("models_classification"), _r("models"), _r("transfer"), _r("real_world")
    nx = get(RW, "networkx", "backtest_summary", "all", default={})
    med = lambda m: get(nx, "median_ttff_s", m, "median")  # noqa: E731
    return [
        ("Failure rate per (run, test class)", "0.243%", f"{get(L, 'pooled', 'pos_rate_fail'):.3%}", "labels.json"),
        ("Accuracy of always predicting 'pass'", "99.76%", f"{get(L, 'pooled', 'always_pass_accuracy'):.2%}",
         "labels.json"),
        ("PR-AUC testC: LR / RF / LightGBM / vote / stack", "0.193 / 0.195 / 0.218 / 0.220 / 0.227",
         " / ".join(f"{get(C, 'models', m, 'pr_auc'):.3f}" for m in ("lr", "rf", "lgbm", "vote", "stack")),
         "models_classification.json"),
        ("APFDc All: stack / LightGBM / ChangedOrNewFirst / cbt_LastFail", "0.880 / 0.871 / 0.863 / 0.851",
         " / ".join(f"{_apfdc(M, 'All', m):.3f}" for m in ("stack", "lgbm", "ChangedOrNewFirst", "cbt_LastFail")),
         "models.json"),
        ("LightGBM − ChangedOrNewFirst, All", "+0.008 [-0.002, +0.019]",
         _ci(get(M, "vs_best_simple", "All", "macro10", "lgbm")), "models.json"),
        ("LightGBM − cbt_LastFail, All", "+0.020 [+0.008, +0.032]", _ci(get(M, "vs_cbt_lastfail_All")),
         "models.json"),
        ("APFDc FirstFail-old: LightGBM / QTF", "0.708 / 0.800",
         f"{_apfdc(M, 'FirstFail-old', 'lgbm'):.3f} / {_apfdc(M, 'FirstFail-old', 'QTF'):.3f}", "models.json"),
        ("Δ FirstFail-old LightGBM − QTF", "-0.092 [-0.134, -0.053]",
         _ci(get(M, "vs_best_simple", "FirstFail-old", "macro10", "lgbm")), "models.json"),
        ("NetworkX: number of bugs in the backtest", "318", str(get(nx, "n")), "real_world.json"),
        ("NetworkX median s to first failure: default / smartci / changed-files-first", "124.74 / 0.09 / 0.08",
         f"{med('default'):.2f} / {med('smartci'):.2f} / {med('changed_files_first'):.2f}", "real_world.json"),
        ("TVM-only PR-AUC valB / testC", "0.680 / 0.037",
         f"{get(T, 'variants', 'tvm_only', 'valB_pr_auc'):.3f} / {get(T, 'variants', 'tvm_only', 'testC_pr_auc'):.3f}",
         "transfer.json"),
    ]


RUBRIC = [
    ("1 EDA", "EDA_REPORT.md §1–§5", ["A_headline_all_vs_firstfail", "A_macro_table", "B_classes_per_run",
                                       "B_duration_cdf", "C_builds_per_month", "C_runs_per_project",
                                       "D_failed_classes_per_run", "D_failure_frequency_tail",
                                       "D_first_time_failures", "D_flaky_share", "E_change_size", "E_extensions",
                                       "F_overlap_lift", "F_overlap_share", "G_time_to_first_failure",
                                       "H_split_ftf_runs"], "reports/eda_json/*.json, labels.json", ""),
    ("2 Feature derivation", "FEATURES.md (definitions, univariate signal, correlation, rejected)",
     ["features_univariate", "features_corr"], "univariate.json, leakage_signal.json, leakage_bruteforce.json", ""),
    ("3 Classification", "MODELING.md §1, §2, §4", [], "models_classification.json",
     "thin: tables only, no PR-curve figure comparing LR / RF / LightGBM"),
    ("4 Regularization", "MODELING.md §3", ["reg_lr_C", "reg_lr_l1_path", "reg_rf_depth", "reg_lgbm_curves"],
     "tune_lr.json, tune_rf.json, tune_lgbm.json", ""),
    ("5 Hyperparameter tuning", "MODELING.md §3 (Optuna TPE)",
     ["tune_lgbm_history", "tune_lgbm_importance", "tune_lgbm_slice"], "tune_lgbm.json, tune_lr.json, tune_rf.json",
     ""),
    ("6 Ensembles", "MODELING.md §6", ["ensemble_error_corr"], "models_classification.json, models.json",
     "thin: no figure of vote / stack vs base models (table only)"),
    ("7 Performance analysis", "MODELING.md §4, §5, §8, §9; RESULTS.md",
     ["calibration_reliability", "shap_global"], "models.json, calibration.json, interpret.json, baselines.json",
     "thin: no figure of APFDc vs every baseline with CIs (tables only)"),
]


def figure_ok(name: str) -> tuple[bool, str]:
    from PIL import Image
    f = FIG / f"{name}.png"
    if not f.exists():
        return False, "missing"
    im = np.asarray(Image.open(f).convert("L"), dtype=float)
    ok = im.std() > 5 and (im < 250).mean() > 0.01
    return ok, f"{im.shape[1]}×{im.shape[0]}, {'has content' if ok else 'BLANK'}"


def build() -> str:
    A, S = _r("audit_runs"), _r("audit_spotcheck")
    P0, LB, LS, G2, RW = _r("phase0_facts"), _r("leakage_bruteforce"), _r("leakage_signal"), _r(
        "gate2_reproduction"), _r("real_world")
    g5 = get(RW, "networkx", "gate5", default={})
    rows: list[list[str]] = []

    def row(item, claim, how, result, evidence):
        rows.append([item, claim, how, result, evidence])

    # A1 tests
    t = A.get("tests", {})
    row("A1 Tests", "the full test suite passes", "`pytest` with JUnit XML (scripts/audit_runs.py)",
        "pass" if t.get("failed") == 0 and t.get("errors") == 0 and t.get("tests") else "fail",
        f"{t.get('passed')} passed, {t.get('failed')} failed, {t.get('errors')} errors, {t.get('skipped')} skipped "
        f"({t.get('seconds')} s). Nothing skips because the dataset is present on this machine; "
        "dataset-dependent tests are not yet marked (Phase F).")
    # A2 gates
    facts = [k for k in P0 if k.startswith("fact")]
    row("A2 GATE 0", "all facts recomputed and logged", "phase0_facts.json has every fact; WORKLOG 2026-10-20",
        "pass" if len(facts) == 5 else "partly", f"{len(facts)}/5 facts in phase0_facts.json")
    flagged = LS.get("flagged") or []
    row("A2 GATE 1", "leakage tests pass; brute force matches 50/50",
        "leakage_bruteforce.json, leakage_signal.json, tests/test_leakage.py in A1",
        "pass" if LB.get("n_match") == LB.get("n_runs") == 50 and not flagged else "fail",
        f"{LB.get('n_match')}/{LB.get('n_runs')} runs match ({LB.get('n_rows_checked')} rows); "
        f"single-feature PR-AUC flags: {len(flagged)} (threshold {LS.get('threshold')})")
    cells = get(G2, "gate", default={})
    worst = max(cells.items(), key=lambda kv: abs(kv[1]["diff"])) if cells else ("-", {"diff": float("nan")})
    row("A2 GATE 2", "paper baselines reproduced within ±0.005", "gate2_reproduction.json → gate",
        "pass" if G2.get("gate_pass") else "fail",
        f"{sum(v['pass'] for v in cells.values())}/{len(cells)} cells pass; largest |Δ| {worst[0]} "
        f"{worst[1]['diff']:+.4f}")
    rub_missing = [(n, f) for n, _, figs, _, _ in RUBRIC for f in figs if not figure_ok(f)[0]]
    row("A2 GATE 3", "every rubric deliverable exists; MODELING/FEATURES numbers generated from JSON",
        "A3 regeneration + A5 figure check", "pass" if not rub_missing else "fail",
        "generators rebuild both reports; all listed figures have content" if not rub_missing
        else f"missing/blank figures: {rub_missing}")
    fx = A.get("fixture", {})
    fx_ok = all(fx.get(k, {}).get("returncode") == 0 for k in ("profile", "learn", "backtest", "compare"))
    nx_prof = get(RW, "networkx", "profile")
    row("A2 GATE 4", "fresh venv; profile / learn / backtest / compare end to end on fixture and NetworkX",
        "A6 + A7 re-run now; NetworkX outputs in real_world.json",
        "partly" if fx_ok else "fail",
        f"fixture part re-run now: {'pass' if fx_ok else 'FAIL'}; NetworkX profile/learn/backtest exist "
        f"({'yes' if nx_prof else 'no'}); NetworkX `compare` only inside the battery GATE 5 run, so the "
        "NetworkX part waits for the mains-power rerun (Phase C)")
    row("A2 GATE 5", "simulated vs real time within 10% + overhead", "gate5_networkx.json",
        "pass" if g5.get("gate5_pass") else "fail",
        f"{g5.get('n_pass')}/{g5.get('n_checks')} checks, measured on battery (CPU throttled); not authoritative "
        "until re-run on AC power (Phase C)")
    # A3 regeneration and numbers
    rg = A.get("regen", {})
    ch = rg.get("changed_lines", {})
    row("A3 Regenerate reports", "committed reports equal their generators' output",
        "re-ran every `stp.reports.*` generator, `git diff` ignoring timestamps, restored",
        "pass" if rg.get("identical") else "partly",
        "identical" if rg.get("identical") else
        "differs in " + ", ".join(f"`{k}` ({len(v)} lines)" for k, v in ch.items()) +
        ": sympy mining finished after the last commit (its learn summary now exists), and RESULTS.md §5 "
        "prints a spurious `_meta` bullet (generator iterates over the `_meta` key)")
    cl = claims()
    bad = [c for c in cl if c[1].replace("−", "-") != c[2]]
    row("A3 Headline numbers", "the 11 values in the prompt's table", "regenerated from JSON at the same precision "
        "(table below)", "pass" if not bad else "fail",
        "all equal" if not bad else f"{len(bad)} differ: " + "; ".join(f"{c[0]}: {c[1]} vs {c[2]}" for c in bad))
    # A4 spot check
    sr = S.get("runs", [])
    row("A4 Independent spot check", "per-run APFDc of the shipped model and a baseline recompute from raw data",
        f"`scripts/audit_spotcheck.py --seed {S.get('seed')}` (own csv parser, plain lightgbm + np.interp, "
        "own APFDc loop; no stp/smartci import)", "pass" if S.get("all_match") else "fail",
        f"{sum(r['model']['match'] for r in sr)}/{len(sr)} model, {sum(r['qtf']['match'] for r in sr)}/{len(sr)} QTF "
        "match the stored values (" + ", ".join(f"{r['project']} {r['pr']}" for r in sr) + "). First attempt used "
        "the EMA duration for QTF and mismatched on 2 runs; the documented QTF uses the last as-of duration.")
    # A5 rubric
    thin = [f"{n}: {note}" for n, _, _, _, note in RUBRIC if note]
    row("A5 Rubric deliverables", "every rubric item has a report section, figures and a result file",
        "table below; every figure opened and checked for content", "partly" if thin else "pass",
        "; ".join(thin) if thin else "complete")
    # A6 fresh venv
    fv = A.get("fresh_venv", {})
    row("A6 Exported model", "loads and scores in a fresh venv with no LRTS data",
        "uv venv + non-editable install into a temp dir; score a synthetic change",
        "pass" if fv.get("probe_returncode") == 0 and fv.get("top") == "tests/test_paths.py" else "fail",
        f"model {fv.get('model_version')}, {fv.get('n_features')} features (+{fv.get('n_features_coldstart')} "
        f"cold start); top test for a change to `paths.py`: `{fv.get('top')}` ({fv.get('model_used')}); research "
        f"modules imported: {fv.get('research_modules_imported')}. Non-editable on purpose: with `-e`, "
        "`stp.paths` would still resolve to this repo's data/.")
    # A7 tool
    cp = fx.get("compare_parsed", {})
    d, s = cp.get("default", {}), cp.get("smartci", {})
    row("A7 The tool (fixture repo)", "profile, learn, backtest, compare run end to end", "fresh venv's `smartci` CLI, "
        "real packaged model", "pass" if fx_ok else "fail",
        "exit codes " + ", ".join(f"{k} {fx.get(k, {}).get('returncode')}" for k in
                                  ("profile", "learn", "backtest", "compare")) +
        (f". compare: first failure default {d.get('first_failure_s')} s vs smartci {s.get('first_failure_s')} s, "
         f"whole session {d.get('elapsed_s')} s vs {s.get('elapsed_s')} s (on battery, so timings are noisy: "
         "a manual run of the same command earlier gave 3.4 s vs 6.1 s, i.e. smartci's own start-up can cost more "
         "than it saves on a ~1 s suite)" if d and s else ""))
    # A8 app
    sm, sv = A.get("smoke", {}), A.get("server", {})
    row("A8 The app", "smoke passes; every page renders", "`python -m stp.demo.smoke` (AppTest renders all 5 pages; "
        "scoreboard vs JSON; 20 raw replays; backtest rows); `streamlit run` health check",
        "pass" if sm.get("returncode") == 0 and sv.get("health_ok") else "fail",
        "; ".join(sm.get("lines", [])) + f"; server healthy after {sv.get('seconds_to_healthy')} s. "
        "The app has 5 pages and no rubric walk-through page (Phase E).")
    # A9 leftovers
    lo = A.get("leftovers", {})
    cand = lo.get("candidate_clones_mb", {})
    row("A9 Leftovers", "stale, empty or half-done items", "git grep, directory sizes, STATUS.md read",
        "fail" if cand or lo.get("sympy_mentions") or lo.get("owner_placeholders") else "pass",
        f"sympy: mined only (no profile, no backtest), mentioned in {len(lo.get('sympy_mentions', {}))} tracked "
        f"files + demo_bundle/repos/sympy; candidate clones {', '.join(f'{k} {v} MB' for k, v in cand.items())} "
        f"(git-ignored: {lo.get('candidate_clones_ignored')}); `OWNER` placeholders in "
        f"{len(lo.get('owner_placeholders', {}))} files; 'self-healing' wording: "
        f"{sum(lo.get('heal_wording', {}).values())} occurrences; STATUS.md 'Current/Next' still describes "
        "mutate 180/300 and sympy subset timing (stale)")

    fails = [r for r in rows if r[3] != "pass"]
    out = ["# AUDIT", "",
           "Phase A of `docs/PROMPT_FINISH.md`. Generated by `python -m stp.reports.audit_md` from "
           "`reports/results/audit_runs.json` (`scripts/audit_runs.py`), `audit_spotcheck.json` "
           "(`scripts/audit_spotcheck.py`) and the study's results JSON.",
           f"Checks run {A.get('started')} – {A.get('finished')}; laptop on AC power: {A.get('on_ac_power')} "
           "(no timing claim in this audit depends on it).", "",
           "## Summary", ""]
    if fails:
        out += [f"- **{r[0]}: {r[3]}.** {r[4]}" for r in fails]
    out += ["", "No headline number is wrong, so work continues past GATE A." if not bad else
            "**A headline number differs: stop here (prompt rule).**", "",
            "**Things the repository contradicts in the prompt:** (1) 'self-healing' wording is already gone from "
            "every tracked file; (2) sympy is not empty: mining finished (see A3), but it has no profile or "
            "backtest; (3) NetworkX's '318 bugs' are 18 held-out real (mined, rebased) bugs plus 300 synthetic "
            "mutants, not 318 real bugs; (4) the 'LightGBM' APFDc/PR-AUC numbers are the tuned model "
            "(`cal_lgbm`), while smartci ships the `all_to_tvm` variant (disclosed in MODELING.md §7); the "
            "spot check A4 covers the shipped variant.", "",
            "## Checks", "", table(["Item", "Claim", "How checked", "Result", "Evidence"], rows), "",
            "## Headline numbers (A3)", "",
            table(["Claim", "Prompt", "Regenerated", "Source"], [list(c) for c in cl]), "",
            "## Spot check (A4)", ""]
    out.append(table(["Run", "Tests / failing", "Model APFDc recomputed", "Model stored (bundle)",
                      "QTF recomputed", "QTF stored (bundle / harness)", "Match"],
                     [[f"{r['project']} {r['pr']} build {r['build']} `{r['stage']}`", f"{r['n_tests']} / {r['n_fail']}",
                       f"{r['model']['recomputed_min']:.6f}", f"{r['model']['stored_bundle']:.6f}",
                       f"{r['qtf']['recomputed_min']:.6f}",
                       f"{r['qtf']['stored_bundle']:.6f} / {r['qtf']['stored_harness']:.6f}",
                       "yes" if r["model"]["match"] and r["qtf"]["match"] else "NO"] for r in sr]))
    out += ["", "## Rubric deliverables (A5)", ""]
    rr = []
    for n, sec, figs, res, note in RUBRIC:
        fs = "; ".join(f"`{f}.png` ({figure_ok(f)[1]})" for f in figs) or "none"
        rr.append([n, sec, fs, res, note or "ok"])
    out.append(table(["Rubric item", "Report section", "Figures (checked)", "Result files", "Gap"], rr))
    pc, fl = _r("publish_check"), _r("floor_tradeoff")
    res_rows = [
        ["A2 GATE 4 (NetworkX part)", "open", "needs mains power: `python live_demo/phase_c.py --repeats 3` (HUMAN_TODO 0)"],
        ["A2 GATE 5", "open", "same run re-profiles NetworkX and re-runs `live_demo/gate5.py --seed 5`; reported as it is"],
        ["A3 Regenerate reports", "fixed", "sympy dropped (one sentence in REAL_WORLD.md); `_meta` bullet removed; "
                                           "every report regenerated and committed"],
        ["A5 Rubric deliverables", "fixed", "new figures `cls_models`, `ens_vs_base`, `perf_apfdc_forest`, "
                                            "`error_firstfail`, `tradeoff_floor` (`python -m stp.reports.extra_figures`)"],
        ["A9 Leftovers", "fixed", "sympy removed; `external/cand_*` deleted; STATUS.md rewritten; `OWNER` placeholders "
                                  "kept on purpose until the repository exists (HUMAN_TODO 3); publish check "
                                  + ("passes" if pc.get("pass") else "FAILS")],
        ["Old RESULTS.md claim: model beats the best simple rule on all failures", "corrected",
         "it is a tie (CI includes 0); RESULTS.md and README now decide the wording from the CI"],
        ["Phase D floor", "reported", f"LRTS ship rule met (f* = {fl.get('f_star')}); NetworkX deployment check failed, "
                                      "so it is off by default (RESULTS.md 4.3)"],
    ]
    out += ["", "## Resolution after phases B–G", "", table(["Item", "Status", "How"], res_rows)]
    out += ["", "## Leftovers (A9)", "",
            table(["Item", "Detail"],
                  [["sympy", "mined bugs only; no profile, adapter or backtest; appears in README, STATUS, app, "
                             "REAL_WORLD, RESULTS, SLIDE_NUMBERS, real_world.json, demo_bundle/repos/sympy"],
                   ["candidate clones", ", ".join(f"`external/{k}` {v} MB" for k, v in cand.items())],
                   ["`OWNER` placeholders", ", ".join(f"`{k}`" for k in lo.get("owner_placeholders", {}))],
                   ["STATUS.md", "'Current' and 'Next' describe work finished in October (mutate, NetworkX "
                                 "backtest, sympy subset timing)"],
                   ["RESULTS.md §5", "spurious `_meta` bullet"],
                   ["Rubric figures", "no PR-curve, ensemble-vs-base or APFDc-vs-baselines figure"],
                   ["Tests", "dataset-dependent tests are not marked to skip without data"],
                   ["`stp.paths` in a non-editable install", "fails (configs/data.yaml not packaged); smartci does "
                                                             "not import it, so the tool is unaffected"]]), ""]
    return "\n".join(out)


def main() -> None:
    (paths.ROOT / "reports" / "AUDIT.md").write_text(build(), encoding="utf-8")
    print("wrote reports/AUDIT.md")


if __name__ == "__main__":
    main()
