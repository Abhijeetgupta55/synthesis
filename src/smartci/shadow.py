"""Shadow mode for CI: `pytest --smartci-shadow` ranks but keeps the order; `smartci report` summarises.

For every shadow receipt whose run had a failure, the time to the first failing *file* is computed under the
order CI actually used, smartci's ranking, and the simple baselines, from that run's own measured per-file
durations (file granularity: the whole first failing file counts, the same for every ordering).
Report: after N failing runs, "smartci would have surfaced the first failure X min earlier (median); better on A,
worse on B" against the current order and each baseline. If a simple baseline is as good or better, it says so.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from smartci import receipts as R
from smartci.history import state_dir


def _ttff(order: list[str], dur: dict[str, float], failing: set[str]) -> float:
    t = 0.0
    for f in order:
        t += dur.get(f, 0.0)
        if f in failing:
            return t
    return float("nan")


def report(repo: Path) -> dict:
    d = state_dir(repo) / "receipts"
    rows = []
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        r = R.read(f)
        if not r.get("shadow") or not r.get("results"):
            continue
        failing = {k for k, v in r["results"].items() if v["outcome"] == "failed"}
        if not failing:
            continue
        dur = {k: v["duration_s"] for k, v in r["results"].items()}
        orig = [x for x in r["original_order"] if x in dur]
        feats = {x["test_file"]: x["features"] for x in r["ranking"]}
        pos = {x: i for i, x in enumerate(orig)}
        ords = {"current": orig, "smartci": [x["test_file"] for x in r["ranking"] if x["test_file"] in dur],
                "fastest_first": sorted(orig, key=lambda x: (feats.get(x, {}).get("dur_ema_asof", 0), pos[x])),
                "recently_failed_first": sorted(orig, key=lambda x: (feats.get(x, {}).get("h_days_since_last_fail", 9999),
                                                                    pos[x])),
                "changed_files_first": sorted(orig, key=lambda x: (-float(feats.get(x, {}).get("test_file_in_diff", 0)),
                                                                  -feats.get(x, {}).get("path_prefix_overlap", 0),
                                                                  pos[x]))}
        rows.append({"receipt": f.name, **{k: _ttff(o, dur, failing) for k, o in ords.items()}})
    out = {"n_failing_runs": len(rows), "runs": rows, "vs": {}}
    if rows:
        sm = np.array([x["smartci"] for x in rows])
        for b in ("current", "fastest_first", "recently_failed_first", "changed_files_first"):
            v = np.array([x[b] for x in rows])
            out["vs"][b] = {"median_minutes_earlier": float(np.median(v - sm) / 60), "better": int((sm < v).sum()),
                            "worse": int((sm > v).sum()), "equal": int((sm == v).sum())}
        best = min(out["vs"], key=lambda b: np.median([x[b] for x in rows]))
        out["best_simple"] = best
        out["message"] = (
            f"Over {len(rows)} failing runs, smartci would have surfaced the first failure "
            f"{out['vs']['current']['median_minutes_earlier']:.1f} min earlier than your current order (median); "
            f"better on {out['vs']['current']['better']}, worse on {out['vs']['current']['worse']}.")
        if np.median([x[best] for x in rows]) <= np.median(sm) and best != "current":
            out["message"] += f" The simple rule '{best}' did as well or better; consider using it."
    return out
