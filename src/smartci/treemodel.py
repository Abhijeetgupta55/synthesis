"""Pure-numpy evaluator for LightGBM text models (numerical splits), so the pytest plugin does not import lightgbm
(which pulls in scikit-learn and costs seconds of start-up per test session).

Semantics follow LightGBM's Tree::NumericalDecision: decision_type bit 1 = default_left, bits 2-3 = missing type
(0 none, 1 zero, 2 NaN). With missing type 'zero', values with |x| <= 1e-35 (and NaN) take the default direction;
with 'NaN', NaN takes it; otherwise NaN is treated as 0. Then x <= threshold goes left.
Checked against lightgbm.Booster.predict in tests/test_smartci.py.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

K_ZERO = 1e-35


class Tree:
    def __init__(self, kv: dict[str, str]):
        n_leaves = int(kv["num_leaves"])
        self.leaf_value = np.array(kv["leaf_value"].split(), float)
        if n_leaves == 1:
            self.split_feature = np.zeros(0, int)
            return
        self.split_feature = np.array(kv["split_feature"].split(), int)
        self.threshold = np.array(kv["threshold"].split(), float)
        dt = np.array(kv["decision_type"].split(), int)
        if (dt & 1).any():
            raise ValueError("categorical splits are not supported by smartci.treemodel")
        self.default_left = (dt >> 1) & 1 == 1
        self.missing_type = (dt >> 2) & 3
        self.left = np.array(kv["left_child"].split(), int)
        self.right = np.array(kv["right_child"].split(), int)

    def predict(self, X: np.ndarray) -> np.ndarray:
        n = len(X)
        if len(self.split_feature) == 0:
            return np.full(n, self.leaf_value[0])
        node = np.zeros(n, int)
        out = np.empty(n)
        active = np.arange(n)
        while len(active):
            nd = node[active]
            x = X[active, self.split_feature[nd]]
            mt = self.missing_type[nd]
            isnan = np.isnan(x)
            x0 = np.where(isnan & (mt != 2), 0.0, x)
            use_default = ((mt == 1) & (np.abs(x0) <= K_ZERO)) | ((mt == 2) & isnan)
            go_left = np.where(use_default, self.default_left[nd], x0 <= self.threshold[nd])
            nxt = np.where(go_left, self.left[nd], self.right[nd])
            leaf = nxt < 0
            out[active[leaf]] = self.leaf_value[~nxt[leaf]]
            node[active[~leaf]] = nxt[~leaf]
            active = active[~leaf]
        return out


class TextModel:
    def __init__(self, path: Path):
        text = Path(path).read_text(encoding="utf-8")
        header, _, rest = text.partition("Tree=")
        self.feature_names = []
        self.sigmoid = 1.0
        for ln in header.splitlines():
            if ln.startswith("feature_names="):
                self.feature_names = ln.split("=", 1)[1].split()
            if ln.startswith("objective=") and "sigmoid:" in ln:
                self.sigmoid = float(ln.split("sigmoid:")[1].split()[0])
        self.trees = []
        for block in ("Tree=" + rest).split("Tree=")[1:]:
            body = block.split("end of trees")[0]
            kv = {}
            for ln in body.splitlines()[1:]:
                if "=" in ln:
                    k, v = ln.split("=", 1)
                    kv[k] = v
            if "num_leaves" in kv:
                self.trees.append(Tree(kv))

    def raw(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        return np.sum([t.predict(X) for t in self.trees], axis=0) if self.trees else np.zeros(len(X))

    def predict(self, X: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-self.sigmoid * self.raw(X)))
