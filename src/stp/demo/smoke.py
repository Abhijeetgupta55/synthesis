"""Demo smoke test: python -m stp.demo.smoke

  1. renders all six pages of app/demo.py headlessly (streamlit.testing AppTest) and fails on any exception
  2. demo_bundle/results/*.json equal reports/results/*.json; every figure the app names exists
  3. 'Predict live' parity: the app's scores equal `smartci rank --files` for the same input
  4. 20 random LRTS replays recomputed from the raw test_class.csv.zip (stp.demo.verify) -> all MATCH
  5. 5 random backtest rows per bundled repo recomputed from the stored order prefixes and profile durations
Exit code 0 only if everything passes.
"""
from __future__ import annotations

import json
import random
import sys

from stp import paths
from stp.demo import verify

BUNDLE = paths.ROOT / "demo_bundle"
APP = paths.ROOT / "app" / "demo.py"


PAGES = ["Overview", "The ML pipeline", "Predict live", "Race replay", "Results", "Limits and honesty"]


def check_pages() -> list[str]:
    """Render every page headlessly (all pipeline tabs render on one run; the race page with both sources)."""
    from streamlit.testing.v1 import AppTest

    errs = []
    for page in PAGES:
        at = AppTest.from_file(str(APP), default_timeout=300)
        at.run()
        at.sidebar.radio[0].set_value(page).run()
        if at.exception:
            errs.append(f"page '{page}': {at.exception[0].message}")
            continue
        if page == "Race replay":
            at.radio[0].set_value("LRTS held-out builds").run()
            if at.exception:
                errs.append(f"page '{page}' (LRTS): {at.exception[0].message}")
        if page == "The ML pipeline" and len(at.tabs) != 7:
            errs.append(f"page '{page}': {len(at.tabs)} tabs, expected 7")
        if page == "Predict live" and not at.dataframe:
            errs.append("page 'Predict live': no ranked table rendered")
    return errs


def check_results() -> list[str]:
    """Bundled results equal reports/results (the app reads only the bundle copies)."""
    errs = []
    for f in sorted(paths.RESULTS.glob("*.json")):
        b = BUNDLE / "results" / f.name
        if not b.exists() or b.read_bytes() != f.read_bytes():
            errs.append(f"demo_bundle/results/{f.name} differs from reports/results (rebuild: "
                        "python -m stp.demo.build_bundle --parts results)")
    return errs


def check_figures() -> list[str]:
    """Every figure the app names exists in the bundle."""
    import re
    names = set(re.findall(r'fig\("([A-Za-z0-9_]+)"', APP.read_text(encoding="utf-8")))
    names |= {"C_runs_per_project", "D_failure_frequency_tail", "D_first_time_failures", "G_time_to_first_failure",
              "F_overlap_lift"}
    return [f"figure {n}.png missing from demo_bundle/figures" for n in sorted(names)
            if not (BUNDLE / "figures" / f"{n}.png").exists()]


def check_live_parity() -> list[str]:
    """The 'Predict live' scores equal `smartci rank --files` for the same input."""
    import os
    import subprocess
    from stp.demo import live
    files = ["networkx/algorithms/flow/maxflow.py", "networkx/classes/graph.py"]
    app = live.live_rank(files)
    env = {k: v for k, v in os.environ.items() if k != "SMARTCI_DIR"}
    out = subprocess.run([sys.executable, "-m", "smartci.cli", "--repo", str(live.LIVE), "rank", "--files", *files,
                          "--at", repr(live.meta()["as_of"]), "--json"], capture_output=True, text=True, env=env)
    if out.returncode:
        return [f"smartci rank failed: {out.stderr[-300:]}"]
    cli = json.loads(out.stdout.strip().splitlines()[-1])
    if [r["test_file"] for r in app] != [r["test_file"] for r in cli]:
        return ["live: app order differs from the command line"]
    bad = [a["test_file"] for a, c in zip(app, cli) if abs(a["p_fail"] - c["p_fail"]) > 1e-12]
    return [f"live: {len(bad)} scores differ from the command line"] if bad else []


def check_replays(n: int = 20, seed: int = 3) -> list[str]:
    idx = json.loads((BUNDLE / "lrts" / "index.json").read_text(encoding="utf-8"))
    errs = []
    for item in random.Random(seed).sample(idx, min(n, len(idx))):
        code = verify.main(["--project", item["project"], "--pr", item["pr_name"], "--build", str(item["build_id"]),
                            "--stage", item["stage_id"]])
        if code:
            errs.append(f"replay mismatch {item['file']}")
    return errs


def check_backtests(n: int = 5, seed: int = 4) -> list[str]:
    errs = []
    for d in sorted((BUNDLE / "repos").glob("*")) if (BUNDLE / "repos").exists() else []:
        if not (d / "backtest.json").exists():
            continue                     # repo copied before its backtest exists
        bt = json.loads((d / "backtest.json").read_text(encoding="utf-8"))
        prof = json.loads((d / "profile.json").read_text(encoding="utf-8"))
        nodes: dict[str, list[str]] = {}
        for nid in prof["nodeids"]:
            nodes.setdefault(nid.split("::", 1)[0], []).append(nid)
        for b in random.Random(seed).sample(bt["bugs"], min(n, len(bt["bugs"]))):
            failing = set(b.get("failing_nodeids") or [])
            for m, pre in b.get("prefix", {}).items():
                *before, last = pre
                t = sum(x[1] for x in before)
                if failing:
                    ovh = float(prof.get("per_test_overhead_s", 0.0))   # same per-test cost the simulator adds
                    for nid in nodes.get(last[0], []):
                        t += prof["nodeid_durations"].get(nid, 0.0) + ovh
                        if nid in failing:
                            break
                if abs(t - b["ttff_s"][m]) > 1e-3 * max(1.0, t) + 1e-3:
                    errs.append(f"{d.name} {b['id']} {m}: recomputed {t:.3f}s vs stored {b['ttff_s'][m]:.3f}s")
    return errs


def main() -> int:
    errs = []
    for name, fn in (("pages", check_pages), ("results", check_results), ("figures", check_figures),
                     ("live parity", check_live_parity), ("replays", check_replays), ("backtests", check_backtests)):
        e = fn()
        print(f"[smoke] {name}: {'OK' if not e else f'{len(e)} problem(s)'}")
        for x in e[:10]:
            print("   ", x)
        errs += e
    print("SMOKE:", "PASS" if not errs else "FAIL")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
