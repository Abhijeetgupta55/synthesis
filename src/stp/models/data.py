"""Phase 3 training / calibration data from the feature store.

Negative sampling (training runs only).
  Every failing (run, test) row is kept. Per run, up to K passing rows are sampled in two strata:
  'related' (the test shares a top module or a path prefix with the change, its file is in the change, or a name
  token overlaps) gets up to K/2, the rest come from 'unrelated'. Related tests are a small share of a run but hold
  most change-driven failures (EDA §F), so over-sampling them gives the model more informative negatives.
  Each sampled negative carries weight = stratum size / sampled count, so weighted sums still estimate the
  population. Run-level sampling (documented, for the 2 GB RAM budget): at most `max_failed_runs` failed training
  runs per project (evenly spaced in time) and a fraction `passing_frac` of passing runs; run weights compensate.
Calibration set: *unsampled* rows of a random subset of validation runs (all tests of each chosen run), because
sampling distorts predicted probabilities and calibration must see the real base rate.

Outputs: data/processed/train/<name>.parquet
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from stp import paths
from stp.evaluation.harness import iter_runs
from stp.features.schema import FEATURES, LABELS
from stp.features.store import store_dir, store_ready

TRAIN_DIR = paths.PROCESSED / "train"
FEATS = [c for c in FEATURES if c != "semantic_sim"]
COLS = FEATS + LABELS + ["test_id", "y_duration_s"]


def _related(d: dict) -> np.ndarray:
    return (d["same_top_module"].astype(bool) | (d["path_prefix_overlap"] > 0) | d["test_file_in_diff"].astype(bool)
            | (d["name_token_overlap"] > 0))


def pick_runs(runs: pd.DataFrame, split: str, max_failed: int | None, passing_frac: float, rng) -> pd.DataFrame:
    r = runs[runs.split == split]
    f, p = r[r.failed], r[~r.failed]
    wf = 1.0
    if max_failed is not None and len(f) > max_failed:
        idx = np.linspace(0, len(f) - 1, max_failed).round().astype(int)   # evenly spaced in time (run order)
        wf = len(f) / max_failed
        f = f.iloc[np.unique(idx)]
    p = p[rng.random(len(p)) < passing_frac] if passing_frac < 1 else p
    out = pd.concat([f.assign(run_weight=wf), p.assign(run_weight=1.0 / passing_frac if passing_frac else 0.0)])
    return out.sort_values("run_idx")


def build_training_sample(name: str, K: int = 200, max_failed_runs: int | None = 6000, passing_frac: float = 0.1,
                          seed: int = 42, projects: list[str] | None = None) -> dict:
    TRAIN_DIR.mkdir(parents=True, exist_ok=True)
    out = TRAIN_DIR / f"{name}.parquet"
    writer = None
    stats = {}
    rng = np.random.default_rng(seed)
    for p in projects or paths.PROJECTS:
        if not store_ready(p):
            continue
        t0 = time.time()
        runs = pd.read_parquet(store_dir(p) / "runs.parquet")
        sel = pick_runs(runs, "train", max_failed_runs, passing_frac, rng)
        meta = sel.set_index("run_idx")
        n_rows = n_pos = 0
        buf: list[pd.DataFrame] = []
        for ri, d in iter_runs(p, set(sel.run_idx.tolist()), COLS):
            fail = d["y_fail"].astype(bool)
            rel = _related(d)
            keep = fail.copy()
            w = np.ones(len(fail))
            for stratum, quota in ((rel & ~fail, K // 2), (~rel & ~fail, None)):
                idx = np.flatnonzero(stratum)
                q = quota if quota is not None else K - int(min(len(np.flatnonzero(rel & ~fail)), K // 2))
                if len(idx) > q:
                    chosen = rng.choice(idx, q, replace=False)
                    w[chosen] = len(idx) / q
                else:
                    chosen = idx
                keep[chosen] = True
            m = meta.loc[ri]
            df = pd.DataFrame({c: d[c][keep] for c in COLS})
            df["weight"] = w[keep] * m.run_weight
            df["run_idx"] = ri
            df["project"] = p
            df["pr_name"] = m.pr_name
            df["start_ts"] = m.start_ts
            buf.append(df)
            n_rows += int(keep.sum())
            n_pos += int(fail.sum())
            if sum(len(b) for b in buf) > 500_000:
                tbl = pa.Table.from_pandas(pd.concat(buf, ignore_index=True), preserve_index=False)
                writer = writer or pq.ParquetWriter(out, tbl.schema, compression="zstd")
                writer.write_table(tbl)
                buf = []
        if buf:
            tbl = pa.Table.from_pandas(pd.concat(buf, ignore_index=True), preserve_index=False)
            writer = writer or pq.ParquetWriter(out, tbl.schema, compression="zstd")
            writer.write_table(tbl)
        stats[p] = {"runs": int(len(sel)), "failed_runs": int(sel.failed.sum()), "rows": n_rows, "positives": n_pos,
                    "failed_run_weight": float(sel[sel.failed].run_weight.max()) if sel.failed.any() else None,
                    "seconds": time.time() - t0}
        print(f"  [sample] {p}: {stats[p]}", flush=True)
    if writer:
        writer.close()
    return stats


def build_calibration_set(name: str, run_frac: float = 0.25, max_runs: int = 600, seed: int = 43,
                          split: str = "val", part: str | None = None, projects: list[str] | None = None) -> dict:
    """All rows of a random subset of `split` runs (passing and failed), per project.
    part='first' / 'second' restricts to the earlier / later half of the split's runs (by start time)."""
    TRAIN_DIR.mkdir(parents=True, exist_ok=True)
    out = TRAIN_DIR / f"{name}.parquet"
    rng = np.random.default_rng(seed)
    writer, stats = None, {}
    for p in projects or paths.PROJECTS:
        if not store_ready(p):
            continue
        runs = pd.read_parquet(store_dir(p) / "runs.parquet")
        r = runs[runs.split == split].sort_values("start_ts")
        if part == "first":
            r = r.iloc[: len(r) // 2]
        elif part == "second":
            r = r.iloc[len(r) // 2:]
        n = min(max_runs, max(1, int(round(run_frac * len(r)))))
        sel = r.iloc[np.sort(rng.choice(len(r), n, replace=False))]
        meta = sel.set_index("run_idx")
        buf = []
        for ri, d in iter_runs(p, set(sel.run_idx.tolist()), COLS):
            df = pd.DataFrame({c: d[c] for c in COLS})
            df["weight"] = 1.0
            df["run_idx"] = ri
            df["project"] = p
            df["pr_name"] = meta.loc[ri].pr_name
            df["start_ts"] = meta.loc[ri].start_ts
            buf.append(df)
        tbl = pa.Table.from_pandas(pd.concat(buf, ignore_index=True), preserve_index=False)
        writer = writer or pq.ParquetWriter(out, tbl.schema, compression="zstd")
        writer.write_table(tbl)
        stats[p] = {"runs": int(n), "rows": int(tbl.num_rows), "positives": int(tbl.column("y_fail").to_numpy().sum())}
        print(f"  [calib] {p}: {stats[p]}", flush=True)
    if writer:
        writer.close()
    return stats
