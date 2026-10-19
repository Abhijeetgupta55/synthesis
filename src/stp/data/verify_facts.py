"""Phase 0: recompute the prompt's "facts" 1-5 from the interim tables with exact logic.

  1  concurrency: share of runs whose previous run (same project+stage, by start time) had not finished when this
     run started; whether LRTS `last_outcome` equals "outcome in the previous run (by start) of the same stage that
     contains the test"; how often that previous run was still running; build_duration units and outliers.
  2  first-time failures (EDA definition, after the 15% burn-in): share that are brand-new test classes, whose own
     test file is edited in the build's diff, or existing tests. Exact FQN -> path mapping (stp.features.testmap),
     with a basename-only variant for comparison, and the mapping's match rate per project.
  3  build_duration / test_suite_duration_s (wall-clock vs summed test time), median per project.
  4  regime shift: failed-run rate per EDA split; TVM builds whose stages fall into different splits.
  5  TVM test classes and failures under tests/python.

Output: reports/results/phase0_facts.json.   Usage: python -m stp.data.verify_facts
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from stp import paths
from stp.eda.common import with_macro
from stp.features.testmap import suffix_index, test_path_suffixes
from stp.results import connect, save_result

BURN_IN = 0.15
RUNS = f"read_parquet('{paths.RUNS_PQ.as_posix()}')"


def tr(project: str) -> str:
    return f"read_parquet('{(paths.TEST_RESULTS_DIR / f'project={project}').as_posix()}/*.parquet')"


# ------------------------------------------------------------------------------------------------ fact 1
def fact1(con) -> dict:
    per = con.sql(f"""
        WITH r AS (
          SELECT project, stage_id, build_timestamp ts, build_duration bd,
                 lag(build_timestamp + build_duration) OVER w prev_end,
                 max(build_timestamp + build_duration) OVER (PARTITION BY project, stage_id
                     ORDER BY build_timestamp, pr_name, build_id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) any_prev_end,
                 lag(build_timestamp) OVER w prev_start
          FROM {RUNS} WINDOW w AS (PARTITION BY project, stage_id ORDER BY build_timestamp, pr_name, build_id))
        SELECT project, count(*) n_runs_with_prev,
               avg((prev_end > ts)::INT) share_prev_unfinished,
               avg((any_prev_end > ts)::INT) share_any_earlier_unfinished,
               avg((prev_start = ts)::INT) share_same_start_ts
        FROM r WHERE prev_end IS NOT NULL GROUP BY 1 ORDER BY 1""").df().set_index("project")
    bd = con.sql(f"""
        SELECT median(build_duration) med_build_duration_s, median(test_suite_duration_s) med_suite_s,
               max(build_duration) / 86400 max_build_duration_days,
               quantile_cont(build_duration, 0.99) / 3600 p99_build_duration_h,
               quantile_cont(build_duration, 0.999) / 3600 p999_build_duration_h,
               avg((build_duration > 86400)::INT) share_over_1d, avg((build_duration > 2*86400)::INT) share_over_2d
        FROM {RUNS}""").df().iloc[0].to_dict()

    # last_outcome check on a 1-in-10 hash sample of test classes (full history for each sampled class).
    lo = {}
    for p in paths.PROJECTS:
        d = con.sql(f"""
            WITH t AS (
              SELECT t.stage_id::VARCHAR stage_id, t.build_timestamp ts, t.pr_name::VARCHAR pr_name, t.build_id,
                     t.testclass, t.outcome::VARCHAR = 'fail' fail, t.last_outcome::VARCHAR = 'fail' lo_fail,
                     r.build_duration bd
              FROM {tr(p)} t JOIN (SELECT pr_name, build_id, stage_id, build_duration FROM {RUNS} WHERE project = '{p}') r
                ON t.pr_name::VARCHAR = r.pr_name AND t.build_id = r.build_id AND t.stage_id::VARCHAR = r.stage_id
              WHERE hash(t.testclass) % 10 = 0),
            w AS (
              SELECT *, lag(fail) OVER x prev_fail, lag(ts + bd) OVER x prev_end
              FROM t WINDOW x AS (PARTITION BY stage_id, testclass ORDER BY ts, pr_name, build_id))
            SELECT count(*) n_rows,
                   avg((coalesce(prev_fail, false) = lo_fail)::INT) match_prev_by_start,
                   avg((prev_end > ts)::INT) share_rows_prev_unfinished,
                   sum((lo_fail AND prev_end > ts)::INT) / nullif(sum(lo_fail::INT), 0) share_lofail_from_unfinished,
                   sum(lo_fail::INT) n_lo_fail
            FROM w""").df().iloc[0].to_dict()
        lo[p] = d
        print(f"  [fact1] {p}: last_outcome match {d['match_prev_by_start']:.5f}  rows {int(d['n_rows']):,}")
    return {
        "share_prev_run_unfinished_at_start": with_macro(per.share_prev_unfinished.to_dict()),
        "share_any_earlier_run_unfinished_at_start": with_macro(per.share_any_earlier_unfinished.to_dict()),
        "share_prev_run_same_start_ts": with_macro(per.share_same_start_ts.to_dict()),
        "build_duration": bd,
        "last_outcome_check_10pct_class_sample": lo,
        "last_outcome_match_rate": with_macro({p: v["match_prev_by_start"] for p, v in lo.items()}),
        "share_last_outcome_fail_rows_from_unfinished_run": with_macro(
            {p: v["share_lofail_from_unfinished"] for p, v in lo.items()}),
    }


# ------------------------------------------------------------------------------------------------ fact 2
def fact2(con) -> dict:
    runs = con.sql(f"SELECT project, pr_name, build_id, stage_id, build_timestamp FROM {RUNS}").df()
    cut = runs.groupby("project").build_timestamp.quantile(BURN_IN)
    cf = con.sql(f"SELECT project, pr_name, build_id, filename FROM read_parquet('{paths.CHANGED_FILES_PQ.as_posix()}')").df()
    ch = con.sql(f"SELECT DISTINCT project, pr_name, build_id FROM read_parquet('{paths.CHANGES_PQ.as_posix()}') "
                 "WHERE compare_found").df()
    out = {k: {} for k in ["share_new", "share_edited", "share_existing", "share_edited_basename",
                           "share_existing_basename", "n_ftf_rows", "n_ftf_rows_with_change_data",
                           "map_rate_classes_exact", "map_rate_classes_fallback", "map_rate_failure_rows_exact",
                           "share_classes_mappable"]}
    for p in paths.PROJECTS:
        t0 = time.time()
        f = con.sql(f"""
            SELECT pr_name, build_id, stage_id, build_timestamp ts, testclass FROM read_parquet('{paths.FAILURES_PQ.as_posix()}')
            WHERE project = '{p}' AND ftf AND build_timestamp > {cut[p]}""").df()
        first_seen = con.sql(f"SELECT testclass, min(build_timestamp) fs FROM {tr(p)} GROUP BY 1").df()
        f = f.merge(first_seen, on="testclass", how="left")
        f["is_new"] = f.fs >= f.ts  # never seen in a strictly earlier-started run of the project (any stage)
        cfp = cf[cf.project == p]
        files_by_build = cfp.groupby(["pr_name", "build_id"]).filename.apply(list).to_dict()
        have = set(map(tuple, ch[ch.project == p][["pr_name", "build_id"]].to_numpy()))
        f = f[[(a, b) in have for a, b in zip(f.pr_name, f.build_id)]].copy()
        edited, edited_bn = [], []
        for pr, bid, tc in zip(f.pr_name, f.build_id, f.testclass):
            fl = files_by_build.get((pr, bid), [])
            idx = suffix_index(fl)
            edited.append(any(s in idx for s in test_path_suffixes(tc)))
            bns = {x.rsplit("/", 1)[-1] for x in fl}
            edited_bn.append(any(s.rsplit("/", 1)[-1] in bns for s in test_path_suffixes(tc)))
        f["edited"], f["edited_bn"] = edited, edited_bn
        n = len(f)
        out["n_ftf_rows_with_change_data"][p] = n
        if n:
            out["share_new"][p] = f.is_new.mean()
            out["share_edited"][p] = (~f.is_new & f.edited).mean()
            out["share_existing"][p] = (~f.is_new & ~f.edited).mean()
            out["share_edited_basename"][p] = (~f.is_new & f.edited_bn).mean()
            out["share_existing_basename"][p] = (~f.is_new & ~f.edited_bn).mean()

        # mapping match rate: distinct test classes whose mapped file appears among ANY changed file of the project
        # (only ever-changed files are observable, so this is a lower bound on true mappability).
        allidx = suffix_index(cfp.filename.unique())
        classes = first_seen.testclass.to_numpy()
        mappable = np.array([len(test_path_suffixes(c)) > 0 for c in classes])
        exact = np.array([any(s in allidx for s in test_path_suffixes(c)) for c in classes])
        fb = np.array([any(s in allidx for s in test_path_suffixes(c, fallback=True)) for c in classes])
        out["share_classes_mappable"][p] = mappable.mean()
        out["map_rate_classes_exact"][p] = exact.mean()
        out["map_rate_classes_fallback"][p] = fb.mean()
        fr = con.sql(f"SELECT testclass FROM read_parquet('{paths.FAILURES_PQ.as_posix()}') WHERE project = '{p}'").df()
        ok = dict(zip(classes, exact))
        out["map_rate_failure_rows_exact"][p] = fr.testclass.map(ok).fillna(False).mean()
        print(f"  [fact2] {p}: ftf rows {n}, new {out['share_new'].get(p)}, edited {out['share_edited'].get(p)}, "
              f"map exact {exact.mean():.3f} fallback {fb.mean():.3f}  ({time.time() - t0:.0f}s)")
    res = {k: with_macro(v) if k not in ("n_ftf_rows",) else v for k, v in out.items() if v}
    res["definition"] = ("ftf = EDA first-time failure (no earlier failure of the class in the same project+stage by "
                         "start time), restricted to runs after the per-project 15% burn-in and builds with compare "
                         "data. new = class not present in any strictly earlier-started run of the project; edited = "
                         "not new and the class's own file (exact suffix mapping) is in the build's changed files.")
    return res


# ------------------------------------------------------------------------------------------- facts 3-5
def fact3(con) -> dict:
    d = con.sql(f"""SELECT project, median(build_duration / test_suite_duration_s) r FROM {RUNS}
                    WHERE test_suite_duration_s > 0 GROUP BY 1""").df()
    return {"median_build_duration_over_suite": with_macro(dict(zip(d.project, d.r)))}


def fact4(con) -> dict:
    d = con.sql(f"""SELECT r.project, s.split, avg(r.failed::INT) fr, count(*) n FROM {RUNS} r
                    JOIN read_parquet('{(paths.INTERIM / 'splits.parquet').as_posix()}') s USING (project, pr_name, build_id, stage_id)
                    GROUP BY 1, 2""").df()
    rate = {p: {sp: g[g.split == sp].fr.iloc[0] for sp in ("train", "val", "test")} for p, g in d.groupby("project")}
    multi = con.sql(f"""SELECT project, count(*) n FROM (
                          SELECT project, pr_name, build_id FROM read_parquet('{(paths.INTERIM / 'splits.parquet').as_posix()}')
                          GROUP BY ALL HAVING count(DISTINCT split) > 1) GROUP BY 1""").df()
    return {"failed_run_rate_by_eda_split": rate, "builds_with_stages_in_different_splits": dict(zip(multi.project, multi.n))}


def fact5(con) -> dict:
    d = con.sql(f"""SELECT count(DISTINCT testclass) n_classes,
                           count(DISTINCT testclass) FILTER (WHERE regexp_matches(testclass, '^(ctypes|cython)\\.tests\\.python\\.')) n_py,
                           count(DISTINCT regexp_replace(testclass, '^(ctypes|cython)\\.', '')) n_modules,
                           count(DISTINCT regexp_replace(testclass, '^(ctypes|cython)\\.', ''))
                               FILTER (WHERE regexp_matches(testclass, '^(ctypes|cython)\\.tests\\.python\\.')) n_py_modules
                    FROM {tr('tvm')}""").df().iloc[0].to_dict()
    f = con.sql(f"""SELECT avg(regexp_matches(testclass, '^(ctypes|cython)\\.tests\\.python\\.')::INT) share_py,
                           count(*) n FROM read_parquet('{paths.FAILURES_PQ.as_posix()}') WHERE project = 'tvm'""").df().iloc[0]
    return {**d, "share_tvm_failures_under_tests_python": f.share_py, "n_tvm_failure_rows": f.n}


def main() -> None:
    con = connect()
    res = {}
    for name, fn in [("fact3", fact3), ("fact4", fact4), ("fact5", fact5), ("fact1", fact1), ("fact2", fact2)]:
        t0 = time.time()
        res[name] = fn(con)
        print(f"[{name}] done in {time.time() - t0:.0f}s")
    save_result("phase0_facts", res)


if __name__ == "__main__":
    main()
