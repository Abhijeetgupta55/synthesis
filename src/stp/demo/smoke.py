"""Demo smoke test: python -m stp.demo.smoke

  1. renders all eight pages of app/demo.py headlessly (streamlit.testing AppTest) and fails on any exception;
     on 'ML Lab' it presses Train and every guided experiment (live fits; each must finish in <= 30 s) and on
     'Real PRs' it presses 'Show me a loss' (the build shown must be a loss)
  2. demo_bundle/results/*.json equal reports/results/*.json; every figure the app names exists
  3. 'Predict live' parity: the app's scores equal `smartci rank --files` for the same input
  4. 20 random LRTS replays and 10 random Real PRs replays recomputed from the raw test_class.csv.zip
     (stp.demo.verify) -> all MATCH (skipped with a note when the raw LRTS download is absent)
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


PAGES = ["Start here", "ML Lab", "Real PRs", "Break the code (guided demo)", "The ML pipeline", "Predict live",
         "Results", "Limits and honesty"]
LAB_LIMIT_S = 30.0


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
        if page == "ML Lab":
            errs += _check_lab(at)
        if page == "Real PRs":
            loss = next(b for b in at.button if b.label == "Show me a loss")
            loss.click().run()
            if at.exception:
                errs.append(f"page '{page}' (loss): {at.exception[0].message}")
            elif not any("outcome **loss**" in m.value for m in at.markdown):
                errs.append("page 'Real PRs': 'Show me a loss' did not show a loss")
        if page == "The ML pipeline" and len(at.tabs) != 7:
            errs.append(f"page '{page}': {len(at.tabs)} tabs, expected 7")
        if page == "Predict live" and not at.dataframe:
            errs.append("page 'Predict live': no ranked table rendered")
    return errs


def _check_lab(at) -> list[str]:
    import time
    errs = []
    for b in [b for b in at.button if b.label in ("Run this experiment", "Train")]:
        t0 = time.time()
        b.click().run()
        dt = time.time() - t0
        if at.exception:
            return [f"page 'ML Lab' ({b.label}): {at.exception[0].message}"]
        print(f"    ML Lab {b.label}: {dt:.1f} s")
        if dt > LAB_LIMIT_S:
            errs.append(f"page 'ML Lab': '{b.label}' took {dt:.1f} s (> {LAB_LIMIT_S:.0f} s)")
    if sum("Takeaway" in s.value for s in at.success) != 4:
        errs.append("page 'ML Lab': expected 4 computed takeaways")
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
    if not verify.RAW.exists():
        print("    (raw LRTS download absent: replays not recomputed)")
        return []
    errs = []
    for bundle, k in (("lrts", n), ("real_prs", 10)):
        idx = json.loads((BUNDLE / bundle / "index.json").read_text(encoding="utf-8"))
        for item in random.Random(seed).sample(idx, min(k, len(idx))):
            code = verify.main(["--bundle", bundle, "--project", item["project"], "--pr", item["pr_name"],
                                "--build", str(item["build_id"]), "--stage", item["stage_id"]])
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
