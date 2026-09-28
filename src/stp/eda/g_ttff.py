"""3.G Time-to-first-failure (the "hours saved" story). SAMPLE-BASED: <= 300 failed runs per project (seeded).

Simulation assumptions: test classes run sequentially; the cost of a class is its *actual* duration in that run;
TTFF = elapsed time until the first failing class finishes.
Orderings (history strictly before the run, same project + stage):
  Random        expected TTFF over 20 shuffles
  QTF           ascending duration in the previous run of the stage (classes unseen there get the stage median)
  LastFail      ascending time since the class last failed (never failed -> last), ties broken by QTF
                (= the paper's cbt_LastFail_Asc)
  Oracle        shortest failing class first (ceiling)
"""
from __future__ import annotations

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stp import paths
from stp.eda.common import PALETTE, save_json, savefig, style, with_macro

RUN_KEY = ["project", "pr_name", "build_id", "stage_id"]
STRATS = ["Random", "QTF", "LastFail", "Oracle"]


def sample_runs(runs: pd.DataFrame, labels: pd.DataFrame, k: int, seed: int) -> pd.DataFrame:
    r = runs.sort_values(["project", "stage_id", "build_timestamp"]).copy()
    prev = r.groupby(["project", "stage_id"])[["pr_name", "build_id"]].shift(1)
    r["prev_pr_name"], r["prev_build_id"] = prev.pr_name, prev.build_id
    fr = r[r.failed].merge(labels[RUN_KEY + ["has_ftf", "all_ftf"]], on=RUN_KEY, how="left")
    return fr.sample(frac=1.0, random_state=seed).groupby("project").head(k).reset_index(drop=True)


def ttff(order_dur: np.ndarray, order_fail: np.ndarray) -> float:
    idx = np.flatnonzero(order_fail)
    return float(np.cumsum(order_dur)[idx[0]]) if len(idx) else np.nan


def simulate(sample: pd.DataFrame, n_shuffles: int, seed: int) -> pd.DataFrame:
    tr = f"read_parquet('{paths.TEST_RESULTS_DIR.as_posix()}/*/*.parquet', hive_partitioning=true)"
    con = duckdb.connect()
    s = sample[RUN_KEY + ["build_timestamp", "prev_pr_name", "prev_build_id"]].copy()
    s["sid"] = np.arange(len(s))
    con.register("s", s)
    cur = con.sql(f"""
        SELECT s.sid, t.testclass, t.duration_s::DOUBLE dur, t.outcome::VARCHAR = 'fail' AS fail
        FROM {tr} t JOIN s ON t.project = s.project AND t.pr_name::VARCHAR = s.pr_name AND t.build_id = s.build_id
                            AND t.stage_id::VARCHAR = s.stage_id""").df()
    prev = con.sql(f"""
        SELECT s.sid, t.testclass, t.duration_s::DOUBLE prev_dur
        FROM {tr} t JOIN s ON t.project = s.project AND t.pr_name::VARCHAR = s.prev_pr_name
                            AND t.build_id = s.prev_build_id AND t.stage_id::VARCHAR = s.stage_id""").df()
    lastfail = con.sql(f"""
        SELECT s.sid, f.testclass, max(f.build_timestamp) last_fail_ts
        FROM read_parquet('{paths.FAILURES_PQ.as_posix()}') f
        JOIN s ON f.project = s.project AND f.stage_id = s.stage_id AND f.build_timestamp < s.build_timestamp
        GROUP BY ALL""").df()
    d = cur.merge(prev, on=["sid", "testclass"], how="left").merge(lastfail, on=["sid", "testclass"], how="left")
    rng = np.random.default_rng(seed)
    out = []
    for sid, g in d.groupby("sid", sort=True):
        dur, fail = g.dur.to_numpy(), g.fail.to_numpy()
        med = np.nanmedian(g.prev_dur) if g.prev_dur.notna().any() else 0.0
        pdur = g.prev_dur.fillna(med).to_numpy()
        since = np.where(g.last_fail_ts.notna(), -g.last_fail_ts.fillna(0).to_numpy(), np.inf)
        res = {"sid": sid, "suite_s": dur.sum(), "n_classes": len(dur), "n_fail": int(fail.sum()),
               "has_prev_run": bool(g.prev_dur.notna().any())}
        res["Random"] = np.mean([ttff(dur[p], fail[p]) for p in (rng.permutation(len(dur)) for _ in range(n_shuffles))])
        o = np.lexsort((rng.random(len(dur)), pdur))
        res["QTF"] = ttff(dur[o], fail[o])
        o = np.lexsort((rng.random(len(dur)), pdur, since))
        res["LastFail"] = ttff(dur[o], fail[o])
        res["Oracle"] = float(dur[fail].min()) if fail.any() else np.nan
        out.append(res)
    res = pd.DataFrame(out).merge(sample.assign(sid=np.arange(len(sample)))[["sid"] + RUN_KEY + ["has_ftf", "all_ftf"]],
                                  on="sid")
    return res


