"""Phase 1.4a: per-change file lists and diff-token bags from the raw GitHub compare JSON (shadata/).

A *change* is one (project, pr_name, build_id, trunk_sha, build_head_sha) pair: what a run's code differs from
trunk by. It is keyed by the SHA pair, not only by build, because TVM reuses one pr/build id across Jenkins jobs
whose stages start days apart with different head SHAs (EDA §5). Each run points to exactly one change.

Outputs, per project (resumable: a finished project is skipped):
  data/processed/diffs/project=<p>/changes.parquet  change_idx, keys, n_files, additions, deletions, has_patch,
                                                    patch_chars_used
  data/processed/diffs/project=<p>/files.parquet    change_idx, filename, status, additions, deletions
  data/processed/diffs/project=<p>/tokens.parquet   change_idx, token, count   (paths + patch text, capped)

Usage: python -m stp.data.build_diffs [--projects a,b]
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import time

import pandas as pd

from stp import paths
from stp.features.tokens import diff_token_counts

DIFFS_DIR = paths.PROCESSED / "diffs"
CHANGE_KEY = ["pr_name", "build_id", "trunk_sha", "build_head_sha"]


def read_change(project: str, pr_name: str, build_id: int, base: str, head: str) -> tuple[list[dict], list[str]]:
    """Files (first occurrence across pages, GitHub order) and their patch texts for one compare pair."""
    d = paths.LRTS_SHADATA_DIR / project / "compare_commits" / f"{pr_name}_build{build_id}"
    files: dict[str, dict] = {}
    patches: dict[str, str | None] = {}
    page = 1
    while True:
        fp = d / f"{base}_{head}_page{page}.json"
        if not fp.exists():
            break
        with open(fp, encoding="utf-8") as fh:
            data = json.load(fh)
        for x in data.get("files", []) or []:
            fn = x["filename"]
            if fn not in files:
                files[fn] = {"filename": fn, "status": x.get("status"), "additions": int(x.get("additions", 0)),
                             "deletions": int(x.get("deletions", 0)),
                             "previous_filename": x.get("previous_filename")}
                patches[fn] = x.get("patch")
        page += 1
    return list(files.values()), [patches[f] for f in files]


def _work(args):
    project, idx, pr_name, build_id, base, head, max_chars, stop = args
    files, patches = read_change(project, pr_name, build_id, base, head)
    names = [f["filename"] for f in files]
    # A rename touches the old path too; both names describe the code that moved.
    names += [f["previous_filename"] for f in files if f["previous_filename"]]
    counts = diff_token_counts(names, patches, max_chars=max_chars, extra_stop=stop)
    used = min(sum(len(p or "") for p in patches), max_chars)
    meta = {"change_idx": idx, "n_files": len(files), "additions": sum(f["additions"] for f in files),
            "deletions": sum(f["deletions"] for f in files), "has_patch": any(p for p in patches),
            "patch_chars_used": used}
    return meta, [{**f, "change_idx": idx} for f in files], [(idx, t, c) for t, c in counts.items()]


def build_project(project: str, pool: mp.pool.Pool) -> None:
    out = DIFFS_DIR / f"project={project}"
    if (out / "_SUCCESS").exists():
        print(f"[diffs] {project}: done already, skipping")
        return
    t0 = time.time()
    runs = pd.read_parquet(paths.RUNS_PQ, columns=["project"] + CHANGE_KEY)
    ch = runs[runs.project == project].drop_duplicates(CHANGE_KEY).sort_values(CHANGE_KEY).reset_index(drop=True)
    ch.insert(0, "change_idx", range(len(ch)))
    cfg = paths.config()
    stop = frozenset(cfg["project_stopwords"].get(project, []))
    args = [(project, i, pr, int(b), base, head, cfg["features"]["patch_max_chars"], stop)
            for i, pr, b, base, head in ch[["change_idx"] + CHANGE_KEY].itertuples(index=False, name=None)]
    metas, files, toks = [], [], []
    for i, (m, f, t) in enumerate(pool.imap(_work, args, chunksize=8)):
        metas.append(m)
        files.extend(f)
        toks.extend(t)
        if i % 2000 == 0:
            print(f"  [diffs] {project}: {i:,}/{len(args):,} changes  {time.time() - t0:.0f}s", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    ch.merge(pd.DataFrame(metas), on="change_idx").to_parquet(out / "changes.parquet", index=False)
    pd.DataFrame(files, columns=["change_idx", "filename", "status", "additions", "deletions",
                                 "previous_filename"]).to_parquet(out / "files.parquet", index=False)
    tk = pd.DataFrame(toks, columns=["change_idx", "token", "count"])
    tk["token"] = tk["token"].astype("category")
    tk.to_parquet(out / "tokens.parquet", index=False)
    (out / "_SUCCESS").write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
    print(f"[diffs] {project}: {len(ch):,} changes, {len(files):,} files, {len(toks):,} token rows "
          f"in {time.time() - t0:.0f}s", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects", default=",".join(paths.PROJECTS))
    ap.add_argument("--workers", type=int, default=5)
    a = ap.parse_args()
    with mp.Pool(a.workers) as pool:
        for p in a.projects.split(","):
            build_project(p, pool)


if __name__ == "__main__":
    main()
