"""The repository's own CI history in .smartci/, and as-of features computed from it.

Scoring unit: the test *file* (a pytest module), the closest analogue of an LRTS test class.
  .smartci/history.parquet  one row per (run, test file): run_id, start_ts, end_ts, stage, test_file, duration_s, fail
  .smartci/runs.parquet     one row per run: run_id, start_ts, end_ts, commit, base, changed files (JSON list)
`smartci record --junit report.xml --start <ts> --end <ts> [--commit SHA]` appends a run.
Features use exactly the research pipeline's pure functions (stp.features.history / cofail), with the same as-of
rule: a run is usable for a query at time t only if it ended at or before t.
"""
from __future__ import annotations

import json
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from stp.features.cofail import RunRecord, cofail_features
from stp.features.history import Event, HistoryParams, cost_features, history_features

STAGE = "default"


def state_dir(repo: Path) -> Path:
    """Where smartci keeps its state: $SMARTCI_DIR if set (used by `compare` inside throwaway worktrees so they share
    the main checkout's profile/history/adapter), else <repo>/.smartci."""
    env = os.environ.get("SMARTCI_DIR")
    return Path(env) if env else Path(repo) / ".smartci"


def smartci_dir(repo: Path) -> Path:
    """.smartci/ in the repo, listed in .git/info/exclude (a local, untracked ignore) so `git status` stays clean.
    pytest's default norecursedirs ('.*') keeps it from collecting the worktrees inside."""
    d = state_dir(repo)
    d.mkdir(parents=True, exist_ok=True)
    ex = Path(repo) / ".git" / "info" / "exclude"
    if ex.parent.exists():
        txt = ex.read_text(encoding="utf-8") if ex.exists() else ""
        if ".smartci/" not in txt.splitlines():
            ex.write_text(txt + ("" if txt.endswith("\n") or not txt else "\n") + ".smartci/\n", encoding="utf-8")
    return d


def resolve_file(repo: Path, classname: str, file_attr: str | None, cache: dict) -> str | None:
    """Map a JUnit testcase to its test file (repo-relative, '/' separators)."""
    if file_attr:
        return Path(file_attr).as_posix()
    if classname in cache:
        return cache[classname]
    parts = classname.split(".")
    found = None
    for k in range(len(parts), 0, -1):
        cand = "/".join(parts[:k]) + ".py"
        if (Path(repo) / cand).exists():
            found = cand
            break
    cache[classname] = found
    return found


def junit_cases(junit: Path) -> list[dict]:
    """Every <testcase> of a pytest JUnit file (junit_family=xunit1, which carries `file`) as a pytest node id:
    file::Class::name for methods, file::name for functions. Collection errors have kind='collection'."""
    root = ET.parse(junit).getroot()
    out = []
    for tc in root.iter("testcase"):
        f = (tc.get("file") or "").replace("\\", "/")
        cls, name = tc.get("classname", ""), tc.get("name", "")
        bad = [ch for ch in tc if ch.tag in ("failure", "error")]
        kind = "collection" if any(ch.tag == "error" and "collection" in (ch.get("message") or "").lower()
                                   for ch in bad) else "test"
        mod = f[:-3].replace("/", ".") if f.endswith(".py") else ""
        rest = cls[len(mod) + 1:] if mod and cls.startswith(mod + ".") else ""
        nid = "::".join([x for x in [f, *rest.split("."), name] if x]) if f else f"{cls}::{name}"
        out.append({"nodeid": nid, "file": f, "duration_s": float(tc.get("time", 0) or 0), "failed": bool(bad),
                    "skipped": any(ch.tag == "skipped" for ch in tc), "kind": kind})
    return out


