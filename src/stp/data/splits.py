"""Phase 1.1: build-level chronological split and rolling-origin windows, plus the as-of time columns.

Split. Per project, builds `(project, pr_name, build_id)` are ordered by build start = min(build_timestamp) over
their stages (TVM stages of one build can start days apart). The first 70% of builds are train, the next 15% val,
the last 15% test. All stages of a build share its split, so no build is spread across splits.

Rolling origin. The last 30% of each project's builds (val + test) is cut into consecutive 30-day windows starting
at the train/val boundary. Window k is evaluated with a model fitted on everything that *finished* before the
window starts (expanding training set). The column `roll_window` (k = 0, 1, ...) is null for train builds.

As-of time. Each run gets `start_ts` = build_timestamp and `end_ts` = start + clip(build_duration, 1 s, CAP_S).
A run R may use the results of run Q only if Q.end_ts <= R.start_ts (and Q is not R).
The cap is 24 h: p99.9 of build_duration is 25.6 h, 0.12% of runs exceed 24 h, and the maximum (83 days) is
not a plausible test-execution time (reports/results/phase0_facts.json, fact 1d).

Output: data/processed/splits_build.parquet (one row per run). Usage: python -m stp.data.splits
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from stp import paths
from stp.results import save_result

CAP_S = 24 * 3600
WINDOW_S = 30 * 86400
RUN_KEY = ["project", "pr_name", "build_id", "stage_id"]


def build_splits(runs: pd.DataFrame) -> pd.DataFrame:
    cfg = paths.config()["split"]
    r = runs[RUN_KEY + ["build_timestamp", "build_duration", "failed", "run_id"]].copy()
    r["start_ts"] = r["build_timestamp"]
    r["end_ts"] = r["start_ts"] + r["build_duration"].clip(lower=1, upper=CAP_S)
    r["duration_capped"] = r["build_duration"] > CAP_S
    b = r.groupby(["project", "pr_name", "build_id"], as_index=False).start_ts.min().rename(
        columns={"start_ts": "build_start_ts"})
    b = b.sort_values(["project", "build_start_ts", "pr_name", "build_id"]).reset_index(drop=True)
    b["rank"] = b.groupby("project").cumcount()
    b["n_builds"] = b.groupby("project").build_start_ts.transform("size")
    frac = (b["rank"] + 1) / b["n_builds"]
    q1, q2 = cfg["train"], cfg["train"] + cfg["val"]
    b["split"] = np.where(frac <= q1, "train", np.where(frac <= q2, "val", "test"))
    boundary = b[b.split != "train"].groupby("project").build_start_ts.min().rename("roll_origin_ts")
    b = b.join(boundary, on="project")
    k = np.floor((b.build_start_ts - b.roll_origin_ts) / WINDOW_S)
    b["roll_window"] = pd.array(np.where(b.split == "train", np.nan, k), dtype="Int16")
    b["roll_window_start_ts"] = b.roll_origin_ts + b.roll_window.astype("float64") * WINDOW_S
    out = r.merge(b[["project", "pr_name", "build_id", "build_start_ts", "split", "roll_window",
                     "roll_window_start_ts"]], on=["project", "pr_name", "build_id"], how="left", validate="m:1")
    assert out.split.notna().all() and len(out) == len(runs)
    return out.sort_values(["project", "start_ts", "pr_name", "build_id", "stage_id"]).reset_index(drop=True)


def summary(s: pd.DataFrame) -> dict:
    g = s.groupby(["project", "split"])
    runs = g.size().unstack().reindex(columns=["train", "val", "test"]).fillna(0).astype(int)
    builds = s.drop_duplicates(["project", "pr_name", "build_id"]).groupby(["project", "split"]).size().unstack()
    fr = g.failed.mean().unstack()
    dates = s.groupby(["project", "split"]).start_ts.agg(["min", "max"])
    windows = s[s.roll_window.notna()].groupby("project").roll_window.max() + 1
    return {
        "cap_hours": CAP_S / 3600, "share_runs_capped": float(s.duration_capped.mean()),
        "n_runs_capped": int(s.duration_capped.sum()), "window_days": WINDOW_S / 86400,
        "runs": runs.to_dict(orient="index"), "builds": builds.to_dict(orient="index"),
        "failed_run_rate": fr.to_dict(orient="index"),
        "date_range": {f"{p}|{sp}": [pd.to_datetime(v["min"], unit="s").strftime("%Y-%m-%d"),
                                     pd.to_datetime(v["max"], unit="s").strftime("%Y-%m-%d")]
                       for (p, sp), v in dates.iterrows()},
        "n_roll_windows": windows.astype(int).to_dict(),
        "builds_with_stages_in_different_splits": int(
            s.groupby(["project", "pr_name", "build_id"]).split.nunique().gt(1).sum()),
    }


def main() -> None:
    runs = pd.read_parquet(paths.RUNS_PQ)
    s = build_splits(runs)
    paths.PROCESSED.mkdir(parents=True, exist_ok=True)
    s.to_parquet(paths.SPLITS_BUILD_PQ, index=False)
    sm = summary(s)
    save_result("splits", sm)
    print(pd.DataFrame(sm["runs"]).T.to_string())
    print("windows", sm["n_roll_windows"], "capped", sm["n_runs_capped"],
          "multi-split builds", sm["builds_with_stages_in_different_splits"])


if __name__ == "__main__":
    main()
