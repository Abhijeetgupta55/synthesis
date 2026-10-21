"""The repository's own CI history in .smartci/, and as-of features computed from it.

Scoring unit: the test *file* (a pytest module), the closest analogue of an LRTS test class.
  .smartci/history.jsonl  one line per (run, test file): run_id, start_ts, end_ts, stage, test_file, duration_s, fail
  .smartci/runs.jsonl     one line per run: run_id, start_ts, end_ts, commit, base, changed files
(JSON Lines rather than parquet: readable without tools, and the pytest plugin avoids importing pandas/pyarrow,
which costs seconds per session.)
`smartci record --junit report.xml --start <ts> --end <ts> [--commit SHA]` appends a run.
Features use exactly the research pipeline's pure functions (stp.features.history / cofail), with the same as-of
rule: a run is usable for a query at time t only if it ended at or before t.
"""
from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

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


def _module_of(classname: str, file_attr: str) -> tuple[str, str]:
    """(test file, class path inside it) for a JUnit testcase.

    The classname is authoritative: its longest dotted prefix whose last part looks like a pytest module
    (test_*/ *_test) is the module. The `file` attribute is only a fallback: for an *inherited* test method it names
    the file where the method is defined (e.g. TestDiGraph.test_contains inherited from test_graph.py), not the file
    that holds the test class, so trusting it gives a wrong node id."""
    # a run whose rootdir resolved to the main checkout (old commits without a pytest config) names classes
    # ".smartci.worktrees.<name>.pkg.tests.test_x"; drop that prefix so ids are relative to the worktree
    m = re.match(r"^\.?smartci\.worktrees\.[^.]+\.", classname or "")
    if m:
        classname = classname[m.end():]
    parts = classname.split(".") if classname else []
    for k in range(len(parts), 0, -1):
        last = parts[k - 1]
        if last.startswith("test_") or last.endswith("_test"):
            return "/".join(parts[:k]) + ".py", ".".join(parts[k:])
    mod = file_attr[:-3].replace("/", ".") if file_attr.endswith(".py") else ""
    rest = classname[len(mod) + 1:] if mod and classname.startswith(mod + ".") else ""
    return file_attr, rest


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
        f, rest = _module_of(cls, f)
        nid = "::".join([x for x in [f, *rest.split("."), name] if x]) if f else f"{cls}::{name}"
        out.append({"nodeid": nid, "file": f, "duration_s": float(tc.get("time", 0) or 0), "failed": bool(bad),
                    "skipped": any(ch.tag == "skipped" for ch in tc), "kind": kind})
    return out


def parse_junit(repo: Path, junit: Path) -> list[dict]:
    """Per test file: summed duration, failed (any failure/error), counts. Skipped-only files count as passed."""
    root = ET.parse(junit).getroot()
    per: dict[str, dict] = {}
    cache: dict = {}
    for tc in root.iter("testcase"):
        f = resolve_file(repo, tc.get("classname", ""), tc.get("file"), cache)
        if f is None:
            continue
        x = per.setdefault(f, {"test_file": f, "duration_s": 0.0, "fail": False, "n_cases": 0, "n_failed": 0})
        bad = any(ch.tag in ("failure", "error") for ch in tc)
        x["duration_s"] += float(tc.get("time", 0) or 0)
        x["fail"] = x["fail"] or bad
        x["n_cases"] += 1
        x["n_failed"] += int(bad)
    return list(per.values())


def _read_jsonl(f: Path) -> list[dict]:
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []


def _write_jsonl(f: Path, rows: list[dict]) -> None:
    f.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def record(repo: Path, junit: Path, start: float, end: float, commit: str | None = None, base: str | None = None,
           changed_files: list[str] | None = None, run_id: str | None = None) -> str:
    """Append one run to .smartci/ (re-recording the same run_id replaces it). Changed files come from git
    when not given."""
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
    h = [{"run_id": run_id, "start_ts": float(start), "end_ts": float(end), "stage": STAGE,
          "test_file": x["test_file"], "duration_s": x["duration_s"], "fail": x["fail"]} for x in per]
    r = [{"run_id": run_id, "start_ts": float(start), "end_ts": float(end), "commit": commit or "",
          "base": base or "", "files": sorted(changed_files)}]
    for name, new in (("history", h), ("runs", r)):
        f = d / f"{name}.jsonl"
        _write_jsonl(f, [x for x in _read_jsonl(f) if x["run_id"] != run_id] + new)
    return run_id


class History:
    """Loaded .smartci history (JSON Lines, readable by eye) with as-of features for a query time t."""

    def __init__(self, repo: Path):
        d = state_dir(repo)
        self.r = sorted(_read_jsonl(d / "runs.jsonl"), key=lambda x: (x["start_ts"], x["run_id"]))
        self.seq = {x["run_id"]: i for i, x in enumerate(self.r)}
        self.by_file: dict[str, list[dict]] = {}
        for x in _read_jsonl(d / "history.jsonl"):
            self.by_file.setdefault(x["test_file"], []).append(x)

    def n_finished(self, t: float) -> int:
        return sum(1 for x in self.r if x["end_ts"] <= t)

    def events(self, test_file: str) -> list[Event]:
        return [Event(self.seq.get(x["run_id"], 0), float(x["start_ts"]), float(x["end_ts"]), x["stage"],
                      bool(x["fail"]), float(x["duration_s"])) for x in self.by_file.get(test_file, [])]

    def records(self) -> list[RunRecord]:
        fails: dict[str, set] = {}
        for f, rows in self.by_file.items():
            for x in rows:
                if x["fail"]:
                    fails.setdefault(x["run_id"], set()).add(f)
        return [RunRecord(self.seq[x["run_id"]], float(x["end_ts"]), frozenset(x["files"]),
                          frozenset(fails.get(x["run_id"], ()))) for x in self.r]

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
