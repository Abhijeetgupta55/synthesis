"""Generate reports/MODELING.md from reports/results/*.json (no hand-typed numbers).

Usage: python -m stp.reports.modeling_md
"""
from __future__ import annotations

from stp import paths
from stp.reports.fmt import ci, diff_ci, f3, pct, table
from stp.results import load_result

GL = {"macro10": "Macro (10)", "kafka": "Kafka", "tvm": "TVM", "small8": "Small-8"}
SUBS = ["All", "FirstFail-asof", "FirstFail-old", "New/Edited"]


def _r(name):
    f = paths.RESULTS / f"{name}.json"
    return load_result(name) if f.exists() else None


def sec_labels(L):
    if not L:
        return "## 1. Labels\n\n(not generated yet)\n"
    rows = [[p, f"{sum(v[s]['rows'] for s in v):,}",
             pct(sum(v[s]['n_fail'] for s in v) / sum(v[s]['rows'] for s in v), 3),
             pct(sum(v[s]['n_ftf_asof'] for s in v) / sum(v[s]['rows'] for s in v), 4)] for p, v in L["per_project"].items()]
    return "\n".join(["## 1. Task and label distribution", "",
                      "Binary classification per (run, test class): P(test fails in this run) from as-of features.", "",
                      table(["Project", "Rows", "Positive rate", "First-time-failure rate"], rows), "",
                      f"Pooled positive rate {pct(L['pooled']['pos_rate_fail'], 3)}; the always-'pass' classifier is "
                      f"**{pct(L['pooled']['always_pass_accuracy'], 2)} accurate** and finds no failure at all. Accuracy "
                      "is therefore useless; the primary classification metric is PR-AUC, and the domain metrics are "
                      "APFDc and time to first failure.", ""])


def sec_sampling(T, S):
    if not T:
        return "## 2. Training data\n\n(not generated yet)\n"
    rows = [[p, v["runs"], v["failed_runs"], f"{v['rows']:,}", f"{v['positives']:,}", f3(v["failed_run_weight"])]
            for p, v in T["per_project"].items()]
    s = ["## 2. Training data: negative sampling, validation halves", "",
         f"K = {T['K']} negatives per run (half from change-related tests), at most {T['max_failed_runs_per_project']} "
         f"failed training runs per project (evenly spaced in time), {pct(T['passing_frac'], 0)} of passing runs; "
         "inverse-probability weights restore the population (`stp/models/data.py`).", "",
         table(["Project", "Runs", "Failed runs", "Rows", "Positives", "Failed-run weight"], rows), "",
         "valA (earlier half of validation, unsampled): tuning + early stopping. valB (later half): calibration, "
         "stacking, scope choice, thresholds. testC (unsampled test runs): classification metrics. Domain metrics: "
         "all failed test runs.", ""]
    if S:
        s += ["History scope (default LightGBM, valB PR-AUC): " + ", ".join(
            f"{k} {v['valB_pr_auc']:.4f} ({v['n_features']} features)" for k, v in S["results"].items())
              + f" → **{S['choice']}**.", ""]
    return "\n".join(s)


