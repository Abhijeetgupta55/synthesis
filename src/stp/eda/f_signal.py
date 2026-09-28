"""3.F Is there a change signal at all? Token overlap between a test-class name and the build's changed-file paths.

Tokens: split on non-alphanumerics and camelCase, lowercase, keep len >= 3, drop generic/project-name stopwords.
overlap(test, run) = |tokens(test class FQN) ∩ tokens(all changed paths of the run's build)|.
Computed on ALL (run, test_class) rows of runs whose build has compare data. Cheap sanity check, not a model.
lift_k = P(fail | overlap >= k) / P(fail); likewise for first-time failures.
"""
from __future__ import annotations

import re
import time

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stp import paths
from stp.eda.common import PALETTE, TEXT_2, save_json, savefig, style, with_macro

MAX_OV = 10
KS = [1, 2, 3]
STOP = {
    "org", "apache", "java", "scala", "src", "main", "test", "tests", "testing", "resources", "impl", "python",
    "com", "junit", "the", "and", "for", "with", "api", "internal", "util", "utils", "common", "core", "jar",
    "kafka", "hadoop", "hbase", "hive", "jackrabbit", "oak", "james", "karaf", "logging", "log4j", "tvm", "activemq",
    "xml", "json", "yaml", "yml", "properties", "txt", "gradle", "pom", "md", "http", "https",
}
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def tokenize(s: str) -> set[str]:
    out = set()
    for part in re.split(r"[^A-Za-z0-9]+", s):
        for t in _CAMEL.findall(part):
            t = t.lower()
            if len(t) >= 3 and t not in STOP and not t.isdigit():
                out.add(t)
    return out


def _csr(token_lists: list[set[str]], vocab: dict[str, int]) -> tuple[np.ndarray, np.ndarray]:
    ind, ptr = [], [0]
    for toks in token_lists:
        ids = [vocab.setdefault(t, len(vocab)) for t in toks]
        ind.extend(ids)
        ptr.append(len(ind))
    return np.asarray(ind, dtype=np.int64), np.asarray(ptr, dtype=np.int64)


def project_counts(con: duckdb.DuckDBPyConnection, project: str) -> tuple[np.ndarray, dict]:
    """counts[category, overlap] with category 0=pass, 1=repeat fail, 2=first-time fail."""
    tr = paths.TEST_RESULTS_DIR / f"project={project}"
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE tr AS
        SELECT pr_name::VARCHAR pr_name, build_id, stage_id::VARCHAR stage_id, testclass, outcome::VARCHAR = 'fail' AS fail
        FROM read_parquet('{tr.as_posix()}/*.parquet')""")
    con.execute("CREATE OR REPLACE TEMP TABLE tc AS SELECT testclass, (row_number() OVER () - 1)::INT tc_id "
                "FROM (SELECT DISTINCT testclass FROM tr)")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ch AS
        SELECT pr_name, build_id, trunk_sha, build_head_sha, (row_number() OVER () - 1)::INT ch_id
        FROM read_parquet('{paths.CHANGES_PQ.as_posix()}') WHERE project = '{project}' AND compare_found""")
    rows = con.sql(f"""
        SELECT ch.ch_id, tc.tc_id, tr.fail, coalesce(f.ftf, false) AS ftf
        FROM tr
        JOIN tc USING (testclass)
        JOIN (SELECT pr_name, build_id, stage_id, trunk_sha, build_head_sha
              FROM read_parquet('{paths.RUNS_PQ.as_posix()}') WHERE project = '{project}') r
          USING (pr_name, build_id, stage_id)
        JOIN ch USING (pr_name, build_id, trunk_sha, build_head_sha)
        LEFT JOIN (SELECT pr_name, build_id, stage_id, testclass, ftf
                   FROM read_parquet('{paths.FAILURES_PQ.as_posix()}') WHERE project = '{project}') f
          USING (pr_name, build_id, stage_id, testclass)
        ORDER BY ch.ch_id""").fetchnumpy()
    n_rows_total = con.sql("SELECT count(*) FROM tr").fetchone()[0]
    ch_id, tc_id = rows["ch_id"].astype(np.int64), rows["tc_id"].astype(np.int64)
    cat = np.where(rows["fail"], np.where(rows["ftf"], 2, 1), 0).astype(np.int64)
    del rows

    tcs = con.sql("SELECT testclass FROM tc ORDER BY tc_id").fetchnumpy()["testclass"]
    files = con.sql(f"""
        SELECT ch.ch_id, list(cf.filename) files FROM ch
        JOIN (SELECT pr_name, build_id, filename FROM read_parquet('{paths.CHANGED_FILES_PQ.as_posix()}')
              WHERE project = '{project}') cf USING (pr_name, build_id)
        GROUP BY ch.ch_id""").df()
    # NB changed_files is keyed by build (pr_name, build_id); builds with >1 base/head pair are rare (audited).
    vocab: dict[str, int] = {}
    t_ind, t_ptr = _csr([tokenize(t) for t in tcs], vocab)
    n_ch = con.sql("SELECT count(*) FROM ch").fetchone()[0]
    ch_tokens = [set() for _ in range(n_ch)]
    for cid, fl in zip(files.ch_id, files.files):
        s = set()
        for f in fl:
            s |= tokenize(f)
        ch_tokens[cid] = s
    c_ind, c_ptr = _csr(ch_tokens, vocab)
    V = len(vocab)
    seg_starts = t_ptr[:-1]
    nonempty = t_ptr[1:] > t_ptr[:-1]

    counts = np.zeros((3, MAX_OV + 1), dtype=np.int64)
    bounds = np.flatnonzero(np.diff(ch_id)) + 1
    starts = np.r_[0, bounds]
    ends = np.r_[bounds, len(ch_id)]
    mask = np.zeros(V + 1, dtype=np.int8)
    ind_ext = np.r_[t_ind, V]  # sentinel so reduceat never indexes past the end
    for s, e in zip(starts, ends):
        cid = ch_id[s]
        toks = c_ind[c_ptr[cid]:c_ptr[cid + 1]]
        mask[toks] = 1
        ov_all = np.add.reduceat(mask[ind_ext], np.minimum(seg_starts, len(t_ind)))[: len(tcs)]
        ov_all = np.where(nonempty, ov_all, 0)
        mask[toks] = 0
        ov = np.minimum(ov_all[tc_id[s:e]], MAX_OV)
        np.add.at(counts, (cat[s:e], ov), 1)
    meta = {"rows_total": int(n_rows_total), "rows_with_change_data": int(len(ch_id)),
            "distinct_test_classes": int(len(tcs)), "builds_with_change_data": int(n_ch), "vocab": V}
    return counts, meta


