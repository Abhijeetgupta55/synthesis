"""Re-derive node ids in stored smartci artefacts from their saved JUnit XML files.

Needed once after the inherited-test node-id fix in history.junit_cases (0.1.0 builds named inherited test methods
after the file that *defines* the method instead of the file that holds the test class). Rewrites, in .smartci/:
  profile.json      nodeid_durations, flaky_nodeids     (from profile/run*.xml)
  bugs.jsonl        failing_nodeids, failing_files       (from learn/<sha10>_bug.xml)
  mutants.jsonl     failing_nodeids, failing_files       (from mutants/<mutant_id>.xml)
Usage: python -m smartci.repair <repo>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from smartci.history import junit_cases, state_dir


def repair(repo: Path) -> dict:
    d = state_dir(Path(repo))
    out = {}
    pf = d / "profile.json"
    if pf.exists():
        p = json.loads(pf.read_text(encoding="utf-8"))
        nd: dict[str, list] = {}
        nf: dict[str, list] = {}
        for x in sorted((d / "profile").glob("run*.xml")):
            for c in junit_cases(x):
                if c["kind"] == "test":
                    nd.setdefault(c["nodeid"], []).append(c["duration_s"])
                    nf.setdefault(c["nodeid"], []).append(c["failed"])
        p["nodeid_durations"] = {k: float(np.mean(v)) for k, v in nd.items()}
        p["flaky_nodeids"] = sorted(k for k, v in nf.items() if len(set(v)) > 1)
        pf.write_text(json.dumps(p, indent=1), encoding="utf-8")
        out["profile_nodeids_with_duration"] = sum(1 for n in p["nodeids"] if n in p["nodeid_durations"])
        out["profile_nodeids"] = len(p["nodeids"])
    for name, key, xml in (("bugs.jsonl", "fix_sha", lambda r: d / "learn" / f"{r['fix_sha'][:10]}_bug.xml"),
                           ("mutants.jsonl", "mutant_id", lambda r: d / "mutants" / f"{r['mutant_id']}.xml")):
        f = d / name
        if not f.exists():
            continue
        rows, changed, missing = [], 0, 0
        for ln in f.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            x = xml(r)
            if x.exists():
                fails = sorted(c["nodeid"] for c in junit_cases(x) if c["failed"] and c["kind"] == "test")
                if fails and fails != r["failing_nodeids"]:
                    changed += 1
                    r["failing_nodeids"] = fails
                    r["failing_files"] = sorted({n.split("::", 1)[0] for n in fails})
            else:
                missing += 1
            rows.append(r)
        f.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        out[name] = {"rows": len(rows), "changed": changed, "xml_missing": missing}
    return out


if __name__ == "__main__":
    print(json.dumps(repair(Path(sys.argv[1] if len(sys.argv) > 1 else ".")), indent=1))
