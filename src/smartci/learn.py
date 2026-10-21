"""`smartci learn`: mine the repo's own history for test-backed bug fixes, and fit the per-repo adapter.

Candidates: non-merge commits since --since that touch at least one non-test .py source file AND at least one test
file, and whose message mentions a fix (fix/fixes/fixed/bug/regression/issue/#123, case-insensitive).
Reproduction of each candidate, in a worktree:
  1. check out the fix commit and run its touched test files: they must pass (else: excluded, "fails on fix")
  2. restore only the *source* files from the parent (files the fix added are removed, files it deleted are
     restored); the fixed tests stay
  3. run the touched test files again; keep the bug iff >= 1 test fails
  4. reset the worktree cleanly
Every exclusion is logged with its reason: no_failure, fails_on_fix, collection_error, timeout, no_tests.
Commits that cannot run under the *current* pinned environment show up as fails_on_fix / collection_error.

Stored in .smartci/bugs.jsonl: fix_sha, parent_sha, date, source files, source diff (fix -> parent, i.e. the
reintroduced bug), failing node ids and files, log path. Exclusions: .smartci/learn_log.jsonl.

Adapter (`fit_adapter`): bugs split chronologically, older 60% adapt / newer 40% evaluate; with >= 20 adapt bugs a
small L2 logistic regression on [global-model logit, covers_changed_lines] is fitted on the adapt bugs' rows
(one row per test file, label = the file has a failing test). Evaluation never uses adapt bugs.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from smartci import history, runner
from smartci.gitdiff import git

# Fix keywords or an explicit issue-closing reference. A bare "(#1234)" is NOT enough: squash-merged PRs end every
# subject with their PR number, which would admit features and refactors (NetworkX since 2024: 293 vs 87 candidates).
FIX_RE = re.compile(r"\b(fix(es|ed|ing)?|bug(s|fix|fixes)?|regression|issue)\b|\b(closes|fixes|resolves)\s+#\d+|\bgh-\d+",
                    re.I)


def is_test_file(path: str) -> bool:
    p = path.replace("\\", "/")
    name = p.rsplit("/", 1)[-1]
    if not name.endswith(".py"):
        return False
    return name.startswith("test_") or name.endswith("_test.py")


def is_source_file(path: str) -> bool:
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return (name.endswith(".py") and not is_test_file(path) and name not in ("conftest.py", "setup.py")
            and not name.startswith("."))


def candidates(repo: Path, since: str | None = None, branch: str = "HEAD") -> list[dict]:
    args = ["log", branch, "--no-merges", "--format=%x1e%H%x1f%P%x1f%ct%x1f%s", "--name-status", "-M"]
    if since:
        args.insert(2, f"--since={since}")
    out = []
    for block in git(repo, *args).split("\x1e")[1:]:
        head, *lines = block.strip().split("\n")
        sha, parents, ts, subject = head.split("\x1f")
        if len(parents.split()) != 1:
            continue
        files = []
        for ln in lines:
            if not ln.strip():
                continue
            parts = ln.split("\t")
            st = parts[0][0]
            files.append((st, parts[-1], parts[1] if st == "R" else None))
        tests = [f for s, f, _ in files if is_test_file(f) and s != "D"]
        src = [(s, f, old) for s, f, old in files if is_source_file(f) or (old and is_source_file(old))]
        if tests and src and FIX_RE.search(subject):
            out.append({"fix_sha": sha, "parent_sha": parents, "date": int(ts), "subject": subject,
                        "test_files": tests, "source_changes": src})
    return sorted(out, key=lambda c: c["date"])


def _restore_sources(wt: Path, cand: dict) -> list[str]:
    """Bring the fix's source files back to the parent state. Returns the source paths touched."""
    touched = []
    for st, f, old in cand["source_changes"]:
        if st == "A":
            (wt / f).unlink(missing_ok=True)
            touched.append(f)
        elif st == "R":
            (wt / f).unlink(missing_ok=True)
            git(wt, "checkout", cand["parent_sha"], "--", old)
            touched += [f, old]
        else:
            git(wt, "checkout", cand["parent_sha"], "--", f)
            touched.append(f)
    return touched


def _failed_nodeids(junit: Path, wt: Path) -> tuple[list[str], bool]:
    """Failing node ids from a JUnit file, and whether there was a collection error."""
    if not junit.exists():
        return [], True
    cases = history.junit_cases(junit)
    return ([c["nodeid"] for c in cases if c["failed"] and c["kind"] == "test"],
            any(c["kind"] == "collection" for c in cases))


