"""Co-failure memory: as-of association between changed files (or directories) and test failures.

Records are past runs: their end time, the files their change touched and the tests that failed. For a query
(test x, change files F, time t), only records with end <= t are used.

  For each changed file f in F:
    if f was changed by some finished run:  score_f = cof(f, x) / (nchg(f) + 1)       file level
    else (unseen file, directory backoff):  score_f = cof(dir(f), x) / (nchg(dir(f)) + 1)
  where nchg(f) = #finished runs whose change touched f and cof(f, x) = #those runs in which x failed
  (directory level: same with "touched a file directly in dir(f)").
  cof_max = max_f score_f, cof_sum = sum_f score_f (files in sorted order), cof_count_max = max_f cof(f, x)
  (raw file-level count; this is what "when cluster.py changed before, this test failed 4 times" quotes).
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


def parent_dir(path: str) -> str:
    p = path.replace("\\", "/")
    return p.rsplit("/", 1)[0] if "/" in p else ""


@dataclass(frozen=True)
class RunRecord:
    seq: int
    end: float
    files: frozenset[str]
    failing_tests: frozenset[str]


def cofail_features(test_id: str, change_files: Iterable[str], records: Sequence[RunRecord], t: float) -> dict:
    av = [r for r in records if r.end <= t]
    nchg: Counter = Counter()
    nchg_d: Counter = Counter()
    cof: Counter = Counter()
    cof_d: Counter = Counter()
    for r in av:
        dirs = {parent_dir(f) for f in r.files}
        nchg.update(r.files)
        nchg_d.update(dirs)
        if test_id in r.failing_tests:
            cof.update(r.files)
            cof_d.update(dirs)
    scores, counts = [], []
    for f in sorted(set(change_files)):
        if nchg[f] > 0:
            scores.append(cof[f] / (nchg[f] + 1))
        else:
            d = parent_dir(f)
            scores.append(cof_d[d] / (nchg_d[d] + 1))
        counts.append(cof[f])
    return {"cof_max": max(scores, default=0.0), "cof_sum": float(sum(scores)),
            "cof_count_max": max(counts, default=0)}
