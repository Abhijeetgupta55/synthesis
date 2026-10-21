"""Text-only fallback for the demo (no browser needed).

    python -m stp.demo.cli                       # a random bundled LRTS build (seed shown)
    python -m stp.demo.cli --seed 42
    python -m stp.demo.cli --project kafka --pr PR-12345 --build 3 --stage <stage>
Prints, per method, the minutes until the first failure and a bar, plus the verify command.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[3] / "demo_bundle"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--project")
    ap.add_argument("--pr")
    ap.add_argument("--build", type=int)
    ap.add_argument("--stage")
    a = ap.parse_args(argv)
    idx = json.loads((BUNDLE / "lrts" / "index.json").read_text(encoding="utf-8"))
    if a.project and a.pr:
        item = next(x for x in idx if x["project"] == a.project and x["pr_name"] == a.pr
                    and (a.build is None or x["build_id"] == a.build) and (a.stage is None or x["stage_id"] == a.stage))
    else:
        seed = a.seed if a.seed is not None else random.SystemRandom().randrange(10**6)
        item = random.Random(seed).choice(idx)
        print(f"seed {seed}")
    rec = json.loads((BUNDLE / item["file"]).read_text(encoding="utf-8"))
    print(f"{rec['project']} {rec['pr_name']} build {rec['build_id']} stage {rec['stage_id']} "
          f"({rec['n_tests']} test classes, {rec['n_fail']} failing, {rec['suite_s'] / 60:.0f} min summed)")
    if rec.get("pr_url"):
        print(rec["pr_url"])
    longest = max(r["ttff_s"] for r in rec["methods"].values())
    for m, r in sorted(rec["methods"].items(), key=lambda kv: kv[1]["ttff_s"]):
        bar = "#" * max(1, int(50 * r["ttff_s"] / longest))
        print(f"{m:20s} {r['ttff_s'] / 60:8.2f} min  APFDc {r['apfdc']:.3f}  {bar}")
    print(f"verify: python -m stp.demo.verify --project {rec['project']} --pr {rec['pr_name']} "
          f"--build {rec['build_id']} --stage {rec['stage_id']}")


if __name__ == "__main__":
    main()
