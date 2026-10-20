"""Receipts: an auditable JSON record of one prioritised pytest session (.smartci/receipts/<timestamp>.json).

Before the run: repo, base and head SHAs, diff hash, model version/variant, every test file's features,
probability, expected duration, priority and rank, plus pytest's original file order.
After the run: each file's real outcome and duration, and when (seconds after the first test started) the first
failure was reported. Anyone can recompute the ranking from the stored features and the published model.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from smartci.history import state_dir

SCHEMA_VERSION = 1
REQUIRED = ["schema_version", "created", "repo", "base_sha", "head_sha", "diff_hash", "model_version",
            "model_variant", "original_order", "ranking", "results", "first_failure", "session"]
RANK_FIELDS = ["rank", "test_file", "p_fail", "expected_duration_s", "priority", "features"]


def new_receipt(repo: Path, base_sha: str, head_sha: str, diff_hash: str, model_version: str, model_variant: str,
                original_order: list[str], ranking: list[dict], changed_files: list[str]) -> dict:
    return {"schema_version": SCHEMA_VERSION, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "repo": str(Path(repo).resolve()), "base_sha": base_sha, "head_sha": head_sha, "diff_hash": diff_hash,
            "model_version": model_version, "model_variant": model_variant, "changed_files": changed_files,
            "original_order": original_order, "ranking": ranking, "results": {}, "first_failure": None,
            "session": {}}


def path_for(repo: Path, receipt: dict) -> Path:
    d = state_dir(repo) / "receipts"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{receipt['created'].replace(':', '')}_{receipt['head_sha'][:8]}.json"


def write(path: Path, receipt: dict) -> None:
    Path(path).write_text(json.dumps(receipt, indent=1, default=float), encoding="utf-8")


def read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate(r: dict) -> list[str]:
    """Problems with a receipt (empty list = valid)."""
    errs = [f"missing {k}" for k in REQUIRED if k not in r]
    for i, x in enumerate(r.get("ranking", [])):
        errs += [f"ranking[{i}] missing {k}" for k in RANK_FIELDS if k not in x]
        if x.get("rank") != i + 1:
            errs.append(f"ranking[{i}] has rank {x.get('rank')}")
    if sorted(x["test_file"] for x in r.get("ranking", [])) != sorted(r.get("original_order", [])):
        errs.append("ranking and original_order contain different files (a file was dropped or added)")
    return errs


def latest(repo: Path) -> Path | None:
    d = state_dir(repo) / "receipts"
    fs = sorted(d.glob("*.json")) if d.exists() else []
    return fs[-1] if fs else None
