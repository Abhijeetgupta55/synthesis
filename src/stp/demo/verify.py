"""Independent check of one LRTS replay shown in the demo.

    python -m stp.demo.verify [--bundle lrts|real_prs] --project kafka --pr PR-12345 --build 3 --stage <stage>

Reads the build's *raw* LRTS file (processed_test_result/<project>/<pr>_build<N>/stage_<stage>/test_class.csv.zip),
takes each method's test order from demo_bundle/<bundle>/<project>/<pr>_<build>_<stage>.json, and recomputes APFDc and
time to first failure from the raw durations and outcomes with a 10-line implementation written here (not the
pipeline's). Prints MATCH / MISMATCH per method and exits 1 on any mismatch.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "long_running_test_suites" / "long_running_test_suites" / "processed_test_result"
BUNDLE = ROOT / "demo_bundle" / "lrts"
BUNDLES = ("lrts", "real_prs")


def read_raw(project: str, pr: str, build: int, stage: str) -> dict[str, tuple[float, int]]:
    f = RAW / project / f"{pr}_build{build}" / f"stage_{stage}" / "test_class.csv.zip"
    with zipfile.ZipFile(f) as z:
        name = z.namelist()[0]
        rows = list(csv.reader(io.StringIO(z.read(name).decode("utf-8"))))
    head = rows[0]
    i_t, i_d, i_o = head.index("testclass"), head.index("duration"), head.index("outcome")
    return {c[i_t]: (float(c[i_d]), int(float(c[i_o]))) for c in rows[1:] if c}


def apfdc(durs: list[float], fails: list[int]) -> float:
    d = [x + 0.001 for x in durs]
    total, n = sum(d), sum(fails)
    tail, cost = total, 0.0
    for di, fi in zip(d, fails):
        if fi:
            cost += tail - di / 2
        tail -= di
    return cost / (n * total)


def ttff(durs: list[float], fails: list[int]) -> float:
    t = 0.0
    for di, fi in zip(durs, fails):
        t += di + 0.001
        if fi:
            return t
    return float("nan")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--pr", required=True)
    ap.add_argument("--build", type=int, required=True)
    ap.add_argument("--stage", required=True)
    ap.add_argument("--bundle", choices=BUNDLES, default="lrts")
    a = ap.parse_args(argv)
    raw = read_raw(a.project, a.pr, a.build, a.stage)
    rec = json.loads((BUNDLE.parent / a.bundle / a.project / f"{a.pr}_{a.build}_{a.stage}.json").read_text(encoding="utf-8"))
    bad = 0
    print(f"raw file: {len(raw)} test classes, {sum(o for _, o in raw.values())} failing")
    for m, r in rec["methods"].items():
        order = [rec["names"][i] for i in r["order"]]
        if sorted(order) != sorted(raw):
            print(f"MISMATCH {m}: ordered test set differs from the raw file")
            bad += 1
            continue
        d = [raw[t][0] for t in order]
        f = [raw[t][1] for t in order]
        a1, t1 = apfdc(d, f), ttff(d, f)
        ok = abs(a1 - r["apfdc"]) < 1e-5 and abs(t1 - r["ttff_s"]) < 1e-3 * max(1.0, t1)
        bad += not ok
        print(f"{'MATCH' if ok else 'MISMATCH':8s} {m:20s} APFDc raw {a1:.6f} bundle {r['apfdc']:.6f}   "
              f"TTFF raw {t1 / 60:.2f} min bundle {r['ttff_s'] / 60:.2f} min")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
