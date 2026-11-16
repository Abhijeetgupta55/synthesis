"""Phase A.4 independent spot check (imports neither `stp` nor `smartci`).

For N randomly chosen held-out (test-split, failed) LRTS runs from the demo bundle (seed logged):
  1. read durations and outcomes from the run's *raw* LRTS test_class.csv.zip with a csv parser written here;
  2. read the run's feature rows from the feature store (as-of features; parquet only);
  3. QTF baseline (LRTS definition): order by the last as-of duration (dur_last_asof) ascending;
  4. shipped model: score with models/global/model.txt (plain lightgbm.Booster), calibrate with np.interp on
     models/global/calibration.json, priority = p / (dur_ema_asof + 0.001) descending;
  5. compute APFDc with a loop written here and compare with the stored per-run values:
     QTF  -> data/processed/eval/baselines_runs/<project>.parquet (harness output, split test, subset All)
             and the demo bundle;
     model -> the demo bundle's 'smartci (LightGBM)' entry (the harness stores no per-run values for the
             exported variant; its 'lgbm' rows are the tuned model before export).
Ties in a priority are reported: when tied tests differ in outcome, APFDc depends on the tie-break, so the
check reports the min/max APFDc over tie-break orders instead of a point value.

Usage: python scripts/audit_spotcheck.py [--seed 20261116] [--n 3]   -> reports/results/audit_spotcheck.json
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow.dataset as ds

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "long_running_test_suites" / "long_running_test_suites" / "processed_test_result"
STORE = ROOT / "data" / "processed" / "features"
MODEL = ROOT / "models" / "global"
TOL = 1e-6


def raw_run(project, pr, build, stage):
    f = RAW / project / f"{pr}_build{build}" / f"stage_{stage}" / "test_class.csv.zip"
    with zipfile.ZipFile(f) as z:
        rows = list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode("utf-8"))))
    h = rows[0]
    it, idur, iout = h.index("testclass"), h.index("duration"), h.index("outcome")
    return {r[it]: (float(r[idur]), int(float(r[iout]))) for r in rows[1:] if r}


def apfdc_loop(durs, fails):
    d = [x + 0.001 for x in durs]
    total, n = sum(d), sum(fails)
    tail, cost = total, 0.0
    for di, fi in zip(d, fails):
        if fi:
            cost += tail - di / 2
        tail -= di
    return cost / (n * total)


def apfdc_range(prio, durs, fails):
    """APFDc for order by `prio` descending; within tied groups put failing tests first (max) or last (min)."""
    prio, durs, fails = map(np.asarray, (prio, durs, fails))
    out = []
    for fail_key in (-fails, fails):            # best case, worst case inside each tie group
        o = np.lexsort((fail_key, -prio))
        out.append(apfdc_loop(durs[o].tolist(), fails[o].tolist()))
    ties = pd.Series(prio).duplicated(keep=False).to_numpy()
    mixed = pd.DataFrame({"p": prio, "f": fails})[ties].groupby("p").f.nunique().gt(1).sum()
    return min(out), max(out), int(ties.sum()), int(mixed)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261116)
    ap.add_argument("--n", type=int, default=3)
    a = ap.parse_args(argv)
    index = json.loads((ROOT / "demo_bundle" / "lrts" / "index.json").read_text(encoding="utf-8"))
    pick = np.random.default_rng(a.seed).choice(len(index), a.n, replace=False)
    schema = json.loads((MODEL / "schema.json").read_text(encoding="utf-8"))
    feats = [f["name"] for f in schema["features"]]
    dflt = {f["name"]: f["default"] for f in schema["features"]}
    cal = json.loads((MODEL / "calibration.json").read_text(encoding="utf-8"))["model"]
    booster = lgb.Booster(model_file=str(MODEL / "model.txt"))
    results = []
    for k in pick:
        e = index[int(k)]
        p, pr, b, st = e["project"], e["pr_name"], int(e["build_id"]), e["stage_id"]
        raw = raw_run(p, pr, b, st)
        runs = pd.read_parquet(STORE / f"project={p}" / "runs.parquet")
        ri = int(runs[(runs.pr_name == pr) & (runs.build_id == b) & (runs.stage_id == st)].run_idx.iloc[0])
        tests = pd.read_parquet(STORE / f"project={p}" / "tests.parquet").set_index("test_id").testclass
        parts = sorted(str(f) for f in (STORE / f"project={p}").glob("part-*.parquet"))
        rows = ds.dataset(parts, format="parquet").to_table(
            filter=ds.field("run_idx") == ri, columns=sorted(set(feats) | {"test_id", "dur_ema_asof", "dur_last_asof"})).to_pandas()
        names = tests.loc[rows.test_id].to_numpy()
        assert set(names) == set(raw), "feature-store test set differs from the raw file"
        durs = np.array([raw[n][0] for n in names])
        fails = np.array([raw[n][1] for n in names])
        X = np.column_stack([pd.to_numeric(rows[c], errors="coerce").fillna(dflt[c]).to_numpy(np.float64)
                             for c in feats]).astype(np.float32)
        r = booster.predict(X)
        pfail = np.interp(r, cal["x"], cal["y"]) + 1e-9 * r
        dur_exp = rows.dur_ema_asof.to_numpy(np.float64)
        prio_model = pfail / (dur_exp + 1e-3)
        prio_qtf = -rows.dur_last_asof.to_numpy(np.float64)  # QTF = LRTS quickest-first: last as-of duration
        m_lo, m_hi, m_ties, m_mixed = apfdc_range(prio_model, durs, fails)
        q_lo, q_hi, q_ties, q_mixed = apfdc_range(prio_qtf, durs, fails)
        rec = json.loads((ROOT / e["file"].replace("lrts/", "demo_bundle/lrts/", 1)).read_text(encoding="utf-8"))
        b_model = rec["methods"]["smartci (LightGBM)"]["apfdc"]
        b_qtf = rec["methods"]["QTF"]["apfdc"]
        h = pd.read_parquet(ROOT / "data" / "processed" / "eval" / "baselines_runs" / f"{p}.parquet")
        h = h[(h.run_idx == ri) & (h.method == "QTF") & (h.subset == "All") & (h.split == "test")]
        h_qtf = float(h.apfdc.iloc[0]) if len(h) else None
        inside = lambda v, lo, hi: v is not None and lo - TOL <= v <= hi + TOL
        res = {"project": p, "pr": pr, "build": b, "stage": st, "run_idx": ri, "n_tests": int(len(names)),
               "n_fail": int(fails.sum()),
               "model": {"recomputed_min": m_lo, "recomputed_max": m_hi, "tied_tests": m_ties,
                         "tie_groups_with_mixed_outcome": m_mixed, "stored_bundle": b_model,
                         "match": inside(b_model, m_lo, m_hi)},
               "qtf": {"recomputed_min": q_lo, "recomputed_max": q_hi, "tied_tests": q_ties,
                       "tie_groups_with_mixed_outcome": q_mixed, "stored_bundle": b_qtf, "stored_harness": h_qtf,
                       "match": inside(b_qtf, q_lo, q_hi) and inside(h_qtf, q_lo, q_hi)}}
        results.append(res)
        print(f"{p} {pr} b{b} {st}: model {m_lo:.6f}..{m_hi:.6f} vs bundle {b_model:.6f} "
              f"[{'MATCH' if res['model']['match'] else 'MISMATCH'}]; QTF {q_lo:.6f}..{q_hi:.6f} vs bundle "
              f"{b_qtf:.6f} / harness {h_qtf} [{'MATCH' if res['qtf']['match'] else 'MISMATCH'}]")
    out = {"seed": a.seed, "n": a.n, "picked_index_positions": [int(k) for k in pick], "runs": results,
           "all_match": all(r["model"]["match"] and r["qtf"]["match"] for r in results)}
    (ROOT / "reports" / "results" / "audit_spotcheck.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("ALL MATCH" if out["all_match"] else "SOME MISMATCH")
    return 0 if out["all_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