def lifts(counts: np.ndarray) -> dict:
    tot = counts.sum()
    fail = counts[1] + counts[2]
    ftf = counts[2]
    repeat = counts[1]
    out = {"p_fail": fail.sum() / tot, "p_ftf": ftf.sum() / tot}
    for k in KS:
        sel = counts[:, k:].sum()
        out[f"share_rows_overlap_ge{k}"] = sel / tot
        out[f"lift_fail_k{k}"] = (fail[k:].sum() / sel) / out["p_fail"] if sel and out["p_fail"] else None
        out[f"lift_ftf_k{k}"] = (ftf[k:].sum() / sel) / out["p_ftf"] if sel and out["p_ftf"] else None
        out[f"lift_repeat_k{k}"] = (repeat[k:].sum() / sel) / (repeat.sum() / tot) if sel and repeat.sum() else None
        out[f"recall_ftf_k{k}"] = ftf[k:].sum() / ftf.sum() if ftf.sum() else None
    for name, row in [("pass", counts[0]), ("repeat_fail", counts[1]), ("first_time_fail", counts[2])]:
        out[f"mean_overlap_{name}"] = (row * np.arange(MAX_OV + 1)).sum() / row.sum() if row.sum() else None
        out[f"share_overlap_ge1_{name}"] = row[1:].sum() / row.sum() if row.sum() else None
    return out


def run() -> dict:
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order=false")
    per, metas, allc = {}, {}, {}
    for p in paths.PROJECTS:
        t0 = time.time()
        c, meta = project_counts(con, p)
        per[p], metas[p], allc[p] = lifts(c), meta, c.tolist()
        print(f"  [F] {p}: {meta['rows_with_change_data']:,} rows, lift_ftf_k1={per[p]['lift_ftf_k1']}, "
              f"{time.time() - t0:.0f}s")
    keys = list(next(iter(per.values())).keys())
    s = {k: with_macro({p: per[p][k] for p in per}) for k in keys}
    s["meta"] = metas
    s["counts_by_category_and_overlap"] = allc
    s["definition"] = __doc__
    save_json(s, "F_signal")
    plot(s)
    return s


def plot(s: dict) -> None:
    style()
    projects = paths.PROJECTS
    fig, axes = plt.subplots(1, 2, figsize=(13, 3.8))
    x = np.arange(len(projects) + 1)
    w = 0.27
    for ax, kind, title in [(axes[0], "ftf", "first-time failures"), (axes[1], "repeat", "repeat failures")]:
        for i, k in enumerate(KS):
            d = s[f"lift_{kind}_k{k}"]
            vals = [d["per_project"].get(p) or np.nan for p in projects] + [d["macro"] or np.nan]
            ax.bar(x + (i - 1) * w, vals, w - 0.02, color=PALETTE[i], label=f"overlap ≥ {k}")
        ax.axhline(1, color=TEXT_2, lw=1, ls="--")
        ax.set_xticks(x, projects + ["MACRO"])
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        ax.set_yscale("log")
        ax.set_ylabel("lift over base rate (log)")
        ax.set_title(f"Name-token overlap lift: {title}")
        ax.legend(fontsize=8)
    savefig(fig, "F_overlap_lift")

    fig, ax = plt.subplots(figsize=(8, 3.4))
    for i, (name, lab) in enumerate([("pass", "passing"), ("repeat_fail", "repeat failing"),
                                     ("first_time_fail", "first-time failing")]):
        d = s[f"share_overlap_ge1_{name}"]
        vals = [d["per_project"].get(p) or np.nan for p in projects] + [d["macro"] or np.nan]
        ax.bar(x + (i - 1) * w, vals, w - 0.02, color=PALETTE[i], label=lab)
    ax.set_xticks(x, projects + ["MACRO"])
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.set_ylabel("share with overlap ≥ 1")
    ax.set_title("Share of (run, test class) rows whose name shares a token with the change")
    ax.legend(fontsize=8)
    savefig(fig, "F_overlap_share")


if __name__ == "__main__":
    s = run()
    for k in ["lift_ftf_k1", "lift_ftf_k2", "lift_fail_k1", "recall_ftf_k1", "share_rows_overlap_ge1"]:
        print(k, s[k]["macro"])
