"""Phase 3.8 interpretation: SHAP vs LR coefficients, and the 20 worst-ranked first-time failures.

SHAP (TreeExplainer, exact for trees) on a random 20k-row sample of testC: mean |SHAP| per feature = global
importance in log-odds units. LR: |standardised coefficient|. Agreement = Spearman correlation of the two rankings.
Error analysis: on testC failed runs, every first-time failure's position under the LightGBM ordering (fraction of
the run's tests ahead of it); the 20 worst, with their feature values and the three largest SHAP contributions.

Outputs: reports/results/interpret.json, reports/figures/shap_global.png
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from stp.eda.common import PALETTE, savefig, style
from stp.features.store import store_dir
from stp.models.common import load, load_model
from stp.results import save_result


def main(n_shap: int = 20_000) -> dict:
    import matplotlib.pyplot as plt
    import shap

    lg = load_model("lgbm")
    cal = load_model("cal_lgbm")
    lr = load_model("lr")
    cols = lg["cols"]
    X, m = load("testC", cols, ["y_fail", "y_ftf_asof", "project", "run_idx", "test_id", "y_duration_s",
                                "dur_ema_asof"])
    rng = np.random.default_rng(0)
    idx = rng.choice(len(X), min(n_shap, len(X)), replace=False)
    ex = shap.TreeExplainer(lg["model"])
    sv = ex.shap_values(X[idx])
    sv = sv[1] if isinstance(sv, list) else sv
    imp = np.abs(sv).mean(axis=0)
    shap_imp = dict(zip(cols, imp.tolist()))
    coef = lr["model"][-1].coef_[0]
    lr_cols = lr["cols"]
    lr_imp = dict(zip(lr_cols, np.abs(coef).tolist()))
    common = [c for c in cols if c in lr_imp]
    rho = spearmanr([shap_imp[c] for c in common], [lr_imp[c] for c in common]).statistic
    style()
    top = sorted(cols, key=lambda c: -shap_imp[c])[:15]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.barh(top[::-1], [shap_imp[c] for c in top[::-1]], color=PALETTE[0])
    ax.set_xlabel("mean |SHAP| (log-odds), testC sample")
    ax.set_title("LightGBM global feature importance")
    savefig(fig, "shap_global")

    # error analysis over all testC failed runs
    p = cal.predict({c: X[:, j] for j, c in enumerate(cols)})
    prio = -(p / (m.dur_ema_asof.to_numpy() + 1e-3))
    rows = []
    for (pj, ri), ix in m.groupby(["project", "run_idx"]).indices.items():
        ftf = m.y_ftf_asof.to_numpy(bool)[ix]
        if not ftf.any():
            continue
        o = np.argsort(prio[ix], kind="stable")
        pos = np.empty(len(ix))
        pos[o] = np.arange(len(ix)) / max(1, len(ix) - 1)
        for k in np.flatnonzero(ftf):
            rows.append((pj, int(ri), int(m.test_id.to_numpy()[ix][k]), float(pos[k]), int(ix[k])))
    e = pd.DataFrame(rows, columns=["project", "run_idx", "test_id", "position_frac", "row"])
    worst = e.sort_values("position_frac", ascending=False).head(20)
    sv_w = ex.shap_values(X[worst.row.to_numpy()])
    sv_w = sv_w[1] if isinstance(sv_w, list) else sv_w
    names = {}
    out_w = []
    for k, r in enumerate(worst.itertuples()):
        if r.project not in names:
            names[r.project] = pd.read_parquet(store_dir(r.project) / "tests.parquet").set_index("test_id").testclass
        contrib = sorted(zip(cols, sv_w[k]), key=lambda t: -abs(t[1]))[:3]
        out_w.append({"project": r.project, "run_idx": r.run_idx, "testclass": names[r.project].get(r.test_id),
                      "position_frac": r.position_frac,
                      "features": {c: float(X[r.row, j]) for j, c in enumerate(cols)},
                      "top_shap": [{"feature": c, "shap": float(v)} for c, v in contrib]})
    res = {"shap_mean_abs": shap_imp, "lr_abs_coef": lr_imp, "spearman_shap_vs_lr": float(rho),
           "n_shap_rows": int(len(idx)), "n_ftf_testC": int(len(e)),
           "ftf_position_frac_median": float(e.position_frac.median()) if len(e) else None,
           "worst20": out_w}
    save_result("interpret", res)
    return res


if __name__ == "__main__":
    main()
