"""The demo's 'Predict live' scoring: the real packaged model on NetworkX's bundled smartci state.

This is a thin wrapper around `smartci.whatif.rank_paths`, the same function `smartci rank --files` runs, with the
bundled state directory and a fixed as-of time, so the app and the command line give identical scores
(tests/test_demo_live.py checks this). Nothing here is precomputed.

Command-line equivalent of live_rank(files):
    smartci --repo demo_bundle/live/networkx rank --files <files> --at <as_of> --json
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIVE = ROOT / "demo_bundle" / "live" / "networkx"


def meta() -> dict:
    return json.loads((LIVE / "live_meta.json").read_text(encoding="utf-8"))


def live_rank(files: list[str], additions: int | None = None, deletions: int | None = None) -> list[dict]:
    from smartci.whatif import rank_paths
    os.environ.pop("SMARTCI_DIR", None)          # read the bundled state, never another repo's
    return rank_paths(LIVE, files, t=meta()["as_of"], explain=True, additions=additions, deletions=deletions)


def baselines(rows: list[dict]) -> dict[str, list[str]]:
    """Orders the simple rules give for the same change, defined exactly as in `smartci backtest`:
    changed-files-first = by (test file in change, path overlap, name overlap) descending, then pytest's order;
    fastest-first = by profiled duration ascending, then pytest's order."""
    from smartci.whatif import suite
    prof = json.loads((LIVE / ".smartci" / "profile.json").read_text(encoding="utf-8"))
    dur = prof["durations"]
    tests = suite(LIVE)
    pos = {t: i for i, t in enumerate(tests)}
    rel = {r["test_file"]: tuple(-float(x) for x in r["relatedness"]) for r in rows}
    return {"changed_files_first": sorted(tests, key=lambda t: (rel[t], pos[t])),
            "fastest_first": sorted(tests, key=lambda t: (dur.get(t, 1.0), pos[t]))}


def command(files: list[str], additions: int | None = None, deletions: int | None = None) -> str:
    extra = ""
    if additions is not None:
        extra += f" --additions {additions}"
    if deletions is not None:
        extra += f" --deletions {deletions}"
    return (f"smartci --repo demo_bundle/live/networkx rank --files {' '.join(files)} --at {meta()['as_of']}"
            f"{extra} --json")
