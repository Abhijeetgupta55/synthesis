"""GATE 1 checks on the built feature store.

  bruteforce   N random real runs (stratified: N/10 per project, half of them failed runs): every feature and label
               of every test in the run is recomputed from raw tables with the pure reference functions
               (stp.features.bruteforce) and compared with the store. Integer/boolean columns must be equal; float
               columns must agree to 1e-6 relative (summation order and libm `log` can differ in the last bits).
  signal       single-feature PR-AUC on a sample of training rows (all positives + random negatives, PR-AUC
               reported against the full-population base rate). Any feature with PR-AUC > 0.95 is flagged as
               suspicious (a leak would make one column almost perfectly predictive).

Outputs: reports/results/leakage_bruteforce.json, reports/results/leakage_signal.json
Usage:   python -m stp.features.verify_store [--runs 50] [--seed 7] [--only bruteforce|signal]
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from stp import paths
from stp.features.bruteforce import ProjectContext
from stp.features.schema import EVAL_ONLY, FEATURES, LABELS
from stp.features.store import parts_glob, store_dir, store_ready
from stp.results import connect, save_result

CHECK_COLS = [c for c in FEATURES if c != "semantic_sim"] + LABELS + EVAL_ONLY


def _dtype(c: str) -> str:
    return FEATURES[c]["dtype"] if c in FEATURES else ("float32" if c in EVAL_ONLY else "bool")


def compare(store_rows: pd.DataFrame, brute: pd.DataFrame) -> dict:
    m = store_rows.merge(brute, on="testclass", suffixes=("_s", "_b"))
    res = {"n_tests_store": len(store_rows), "n_tests_brute": len(brute), "n_joined": len(m), "mismatches": []}
    if not (len(m) == len(store_rows) == len(brute)):
        res["mismatches"].append({"column": "_row_set", "detail": "test sets differ"})
    for c in CHECK_COLS:
        dt = _dtype(c)
        a = m[f"{c}_s"].to_numpy()
        b = m[f"{c}_b"].to_numpy().astype(dt)
        if "float" in dt:
            ok = np.isclose(a.astype(float), b.astype(float), rtol=1e-6, atol=1e-9)
        else:
            ok = a == b
        if not ok.all():
            i = np.flatnonzero(~ok)[:3]
            res["mismatches"].append({"column": c, "n_bad": int((~ok).sum()), "tests": m.testclass.iloc[i].tolist(),
                                      "store": a[i].tolist(), "brute": b[i].tolist()})
    return res


def check_bruteforce(n_runs: int, seed: int, projects: list[str] | None = None) -> dict:
    """projects=None checks all; a subset re-checks those projects and keeps earlier results for the others."""
    con = connect()
    per = max(1, n_runs // len(paths.PROJECTS))
    results = []
    todo = projects or paths.PROJECTS
    prev = paths.RESULTS / "leakage_bruteforce.json"
    if projects and prev.exists():
        import json
        results = [r for r in json.loads(prev.read_text())["runs"] if r["project"] not in projects]
    for p in todo:
        rng = np.random.default_rng([seed, paths.PROJECTS.index(p)])
        if not store_ready(p):
            print(f"  [bruteforce] {p}: store not built, skipped")
            continue
        t0 = time.time()
        runs = pd.read_parquet(store_dir(p) / "runs.parquet")
        tests = pd.read_parquet(store_dir(p) / "tests.parquet")
        failed = runs[runs.failed].run_idx.to_numpy()
        passed = runs[~runs.failed].run_idx.to_numpy()
        n_f = min(len(failed), (per + 1) // 2)
        pick = list(rng.choice(failed, n_f, replace=False)) + list(rng.choice(passed, per - n_f, replace=False))
        ctx = ProjectContext(p)
        for ri in pick:
            run = runs[runs.run_idx == ri].iloc[0]
            st = con.sql(f"SELECT * FROM read_parquet('{parts_glob(p)}') WHERE run_idx = {int(ri)}").df()
            st = st.merge(tests, on="test_id")
            q = ctx.runs[(ctx.runs.pr_name == run.pr_name) & (ctx.runs.build_id == run.build_id)
                         & (ctx.runs.stage_id == run.stage_id)].iloc[0]
            bf = ctx.recompute(q)
            r = compare(st, bf)
            r.update(project=p, run_idx=int(ri), run_id=run.run_id, failed=bool(run.failed),
                     n_fail=int(st.y_fail.sum()), n_test_file_in_diff=int(st.test_file_in_diff.sum()),
                     n_cof_nonzero=int((st.cof_max > 0).sum()), n_new=int(st.is_new_test.sum()))
            r["match"] = not r["mismatches"]
            results.append(r)
            print(f"  [bruteforce] {p} run {ri}: {len(st)} tests, match={r['match']}", flush=True)
        print(f"  [bruteforce] {p}: {time.time() - t0:.0f}s", flush=True)
    results.sort(key=lambda r: (paths.PROJECTS.index(r["project"]), r["run_idx"]))
    n_ok = sum(r["match"] for r in results)
    out = {"n_runs": len(results), "n_match": n_ok, "seed": seed, "columns_checked": CHECK_COLS,
           "n_rows_checked": int(sum(r["n_joined"] for r in results)),
           "coverage": {"rows_failing": int(sum(r["n_fail"] for r in results)),
                        "rows_test_file_in_diff": int(sum(r["n_test_file_in_diff"] for r in results)),
                        "rows_cofail_nonzero": int(sum(r["n_cof_nonzero"] for r in results)),
                        "rows_new_test": int(sum(r["n_new"] for r in results))},
           "runs": results}
    save_result("leakage_bruteforce", out)
    print(f"[bruteforce] {n_ok}/{len(results)} runs match")
    return out


def check_signal(neg_per_project: int = 200_000, seed: int = 7, threshold: float = 0.95) -> dict:
    from sklearn.metrics import average_precision_score

    con = connect()
    feats = [c for c in FEATURES if c != "semantic_sim"]
    per = {}
    for p in paths.PROJECTS:
        if not store_ready(p):
            continue
        runs = pd.read_parquet(store_dir(p) / "runs.parquet", columns=["run_idx", "split"])
        con.register("rs", runs[runs.split == "train"])
        n_all, n_pos = con.sql(f"SELECT count(*), sum(y_fail::INT) FROM read_parquet('{parts_glob(p)}') "
                               "SEMI JOIN rs USING (run_idx)").fetchone()
        frac = min(1.0, neg_per_project / max(1, n_all - n_pos))
        d = con.sql(f"""SELECT {', '.join(feats)}, y_fail FROM read_parquet('{parts_glob(p)}') SEMI JOIN rs USING (run_idx)
                        WHERE y_fail OR hash(run_idx * 1000003 + test_id + {seed}) % 1000000 < {int(frac * 1e6)}""").df()
        con.unregister("rs")
        w = np.where(d.y_fail, 1.0, 1.0 / frac)   # inverse-probability weights restore the population base rate
        per[p] = {}
        for c in feats:
            x = d[c].astype(float).to_numpy()
            x = np.nan_to_num(x, nan=0.0)
            # orient each feature so that larger = riskier (choose the better of the two directions)
            ap = max(average_precision_score(d.y_fail, x, sample_weight=w),
                     average_precision_score(d.y_fail, -x, sample_weight=w))
            per[p][c] = ap
        print(f"  [signal] {p}: n={len(d):,}, base rate {n_pos / n_all:.5f}, "
              f"max PR-AUC {max(per[p].values()):.3f} ({max(per[p], key=per[p].get)})", flush=True)
    flagged = sorted({(p, c) for p, v in per.items() for c, ap in v.items() if ap > threshold})
    out = {"threshold": threshold, "pr_auc_single_feature_train": per,
           "flagged": [{"project": p, "feature": c, "pr_auc": per[p][c]} for p, c in flagged],
           "macro_by_feature": {c: float(np.mean([per[p][c] for p in per])) for c in feats}}
    save_result("leakage_signal", out)
    print(f"[signal] flagged: {out['flagged']}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", default="bruteforce,signal")
    ap.add_argument("--projects", default=None)
    a = ap.parse_args()
    if "bruteforce" in a.only:
        check_bruteforce(a.runs, a.seed, a.projects.split(",") if a.projects else None)
    if "signal" in a.only:
        check_signal(seed=a.seed)


if __name__ == "__main__":
    main()
