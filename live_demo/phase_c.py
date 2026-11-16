"""Phase C timing (docs/PROMPT_FINISH.md): run only on mains power with nothing else heavy running.

    python live_demo/phase_c.py [--steps profile,gate5,demo] [--seed 5] [--repeats 1]

  profile  smartci profile on external/networkx (pinned base), so durations are measured under the same conditions
  gate5    python live_demo/gate5.py --repo external/networkx --seed <seed>  (writes gate5_networkx.json)
  demo     live-demo timing: for 5 mined bugs + 5 mutants (seeded; only bugs whose failing files lie inside the
           subset, so both variants run the same bugs), the real wall-clock time of both lanes of `smartci compare`,
           including pytest start-up and collection, for two variants: the full suite and `networkx/algorithms`.
           Writes reports/results/live_demo_timing.json; `python -m stp.reports.demo_timing_md` renders it.
Refuses to start (exit 2) when Windows reports the battery as discharging. Re-checks power before every run and
marks any run made on battery.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "external" / "networkx"
NX_PY = REPO / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
NX_SC = REPO / ".venv" / ("Scripts/smartci.exe" if os.name == "nt" else "bin/smartci")
SUBSET = "networkx/algorithms"
OUT = ROOT / "reports" / "results" / "live_demo_timing.json"
sys.path.insert(0, str(ROOT / "live_demo"))
from pick_bug import candidates  # noqa: E402


def on_ac() -> bool | None:
    if os.name != "nt":
        return None
    r = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Battery).BatteryStatus"],
                       capture_output=True, text=True)
    s = r.stdout.strip()
    return True if not s else s != "1"


def step_profile() -> dict:
    t0 = time.time()
    r = subprocess.run([str(NX_SC), "profile"], cwd=REPO, capture_output=True, text=True)
    return {"returncode": r.returncode, "seconds": round(time.time() - t0, 1), "tail": r.stdout[-800:]}


def step_gate5(seed: int) -> dict:
    t0 = time.time()
    r = subprocess.run([sys.executable, str(ROOT / "live_demo" / "gate5.py"), "--repo", "external/networkx",
                        "--seed", str(seed)], cwd=ROOT, capture_output=True, text=True)
    return {"returncode": r.returncode, "seconds": round(time.time() - t0, 1), "tail": r.stdout[-1500:]}


def step_demo(seed: int, repeats: int) -> dict:
    import random
    c = candidates(REPO, SUBSET)                      # inside the subset, so both variants can run the same bugs
    rng = random.Random(seed)
    mined = [b for b in c if b["kind"] == "mined"]
    muts = [b for b in c if b["kind"] != "mined"]
    pick = rng.sample(mined, min(5, len(mined))) + rng.sample(muts, min(5, len(muts)))
    runs = []
    for rep in range(repeats):
        for b in pick:
            for variant, extra in (("full", []), ("subset", ["--", SUBSET])):
                ac = on_ac()
                t0 = time.perf_counter()
                r = subprocess.run([str(NX_SC), "compare", "--bug", b["id"], *extra], cwd=REPO, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace")
                total = time.perf_counter() - t0
                saved = sorted((REPO / ".smartci" / "compare").glob("*.json"), key=lambda f: f.stat().st_mtime)
                res = json.loads(saved[-1].read_text(encoding="utf-8")) if saved else {}
                lanes = {k: {"elapsed_s": v.get("elapsed_s"), "first_failure_after_s": v.get("first_failure_after_s"),
                             "failed_line": v.get("failed_line")} for k, v in res.get("runs", {}).items()}
                runs.append({"repeat": rep, "variant": variant, "kind": b["kind"], "id": b["id"],
                             "title": b.get("title"), "on_ac": ac, "returncode": r.returncode,
                             "command_s": round(total, 2), "lanes": lanes,
                             "simulated_ttff_s": {k: b["ttff_s"].get(k) for k in ("default", "smartci")}})
                print(f"  [demo] rep {rep} {variant:6s} {b['kind']:6s} {b['id'][:14]}: "
                      + ", ".join(f"{k} {v['elapsed_s']:.1f}s" for k, v in lanes.items() if v["elapsed_s"]),
                      flush=True)
    return {"seed": seed, "subset": SUBSET, "picked": [b["id"] for b in pick], "runs": runs}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", default="profile,gate5,demo")
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--allow-battery", action="store_true", help="dry runs only; results are marked on_ac=false")
    a = ap.parse_args(argv)
    if on_ac() is False and not a.allow_battery:
        print("phase_c: the laptop is on battery; timing is not meaningful. Plug in and re-run.")
        return 2
    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for s in a.steps.split(","):
        print(f"[phase_c] {s} ...", flush=True)
        res = {"profile": step_profile, "gate5": lambda: step_gate5(a.seed),
               "demo": lambda: step_demo(a.seed, a.repeats)}[s]()
        res["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if s == "demo":
            out.setdefault("demo_sessions", []).append(res)
        else:
            out[s] = res
        OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
