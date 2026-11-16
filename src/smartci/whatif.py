"""Rank a repository's test files for a *hypothetical* change given as file paths only (no patch text).

Used by `smartci rank --files ...` and by the demo app's "Predict live" page, so both produce the same scores from
the same inputs: the repo's `.smartci/` state (profile, history, adapter, coverage map) and the packaged model.

How a paths-only change is turned into model inputs:
  - changed files = the given paths; diff tokens = tokens of the paths only;
  - change size: additions / deletions as given, else the median of the repo's own mined bug-fix changes
    (`typical_size`). Zero would be wrong: the model learned that a 0-line change is unusual and raises risk;
  - coverage signal (only if the adapter uses it): a test file "covers" the change if it executed any line of a
    changed file in the coverage map (file level, because without a patch there are no changed lines);
  - test files = the profiled suite in pytest's default order; history is read as of `t`.
"""
from __future__ import annotations

from pathlib import Path

from smartci import coverage_map
from smartci.explain import reasons
from smartci.history import state_dir
from smartci.scoring import GlobalModel, Scored, load_adapter, score, stable_order
from stp.features.change import Change
from stp.features.tokens import diff_token_counts


# the features smartci backtest's changed-files-first rule sorts by (descending), in this order
RELATEDNESS = ("test_file_in_diff", "path_prefix_overlap", "name_token_overlap")


def stopwords(repo: Path) -> frozenset[str]:
    return frozenset({Path(repo).resolve().name.lower().replace("-", "")})


def typical_size(repo: Path) -> tuple[int, int]:
    """Median (additions, deletions) of the mined bug-fix changes in .smartci/bugs.jsonl (10, 10 if none)."""
    import json
    f = state_dir(repo) / "bugs.jsonl"
    a, d = [], []
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            s = json.loads(line).get("source_diff", "").splitlines()
            a.append(sum(1 for x in s if x.startswith("+") and not x.startswith("+++")))
            d.append(sum(1 for x in s if x.startswith("-") and not x.startswith("---")))
    if not a:
        return 10, 10
    med = lambda v: int(sorted(v)[len(v) // 2])  # noqa: E731
    return med(a), med(d)


def change_from_paths(paths: list[str], stop: frozenset[str], additions: int = 10, deletions: int = 10) -> Change:
    paths = sorted({p.replace("\\", "/") for p in paths})
    return Change(files=paths, additions=int(additions), deletions=int(deletions),
                  token_counts=dict(diff_token_counts(paths, [None] * len(paths), extra_stop=stop)), has_data=True)


def covering_from_paths(cmap: dict | None, paths: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    if not cmap:
        return out
    for f in paths:
        for tests in (cmap["lines"].get(f) or {}).values():
            for t in tests:
                name = cmap["tests"][t]
                out[name] = out.get(name, 0) + 1
    return out


def suite(repo: Path) -> list[str]:
    import json
    p = json.loads((state_dir(repo) / "profile.json").read_text(encoding="utf-8"))
    return list(p["default_order"])


def rank_paths(repo: Path, paths: list[str], t: float | None = None, explain: bool = True,
               model: GlobalModel | None = None, additions: int | None = None,
               deletions: int | None = None) -> list[dict]:
    """Ranked rows (best first): test file, P(fail), expected duration, priority, model, top-3 reasons."""
    repo = Path(repo)
    stop = stopwords(repo)
    ta, td = typical_size(repo)
    change = change_from_paths(paths, stop, ta if additions is None else additions, td if deletions is None else deletions)
    ad = load_adapter(repo)
    covering = covering_from_paths(coverage_map.load(repo), change.files) if ad and ad.get("uses_coverage") else None
    tests = suite(repo)
    sc: list[Scored] = score(repo, tests, change, t=t, model=model, stop=stop, explain=explain, covering=covering)
    rows = []
    for rank, i in enumerate(stable_order(sc), 1):
        s = sc[i]
        rs = reasons(s, change.files)[0] if explain else []
        rows.append({"rank": rank, "test_file": s.test_file, "p_fail": s.p_fail,
                     "expected_duration_s": s.expected_duration, "priority": s.priority, "model": s.model,
                     "covers_change": bool(covering and covering.get(s.test_file)), "reasons": rs,
                     "relatedness": [s.features.get(k, 0) for k in RELATEDNESS]})
    return rows
