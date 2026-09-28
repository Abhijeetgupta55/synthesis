"""3.H Split feasibility and distribution shift: chronological 70/15/15 split per project by run build_timestamp.

Split boundaries are the 70th / 85th percentiles of each project's run timestamps. A build's stages can have
different timestamps (TVM), so the split is at run level; all first-time-failure labels use full prior history.
"""
from __future__ import annotations

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stp import paths
from stp.eda.common import PALETTE, save_json, savefig, style

RUN_KEY = ["project", "pr_name", "build_id", "stage_id"]


def assign_splits(runs: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    cfg = paths.config()["split"]
    q1, q2 = cfg["train"], cfg["train"] + cfg["val"]
    bounds = runs.groupby("project").build_timestamp.quantile([q1, q2]).unstack()
    bounds.columns = ["train_end_ts", "val_end_ts"]
    r = runs.join(bounds, on="project")
    r["split"] = np.where(r.build_timestamp <= r.train_end_ts, "train",
                          np.where(r.build_timestamp <= r.val_end_ts, "val", "test"))
    dates = {p: {"train_end": pd.to_datetime(b.train_end_ts, unit="s", utc=True).strftime("%Y-%m-%d %H:%M"),
                 "val_end": pd.to_datetime(b.val_end_ts, unit="s", utc=True).strftime("%Y-%m-%d %H:%M")}
             for p, b in bounds.iterrows()}
    return r, dates


def summarize(r: pd.DataFrame, labels: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    r = r.merge(labels[RUN_KEY + ["has_ftf", "all_ftf"]], on=RUN_KEY, how="left")
    r["has_ftf"] = r.has_ftf.fillna(False).astype(bool)
    r["all_ftf"] = r.all_ftf.fillna(False).astype(bool)
    tr = f"read_parquet('{paths.TEST_RESULTS_DIR.as_posix()}/*/*.parquet', hive_partitioning=true)"
    con = duckdb.connect()
    con.register("rs", r[RUN_KEY + ["split"]])
    classes = con.sql(f"""
        SELECT DISTINCT t.project, rs.split, t.testclass
        FROM {tr} t JOIN rs ON t.project = rs.project AND t.pr_name::VARCHAR = rs.pr_name
             AND t.build_id = rs.build_id AND t.stage_id::VARCHAR = rs.stage_id""").df()
    rows = []
    for (p, sp), d in r.groupby(["project", "split"]):
        rows.append({"project": p, "split": sp, "runs": len(d), "failed_runs": int(d.failed.sum()),
                     "ftf_runs": int(d.has_ftf.sum()), "all_ftf_runs": int(d.all_ftf.sum()),
                     "failure_rate": d.failed.mean(), "mean_duration_h": d.duration_h.mean(),
                     "from": d.build_dt.min().strftime("%Y-%m-%d"), "to": d.build_dt.max().strftime("%Y-%m-%d")})
    tbl = pd.DataFrame(rows)
    cls = classes.groupby(["project", "split"]).testclass.nunique().rename("distinct_test_classes").reset_index()
    tbl = tbl.merge(cls, on=["project", "split"], how="left")
    unseen = {}
    for p, d in classes.groupby("project"):
        train = set(d[d.split == "train"].testclass)
        test = set(d[d.split == "test"].testclass)
        unseen[p] = len(test - train) / len(test) if test else None
    tbl["pct_test_classes_unseen_in_train"] = tbl.apply(
        lambda x: unseen.get(x.project) if x.split == "test" else None, axis=1)
    minimum = paths.config()["eda"]["min_first_fail_runs_in_test"]
    test = tbl[tbl.split == "test"].set_index("project")
    too_small = sorted(test[test.ftf_runs < minimum].index)
    return {"table": tbl.to_dict(orient="records"), "too_small_to_evaluate_alone": too_small,
            "min_ftf_runs_threshold": minimum,
            "test_split_ftf_runs": test.ftf_runs.to_dict(),
            "test_split_ftf_runs_total": int(test.ftf_runs.sum()),
            "unseen_test_classes_in_test": {"per_project": unseen,
                                            "macro": float(np.mean([v for v in unseen.values() if v is not None]))}}, tbl


def plot(tbl: pd.DataFrame, minimum: int) -> None:
    style()
    projects = paths.PROJECTS
    fig, ax = plt.subplots(figsize=(9, 3.4))
    x = np.arange(len(projects))
    w = 0.27
    for i, (sp, c) in enumerate([("train", PALETTE[0]), ("val", PALETTE[2]), ("test", PALETTE[1])]):
        vals = [tbl[(tbl.project == p) & (tbl.split == sp)].ftf_runs.sum() for p in projects]
        ax.bar(x + (i - 1) * w, np.maximum(vals, 0.8), w - 0.02, color=c, label=sp)
    ax.axhline(minimum, color="black", lw=1, ls="--")
    ax.text(len(projects) - 0.5, minimum * 1.1, f"{minimum} runs", ha="right", fontsize=8)
    ax.set_yscale("log")
    ax.set_xticks(x, projects)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.set_ylabel("runs with ≥1 first-time failure (log)")
    ax.set_title("First-time-failure runs per chronological split")
    ax.legend(ncols=3, fontsize=8)
    savefig(fig, "H_split_ftf_runs")


def run() -> dict:
    runs = pd.read_parquet(paths.RUNS_PQ)
    labels = pd.read_parquet(paths.INTERIM / "failed_run_labels.parquet")
    r, dates = assign_splits(runs)
    r[RUN_KEY + ["split"]].to_parquet(paths.INTERIM / "splits.parquet", index=False)
    s, tbl = summarize(r, labels)
    s["split_dates"] = dates
    save_json(s, "H_split")
    plot(tbl, s["min_ftf_runs_threshold"])
    return s


if __name__ == "__main__":
    s = run()
    print(pd.DataFrame(s["table"]).to_string())
    print("too small:", s["too_small_to_evaluate_alone"])
