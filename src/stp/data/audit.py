"""Count cross-checks between the tidy tables and the LRTS metadata. Writes reports/eda_json/audit.json.

Usage:  python -m stp.data.audit
"""
from __future__ import annotations

import pandas as pd

from stp import paths
from stp.eda.common import save_json

RUN_KEY = ["project", "pr_name", "build_id", "stage_id"]
BUILD_KEY = ["project", "pr_name", "build_id"]


def compare_columns(left: pd.DataFrame, right: pd.DataFrame, on: list[str],
                    pairs: list[tuple[str, str]], by: str = "project") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Inner/outer join `left` and `right` on `on` and check each (left_col, right_col) pair for equality.

    Returns (per-group summary, mismatching rows). Rows present on only one side are counted, never dropped."""
    m = left.merge(right, on=on, how="outer", indicator=True, suffixes=("", "_r"))
    both = m[m["_merge"] == "both"].copy()
    ok = pd.Series(True, index=both.index)
    for a, b in pairs:
        eq = both[a].eq(both[b]) | (both[a].isna() & both[b].isna())
        both[f"ok_{a}"] = eq
        ok &= eq
    both["ok"] = ok
    summary = pd.DataFrame({
        "left_only": m[m["_merge"] == "left_only"].groupby(by).size(),
        "right_only": m[m["_merge"] == "right_only"].groupby(by).size(),
        "matched_rows": both.groupby(by).size(),
        "all_equal": both.groupby(by)["ok"].sum(),
    }).fillna(0).astype(int)
    summary["match_rate"] = (summary["all_equal"] / summary["matched_rows"].where(summary["matched_rows"] > 0)).round(6)
    return summary, both[~both["ok"]]


def _records(df: pd.DataFrame) -> list[dict]:
    return df.reset_index().to_dict(orient="records")


def audit_runs(runs: pd.DataFrame) -> dict:
    repo = pd.read_csv(paths.LRTS_DATASET_CSV, dtype={"stage_id": str})
    init = pd.read_csv(paths.LRTS_DATASET_INIT_CSV)
    cols = ["num_pass_class", "num_fail_class", "num_trans_class", "build_timestamp", "build_head_sha", "trunk_sha"]
    summ, mism = compare_columns(runs[RUN_KEY + cols], repo[RUN_KEY + cols].rename(columns={c: c + "_r" for c in cols}),
                                 RUN_KEY, [(c, c + "_r") for c in cols])
    dur = runs.merge(repo[RUN_KEY + ["test_suite_duration_s"]], on=RUN_KEY, suffixes=("", "_repo"))
    rel = (dur.test_suite_duration_s - dur.test_suite_duration_s_repo).abs() / dur.test_suite_duration_s_repo.clip(lower=1)
    per_proj = runs.groupby("project").agg(runs=("run_id", "size"), failed_runs=("failed", "sum"),
                                           paper_runs=("in_paper_subset", "sum"))
    build_defs = {
        "project,pr_name,build_id": runs[BUILD_KEY].drop_duplicates().shape[0],
        "project,build_head_sha": runs[["project", "build_head_sha"]].drop_duplicates().shape[0],
        "project,pr_name,build_id,build_timestamp": runs[BUILD_KEY + ["build_timestamp"]].drop_duplicates().shape[0],
    }
    ts_per_build = runs.groupby(BUILD_KEY).build_timestamp.nunique()
    return {
        "full_dataset_csv_rows": len(runs),
        "full_failed_runs": int(runs.failed.sum()),
        "full_builds_by_definition": build_defs,
        "full_failed_builds": runs[runs.failed][BUILD_KEY].drop_duplicates().shape[0],
        "readme_claims": {"runs": 108366, "builds": 32199, "failed_runs": 49674, "failed_builds": 22763,
                          "mean_duration_h": 6.75, "mean_classes_per_run": 980, "mean_failed_classes_per_failed_run": 5},
        "full_mean_duration_h": runs.duration_h.mean(),
        "full_share_runs_over_2h": (runs.duration_h > 2).mean(),
        "full_mean_classes_per_run": runs.n_classes.mean(),
        "full_mean_failed_classes_per_failed_run": runs[runs.failed].num_fail_class.mean(),
        "repo_dataset_csv_rows": len(repo),
        "repo_dataset_init_builds": len(init),
        "repo_rows_found_in_full": int(summ.matched_rows.sum()),
        "repo_rows_missing_from_full": int(summ.right_only.sum()),
        "repo_vs_full_column_match": _records(summ),
        "repo_vs_full_first_mismatches": mism.head(20)[RUN_KEY + [c for c in mism.columns if c.startswith("ok_")]]
        .to_dict(orient="records"),
        "duration_rel_diff_repo_vs_full": {"median": rel.median(), "p90": rel.quantile(0.9), "max": rel.max(),
                                           "share_gt_10pct": (rel > 0.10).mean()},
        "per_project": _records(per_proj),
        "kafka_share": {"full": (runs.project == "kafka").mean(),
                        "paper_subset": (runs[runs.in_paper_subset].project == "kafka").mean()},
        "tvm_share": {"full": (runs.project == "tvm").mean(),
                      "paper_subset": (runs[runs.in_paper_subset].project == "tvm").mean()},
        "builds_with_multiple_timestamps_by_project": (ts_per_build > 1).groupby("project").mean().to_dict(),
    }


def audit_test_files(runs: pd.DataFrame) -> dict:
    fa = pd.read_parquet(paths.RUN_FILE_AUDIT_PQ)
    inv = pd.read_csv(paths.INTERIM / "test_file_inventory.csv", index_col=0)
    summ, mism = compare_columns(
        runs[RUN_KEY + ["num_pass_class", "num_fail_class"]], fa, RUN_KEY,
        [("num_pass_class", "file_pass"), ("num_fail_class", "file_fail")])
    return {
        "file_inventory": _records(inv),
        "files_total": int(inv.files.sum()),
        "files_not_in_dataset_csv": int(inv.files_not_in_dataset_csv.sum()),
        "runs_without_file": int(inv.runs_without_file.sum()),
        "pass_fail_count_match": _records(summ),
        "pass_fail_overall_match_rate": summ.all_equal.sum() / max(summ.matched_rows.sum(), 1),
        "first_20_mismatches": mism.head(20)[RUN_KEY + ["num_pass_class", "file_pass", "num_fail_class", "file_fail"]]
        .to_dict(orient="records"),
        "rows_with_other_outcome_codes": int(fa.file_other_outcome.sum()),
        "runs_with_duplicate_testclass": int((fa.file_dup_testclass > 0).sum()),
        "rows_null_duration": int(fa.file_null_duration.sum()),
        "file_column_sets": fa.file_columns.value_counts().to_dict(),
    }


def audit_first_failure(runs: pd.DataFrame) -> dict:
    import duckdb

    per_run = duckdb.sql(f"""
        SELECT project, pr_name, build_id, stage_id,
               sum(ftf_paper::INT) AS my_ftf_paper, sum(ftf::INT) AS my_ftf
        FROM read_parquet('{paths.FAILURES_PQ.as_posix()}') GROUP BY ALL""").df()
    r = runs[runs.in_paper_subset][RUN_KEY + ["lrts_num_first_failure", "num_fail_class"]].merge(
        per_run, on=RUN_KEY, how="left").fillna({"my_ftf_paper": 0, "my_ftf": 0})
    r["agree"] = r.my_ftf_paper == r.lrts_num_first_failure
    r["run_has_ftf_lrts"] = r.lrts_num_first_failure > 0
    r["run_has_ftf_mine"] = r.my_ftf_paper > 0
    by = r.groupby("project").agg(
        runs=("agree", "size"), count_agree=("agree", "mean"),
        lrts_ftf_rows=("lrts_num_first_failure", "sum"), my_ftf_paper_rows=("my_ftf_paper", "sum"),
        my_ftf_full_history_rows=("my_ftf", "sum"),
        lrts_ftf_runs=("run_has_ftf_lrts", "sum"), my_ftf_runs=("run_has_ftf_mine", "sum"),
        run_flag_agree=("run_has_ftf_lrts", lambda s: (s == r.loc[s.index, "run_has_ftf_mine"]).mean()))
    return {
        "per_project": _records(by),
        "overall_count_agreement": r.agree.mean(),
        "overall_run_flag_agreement": (r.run_has_ftf_lrts == r.run_has_ftf_mine).mean(),
        "first_20_disagreements": r[~r.agree].head(20).to_dict(orient="records"),
    }


def audit_changes(runs: pd.DataFrame) -> dict:
    ch = pd.read_parquet(paths.CHANGES_PQ)
    cs = pd.read_csv(paths.LRTS_CHANGE_STATS_CSV)
    # LRTS sums files/additions/deletions over all compare pages without deduplication -> compare the *_raw cols.
    agg = ch.groupby(BUILD_KEY, as_index=False).agg(
        n_files_raw_sum_pages=("n_files_raw_sum_pages", "sum"), additions_raw=("additions_raw", "sum"),
        deletions_raw=("deletions_raw", "sum"))
    summ, mism = compare_columns(
        agg, cs, BUILD_KEY, [("n_files_raw_sum_pages", "num_changed_files"),
                              ("additions_raw", "num_addition"), ("deletions_raw", "num_deletion")])
    return {
        "change_rows": len(ch),
        "builds_with_multiple_base_head_pairs": int(ch.duplicated(BUILD_KEY, keep=False).sum()),
        "compare_found_rate": _records(ch.groupby("project").compare_found.mean().to_frame()),
        "vs_change_stats_csv": _records(summ),
        "vs_change_stats_overall_match_rate": summ.all_equal.sum() / max(summ.matched_rows.sum(), 1),
        "first_20_mismatches": mism.head(20)[BUILD_KEY + ["n_files_raw_sum_pages", "num_changed_files",
                                                          "additions_raw", "num_addition"]].to_dict(orient="records"),
        "dedup_vs_raw_files_differ_share": (ch.n_files != ch.n_files_raw_sum_pages).mean(),
    }


def run(sections: tuple[str, ...] = ("runs", "tests", "ftf", "changes")) -> dict:
    runs = pd.read_parquet(paths.RUNS_PQ)
    out = {}
    if "runs" in sections:
        out["runs"] = audit_runs(runs)
    if "tests" in sections:
        out["test_files"] = audit_test_files(runs)
    if "ftf" in sections:
        out["first_time_failure"] = audit_first_failure(runs)
    if "changes" in sections:
        out["changes"] = audit_changes(runs)
    save_json(out, "audit")
    return out


if __name__ == "__main__":
    import json

    res = run()
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if not isinstance(vv, list)} for k, v in res.items()},
                     indent=1, default=str))
