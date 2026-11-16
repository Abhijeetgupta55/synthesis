"""Build demo_bundle/lab/: a small real sample for the dashboard's ML Lab (live training) and notebooks/lab_by_hand.

  lab/train_sample.parquet  100,000 rows drawn at random from data/processed/train/train.parquet (the negative-
                            sampled training rows: every failure kept, at most 200 passing tests per CI run)
  lab/later_builds.parquet  every row of a seeded random set of validation runs from valA (time-later, unsampled,
                            the real failure rate), about 100,000 rows
  lab/lab_meta.json         feature groups, provenance, seed
Columns: the 25 model features (float32), y_fail, y_ftf_asof (first-time failure), run_idx, project, start_ts.

Usage: python -m stp.demo.build_lab [--seed 0]
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from stp import paths
from stp.features.schema import FEATURES
from stp.models.common import load_model

OUT = paths.ROOT / "demo_bundle" / "lab"
N_TRAIN = 100_000
N_LATER = 100_000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    cols = load_model("cal_lgbm").entry["cols"]
    keep = cols + ["y_fail", "y_ftf_asof", "run_idx", "project", "start_ts"]
    rng = np.random.default_rng(a.seed)
    tr = pq.read_table(paths.PROCESSED / "train" / "train.parquet", columns=keep).to_pandas()
    tr = tr.iloc[np.sort(rng.choice(len(tr), N_TRAIN, replace=False))]
    va = pq.read_table(paths.PROCESSED / "train" / "valA.parquet", columns=keep).to_pandas()
    runs = va[["project", "run_idx"]].drop_duplicates().sample(frac=1.0, random_state=a.seed)
    sizes = va.groupby(["project", "run_idx"]).size()
    chosen, n = [], 0
    for p, r in runs.itertuples(index=False):
        chosen.append((p, r))
        n += int(sizes.loc[(p, r)])
        if n >= N_LATER:
            break
    ch = pd.MultiIndex.from_tuples(chosen)
    va = va[pd.MultiIndex.from_frame(va[["project", "run_idx"]]).isin(ch)]
    OUT.mkdir(parents=True, exist_ok=True)
    for df, name in ((tr, "train_sample"), (va, "later_builds")):
        df = df.copy()
        for c in cols:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
        df["y_fail"] = df.y_fail.astype(bool)
        df["y_ftf_asof"] = df.y_ftf_asof.astype(bool)
        df.reset_index(drop=True).to_parquet(OUT / f"{name}.parquet", index=False, compression="zstd")
    groups = {}
    for c in cols:
        groups.setdefault(FEATURES[c]["group"], []).append(c)
    meta = {"seed": a.seed, "features": cols, "groups": groups,
            "train_sample": {"rows": int(len(tr)), "failure_rate": float(tr.y_fail.mean()),
                             "source": "random rows of data/processed/train/train.parquet (negative-sampled)"},
            "later_builds": {"rows": int(len(va)), "runs": len(chosen), "failure_rate": float(va.y_fail.mean()),
                             "first_time_failures": int(va.y_ftf_asof.sum()),
                             "source": "all rows of random valA runs (time-later than training, unsampled)"}}
    (OUT / "lab_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    size = sum(f.stat().st_size for f in OUT.iterdir()) / 2**20
    print(f"demo_bundle/lab: {len(tr):,} training rows, {len(va):,} later rows ({len(chosen)} runs), {size:.1f} MB")


if __name__ == "__main__":
    main()