def sec_reg(LR, RF, LG):
    s = ["## 3. Regularisation and hyperparameter tuning", ""]
    if LR:
        b = LR["best"]
        z = LR["l1_zeroed_by_C"]
        s += ["### Logistic regression (L2 / L1 / Elastic-Net × C)", "",
              table(["Penalty", "C", "valA PR-AUC", "zero coefs"],
                    [[r["penalty"], f"{r['C']:g}", f"{r['val_pr_auc']:.4f}", r["n_zero_coef"]] for r in LR["grid"]]), "",
              f"Best: **{b['penalty']}, C = {b['C']:g}** (valA PR-AUC {b['val_pr_auc']:.4f}). Grid on "
              f"{LR['train_rows_grid']:,} rows, refit on {LR['train_rows_refit']:,}. Figures `reg_lr_C.png`, "
              "`reg_lr_l1_path.png`.", "",
              "L1 drives coefficients to exactly zero as C shrinks (embedded feature selection): " + "; ".join(
                  f"C={c}: {len(v)} zeroed" for c, v in z.items()) + ". At the smallest C the survivors are the "
              "features with independent signal; correlated duplicates (h_/hs_ counts) are dropped first.", ""]
    if RF:
        s += ["### Random forest (bagging)", "",
              table(["max_depth", "min_samples_leaf", "max_features", "valA PR-AUC", "train PR-AUC (w)"],
                    [[r["max_depth"], r["min_samples_leaf"], r["max_features"], f"{r['val_pr_auc']:.4f}",
                      f"{r['train_pr_auc_weighted']:.4f}"] for r in RF["trials"]]), "",
              "Depth sweep (train vs valA): " + ", ".join(
                  f"{r['max_depth']}: {r['train_pr_auc_weighted']:.3f}/{r['val_pr_auc']:.3f}" for r in RF["depth_sweep"])
              + ". Deeper trees fit training better and validation worse: the gap is overfitting to rare positives "
              "(`reg_rf_depth.png`).", ""]
    if LG:
        s += ["### LightGBM (boosting): Optuna TPE", "",
              f"{len(LG['trials'])} trials ({sum(t['state'] == 'PRUNED' for t in LG['trials'])} pruned), best valA "
              f"PR-AUC {LG['best_value']:.4f}. Best parameters: " + ", ".join(
                  f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}" for k, v in LG["best_params"].items()) + ".", "",
              "Top-5 configurations (valA PR-AUC → valA APFDc): " + "; ".join(
                  f"#{t['number']} {t['val_pr_auc']:.4f} → {t['val_apfdc_macro']:.4f}" for t in LG["top5"]) + ".", "",
              "Parameter importance (fANOVA): " + ", ".join(
                  f"{k} {v:.2f}" for k, v in LG["param_importance"].items() if isinstance(v, float)) + ".", "",
              f"Refit on {LG['train_rows_refit']:,} rows stopped early at round {LG['refit_best_iteration']} (valA "
              f"PR-AUC {LG['refit_valA_pr_auc']:.4f}). Figures: `tune_lgbm_history.png`, `tune_lgbm_importance.png`, "
              "`tune_lgbm_slice.png`, `reg_lgbm_curves.png` (train vs validation, tuned vs unregularised).", ""]
    return "\n".join(s)


def sec_cls(C):
    if not C:
        return "## 4. Classification metrics (testC)\n\n(not generated yet)\n"
    rows = []
    for m, r in C["models"].items():
        k = r["at_k"]["macro"]
        rows.append([m, f3(r["pr_auc"]), f3(r.get("pr_auc_macro")), f3(r["roc_auc"]), f"{r['brier']:.5f}",
                     "–" if r.get("brier_raw") is None else f"{r['brier_raw']:.5f}", f3(r.get("ftf_pr_auc")),
                     f"{k['p@10']:.3f} / {k['r@10']:.3f}", f"{k['p@100']:.3f} / {k['r@100']:.3f}",
                     f3(r.get("f1_test"))])
    return "\n".join(["## 4. Classification metrics on held-out test rows (testC, unsampled)", "",
                      f"{C['n_rows']:,} rows, {C['n_pos']:,} positives (base rate {pct(C['base_rate'], 3)}). "
                      "ROC-AUC looks high because the negative mass is huge and easy; PR-AUC is the honest number.", "",
                      table(["Model", "PR-AUC (pooled)", "PR-AUC (macro)", "ROC-AUC", "Brier (cal.)", "Brier (raw)",
                             "PR-AUC first-time", "P@10 / R@10", "P@100 / R@100", "F1 @ valB thr."], rows), "",
                      "Confusion matrices at the valB-chosen threshold and reliability curves: "
                      "`models_classification.json`.", ""])