def summarize(res: pd.DataFrame) -> dict:
    out = {"n_sampled_failed_runs": res.groupby("project").size().to_dict(),
           "note": "SAMPLE: <= 300 failed runs per project, uniformly sampled within project (seeded)."}
    for label, d in [("all_failed_runs", res), ("runs_all_failures_first_time", res[res.all_ftf == True])]:  # noqa: E712
        sec = {"n": d.groupby("project").size().to_dict()}
        for s in STRATS + ["suite_s"]:
            sec[f"median_min_{s}"] = with_macro((d.groupby("project")[s].median() / 60).to_dict())
        for s in ["QTF", "LastFail"]:
            sec[f"median_minutes_saved_vs_random_{s}"] = with_macro(
                ((d.Random - d[s]).groupby(d.project).median() / 60).to_dict())
        out[label] = sec
    return out


def plot(s: dict) -> None:
    style()
    projects = paths.PROJECTS
    fig, axes = plt.subplots(1, 2, figsize=(13, 3.8), sharey=True)
    for ax, key, title in [(axes[0], "all_failed_runs", "all failed runs"),
                           (axes[1], "runs_all_failures_first_time", "runs where every failure is first-time")]:
        x = np.arange(len(projects) + 1)
        w = 0.2
        for i, st in enumerate(STRATS):
            d = s[key][f"median_min_{st}"]
            vals = [d["per_project"].get(p, np.nan) for p in projects] + [d["macro"] or np.nan]
            ax.bar(x + (i - 1.5) * w, np.maximum(np.nan_to_num(vals, nan=0), 0.01), w - 0.02,
                   color=PALETTE[i], label=st)
        ax.set_yscale("log")
        ax.set_xticks(x, projects + ["MACRO"])
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        ax.set_title(f"Median minutes to first failure — {title}")
        ax.legend(ncols=4, fontsize=8)
    axes[0].set_ylabel("minutes (log)")
    fig.text(0.01, -0.03, "Sample of ≤300 failed runs per project; sequential execution with actual class durations.",
             fontsize=7)
    savefig(fig, "G_time_to_first_failure")


def run() -> dict:
    cfg = paths.config()["eda"]
    runs = pd.read_parquet(paths.RUNS_PQ)
    labels = pd.read_parquet(paths.INTERIM / "failed_run_labels.parquet")
    sample = sample_runs(runs, labels, cfg["ttff_max_failed_runs_per_project"], cfg["seed"])
    res = simulate(sample, cfg["ttff_random_shuffles"], cfg["seed"])
    res.to_parquet(paths.INTERIM / "ttff_sample.parquet", index=False)
    s = summarize(res)
    save_json(s, "G_ttff")
    plot(s)
    return s


if __name__ == "__main__":
    import json

    s = run()
    print(json.dumps({k: v for k, v in s["all_failed_runs"].items() if k != "n"}, indent=1, default=str)[:3000])