def parse_junit(repo: Path, junit: Path) -> pd.DataFrame:
    """Per test file: summed duration, failed (any failure/error), counts. Skipped-only files count as passed."""
    root = ET.parse(junit).getroot()
    rows, cache = [], {}
    for tc in root.iter("testcase"):
        f = resolve_file(repo, tc.get("classname", ""), tc.get("file"), cache)
        if f is None:
            continue
        failed = any(ch.tag in ("failure", "error") for ch in tc)
        skipped = any(ch.tag == "skipped" for ch in tc)
        rows.append((f, float(tc.get("time", 0) or 0), failed, skipped))
    d = pd.DataFrame(rows, columns=["test_file", "duration_s", "fail", "skipped"])
    if d.empty:
        return pd.DataFrame(columns=["test_file", "duration_s", "fail", "n_cases", "n_failed"])
    return d.groupby("test_file").agg(duration_s=("duration_s", "sum"), fail=("fail", "any"),
                                      n_cases=("fail", "size"), n_failed=("fail", "sum")).reset_index()


def record(repo: Path, junit: Path, start: float, end: float, commit: str | None = None, base: str | None = None,
           changed_files: list[str] | None = None, run_id: str | None = None) -> str:
    """Append one run to .smartci/. Changed files are computed with git when not given."""
    repo = Path(repo)
    d = smartci_dir(repo)
    per = parse_junit(repo, junit)
    if changed_files is None:
        try:
            from smartci.gitdiff import compute
            changed_files = compute(repo, base, include_worktree=False).change.files
        except Exception:  # noqa: BLE001  (no base / shallow clone: co-failure memory just gets no files)
            changed_files = []
    run_id = run_id or f"run-{int(start)}-{commit[:8] if commit else 'local'}"
    h = per.assign(run_id=run_id, start_ts=float(start), end_ts=float(end), stage=STAGE)[
        ["run_id", "start_ts", "end_ts", "stage", "test_file", "duration_s", "fail"]]
    r = pd.DataFrame([{"run_id": run_id, "start_ts": float(start), "end_ts": float(end), "commit": commit or "",
                       "base": base or "", "files": json.dumps(sorted(changed_files))}])
    for name, new in (("history", h), ("runs", r)):
        f = d / f"{name}.parquet"
        old = pd.read_parquet(f) if f.exists() else None
        out = new if old is None else pd.concat([old[old.run_id != run_id], new], ignore_index=True)
        out.to_parquet(f, index=False)
    return run_id


class History:
    """Loaded .smartci history with as-of feature computation for a query time t."""

    def __init__(self, repo: Path):
        d = state_dir(repo)
        self.h = pd.read_parquet(d / "history.parquet") if (d / "history.parquet").exists() else pd.DataFrame(
            columns=["run_id", "start_ts", "end_ts", "stage", "test_file", "duration_s", "fail"])
        self.r = pd.read_parquet(d / "runs.parquet") if (d / "runs.parquet").exists() else pd.DataFrame(
            columns=["run_id", "start_ts", "end_ts", "commit", "base", "files"])
        self.r = self.r.sort_values(["start_ts", "run_id"]).reset_index(drop=True)
        self.seq = {rid: i for i, rid in enumerate(self.r.run_id)}

    def n_finished(self, t: float) -> int:
        return int((self.r.end_ts <= t).sum())

    def events(self, test_file: str) -> list[Event]:
        g = self.h[self.h.test_file == test_file]
        return [Event(self.seq.get(rid, 0), float(s), float(e), st, bool(f), float(du))
                for rid, s, e, st, f, du in zip(g.run_id, g.start_ts, g.end_ts, g.stage, g.fail, g.duration_s)]

    def records(self) -> list[RunRecord]:
        fails = self.h[self.h.fail].groupby("run_id").test_file.apply(frozenset).to_dict()
        return [RunRecord(self.seq[rid], float(e), frozenset(json.loads(fl)), fails.get(rid, frozenset()))
                for rid, e, fl in zip(self.r.run_id, self.r.end_ts, self.r.files)]

    def features(self, test_files: list[str], change_files: list[str], t: float | None = None,
                 params: HistoryParams = HistoryParams()) -> list[dict]:
        t = time.time() if t is None else t
        rows = [history_features(self.events(f), t, STAGE, params) for f in test_files]
        cost = cost_features(rows)
        recs = self.records()
        out = []
        for f, r, c in zip(test_files, rows, cost):
            out.append({**{k: v for k, v in r.items() if not k.startswith("_")}, **c,
                        **cofail_features(f, change_files, recs, t)})
        return out
