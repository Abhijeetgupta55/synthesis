"""GATE 2: reproduce the LRTS paper's history baselines with our own harness, then re-run them as-of.

Protocol (LRTS evaluation/eval_main.py, eval_tcp.py, extract_hist_features.py):
  universe     runs of the paper subset (artifact/metadata/dataset.csv); stages with > 50 runs
  features     per (project, stage), runs walked in start order; for run N the features use runs 1..N-1:
               failure_count, last_failure (1 if the previous run of the test failed, +1 per later pass, 0 if new),
               last_duration (0 if new)
  techniques   QTF            ascending last_duration + eps
               LastFail_Asc   ascending last_failure + eps
               FailCount_Desc ascending 1 / (failure_count + eps)
               cbt_LastFail_Asc ascending (last_failure + eps) * (last_duration + eps)
               Random         uniform priority
               ties broken uniformly at random; 10 seeds averaged per run (eps = 1e-6)
  metric       APFDc_uniqueBug with durations + 0.001 (stp.evaluation.metrics.apfdc)
  variants     All        every failed run
               FirstFail  failing tests that are not first failures (per project+stage, paper universe), are
                          JIRA-flaky (name ends with a listed class whose fix is after the run), or failed in only
                          some stages of the build are removed from the run; runs with no failure left are dropped
  aggregation  mean over seeds per run, over runs per project, macro over projects

Mode `as_of` changes only the history rule: run Q is applied to the state of run R iff Q.end <= R.start
(end = start + capped build_duration). Everything else is identical, so the gap between the modes is the effect
of the concurrency leak.

Outputs: reports/results/gate2_reproduction.json, data/processed/eval/lrts_repro_runs.parquet
Usage:   python -m stp.baselines.lrts_repro
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from stp import paths
from stp.evaluation.metrics import apfdc
from stp.features.store import store_dir, store_ready
from stp.results import save_result

EPS = 1e-6
SEEDS = 10
TECHS = ["Random", "QTF", "LastFail_Asc", "FailCount_Desc", "cbt_LastFail_Asc"]
TARGETS = {  # docs/PROMPT.md fact 7 (paper protocol, macro APFDc_uniqueBug)
    "All": {"QTF": 0.677, "LastFail_Asc": 0.795, "FailCount_Desc": 0.720, "cbt_LastFail_Asc": 0.836},
    "FirstFail": {"QTF": 0.798, "LastFail_Asc": 0.467, "FailCount_Desc": 0.312, "cbt_LastFail_Asc": 0.762},
}
EVAL_DIR = paths.PROCESSED / "eval"


def iter_store_runs(project: str, columns: list[str]):
    """Yield (run_idx, DataFrame-like dict of arrays) from the store parts, in run order."""
    parts = sorted(store_dir(project).glob("part-*.parquet"))
    for f in parts:
        t = pq.read_table(f, columns=["run_idx"] + columns)
        r = t.column("run_idx").to_numpy()
        cols = {c: t.column(c).to_numpy(zero_copy_only=False) for c in columns}
        u, starts = np.unique(r, return_index=True)
        ends = np.r_[starts[1:], len(r)]
        for ri, a, b in zip(u, starts, ends):
            yield int(ri), {c: v[a:b] for c, v in cols.items()}


def firstfail_keep(project: str, runs: pd.DataFrame, tests: pd.DataFrame) -> dict[int, set[int]]:
    """run_idx -> failing test ids that survive the FirstFail filters (first, jira, stageunique)."""
    f = pd.read_parquet(paths.FAILURES_PQ, filters=[("project", "==", project)],
                        columns=["pr_name", "build_id", "stage_id", "build_timestamp", "testclass", "ftf_paper",
                                 "in_paper_subset"])
    f = f[f.in_paper_subset]
    f["build_id"] = f.build_id.astype(np.int64)
    fl = pd.read_parquet(paths.FLAKY_PQ)
    fl = fl[(fl.project == project) & fl.testclass.notna() & fl.fix_timestamp.notna()]
    fl = fl.sort_values("fix_timestamp").drop_duplicates("testclass")
    flaky = list(zip(fl.testclass, fl.fix_timestamp))
    # stage-unique: failing in this stage but not in every (paper-subset) stage of the build
    st = runs[runs.in_paper_subset].groupby(["pr_name", "build_id"]).stage_id.nunique().rename("n_stages")
    nf = f.groupby(["pr_name", "build_id", "testclass"]).stage_id.nunique().rename("n_fail_stages")
    f = f.join(st, on=["pr_name", "build_id"]).join(nf, on=["pr_name", "build_id", "testclass"])
    f["stageunique"] = f.n_fail_stages < f.n_stages
    f["jira"] = [any(tc.endswith(c) and fx > ts for c, fx in flaky) for tc, ts in zip(f.testclass, f.build_timestamp)]
    f["keep"] = f.ftf_paper.fillna(False).astype(bool) & ~f.jira & ~f.stageunique
    f = f.merge(runs[["pr_name", "build_id", "stage_id", "run_idx"]], on=["pr_name", "build_id", "stage_id"])
    f = f.merge(tests, on="testclass")
    return {int(k): set(g.test_id.tolist()) for k, g in f[f.keep].groupby("run_idx")}


def evaluate_run(ids, dur, fail, fc, lf, ld, keep_ff: set[int] | None, rng) -> dict:
    """Seed-averaged APFDc for each technique, All and FirstFail variants."""
    pr = {"QTF": ld + EPS, "LastFail_Asc": lf + EPS, "FailCount_Desc": 1.0 / (fc + EPS),
          "cbt_LastFail_Asc": (lf + EPS) * (ld + EPS)}
    ff_mask = None
    if keep_ff is not None:
        ff_mask = ~fail | np.isin(ids, np.fromiter(keep_ff, np.int64, len(keep_ff)))
    out = {}
    for tech in TECHS:
        a, b = [], []
        for _ in range(SEEDS):
            base = rng.random(len(ids)) if tech == "Random" else pr[tech]
            o = np.lexsort((rng.random(len(ids)), base))
            a.append(apfdc(dur[o], fail[o]))
            if ff_mask is not None and (fail & ff_mask).any():
                oo = o[ff_mask[o]]
                b.append(apfdc(dur[oo], fail[oo]))
        out[("All", tech)] = float(np.mean(a))
        out[("FirstFail", tech)] = float(np.mean(b)) if b else float("nan")
    return out


def run_project(project: str, seed: int = 0) -> pd.DataFrame:
    t0 = time.time()
    runs = pd.read_parquet(store_dir(project) / "runs.parquet")
    tests = pd.read_parquet(store_dir(project) / "tests.parquet")
    paper = runs[runs.in_paper_subset]
    n_stage = paper.groupby("stage_id").size()
    keep_stages = set(n_stage[n_stage > 50].index)
    in_uni = runs.in_paper_subset.to_numpy()
    stage_ids = {s: i for i, s in enumerate(sorted(runs.stage_id.unique()))}
    stage_of = runs.stage_id.map(stage_ids).to_numpy()
    eval_mask = in_uni & runs.failed.to_numpy() & runs.stage_id.isin(keep_stages).to_numpy()
    start, end = runs.start_ts.to_numpy(), runs.end_ts.to_numpy()
    keep_ff = firstfail_keep(project, runs, tests)
    n_t, n_s = len(tests), len(stage_ids)
    state = {m: {"fc": np.zeros(n_t * n_s), "lf": np.zeros(n_t * n_s), "ld": np.zeros(n_t * n_s)}
             for m in ("start_order", "as_of")}
    pending: list[tuple[float, int, tuple]] = []   # as-of: (end, run_idx, data) waiting to be applied
    import heapq

    def apply(s, k, fail, dur):
        s["fc"][k] += fail
        s["lf"][k] = np.where(fail, 1.0, s["lf"][k] + 1.0)
        s["ld"][k] = dur

    rng = np.random.default_rng(seed)
    rows = []
    for ri, d in iter_store_runs(project, ["test_id", "y_fail", "y_duration_s"]):
        if not in_uni[ri]:
            continue
        t = start[ri]
        while pending and pending[0][0] <= t:
            _, _, (k, fl, du) = heapq.heappop(pending)
            apply(state["as_of"], k, fl, du)
        ids = d["test_id"].astype(np.int64)
        fail = d["y_fail"].astype(bool)
        dur = d["y_duration_s"].astype(np.float64)
        k = stage_of[ri] * n_t + ids
        if eval_mask[ri]:
            for mode, s in state.items():
                res = evaluate_run(ids, dur, fail, s["fc"][k], s["lf"][k], s["ld"][k], keep_ff.get(ri, set()), rng)
                for (var, tech), v in res.items():
                    rows.append((ri, mode, var, tech, v))
        apply(state["start_order"], k, fail.astype(np.float64), dur)   # LRTS: visible to the very next run
        heapq.heappush(pending, (end[ri], ri, (k, fail.astype(np.float64), dur)))
    df = pd.DataFrame(rows, columns=["run_idx", "mode", "variant", "tcp", "apfdc"])
    df.insert(0, "project", project)
    print(f"  [repro] {project}: {df.run_idx.nunique():,} evaluated runs in {time.time() - t0:.0f}s", flush=True)
    return df


def paper_values() -> pd.DataFrame:
    """The paper's own per-run outcomes, aggregated with the same protocol (EDA §A; stage filter applied)."""
    b = pd.read_parquet(paths.BASELINES_PQ)
    b = b[b.variant.isin(["d_nofilter", "d_first_jira_stageunique"]) & b.tcp.isin(TECHS)]
    b["variant"] = b.variant.map({"d_nofilter": "All", "d_first_jira_stageunique": "FirstFail"})
    return b.groupby(["variant", "tcp", "project"]).APFDc_uniqueBug.agg(["mean", "count"]).rename(columns={"count": "size"}).reset_index()


