"""Phase B.4 error analysis -> reports/results/error_analysis.json. Uses stored models and the feature store only.

Part 1. Why the model loses to QTF on first-time failures of existing tests (FirstFail-old, test split).
  Hypothesis: the model puts tests that have failed before ahead of tests that never failed, so when the failing
  test is one that never failed, time is spent first on previously-failed tests.
  For every test-split failed run with a FirstFail-old target (harness rules: non-target failures removed), and for
  the tuned LightGBM (`cal_lgbm`, the model the headline APFDc numbers use) and QTF (last as-of duration ascending):
    - share of the suite's time spent before the first target is reached (= TTFF / suite time),
    - of that time, the share spent on tests that had failed before (h_n_fail > 0),
    - the target's own duration percentile within its run,
  and, model only, mean P(fail) of previously-failed vs never-failed passing tests.
  Ties broken with the harness's seeds; aggregated per project, then macro over projects (as in MODELING.md).

Part 2. Why the TVM-only model collapses from validation (valB PR-AUC 0.680) to test (0.037).
  For TVM, per split (train, val first half = valA, val second half = valB, test; halves by run start time):
  row failure rate, failed-run rate, share of rows / failures whose test class never appeared in train,
  share of failures from test classes that failed in train, share of failures in the top-5 failing classes,
  and population stability index (PSI, 10 train-decile bins) of the main features vs train.

Usage: python -m stp.models.error_analysis [--part 1|2|both]
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from stp import paths
from stp.evaluation.harness import EVAL_COLS, eval_runs, iter_runs, jira_flaky_ids, target_masks
from stp.evaluation.metrics import DURATION_EPS
from stp.features.store import store_dir
from stp.models.common import load_model
from stp.results import save_result, load_result

EPS = 1e-3


def _order(prio_asc: np.ndarray, rng) -> np.ndarray:
    return np.lexsort((rng.random(len(prio_asc)), prio_asc))


def _run_stats(o, dur, fail, target, prev_failed) -> dict:
    keep = ~fail | target
    o = o[keep[o]]
    d = dur[o] + DURATION_EPS
    t = target[o]
    first = int(np.flatnonzero(t)[0])
    before = slice(0, first)
    t_before = d[before].sum()
    return {"time_share_before_target": float(t_before / d.sum()),
            "prev_failed_share_of_time_before": float(d[before][prev_failed[o][before]].sum() / t_before)
            if t_before > 0 else 0.0,
            "position_share": first / max(1, len(o) - 1)}


def part1() -> dict:
    cal = load_model("cal_lgbm")
    cols = sorted(set(cal.entry["cols"]) | set(EVAL_COLS) | {"dur_ema_asof", "dur_last_asof", "h_n_fail"})
    per_proj = {}
    for p in paths.PROJECTS:
        runs = eval_runs(p, ("test",))
        if runs.empty:
            continue
        tests = pd.read_parquet(store_dir(p) / "tests.parquet")
        flaky = jira_flaky_ids(p, tests)
        meta = runs.set_index("run_idx")
        acc = defaultdict(list)
        for ri, d in iter_runs(p, set(runs.run_idx.tolist()), cols):
            tg = target_masks(d, float(meta.loc[ri].start_ts), flaky)["FirstFail-old"]
            if not tg.any():
                continue
            dur = d["y_duration_s"].astype(np.float64)
            fail = d["y_fail"].astype(bool)
            prev = d["h_n_fail"].astype(np.float64) > 0
            pf = cal.predict(d)
            rng = np.random.default_rng([11, 0, ri])          # harness seed scheme (base_seed 11, seed 0)
            om = _order(-(pf / (d["dur_ema_asof"].astype(np.float64) + EPS)), rng)
            rng = np.random.default_rng([11, 0, ri])
            oq = _order(d["dur_last_asof"].astype(np.float64) + EPS, rng)
            for name, o in (("model", om), ("QTF", oq)):
                for k, v in _run_stats(o, dur, fail, tg, prev).items():
                    acc[f"{name}|{k}"].append(v)
            ranks = pd.Series(dur).rank(pct=True).to_numpy()
            acc["target_duration_percentile"].append(float(ranks[tg].mean()))
            passing = ~fail
            if (passing & prev).any() and (passing & ~prev).any():
                acc["p_prev_failed"].append(float(pf[passing & prev].mean()))
                acc["p_never_failed"].append(float(pf[passing & ~prev].mean()))
            acc["target_p_percentile"].append(float(pd.Series(pf).rank(pct=True).to_numpy()[tg].mean()))
            acc["prev_failed_share_of_tests"].append(float(prev.mean()))
        if acc:
            per_proj[p] = {"n_runs": len(acc["target_duration_percentile"]),
                           **{k: float(np.median(v)) if "share" in k or "percentile" in k else float(np.mean(v))
                              for k, v in acc.items()}}
        print(f"  [error_analysis] {p}: {per_proj.get(p, {}).get('n_runs', 0)} FirstFail-old runs", flush=True)
    keys = sorted({k for v in per_proj.values() for k in v if k != "n_runs"})
    macro = {k: float(np.mean([v[k] for v in per_proj.values() if k in v])) for k in keys}
    return {"definition": "per project: median over runs (shares, percentiles) or mean (probabilities); "
                          "macro = mean over projects", "n_runs": int(sum(v["n_runs"] for v in per_proj.values())),
            "per_project": per_proj, "macro": macro}


FEATS = ["h_n_fail", "h_fail_rate", "h_days_since_last_fail", "h_fails_last_30d", "h_n_runs_seen", "dur_ema_asof",
         "is_new_test", "test_file_in_diff", "bm25_test_vs_diff", "cof_max", "chg_n_files"]


def part2() -> dict:
    p = "tvm"
    runs = pd.read_parquet(store_dir(p) / "runs.parquet")
    val = runs[runs.split == "val"].sort_values("start_ts")
    half = len(val) // 2
    lab = dict(zip(runs.run_idx, runs.split))
    lab.update({ri: "valA" for ri in val.run_idx.iloc[:half]})
    lab.update({ri: "valB" for ri in val.run_idx.iloc[half:]})
    splits = ["train", "valA", "valB", "test"]
    files = sorted(store_dir(p).glob("part-*.parquet"))
    cols = ["run_idx", "test_id", "y_fail"] + FEATS
    # pass 1: train test classes, train failing classes, a train sample for decile edges
    train_ids, train_fail_ids, sample = set(), set(), {f: [] for f in FEATS}
    rng = np.random.default_rng(0)
    for f in files:
        t = pq.read_table(f, columns=cols).to_pandas()
        t = t[t.run_idx.map(lab) == "train"]
        train_ids.update(t.test_id.unique().tolist())
        train_fail_ids.update(t.test_id[t.y_fail.astype(bool)].unique().tolist())
        s = t.sample(min(len(t), 20000), random_state=int(rng.integers(1 << 30)))
        for c in FEATS:
            sample[c].append(pd.to_numeric(s[c], errors="coerce").to_numpy(np.float64))
    edges = {}
    for c in FEATS:
        x = np.concatenate(sample[c])
        x = x[np.isfinite(x)]
        e = np.unique(np.quantile(x, np.linspace(0, 1, 11)))
        edges[c] = e[1:-1]                                  # inner edges; bins = len+1
    # pass 2: per split aggregates
    agg = {s: {"rows": 0, "fails": 0, "rows_unseen": 0, "fails_unseen": 0, "fails_prev_train_fail": 0,
               "fail_counts": defaultdict(int), "runs": set(), "failed_runs": set(),
               "hist": {c: np.zeros(len(edges[c]) + 2) for c in FEATS}} for s in splits}
    for f in files:
        t = pq.read_table(f, columns=cols).to_pandas()
        t["split"] = t.run_idx.map(lab)
        for s, g in t.groupby("split"):
            if s not in agg:
                continue
            a = agg[s]
            y = g.y_fail.astype(bool).to_numpy()
            unseen = ~g.test_id.isin(train_ids).to_numpy()
            a["rows"] += len(g)
            a["fails"] += int(y.sum())
            a["rows_unseen"] += int(unseen.sum())
            a["fails_unseen"] += int((y & unseen).sum())
            a["fails_prev_train_fail"] += int((y & g.test_id.isin(train_fail_ids).to_numpy()).sum())
            for tid in g.test_id[y]:
                a["fail_counts"][int(tid)] += 1
            a["runs"].update(g.run_idx.unique().tolist())
            a["failed_runs"].update(g.run_idx[y].unique().tolist())
            for c in FEATS:
                x = pd.to_numeric(g[c], errors="coerce").to_numpy(np.float64)
                nan = ~np.isfinite(x)
                b = np.searchsorted(edges[c], x[~nan], side="right")
                a["hist"][c][: len(edges[c]) + 1] += np.bincount(b, minlength=len(edges[c]) + 1)
                a["hist"][c][-1] += nan.sum()                # last bin = missing
    out = {}
    ref = {c: agg["train"]["hist"][c] / agg["train"]["hist"][c].sum() for c in FEATS}
    for s in splits:
        a = agg[s]
        top5 = sum(sorted(a["fail_counts"].values(), reverse=True)[:5])
        psi = {}
        for c in FEATS:
            q = a["hist"][c] / max(1.0, a["hist"][c].sum())
            r = ref[c]
            m = (q > 0) | (r > 0)
            qq, rr = np.clip(q[m], 1e-4, None), np.clip(r[m], 1e-4, None)
            psi[c] = float(((qq - rr) * np.log(qq / rr)).sum())
        out[s] = {"n_runs": len(a["runs"]), "failed_run_rate": len(a["failed_runs"]) / max(1, len(a["runs"])),
                  "rows": a["rows"], "row_failure_rate": a["fails"] / max(1, a["rows"]), "n_fail_rows": a["fails"],
                  "share_rows_unseen_class": a["rows_unseen"] / max(1, a["rows"]),
                  "share_fails_unseen_class": a["fails_unseen"] / max(1, a["fails"]),
                  "share_fails_class_failed_in_train": a["fails_prev_train_fail"] / max(1, a["fails"]),
                  "n_distinct_failing_classes": len(a["fail_counts"]),
                  "share_fails_top5_classes": top5 / max(1, a["fails"]),
                  "psi_vs_train": psi}
    tr = load_result("transfer").get("variants", {}).get("tvm_only", {})
    return {"splits": out, "tvm_only_pr_auc": {"valB": tr.get("valB_pr_auc"), "testC": tr.get("testC_pr_auc")},
            "note": "valA/valB = time halves of the val runs (the training pipeline samples rows from them); "
                    "PSI < 0.1 small, 0.1–0.25 moderate, > 0.25 large shift"}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="both")
    a = ap.parse_args(argv)
    try:
        res = load_result("error_analysis")
        res.pop("_meta", None)
    except FileNotFoundError:
        res = {}
    if a.part in ("1", "both"):
        res["firstfail_old"] = part1()
        save_result("error_analysis", res)
    if a.part in ("2", "both"):
        res["tvm_drift"] = part2()
        save_result("error_analysis", res)
    print("wrote reports/results/error_analysis.json")


if __name__ == "__main__":
    main()
