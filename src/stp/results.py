"""Reported numbers: every figure in a report is read from reports/results/<name>.json, written here."""
from __future__ import annotations

import json
import subprocess
import time

import duckdb

from stp import paths
from stp.eda.common import _clean


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=paths.ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def save_result(name: str, obj: dict) -> None:
    paths.RESULTS.mkdir(parents=True, exist_ok=True)
    obj = {**obj, "_meta": {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "git_sha": git_sha()}}
    (paths.RESULTS / f"{name}.json").write_text(json.dumps(_clean(obj), indent=2), encoding="utf-8")


def load_result(name: str) -> dict:
    return json.loads((paths.RESULTS / f"{name}.json").read_text(encoding="utf-8"))


def connect(memory_limit: str = "1500MB", threads: int = 4) -> duckdb.DuckDBPyConnection:
    """DuckDB connection sized for this machine (~2 GB free RAM): small memory limit, spill to disk."""
    paths.DUCKDB_TMP.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute(f"SET threads={threads}")
    con.execute(f"SET temp_directory='{paths.DUCKDB_TMP.as_posix()}'")
    con.execute("SET preserve_insertion_order=false")
    return con
