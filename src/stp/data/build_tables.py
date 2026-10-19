"""Raw LRTS -> tidy parquet tables in data/interim/.

Tables
  runs.parquet            one row per test-suite run (full processed dataset.csv, 108,366 rows)
  test_results/           one row per (run, test_class); hive-partitioned by project
  run_file_audit.parquet  per run: counts recomputed from its csv.zip (for audit.py)
  failures.parquet        one row per failing (run, test_class) with first-time-failure + flaky labels
  changes.parquet         one row per build (compare API: base=trunk_sha, head=build_head_sha)
  changed_files.parquet   one row per (build, changed file)
  flaky.parquet           JIRA flaky list normalised to test class

Usage:  python -m stp.data.build_tables [--only runs,tests,failures,changes,flaky]
Memory: streams files through a worker pool and flushes parquet parts, so it runs in a few GB of RAM.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import re
import shutil
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from stp import paths

RUN_KEY = ["project", "pr_name", "build_id", "stage_id"]
BUILD_KEY = ["project", "pr_name", "build_id"]
FLUSH_ROWS = 2_000_000
N_WORKERS = max(1, min(6, mp.cpu_count() - 2))


# --------------------------------------------------------------------------------------------- runs
def build_runs() -> pd.DataFrame:
    runs = pd.read_csv(paths.LRTS_FULL_DATASET_CSV, dtype={"stage_id": str, "pr_name": str})
    n_raw = len(runs)
    paper = pd.read_csv(paths.LRTS_DATASET_FILTER_CSV, dtype={"stage_id": str})
    lrts_cols = {
        "num_fail_class+first_failure": "lrts_num_first_failure",
        "num_fail_class+jira_for_fail": "lrts_num_fail_jira_removed",
        "num_fail_class+freqfail_for_fail": "lrts_num_fail_freqfail_removed",
        "num_fail_class+stageunique_for_fail": "lrts_num_fail_stageunique_removed",
    }
    paper = paper[RUN_KEY + list(lrts_cols)].rename(columns=lrts_cols)
    paper["in_paper_subset"] = True
    runs = runs.merge(paper, on=RUN_KEY, how="left")
    runs["in_paper_subset"] = runs["in_paper_subset"].fillna(False).astype(bool)
    assert len(runs) == n_raw, "merge changed row count"

    runs["build_dt"] = pd.to_datetime(runs["build_timestamp"], unit="s", utc=True)
    runs["month"] = runs["build_dt"].dt.strftime("%Y-%m")
    runs["duration_h"] = runs["test_suite_duration_s"] / 3600.0
    runs["n_classes"] = runs["num_pass_class"] + runs["num_fail_class"]
    runs["failed"] = runs["num_fail_class"] > 0
    runs["run_id"] = (runs["project"] + "|" + runs["pr_name"] + "|" + runs["build_id"].astype(str)
                      + "|" + runs["stage_id"])
    runs = runs.sort_values(["project", "build_timestamp", "pr_name", "build_id", "stage_id"]).reset_index(drop=True)
    paths.INTERIM.mkdir(parents=True, exist_ok=True)
    runs.to_parquet(paths.RUNS_PQ, index=False)
    print(f"[runs] {len(runs):,} rows (raw csv {n_raw:,}); paper subset {runs.in_paper_subset.sum():,}")
    print(runs.groupby("project").agg(runs=("run_id", "size"), failed=("failed", "sum"),
                                      paper=("in_paper_subset", "sum")).to_string())
    return runs


# ------------------------------------------------------------------------------------- test results
_BUILD_DIR_RE = re.compile(r"^(?P<pr>.+)_build(?P<bid>\d+)$")


def inventory_test_files() -> pd.DataFrame:
    rows = []
    for f in paths.LRTS_TEST_RESULT_DIR.glob("*/*/stage_*/test_class.csv.zip"):
        stage_dir, build_dir, proj = f.parent.name, f.parent.parent.name, f.parent.parent.parent.name
        m = _BUILD_DIR_RE.match(build_dir)
        if not m:
            print(f"  [inventory] unparseable dir {build_dir}")
            continue
        rows.append((proj, m["pr"], int(m["bid"]), stage_dir[len("stage_"):], str(f)))
    return pd.DataFrame(rows, columns=RUN_KEY + ["path"])


def _read_one(args):
    project, pr_name, build_id, stage_id, ts, path = args
    d = pd.read_csv(path, compression="zip")
    outc = d["outcome"].to_numpy()
    audit = {
        "project": project, "pr_name": pr_name, "build_id": build_id, "stage_id": stage_id,
        "file_rows": len(d), "file_pass": int((outc == 0).sum()), "file_fail": int((outc == 1).sum()),
        "file_other_outcome": int(((outc != 0) & (outc != 1)).sum()),
        "file_dup_testclass": int(d["testclass"].duplicated().sum()),
        "file_duration_sum_s": float(d["duration"].sum()),
        "file_null_duration": int(d["duration"].isna().sum()),
        "file_columns": ",".join(d.columns),
    }
    tbl = {
        "pr_name": pr_name, "build_id": build_id, "stage_id": stage_id, "build_timestamp": ts,
        "testclass": d["testclass"].astype(str).to_numpy(),
        "duration_s": d["duration"].to_numpy(dtype="float64"),
        "fail": (outc == 1),
        "last_outcome_fail": (d["last_outcome"].to_numpy() == 1) if "last_outcome" in d else None,
    }
    return project, audit, tbl


def _flush(project: str, buf: list[dict], part: int) -> None:
    n = [len(b["testclass"]) for b in buf]
    table = pa.table({
        "pr_name": pa.array(np.repeat([b["pr_name"] for b in buf], n)).dictionary_encode(),
        "build_id": pa.array(np.repeat([b["build_id"] for b in buf], n), pa.int32()),
        "stage_id": pa.array(np.repeat([b["stage_id"] for b in buf], n)).dictionary_encode(),
        "build_timestamp": pa.array(np.repeat([b["build_timestamp"] for b in buf], n), pa.float64()),
        "testclass": pa.array(np.concatenate([b["testclass"] for b in buf])),
        "duration_s": pa.array(np.concatenate([b["duration_s"] for b in buf]), pa.float32()),
        "outcome": pa.array(np.where(np.concatenate([b["fail"] for b in buf]), "fail", "pass")).dictionary_encode(),
        "last_outcome": pa.array(np.where(np.concatenate([b["last_outcome_fail"] for b in buf]), "fail", "pass")
                                 ).dictionary_encode(),
    })
    out = paths.TEST_RESULTS_DIR / f"project={project}"
    out.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out / f"part-{part:04d}.parquet", compression="zstd")


def build_test_results(runs: pd.DataFrame) -> None:
    inv = inventory_test_files()
    print(f"[tests] csv.zip files found: {len(inv):,}")
    m = inv.merge(runs[RUN_KEY + ["build_timestamp"]], on=RUN_KEY, how="outer", indicator=True)
    orphan = m[m._merge == "left_only"]
    missing = m[m._merge == "right_only"]
    inv_counts = pd.DataFrame({
        "files": inv.groupby("project").size(),
        "files_not_in_dataset_csv": orphan.groupby("project").size(),
        "runs_without_file": missing.groupby("project").size(),
    }).fillna(0).astype(int)
    inv_counts.to_csv(paths.INTERIM / "test_file_inventory.csv")
    print(inv_counts.to_string())
    todo = m[m._merge == "both"].sort_values(["project", "build_timestamp"])

    if paths.TEST_RESULTS_DIR.exists():
        shutil.rmtree(paths.TEST_RESULTS_DIR)
    args = list(todo[RUN_KEY + ["build_timestamp", "path"]].itertuples(index=False, name=None))
    audits, bufs, sizes, parts = [], {}, {}, {}
    t0 = time.time()
    with mp.Pool(N_WORKERS) as pool:
        for i, (project, audit, tbl) in enumerate(pool.imap(_read_one, args, chunksize=32)):
            audits.append(audit)
            bufs.setdefault(project, []).append(tbl)
            sizes[project] = sizes.get(project, 0) + len(tbl["testclass"])
            if sizes[project] >= FLUSH_ROWS:
                _flush(project, bufs[project], parts.get(project, 0))
                parts[project] = parts.get(project, 0) + 1
                bufs[project], sizes[project] = [], 0
            if i % 10000 == 0:
                print(f"  {i:,}/{len(args):,} files  {time.time() - t0:.0f}s")
    for project, buf in bufs.items():
        if buf:
            _flush(project, buf, parts.get(project, 0))
    pd.DataFrame(audits).to_parquet(paths.RUN_FILE_AUDIT_PQ, index=False)
    n = duckdb.sql(f"select count(*) from read_parquet('{paths.TEST_RESULTS_DIR.as_posix()}/*/*.parquet')").fetchone()[0]
    print(f"[tests] wrote {n:,} (run, test_class) rows in {time.time() - t0:.0f}s")


# ------------------------------------------------------------------------------------------- flaky
def normalize_flaky_name(name: str) -> tuple[str | None, str | None]:
    """'Cls#meth' -> (Cls, meth); '[qfile]' -> (None, qfile); 'a.b.Cls' -> ('a.b.Cls', None)."""
    name = name.strip()
    if "#" in name:
        c, m = name.split("#", 1)
        return c, m
    if name.startswith("["):
        return None, name
    return name, None


def build_flaky() -> pd.DataFrame:
    f = pd.read_csv(paths.LRTS_FLAKY_CSV)
    cm = [normalize_flaky_name(x) for x in f["flaky_test"]]
    f["testclass"] = [c for c, _ in cm]
    f["testmethod"] = [m for _, m in cm]
    f["level"] = np.where(f["testmethod"].notna() & f["testclass"].notna(), "method",
                          np.where(f["testclass"].isna(), "method_only_no_class", "class"))
    f["fix_dt"] = pd.to_datetime(f["fix_timestamp"], unit="s", utc=True)
    f.to_parquet(paths.FLAKY_PQ, index=False)
    print(f"[flaky] {len(f)} rows; levels: {f.level.value_counts().to_dict()}; "
          f"distinct (project, class): {f.dropna(subset=['testclass'])[['project', 'testclass']].drop_duplicates().shape[0]}")
    return f


# ---------------------------------------------------------------------------------------- failures
def build_failures() -> None:
    """Failing (run, test_class) rows + labels. first-time failure = no failure of the same test class in any
    strictly earlier run (by build_timestamp) of the same (project, stage). Two universes:
      ftf        history over all 108k runs of the processed dataset
      ftf_paper  history over only the 57k runs in the paper subset (what LRTS labelled) -- for cross-check."""
    tr = f"read_parquet('{paths.TEST_RESULTS_DIR.as_posix()}/*/*.parquet', hive_partitioning=true)"
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"CREATE TEMP VIEW runs AS SELECT * FROM read_parquet('{paths.RUNS_PQ.as_posix()}')")
    con.execute(f"""
        CREATE TEMP TABLE f AS
        SELECT t.project, t.pr_name::VARCHAR pr_name, t.build_id, t.stage_id::VARCHAR stage_id, t.build_timestamp,
               t.testclass, t.duration_s, t.last_outcome::VARCHAR = 'fail' AS last_outcome_fail, r.in_paper_subset
        FROM {tr} t JOIN runs r USING (project, pr_name, build_id, stage_id)
        WHERE t.outcome = 'fail'""")
    con.execute("""
        CREATE TEMP TABLE f2 AS
        SELECT *,
          min(build_timestamp) OVER (PARTITION BY project, stage_id, testclass) AS first_fail_ts,
          min(CASE WHEN in_paper_subset THEN build_timestamp END)
              OVER (PARTITION BY project, stage_id, testclass) AS first_fail_ts_paper,
          count(*) OVER (PARTITION BY project, testclass) AS n_fail_total_project,
          min(build_timestamp) OVER (PARTITION BY project, testclass) AS first_fail_ts_anystage
        FROM f""")
    # prior failures strictly before this run
    con.execute("""
        CREATE TEMP TABLE f3 AS
        SELECT *,
          (count(*) OVER (PARTITION BY project, stage_id, testclass ORDER BY build_timestamp
                          RANGE BETWEEN UNBOUNDED PRECEDING AND 1e-9 PRECEDING)) AS n_prior_fail,
          build_timestamp = first_fail_ts AS ftf,
          CASE WHEN in_paper_subset THEN build_timestamp = first_fail_ts_paper END AS ftf_paper,
          build_timestamp = first_fail_ts_anystage AS ftf_anystage
        FROM f2""")
    flaky = pd.read_parquet(paths.FLAKY_PQ)
    fl = flaky.dropna(subset=["testclass"]).sort_values("fix_timestamp").drop_duplicates(["project", "testclass"])
    con.register("flaky_df", fl[["project", "testclass", "fix_timestamp"]].rename(columns={"testclass": "flaky_class"}))
    # Strict match: FQN equals the listed name or ends with '.'+name. (LRTS uses a looser str.endswith(name).)
    con.execute("""
        CREATE TEMP TABLE f4 AS
        SELECT f3.*, fl.flaky_class IS NOT NULL AS is_jira_flaky, fl.fix_timestamp AS flaky_fix_ts,
               (fl.flaky_class IS NOT NULL AND f3.build_timestamp < fl.fix_timestamp) AS flaky_before_fix
        FROM f3 LEFT JOIN flaky_df fl
          ON f3.project = fl.project AND (f3.testclass = fl.flaky_class OR suffix(f3.testclass, '.' || fl.flaky_class))
        QUALIFY row_number() OVER (PARTITION BY f3.project, f3.pr_name, f3.build_id, f3.stage_id, f3.testclass
                                   ORDER BY fl.fix_timestamp NULLS LAST) = 1""")
    con.execute(f"COPY f4 TO '{paths.FAILURES_PQ.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
    print(con.sql("""SELECT project, count(*) n_fail_rows, sum(ftf::INT) n_ftf, round(avg(ftf::INT),3) ftf_share,
                            sum(is_jira_flaky::INT) n_flaky FROM f4 GROUP BY 1 ORDER BY 1""").df().to_string())


# ----------------------------------------------------------------------------------------- changes
def _parse_build_changes(args):
    project, pr_name, build_id, base, head = args
    d = paths.LRTS_SHADATA_DIR / project / "compare_commits" / f"{pr_name}_build{build_id}"
    files, authors, n_commits, pages, raw_files, raw_add, raw_del = {}, set(), 0, 0, 0, 0, 0
    status = None
    page = 1
    while True:
        fp = d / f"{base}_{head}_page{page}.json"
        if not fp.exists():
            break
        with open(fp, encoding="utf-8") as fh:
            data = json.load(fh)
        pages += 1
        status = status or data.get("status")
        for x in data.get("files", []) or []:
            raw_files += 1
            raw_add += x.get("additions", 0)
            raw_del += x.get("deletions", 0)
            fn = x["filename"]
            if fn not in files:
                files[fn] = (x.get("status"), x.get("additions", 0), x.get("deletions", 0),
                             "patch" in x and x["patch"] is not None, len(x.get("patch") or ""))
        for c in data.get("commits", []) or []:
            n_commits += 1
            a = ((c.get("commit") or {}).get("author") or {}).get("email")
            if a:
                authors.add(a)
        page += 1
    other_json = sorted(p.name for p in d.glob("*.json")) if d.exists() else []
    diff_file = paths.LRTS_SHADATA_DIR / project / "diff" / f"{pr_name}_build{build_id}.diff"
    build = {
        "project": project, "pr_name": pr_name, "build_id": build_id, "trunk_sha": base, "build_head_sha": head,
        "compare_found": pages > 0, "n_pages": pages, "n_json_in_dir": len(other_json), "compare_status": status,
        "n_files": len(files), "n_files_raw_sum_pages": raw_files,
        "additions": sum(v[1] for v in files.values()), "deletions": sum(v[2] for v in files.values()),
        "additions_raw": raw_add, "deletions_raw": raw_del,
        "n_commits": n_commits, "n_authors": len(authors),
        "n_files_with_patch": sum(v[3] for v in files.values()),
        "has_patch": any(v[3] for v in files.values()),
        "has_diff_file": diff_file.exists(), "diff_file_bytes": diff_file.stat().st_size if diff_file.exists() else 0,
        "extensions": sorted({Path(f).suffix.lower() or "(none)" for f in files}),
    }
    flist = [(project, pr_name, build_id, fn, *v) for fn, v in files.items()]
    return build, flist


def build_changes(runs: pd.DataFrame) -> None:
    builds = runs[BUILD_KEY + ["trunk_sha", "build_head_sha"]].drop_duplicates()
    print(f"[changes] distinct (build, trunk_sha, head_sha): {len(builds):,}; "
          f"distinct builds: {runs[BUILD_KEY].drop_duplicates().shape[0]:,}")
    args = list(builds.itertuples(index=False, name=None))
    out_b, out_f = [], []
    t0 = time.time()
    with mp.Pool(N_WORKERS) as pool:
        for i, (b, fl) in enumerate(pool.imap(_parse_build_changes, args, chunksize=16)):
            out_b.append(b)
            out_f.extend(fl)
            if i % 5000 == 0:
                print(f"  {i:,}/{len(args):,} builds  {time.time() - t0:.0f}s")
    ch = pd.DataFrame(out_b)
    ch.to_parquet(paths.CHANGES_PQ, index=False)
    cf = pd.DataFrame(out_f, columns=BUILD_KEY + ["filename", "file_status", "additions", "deletions",
                                                  "has_patch", "patch_chars"])
    cf.to_parquet(paths.CHANGED_FILES_PQ, index=False)
    print(f"[changes] {len(ch):,} build rows, {len(cf):,} changed-file rows, "
          f"compare found {ch.compare_found.mean():.1%}, has_patch {ch.has_patch.mean():.1%} ({time.time() - t0:.0f}s)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="runs,flaky,tests,failures,changes")
    steps = ap.parse_args().only.split(",")
    paths.INTERIM.mkdir(parents=True, exist_ok=True)
    runs = build_runs() if "runs" in steps else pd.read_parquet(paths.RUNS_PQ)
    if "flaky" in steps:
        build_flaky()
    if "tests" in steps:
        build_test_results(runs)
    if "failures" in steps:
        build_failures()
    if "changes" in steps:
        build_changes(runs)


if __name__ == "__main__":
    main()
