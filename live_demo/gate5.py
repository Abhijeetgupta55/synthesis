"""GATE 5 (simulation honesty): real pytest runs must match the backtest's simulated time to first failure.

    python live_demo/gate5.py --repo external/networkx --seed 5 [--n-mined 5 --n-mutants 5]

Draws n mined (held-out) bugs and n mutants with the logged seed from .smartci/backtest.json, runs
`smartci compare` (sequential, real pytest -x in two worktrees) for each, and compares, for both orderings:
  real      = seconds from the first test's start to the first failure report (from the receipt / timing file)
  simulated = the backtest's TTFF for that ordering (sum of profiled durations)
Pass rule per run: |real − simulated| <= 10% of simulated + overhead, where overhead = the per-test reporting
overhead measured on this machine (median of real − simulated over the runs, capped by the profile's measured
pytest start-up overhead). Writes reports/results/gate5_<repo>.json.
Run on a quiet machine: concurrent jobs inflate real times.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--n-mined", type=int, default=5)
    ap.add_argument("--n-mutants", type=int, default=5)
    a = ap.parse_args()
    repo = (ROOT / a.repo).resolve()
    sdir = repo / ".smartci"
    bt = json.loads((sdir / "backtest.json").read_text(encoding="utf-8"))
    prof = json.loads((sdir / "profile.json").read_text(encoding="utf-8"))
    rng = random.Random(a.seed)
    mined = [b for b in bt["bugs"] if b["kind"] == "mined"]
    muts = [b for b in bt["bugs"] if b["kind"] == "mutant"]
    pick = rng.sample(mined, min(a.n_mined, len(mined))) + rng.sample(muts, min(a.n_mutants, len(muts)))
    exe = repo / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / "smartci"
    rows = []
    for b in pick:
        t0 = time.time()
        r = subprocess.run([str(exe), "compare", "--bug", b["id"]], cwd=repo, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        files = sorted((sdir / "compare").glob("*.json"), key=lambda f: f.stat().st_mtime)
        res = json.loads(files[-1].read_text(encoding="utf-8")) if files else {}
        row = {"kind": b["kind"], "id": b["id"], "url": b.get("url"), "returncode": r.returncode,
               "seconds": time.time() - t0}
        for lane, key in (("default", "default"), ("smartci", "smartci")):
            run = res.get("runs", {}).get(lane, {})
            row[f"{lane}_real_s"] = run.get("first_failure_after_s")
            row[f"{lane}_sim_s"] = b["ttff_s"][key]
            row[f"{lane}_elapsed_s"] = run.get("elapsed_s")
            row[f"{lane}_failed_line"] = run.get("failed_line")
            row[f"{lane}_first_nodeid"] = run.get("first_failure_nodeid")
        # machine-speed factor of *this* compare run: real / profiled durations of the default lane's files that ran
        # completely before the failure (tests unrelated to the bug). Diagnostic only: it separates simulation logic
        # (order, first failure, accumulation) from ambient speed (battery throttling, thermal, other load).
        real_fd = res.get("runs", {}).get("default", {}).get("file_durations_s") or {}
        pre = [f for f, _ in b["prefix"]["default"][:-1]]
        prof_sum = sum(prof["durations"].get(f, 0.0) for f in pre)
        real_sum = sum(real_fd.get(f) or 0.0 for f in pre)
        row["speed_factor"] = real_sum / prof_sum if prof_sum > 5 and real_fd else None
        for lane in ("default", "smartci"):
            if row["speed_factor"] and row[f"{lane}_real_s"] is not None:
                scaled = row[f"{lane}_sim_s"] * row["speed_factor"]
                row[f"{lane}_sim_scaled_s"] = scaled
                row[f"{lane}_rel_err_scaled"] = (row[f"{lane}_real_s"] - scaled) / max(scaled, 1e-9)
        rows.append(row)
        print(f"  {b['kind']:6s} {b['id'][:30]:30s} default real {row['default_real_s']} sim {row['default_sim_s']:.2f} | "
              f"smartci real {row['smartci_real_s']} sim {row['smartci_sim_s']:.2f}", flush=True)
    diffs = [r[f"{l}_real_s"] - r[f"{l}_sim_s"] for r in rows for l in ("default", "smartci") if r[f"{l}_real_s"] is not None]
    startup = min(x for x in prof["overhead_s"] if x is not None)
    overhead = min(sorted(diffs)[len(diffs) // 2] if diffs else 0.0, startup)
    ok_all = True
    for r in rows:
        for lane in ("default", "smartci"):
            real, sim = r[f"{lane}_real_s"], r[f"{lane}_sim_s"]
            ok = real is not None and abs(real - sim) <= 0.1 * sim + max(overhead, 0.0)
            r[f"{lane}_pass"] = bool(ok)
            ok_all &= ok
    import statistics
    sf = [r["speed_factor"] for r in rows if r.get("speed_factor")]
    errs = [r[f"{l}_rel_err_scaled"] for r in rows for l in ("default", "smartci") if r.get(f"{l}_rel_err_scaled") is not None
            and r[f"{l}_sim_s"] > 5]
    out = {"repo": repo.name, "seed": a.seed, "measured_overhead_s": overhead, "profile_startup_overhead_s": startup,
           "speed_factors": sf, "median_abs_rel_err_after_speed_scaling_(sim>5s)":
               statistics.median([abs(e) for e in errs]) if errs else None,
           "rule": "|real - simulated| <= 0.1*simulated + overhead", "runs": rows, "gate5_pass": bool(ok_all),
           "n_pass": sum(r["default_pass"] + r["smartci_pass"] for r in rows), "n_checks": 2 * len(rows),
           "generated": time.strftime("%Y-%m-%d %H:%M:%S")}
    (ROOT / "reports" / "results" / f"gate5_{repo.name}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"GATE 5 {repo.name}: {'PASS' if ok_all else 'FAIL'} ({out['n_pass']}/{out['n_checks']} checks; "
          f"overhead {overhead:.2f}s)")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
