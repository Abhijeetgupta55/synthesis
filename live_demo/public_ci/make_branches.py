"""Prepare one branch per bug on *your* fork, so GitHub's own machines time default vs smartci (public proof).

    python live_demo/public_ci/make_branches.py --fork-dir <local clone of your fork> \
        --smartci-dir external/networkx/.smartci [--n 10 --seed 1] [--push]

First a branch `smartci-base` at the commit the local profile was measured on (profile.json base_sha), with one
commit adding .github/workflows/smartci-compare.yml (jobs default / rule / model + report) and .smartci-baseline/
(profile.json, history.jsonl, runs.jsonl, adapter.json, coverage_map.json: the baseline smartci needs in CI).
Then for each chosen bug (held-out mined bugs from backtest.json, seeded sample):
  1. new branch `smartci-bug-<id8>` from smartci-base
  2. apply the bug's diff (mined: the reverse of the fix's source change; mutant: the mutation) with `git apply --3way`
     (bugs whose diff does not apply are skipped and listed)
  3. commit; with --push also `git push -u origin <branch>` (smartci-base is pushed first)
Open each pull request against `smartci-base`, so the PR diff is only the bug.
Writes live_demo/public_ci/branches.json (branch -> bug id, commit URL) for collect_runs.py.
Nothing is pushed without --push.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "smartci-compare.yml"
BASELINE = ("profile.json", "history.jsonl", "runs.jsonl", "adapter.json", "coverage_map.json")


def git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(r.stderr)
    return r.stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fork-dir", required=True)
    ap.add_argument("--smartci-dir", required=True)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()
    fork = Path(a.fork_dir).resolve()
    sd = (ROOT / a.smartci_dir).resolve()
    bt = json.loads((sd / "backtest.json").read_text(encoding="utf-8"))
    diffs = {json.loads(x)["fix_sha"]: json.loads(x)["source_diff"]
             for x in (sd / "bugs.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()}
    if (sd / "mutants.jsonl").exists():
        diffs.update({json.loads(x)["mutant_id"]: json.loads(x)["diff"]
                      for x in (sd / "mutants.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()})
    bugs = [b for b in bt["bugs"] if b["kind"] == "mined"] or bt["bugs"]
    bugs = random.Random(a.seed).sample(bugs, min(a.n, len(bugs)))
    home = git(fork, "symbolic-ref", "--short", "HEAD")
    sha = json.loads((sd / "profile.json").read_text(encoding="utf-8"))["base_sha"]
    base = "smartci-base"
    git(fork, "checkout", "-q", "-B", base, sha)
    (fork / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    for w in (fork / ".github" / "workflows").glob("*.y*ml"):     # only the comparison runs on these branches
        if w.name != "smartci-compare.yml":
            git(fork, "rm", "-q", str(w.relative_to(fork)))
    (fork / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(WORKFLOW, fork / ".github" / "workflows" / "smartci-compare.yml")
    bl = fork / ".smartci-baseline"
    bl.mkdir(exist_ok=True)
    for f in BASELINE:
        if (sd / f).exists():
            shutil.copyfile(sd / f, bl / f)
    git(fork, "add", "-A", ".github", ".smartci-baseline")
    git(fork, "commit", "-q", "-m", "smartci: comparison workflow and .smartci baseline")
    if a.push:
        git(fork, "push", "-q", "-f", "-u", "origin", base)
    made, skipped = {}, []
    for b in bugs:
        br = f"smartci-bug-{b['id'][:8]}"
        git(fork, "checkout", "-q", base)
        git(fork, "checkout", "-q", "-B", br)
        with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8", newline="\n") as fh:
            fh.write(diffs[b["id"]] if diffs[b["id"]].endswith("\n") else diffs[b["id"]] + "\n")
        r = subprocess.run(["git", "-C", str(fork), "apply", "--3way", fh.name], capture_output=True, text=True)
        Path(fh.name).unlink(missing_ok=True)
        if r.returncode:
            skipped.append({"id": b["id"], "reason": r.stderr.strip()[:200]})
            git(fork, "checkout", "-q", "--", ".", check=False)
            git(fork, "checkout", "-q", base)
            git(fork, "branch", "-D", br, check=False)
            continue
        git(fork, "add", "-A")
        git(fork, "commit", "-q", "-m", f"smartci public proof: reintroduce {b['kind']} {b['id'][:12]}")
        if a.push:
            git(fork, "push", "-q", "-f", "-u", "origin", br)
        made[br] = {"id": b["id"], "kind": b["kind"], "url": b.get("url"), "title": b.get("title"),
                    "expected_failing": b.get("failing_files")}
        print("branch", br, "<-", b["kind"], b["id"][:12])
    git(fork, "checkout", "-q", home)
    (Path(__file__).parent / "branches.json").write_text(json.dumps({"branches": made, "skipped": skipped}, indent=1),
                                                       encoding="utf-8")
    print(f"{len(made)} branches, {len(skipped)} skipped (diff no longer applies). Push: {'done' if a.push else 'not done'}")


if __name__ == "__main__":
    main()
