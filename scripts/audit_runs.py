"""Phase A audit: the checks that need running something. Writes reports/results/audit_runs.json, which
`python -m stp.reports.audit_md` turns into reports/AUDIT.md together with the other results files.

  regen      re-run every report generator, record the non-timestamp diff vs the committed files, restore them
  tests      full pytest suite with JUnit XML -> passed / failed / errors / skipped (+ skip reasons)
  fresh_venv uv venv + NON-editable install of this repo into a temp dir (so stp.paths cannot reach data/),
             load the packaged model and score a synthetic change
  fixture    smartci profile / learn --max 5 / backtest --set mined / compare on the tiny fixture repo, run with
             the fresh venv's smartci CLI and the real packaged model
  smoke      python -m stp.demo.smoke
  server     streamlit run app/demo.py, poll /_stcore/health
  leftovers  sizes of external/cand_* clones; counts of "self-heal" wording and OWNER placeholders

Usage: python scripts/audit_runs.py [--skip tests,fresh_venv,...]
Needs `uv` on PATH for the fresh venv. Power state is recorded because timings here are informational only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
PROBE = r'''
import json, sys
from pathlib import Path
import smartci, smartci.scoring as sc
from stp.features.change import Change
m = sc.GlobalModel()
tests = ["tests/test_graph.py", "tests/test_paths.py", "tests/test_io.py"]
out = sc.score(Path("repo"), tests, Change(files={"src/pkg/paths.py": (10, 2)}), model=m)
top = max(out, key=lambda s: s.priority)
print(json.dumps({"installed_at": smartci.__file__, "model_version": m.version,
                  "n_features": len(m.cols["model"]), "n_features_coldstart": len(m.cols["model_coldstart"]),
                  "scores": {s.test_file: round(s.p_fail, 6) for s in out}, "top": top.test_file,
                  "model_used": top.model,
                  "research_modules_imported": sorted(k for k in sys.modules
                                                      if k.startswith(("stp.paths", "stp.models", "stp.data")))}))
'''


def run(cmd, cwd=None, env=None, timeout=1800):
    t0 = time.time()
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    return r, round(time.time() - t0, 1)


def on_ac_power() -> bool | None:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "(Get-CimInstance Win32_Battery).BatteryStatus"], capture_output=True, text=True)
        s = r.stdout.strip()
        return None if not s else s != "1"   # 1 = discharging
    except Exception:  # noqa: BLE001
        return None


def check_tests(tmp: Path) -> dict:
    xml = tmp / "junit.xml"
    r, sec = run([PY, "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider", f"--junitxml={xml}"], cwd=ROOT)
    root = ET.parse(xml).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    n, f, e, s = (int(suite.get(k, 0)) for k in ("tests", "failures", "errors", "skipped"))
    reasons = sorted({c.find("skipped").get("message", "") for c in suite.iter("testcase")
                      if c.find("skipped") is not None})
    return {"returncode": r.returncode, "seconds": sec, "tests": n, "passed": n - f - e - s, "failed": f,
            "errors": e, "skipped": s, "skip_reasons": reasons}


def check_fresh_venv(tmp: Path) -> dict:
    v = tmp / "freshvenv"
    r1, s1 = run(["uv", "venv", "-q", "-p", "3.11", str(v)])
    py = v / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    r2, s2 = run(["uv", "pip", "install", "-q", "-p", str(py), str(ROOT)])
    probe = tmp / "probe"
    probe.mkdir()
    (probe / "probe.py").write_text(PROBE, encoding="utf-8")
    r3, s3 = run([str(py), "-I", "probe.py"], cwd=probe)
    out = {"install_returncode": r2.returncode, "install_seconds": s1 + s2, "probe_returncode": r3.returncode,
           "install_mode": "non-editable (copies the package; stp.paths.ROOT points into site-packages, no data/)"}
    if r3.returncode == 0:
        out.update(json.loads(r3.stdout.strip().splitlines()[-1]))
    else:
        out["stderr_tail"] = r3.stderr[-1500:]
    out["python"] = str(py)
    return out


def check_fixture(tmp: Path, py: str) -> dict:
    sys.path.insert(0, str(ROOT))
    from tests.smartci_fixture import make_repo  # noqa: E402
    info = make_repo(tmp / "fx")
    repo = Path(info["repo"])
    sc = str(Path(py).parent / ("smartci.exe" if os.name == "nt" else "smartci"))
    env = dict(os.environ, PYTHONPATH=str(repo))
    env.pop("SMARTCI_MODEL_DIR", None)
    steps = {}
    for name, args in (("profile", ["profile"]), ("learn", ["learn", "--max", "5"]),
                       ("backtest", ["backtest", "--set", "mined"]),
                       ("compare", ["compare", "--bug", info["fix_sha"][:8]])):
        r, sec = run([sc, "--python", py, *args], cwd=repo, env=env)
        steps[name] = {"returncode": r.returncode, "seconds": sec, "tail": r.stdout[-600:]}
    cmp = steps["compare"]["tail"]
    m = {k: re.search(rf"^{k}\s+elapsed\s+([\d.]+)s\s+first failure after\s+([\d.]+)s\s+(\S+ \S+)", cmp, re.M)
         for k in ("default", "smartci")}
    steps["compare_parsed"] = {k: {"elapsed_s": float(x.group(1)), "first_failure_s": float(x.group(2)),
                                   "line": x.group(3)} for k, x in m.items() if x}
    kept = json.loads((repo / ".smartci" / "learn_summary.json").read_text(encoding="utf-8"))
    steps["learn_summary"] = kept
    return steps


def check_smoke() -> dict:
    r, sec = run([PY, "-m", "stp.demo.smoke"], cwd=ROOT)
    return {"returncode": r.returncode, "seconds": sec,
            "lines": [ln for ln in r.stdout.splitlines() if ln.startswith(("[smoke]", "SMOKE"))]}


def check_server(port: int = 8599) -> dict:
    p = subprocess.Popen([PY, "-m", "streamlit", "run", "app/demo.py", "--server.headless", "true",
                          "--server.port", str(port)], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok, t0 = False, time.time()
    try:
        while time.time() - t0 < 60 and not ok:
            try:
                ok = urllib.request.urlopen(f"http://localhost:{port}/_stcore/health", timeout=2).read() == b"ok"
            except Exception:  # noqa: BLE001
                time.sleep(1)
    finally:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        else:
            p.kill()
    return {"health_ok": ok, "seconds_to_healthy": round(time.time() - t0, 1)}


GENERATORS = ["baselines_md", "features_md", "modeling_md", "real_world_md", "results_md", "viva_md", "model_card"]
WATCH = ["reports", "models/global", "src/smartci/model", ":!reports/results/audit_*", ":!reports/AUDIT.md"]


def check_regen() -> dict:
    """Re-run every report generator, record what changed vs the committed files, then restore them."""
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *WATCH], cwd=ROOT, capture_output=True,
                           text=True).stdout.strip()
    if dirty:
        return {"skipped": "uncommitted changes under " + ", ".join(WATCH) + ": commit first", "dirty": dirty}
    rcs = {m: run([PY, "-m", f"stp.reports.{m}"], cwd=ROOT)[0].returncode for m in GENERATORS}
    diff = subprocess.run(["git", "diff", "-U0", "--", *WATCH], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout
    changed: dict[str, list[str]] = {}
    cur = None
    for ln in diff.splitlines():
        if ln.startswith("+++ b/"):
            cur = ln[6:]
        elif cur and ln[:1] in "+-" and not ln.startswith(("+++", "---")):
            if '"generated"' in ln or '"git_sha"' in ln or ln.strip() in "+-":
                continue  # timestamps / sha stamps are expected to change
            changed.setdefault(cur, []).append(ln[:300])
    subprocess.run(["git", "checkout", "--", *WATCH], cwd=ROOT)
    return {"generator_returncodes": rcs, "changed_lines": changed,
            "identical": not changed}


def dir_mb(p: Path) -> float:
    total = 0
    for dp, _, fs in os.walk(p):
        for f in fs:
            try:
                total += os.lstat(os.path.join(dp, f)).st_size
            except OSError:
                pass
    return round(total / 2**20, 1)


def check_leftovers() -> dict:
    def grep_count(pat, *excl):
        r = subprocess.run(["git", "grep", "-c", "-i", "-E", pat, "--", ".", *[f":!{x}" for x in excl]],
                           cwd=ROOT, capture_output=True, text=True)
        return {ln.rsplit(":", 1)[0]: int(ln.rsplit(":", 1)[1]) for ln in r.stdout.splitlines()}
    cands = {p.name: dir_mb(p) for p in sorted((ROOT / "external").glob("cand_*"))}
    ignored = subprocess.run(["git", "check-ignore", *[f"external/{c}" for c in cands]], cwd=ROOT,
                             capture_output=True, text=True).stdout.split()
    return {"candidate_clones_mb": cands, "candidate_clones_ignored": len(ignored) == len(cands),
            "heal_wording": grep_count("self.?heal", "docs/"),
            "owner_placeholders": grep_count("OWNER/", "docs/"),
            "sympy_mentions": grep_count("sympy", "docs/", "demo_bundle/repos/sympy/"),
            "cand_paths_in_code": grep_count("external/\"? ?/? ?\"?cand_|cand_sympy", "docs/", "reports/WORKLOG.md",
                                             "demo_bundle/")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", default="")
    a = ap.parse_args(argv)
    skip = set(filter(None, a.skip.split(",")))
    tmp = Path(tempfile.mkdtemp(prefix="smartci_audit_"))
    out = {"on_ac_power": on_ac_power(), "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        for name, fn in (("regen", check_regen), ("tests", lambda: check_tests(tmp)),
                         ("fresh_venv", lambda: check_fresh_venv(tmp)),
                         ("smoke", check_smoke), ("server", check_server), ("leftovers", check_leftovers)):
            if name in skip:
                continue
            print(f"[audit] {name} ...", flush=True)
            out[name] = fn()
        if "fixture" not in skip and out.get("fresh_venv", {}).get("probe_returncode") == 0:
            print("[audit] fixture ...", flush=True)
            out["fixture"] = check_fixture(tmp, out["fresh_venv"]["python"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    f = ROOT / "reports" / "results" / "audit_runs.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    old.update(out)
    f.write_text(json.dumps(old, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items()
                                                              if not isinstance(vv, (dict, list))})
                      for k, v in out.items()}, indent=1, default=str)[:3000])


if __name__ == "__main__":
    main()