def reproduce(repo: Path, cand: dict, wt: Path, timeout: float, python: str | None) -> dict:
    d = history.state_dir(repo) / "learn"
    d.mkdir(parents=True, exist_ok=True)
    sha = cand["fix_sha"]
    runner.reset_worktree(wt, sha)
    tests = [t for t in cand["test_files"] if (wt / t).exists()]
    if not tests:
        return {"status": "excluded", "reason": "no_tests"}
    j_fix = d / f"{sha[:10]}_fix.xml"
    r = runner.run_pytest(wt, ["-q", *tests], junit=j_fix, timeout=timeout, python=python)
    if r.timed_out:
        return {"status": "excluded", "reason": "timeout", "stage": "fix"}
    fails_fix, coll = _failed_nodeids(j_fix, wt)
    if r.returncode in (2, 3, 4) or coll:
        return {"status": "excluded", "reason": "collection_error", "stage": "fix", "returncode": r.returncode}
    if fails_fix:
        return {"status": "excluded", "reason": "fails_on_fix", "n_failed": len(fails_fix)}
    src = _restore_sources(wt, cand)
    diff = git(wt, "diff", "--no-color", "HEAD", "--", *src)
    j_bug = d / f"{sha[:10]}_bug.xml"
    log = d / f"{sha[:10]}_bug.log"
    r = runner.run_pytest(wt, ["-q", *tests], junit=j_bug, timeout=timeout, python=python)
    log.write_text(r.stdout, encoding="utf-8")
    runner.reset_worktree(wt, sha)
    if r.timed_out:
        return {"status": "excluded", "reason": "timeout", "stage": "bug"}
    fails, coll = _failed_nodeids(j_bug, wt)
    if r.returncode in (2, 3, 4) or (coll and not fails):
        return {"status": "excluded", "reason": "collection_error", "stage": "bug", "returncode": r.returncode}
    if not fails:
        return {"status": "excluded", "reason": "no_failure"}
    files = sorted({n.split("::", 1)[0] for n in fails})
    return {"status": "kept", "bug": {"fix_sha": sha, "parent_sha": cand["parent_sha"], "date": cand["date"],
                                      "subject": cand["subject"], "source_files": src, "source_diff": diff,
                                      "failing_nodeids": fails, "failing_files": files,
                                      "touched_test_files": tests, "log": str(log)}}


def learn(repo: Path, since: str | None = None, max_n: int | None = None, timeout: float = 600,
          python: str | None = None, branch: str = "HEAD") -> dict:
    repo = Path(repo).resolve()
    d = history.smartci_dir(repo)
    cands = candidates(repo, since, branch)
    done = {}
    for name in ("bugs.jsonl", "learn_log.jsonl"):
        f = d / name
        if f.exists():
            for ln in f.read_text(encoding="utf-8").splitlines():
                x = json.loads(ln)
                done[x["fix_sha"]] = x
    todo = [c for c in cands if c["fix_sha"] not in done]
    if max_n is not None:
        todo = todo[:max(0, max_n - sum(1 for c in cands if c["fix_sha"] in done))]
    print(f"smartci learn: {len(cands)} candidate commits, {len(done)} already processed, {len(todo)} to run", flush=True)
    wt = runner.worktree(repo, "learn", "HEAD")
    try:
        for i, c in enumerate(todo):
            t0 = time.time()
            res = reproduce(repo, c, wt, timeout, python)
            if res["status"] == "kept":
                with open(d / "bugs.jsonl", "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(res["bug"]) + "\n")
            else:
                with open(d / "learn_log.jsonl", "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"fix_sha": c["fix_sha"], "date": c["date"], "subject": c["subject"],
                                         **res}) + "\n")
            print(f"  [{i + 1}/{len(todo)}] {c['fix_sha'][:10]} {res['status']:8s} {res.get('reason', '')} "
                  f"({time.time() - t0:.0f}s) {c['subject'][:60]}", flush=True)
    finally:
        runner.remove_worktree(repo, wt)
    return summary(repo, len(cands))


def load_bugs(repo: Path) -> list[dict]:
    f = history.state_dir(repo) / "bugs.jsonl"
    if not f.exists():
        return []
    bugs = (json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip())
    return sorted((b for b in bugs if FIX_RE.search(b["subject"])), key=lambda b: b["date"])


