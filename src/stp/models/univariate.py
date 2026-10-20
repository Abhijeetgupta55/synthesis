"""Phase 3.3: univariate signal of every feature on the training sample (weighted back to the population).

Per feature: single-feature PR-AUC (oriented so larger = riskier), mutual information with the label (on
quantile-binned values), lift by bin (P(fail | bin) / P(fail)), and the same PR-AUC for first-time failures.
Correlation: Spearman correlation matrix of all features (heatmap) and the list of pairs with |rho| > 0.9, which
LightGBM tolerates but which make LR coefficients and SHAP shares unstable (see FEATURES.md for how each is handled).

Outputs: reports/results/univariate.json, reports/figures/features_corr.png, features_lift.png
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, mutual_info_score

from stp.eda.common import PALETTE, savefig, style
from stp.models.common import load, subsample_rows
from stp.models.prep import columns
from stp.results import save_result


def binned(x: np.ndarray, bins: int = 10) -> np.ndarray:
    q = np.unique(np.quantile(x, np.linspace(0, 1, bins + 1)))
    if len(q) <= 2:
        return (x > q[0]).astype(int)
    return np.clip(np.searchsorted(q, x, side="right") - 1, 0, len(q) - 2)


def main(n_rows: int = 1_500_000) -> dict:
    import matplotlib.pyplot as plt

    cols = columns()
    rows = subsample_rows("train", n_rows, 11)
    X, m = load("train", cols, ["y_fail", "y_ftf_asof", "weight"], rows=rows)
    y, yf, w = m.y_fail.to_numpy(bool), m.y_ftf_asof.to_numpy(bool), m.weight.to_numpy()
    base = np.average(y, weights=w)
    out = {}
    for j, c in enumerate(cols):
        x = X[:, j].astype(np.float64)
        ap = average_precision_score(y, x, sample_weight=w)
        an = average_precision_score(y, -x, sample_weight=w)
        direction = 1 if ap >= an else -1
        b = binned(x)
        lift = []
        for k in np.unique(b):
            s = b == k
            lift.append({"bin": int(k), "x_min": float(x[s].min()), "x_max": float(x[s].max()),
                         "share_rows": float(w[s].sum() / w.sum()),
                         "lift": float(np.average(y[s], weights=w[s]) / base) if w[s].sum() else None})
        out[c] = {"pr_auc": float(max(ap, an)), "direction": direction,
                  "pr_auc_ftf": float(average_precision_score(yf, direction * x, sample_weight=w)),
                  "mutual_info": float(mutual_info_score(y, b)), "lift_by_bin": lift,
                  "mean_pos": float(x[y].mean()), "mean_neg_weighted": float(np.average(x[~y], weights=w[~y]))}
    corr = pd.DataFrame(X, columns=cols).sample(min(300_000, len(X)), random_state=0).rank().corr().to_numpy()
    pairs = [{"a": cols[i], "b": cols[j], "rho": float(corr[i, j])} for i in range(len(cols)) for j in range(i + 1, len(cols))
             if abs(corr[i, j]) > 0.9]
    style()
    fig, ax = plt.subplots(figsize=(10, 9))
    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)), cols, rotation=90, fontsize=6)
    ax.set_yticks(range(len(cols)), cols, fontsize=6)
    ax.grid(False)
    fig.colorbar(im, ax=ax, shrink=0.7, label="Spearman ρ")
    ax.set_title("Feature correlation (training sample)")
    savefig(fig, "features_corr")
    top = sorted(cols, key=lambda c: -out[c]["pr_auc"])[:12]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(top[::-1], [out[c]["pr_auc"] for c in top[::-1]], color=PALETTE[0], label="all failures")
    ax.barh(top[::-1], [out[c]["pr_auc_ftf"] for c in top[::-1]], color=PALETTE[1], height=0.4,
            label="first-time failures")
    ax.axvline(base, color="#888", ls="--", lw=1)
    ax.set_xscale("log")
    ax.set_xlabel("single-feature PR-AUC (log; dashed = base rate)")
    ax.set_title("Univariate signal on the training sample")
    ax.legend(fontsize=7)
    savefig(fig, "features_univariate")
    res = {"features": out, "base_rate_weighted": float(base), "n_rows": int(len(y)), "n_pos": int(y.sum()),
           "corr_names": cols, "corr": corr.tolist(), "redundant_pairs_abs_rho_gt_0.9": pairs}
    save_result("univariate", res)
    return res


if __name__ == "__main__":
    main()