def sec_domain(M):
    if not M:
        return "## 5. Domain metrics vs baselines\n\n(not generated yet)\n"
    s = ["## 5. Domain metrics vs every baseline (test split, failed runs)", "",
         "Cells: macro APFDc [95% PR-clustered CI]; † = a project with < 30 runs. Δ vs best = paired difference to the "
         "best simple baseline chosen on validation (* = CI excludes 0).", ""]
    for sub in SUBS:
        c = M["cells"].get(sub)
        if not c:
            continue
        best = M["best_simple_by_val"].get(sub)
        s.append(f"### {sub} (best simple baseline: {best})")
        s.append("")
        rows = []
        for m in sorted(c["macro10"], key=lambda m: -(c["macro10"][m]["apfdc"]["mean"] or 0)):
            row = [m] + [ci(c.get(g, {}).get(m, {}).get("apfdc")) for g in GL]
            med = c["macro10"][m]["ttff_min_median"]
            row.append("–" if med.get("median") is None else f"{med['median']:.1f}")
            row.append(pct(c["macro10"][m]["first10_share"]))
            row.append(diff_ci(M["vs_best_simple"].get(sub, {}).get("macro10", {}).get(m)))
            rows.append(row)
        s.append(table(["Method"] + list(GL.values()) + ["Median min to 1st failure", "1st in 10%", "Δ vs best"], rows))
        s.append("")
    if "ablation_question" in M:
        q = M["ablation_question"]
        s += ["### Ablations (A history → B + cost → C + change → D + co-failure), FirstFail-old", "",
              q["question"], "",
              table(["Variant", "Δ APFDc vs best simple (macro, 95% CI)"],
                    [[k, diff_ci(v)] for k, v in q.items() if k != "question"]), ""]
    if "vs_cbt_lastfail_All" in M:
        v = M["vs_cbt_lastfail_All"]
        s += [f"**Model vs cbt_LastFail on All (as-of):** {diff_ci(v)}. "
              + ("The model does **not** beat cbt_LastFail on All." if not (v.get("excludes_zero") and v["mean"] > 0)
                 else "The model beats cbt_LastFail on All."), ""]
    if "regime_shift" in M:
        s += ["### Regime shift and project influence", "",
              table(["Subset", "Δ with Kafka/TVM windows", "Δ without"],
                    [[k, diff_ci(v["with"]), diff_ci(v["without_kafka_tvm"])] for k, v in M["regime_shift"].items()]),
              "", "Leave-one-project-out Δ (main model vs best simple), FirstFail-asof: " + ", ".join(
                  f"−{p}: {v['mean']:+.3f}" for p, v in M.get("leave_one_project_out", {}).get("FirstFail-asof", {}).items()
                  if v["mean"] is not None), ""]
    return "\n".join(s)


def sec_ens(C):
    if not C:
        return ""
    e = C["error_corr"]
    rows = [[n] + [f"{x:.2f}" for x in r] for n, r in zip(e["names"], e["residual_corr"])]
    return "\n".join(["## 6. Ensembles: bagging vs boosting, soft voting, stacking", "",
                      "Residual (y − p) correlation on testC: highly correlated errors leave little for averaging "
                      "to remove.", "", table([""] + e["names"], rows), "",
                      "Whether voting/stacking beats the best single model: compare their rows in §4 and §5.", ""])


def sec_transfer(T):
    if not T:
        return "## 7. Python transfer (TVM)\n\n(not generated yet)\n"
    return "\n".join(["## 7. Python transfer (TVM pytest suites)", "",
                      table(["Variant", "Train projects", "TVM valB PR-AUC", "TVM testC PR-AUC", "testC PR-AUC first-time"],
                            [[k, len(v["train_projects"]), f3(v["valB_pr_auc"]), f3(v["testC_pr_auc"]),
                              f3(v.get("testC_pr_auc_ftf"))] for k, v in T["variants"].items()]), "",
                      f"Shipped: **{T['chosen']}** (highest TVM valB PR-AUC; test shown for confirmation only).", ""])


def sec_interp(I):
    if not I:
        return ""
    top = sorted(I["shap_mean_abs"], key=lambda c: -I["shap_mean_abs"][c])[:10]
    rows = [[w["project"], w["testclass"], f"{w['position_frac']:.2f}",
             "; ".join(f"{t['feature']} {t['shap']:+.2f}" for t in w["top_shap"])] for w in I["worst20"]]
    return "\n".join(["## 8. Interpretation", "",
                      "Top SHAP features (mean |SHAP|): " + ", ".join(f"{c} {I['shap_mean_abs'][c]:.3f}" for c in top)
                      + f". Spearman agreement with |LR coefficient| ranking: {I['spearman_shap_vs_lr']:.2f}.", "",
                      f"Median position of first-time failures in their run (0 = first): {f3(I['ftf_position_frac_median'])}"
                      f" over {I['n_ftf_testC']} testC first-time failures. The 20 worst-ranked:", "",
                      table(["Project", "Test class", "Position", "Top SHAP contributions"], rows), ""])


def main() -> None:
    parts = ["# MODELING", "", "Generated by `python -m stp.reports.modeling_md` from `reports/results/*.json`. "
             "Do not edit by hand.", "",
             sec_labels(_r("labels")), sec_sampling(_r("train_sample"), _r("scope_choice")),
             sec_reg(_r("tune_lr"), _r("tune_rf"), _r("tune_lgbm")), sec_cls(_r("models_classification")),
             sec_domain(_r("models")), sec_ens(_r("models_classification")), sec_transfer(_r("transfer")),
             sec_interp(_r("interpret"))]
    (paths.ROOT / "reports" / "MODELING.md").write_text("\n".join(parts), encoding="utf-8")
    print("wrote reports/MODELING.md")


if __name__ == "__main__":
    main()