def summary(repo: Path, n_candidates: int | None = None) -> dict:
    d = history.state_dir(repo)
    bugs = load_bugs(repo)
    ex = [json.loads(x) for x in (d / "learn_log.jsonl").read_text(encoding="utf-8").splitlines()] \
        if (d / "learn_log.jsonl").exists() else []
    reasons: dict[str, int] = {}
    for e in ex:
        reasons[e["reason"]] = reasons.get(e["reason"], 0) + 1
    s = {"n_candidates": n_candidates, "n_kept": len(bugs), "n_excluded": len(ex), "exclusions": reasons,
         "could_not_run_in_current_env": reasons.get("fails_on_fix", 0) + reasons.get("collection_error", 0)}
    (d / "learn_summary.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    return s


def split_adapt_eval(bugs: list[dict], frac: float = 0.6) -> tuple[list[dict], list[dict]]:
    """Chronological split: older `frac` adapt, newer rest evaluate."""
    k = int(round(frac * len(bugs)))
    return bugs[:k], bugs[k:]


def fit_adapter(repo: Path, min_adapt: int = 20) -> dict:
    """Per-repo adapter on the older 60% of mined bugs: L2 logistic regression on [global logit, covers changed
    lines]. Skipped (and any old adapter removed) with fewer than `min_adapt` adapt bugs."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    from smartci import coverage_map
    from smartci import profile as prof
    from smartci.backtest import Sim, bug_change
    from smartci.scoring import GlobalModel, feature_rows

    repo = Path(repo).resolve()
    d = history.state_dir(repo)
    bugs = [b for b in load_bugs(repo) if b.get("base_status", "ok") == "ok"]   # same bugs the backtest uses
    adapt, ev = split_adapt_eval(bugs)
    f = d / "adapter.json"
    if len(adapt) < min_adapt:
        f.unlink(missing_ok=True)
        return {"fitted": False, "reason": f"only {len(adapt)} adapt bugs (< {min_adapt})", "n_bugs": len(bugs)}
    sim = Sim(prof.load(repo))
    cmap = coverage_map.load(repo)
    model = GlobalModel()
    hist = history.History(repo)
    stop = frozenset({repo.name.lower().replace("-", "")})
    X, y = [], []
    for b in adapt:
        ch, patches = bug_change(b["source_diff"], stop)
        rows = feature_rows(repo, sim.files, ch, float(b["date"]), stop, hist)
        which = "model" if hist.n_finished(float(b["date"])) >= 5 else "model_coldstart"
        p = model.calibrate(model.raw(rows, which), which)
        z = np.log(np.clip(p, 1e-7, 1 - 1e-7) / (1 - np.clip(p, 1e-7, 1 - 1e-7)))
        cov = coverage_map.covering_tests(cmap, patches) if cmap else {}
        fails = set(b.get("failing_files_base") or b["failing_files"])
        for fl, zi in zip(sim.files, z):
            X.append([zi, float(cov.get(fl, 0) > 0)])
            y.append(fl in fails)
    X, y = np.array(X), np.array(y)
    lr = LogisticRegression(C=1.0, max_iter=1000).fit(X, y)
    a = {"fitted": True, "intercept": float(lr.intercept_[0]), "coef_logit": float(lr.coef_[0][0]),
         "coef_cov": float(lr.coef_[0][1]), "uses_coverage": cmap is not None, "n_adapt_bugs": len(adapt),
         "n_eval_bugs": len(ev), "adapt_until": int(adapt[-1]["date"]), "n_rows": int(len(y))}
    f.write_text(json.dumps(a, indent=1), encoding="utf-8")
    return a


def rebase(repo: Path, timeout: float = 900, python: str | None = None) -> dict:
    """Re-apply every mined bug to the *profiled base* (today's code) and record which tests fail there.

    The backtest simulates on today's suite (profile durations and order), so the bug must also be evaluated on
    today's code: base + the bug's source diff (git apply --3way). Bugs whose diff no longer applies, or whose touched
    tests no longer fail on today's code, are marked and excluded from the backtest (listed, not hidden).
    Adds to each bug: base_sha, base_status ('ok' | 'no_apply' | 'no_failure' | 'timeout'), failing_nodeids_base,
    failing_files_base.
    """
    import subprocess
    import tempfile

    from smartci import profile as prof

    repo = Path(repo).resolve()
    d = history.state_dir(repo)
    base = prof.load(repo)["base_sha"]
    f = d / "bugs.jsonl"
    rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    wt = runner.worktree(repo, "rebase", base)
    stats: dict[str, int] = {}
    try:
        for i, b in enumerate(rows):
            if b.get("base_sha") == base and "base_status" in b:
                stats[b["base_status"]] = stats.get(b["base_status"], 0) + 1
                continue
            runner.reset_worktree(wt, base)
            with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8", newline="\n") as fh:
                fh.write(b["source_diff"] if b["source_diff"].endswith("\n") else b["source_diff"] + "\n")
            r = subprocess.run(["git", "-C", str(wt), "apply", "--3way", fh.name], capture_output=True, text=True)
            Path(fh.name).unlink(missing_ok=True)
            b["base_sha"] = base
            conflict = r.returncode != 0 or "conflict" in (r.stderr or "").lower()
            if conflict:
                b["base_status"], b["failing_nodeids_base"], b["failing_files_base"] = "no_apply", [], []
            else:
                tests = [t for t in b["touched_test_files"] if (wt / t).exists()]
                junit = d / "learn" / f"{b['fix_sha'][:10]}_base.xml"
                pr = runner.run_pytest(wt, ["-q", *tests], junit=junit, timeout=timeout, python=python)
                fails = []
                if junit.exists():
                    fails = sorted(c["nodeid"] for c in history.junit_cases(junit) if c["failed"] and c["kind"] == "test")
                b["base_status"] = "timeout" if pr.timed_out else ("ok" if fails else "no_failure")
                b["failing_nodeids_base"] = fails
                b["failing_files_base"] = sorted({n.split("::", 1)[0] for n in fails})
            stats[b["base_status"]] = stats.get(b["base_status"], 0) + 1
            print(f"  [rebase {i + 1}/{len(rows)}] {b['fix_sha'][:10]} {b['base_status']} "
                  f"({len(b['failing_nodeids_base'])} failing)", flush=True)
            f.write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
    finally:
        runner.reset_worktree(wt, base)
        runner.remove_worktree(repo, wt)
    return {"base_sha": base, "status": stats}
