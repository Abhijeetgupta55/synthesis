"""Print a short numbered list of NetworkX bugs for the live demo, or the id of one of them.

    python live_demo/pick_bug.py [--repo external/networkx] [--subset networkx/algorithms] [--n 10] [--seed 1]
    python live_demo/pick_bug.py ... --pick 3          # prints only the id of item 3 (used by run_live_compare.ps1)

The list is a seeded draw of half mined bugs and half mutants from the repo's .smartci/backtest.json. With --subset,
only bugs whose failing test files are all inside that path are listed (so the subset run still catches the bug).
Times shown are the backtest's *simulated* seconds to the first failure (summed measured durations, full suite).
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def candidates(repo: Path, subset: str | None) -> list[dict]:
    bt = json.loads((repo / ".smartci" / "backtest.json").read_text(encoding="utf-8"))
    out = []
    for b in bt["bugs"]:
        files = b.get("failing_files") or []
        if subset and not all(f.replace("\\", "/").startswith(subset.rstrip("/") + "/") for f in files):
            continue
        out.append(b)
    return out


def draw(repo: Path, subset: str | None, n: int, seed: int) -> list[dict]:
    c = candidates(repo, subset)
    rng = random.Random(seed)
    mined = [b for b in c if b["kind"] == "mined"]
    muts = [b for b in c if b["kind"] != "mined"]
    k = min(len(mined), n // 2)
    pick = rng.sample(mined, k) + rng.sample(muts, min(len(muts), n - k))
    return pick


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(ROOT / "external" / "networkx"))
    ap.add_argument("--subset", default=None)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--pick", type=int, default=None)
    a = ap.parse_args(argv)
    items = draw(Path(a.repo), a.subset, a.n, a.seed)
    if a.pick is not None:
        if not 1 <= a.pick <= len(items):
            raise SystemExit(f"pick must be 1..{len(items)}")
        print(items[a.pick - 1]["id"])
        return 0
    print(f"Bugs (seed {a.seed}{', failing tests inside ' + a.subset if a.subset else ''}); simulated seconds to "
          "first failure, default order vs smartci:")
    for i, b in enumerate(items, 1):
        t = b["ttff_s"]
        title = (b.get("title") or b["id"])[:60]
        print(f"  {i:2d}. [{b['kind']:6s}] {title:60s} default {t['default']:7.1f}s  smartci {t['smartci']:6.2f}s")
    print("Run one:  scripts\\run_live_compare.ps1 -Pick <number>   (or -Edit to use your own change)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