def main() -> None:
    frames = [run_project(p) for p in paths.PROJECTS if store_ready(p)]
    df = pd.concat(frames, ignore_index=True)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(EVAL_DIR / "lrts_repro_runs.parquet", index=False)
    per = df.dropna(subset=["apfdc"]).groupby(["mode", "variant", "tcp", "project"]).apfdc.agg(["mean", "size"])
    per = per.reset_index()
    pv = paper_values()
    out = {"protocol": __doc__, "per_project": {}, "macro": {}, "paper_macro": {}, "n_runs": {}, "paper_n_runs": {},
           "gate": {}}
    for (mode, var, tech), g in per.groupby(["mode", "variant", "tcp"]):
        out["per_project"].setdefault(mode, {}).setdefault(var, {})[tech] = dict(zip(g.project, g["mean"]))
        out["macro"].setdefault(mode, {}).setdefault(var, {})[tech] = float(g["mean"].mean())
        out["n_runs"].setdefault(mode, {}).setdefault(var, {})[tech] = int(g["size"].sum())
    for (var, tech), g in pv.groupby(["variant", "tcp"]):
        out["paper_macro"].setdefault(var, {})[tech] = float(g["mean"].mean())
        out["paper_n_runs"].setdefault(var, {})[tech] = int(g["size"].sum())
        out.setdefault("paper_per_project", {}).setdefault(var, {})[tech] = dict(zip(g.project, g["mean"]))
    ok = True
    for var, tg in TARGETS.items():
        for tech, target in tg.items():
            ours = out["macro"]["start_order"][var][tech]
            diff = ours - target
            passed = abs(diff) <= 0.005
            ok &= passed
            out["gate"][f"{var}|{tech}"] = {"target": target, "ours": ours, "diff": diff, "pass": passed,
                                            "as_of": out["macro"]["as_of"][var][tech]}
    out["gate_pass"] = ok
    save_result("gate2_reproduction", out)
    for k, v in out["gate"].items():
        print(f"{k:28s} target {v['target']:.3f}  ours {v['ours']:.4f}  diff {v['diff']:+.4f}  "
              f"{'PASS' if v['pass'] else 'FAIL'}   as-of {v['as_of']:.4f}")
    print("GATE 2:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
