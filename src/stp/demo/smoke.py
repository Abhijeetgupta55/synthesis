"""Demo smoke test: python -m stp.demo.smoke

  1. renders every page of app/demo.py headlessly (streamlit.testing AppTest) and fails on any exception
  2. scoreboard numbers in demo_bundle/scoreboard.json equal reports/results/*.json
  3. 20 random LRTS replays recomputed from the raw test_class.csv.zip (stp.demo.verify) -> all MATCH
  4. 5 random backtest rows per bundled repo recomputed from the stored order prefixes and profile durations
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


def check_pages() -> list[str]:
    from streamlit.testing.v1 import AppTest

    errs = []
    pages = ["Try it on a real repo", "The 108k-build study", "Why this test?", "Scoreboard", "Honesty"]
    for page in pages:
        at = AppTest.from_file(str(APP), default_timeout=120)
        at.run()
        at.sidebar.radio[0].set_value(page).run()
        if at.exception:
            errs.append(f"page '{page}': {at.exception[0].message}")
    return errs


def check_scoreboard() -> list[str]:
    sb = json.loads((BUNDLE / "scoreboard.json").read_text(encoding="utf-8"))
    errs = []
    for name, val in sb.items():
        f = paths.RESULTS / f"{name}.json"
        ref = json.loads(f.read_text(encoding="utf-8"))
        if name == "models_classification":
            ref.pop("reliability", None)
        if json.dumps(ref, sort_keys=True, default=float) != json.dumps(val, sort_keys=True, default=float):
            errs.append(f"scoreboard '{name}' differs from reports/results/{name}.json (rebuild the bundle)")
    return errs


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
                    for nid in nodes.get(last[0], []):
                        t += prof["nodeid_durations"].get(nid, 0.0)
                        if nid in failing:
                            break
                if abs(t - b["ttff_s"][m]) > 1e-3 * max(1.0, t) + 1e-3:
                    errs.append(f"{d.name} {b['id']} {m}: recomputed {t:.3f}s vs stored {b['ttff_s'][m]:.3f}s")
    return errs


def main() -> int:
    errs = []
    for name, fn in (("pages", check_pages), ("scoreboard", check_scoreboard), ("replays", check_replays),
                     ("backtests", check_backtests)):
        e = fn()
        print(f"[smoke] {name}: {'OK' if not e else f'{len(e)} problem(s)'}")
        for x in e[:10]:
            print("   ", x)
        errs += e
    print("SMOKE:", "PASS" if not errs else "FAIL")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
