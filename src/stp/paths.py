"""All filesystem paths, resolved from configs/data.yaml relative to the repo root."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "configs" / "data.yaml"


@lru_cache(maxsize=1)
def config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _p(key: str) -> Path:
    return ROOT / config()["paths"][key]


RAW = _p("raw")
INTERIM = _p("interim")
PROCESSED = _p("processed")
LRTS_REPO = _p("lrts_repo")
FIGURES = _p("figures")
EDA_JSON = _p("eda_json")
REPORT = _p("report")
PROJECTS: list[str] = config()["projects"]

# Files shipped inside the LRTS git repo
LRTS_ARTIFACT = LRTS_REPO / "artifact"
LRTS_DATASET_CSV = LRTS_ARTIFACT / "metadata" / "dataset.csv"
LRTS_DATASET_FILTER_CSV = LRTS_ARTIFACT / "metadata" / "dataset_filter.csv"
LRTS_DATASET_INIT_CSV = LRTS_ARTIFACT / "metadata" / "dataset_init.csv"
LRTS_FLAKY_CSV = LRTS_ARTIFACT / "flaky_test" / "flaky_tests.csv"
LRTS_CHANGE_STATS_CSV = LRTS_ARTIFACT / "evaluation" / "change_info" / "change_stats.csv"
LRTS_EVAL_OUTCOME = LRTS_ARTIFACT / "evaluation" / "eval_outcome"

# Interim tables
RUNS_PQ = INTERIM / "runs.parquet"
TEST_RESULTS_DIR = INTERIM / "test_results"  # hive-partitioned by project
CHANGES_PQ = INTERIM / "changes.parquet"
CHANGED_FILES_PQ = INTERIM / "changed_files.parquet"
FLAKY_PQ = INTERIM / "flaky.parquet"
BASELINES_PQ = INTERIM / "paper_baselines.parquet"


def ensure_dirs() -> None:
    for d in (RAW, INTERIM, PROCESSED, FIGURES, EDA_JSON):
        d.mkdir(parents=True, exist_ok=True)

# Extracted processed LRTS (Google Drive zip). The zip nests a top-level folder of the same name.
LRTS_DATA = RAW / "long_running_test_suites" / "long_running_test_suites"
LRTS_FULL_DATASET_CSV = LRTS_DATA / "dataset.csv"
LRTS_TEST_RESULT_DIR = LRTS_DATA / "processed_test_result"
LRTS_SHADATA_DIR = LRTS_DATA / "shadata"

# More interim tables
RUN_FILE_AUDIT_PQ = INTERIM / "run_file_audit.parquet"   # per-run counts recomputed from the csv.zip
FAILURES_PQ = INTERIM / "failures.parquet"               # one row per failing (run, test_class), with labels

# Phase 1+ outputs
RESULTS = ROOT / "reports" / "results"                    # every reported number lives in a JSON here
SPLITS_BUILD_PQ = PROCESSED / "splits_build.parquet"
FEATURES_DIR = PROCESSED / "features"                    # hive-partitioned by project
DUCKDB_TMP = PROCESSED / "_duckdb_tmp"                   # spill directory for out-of-core queries
