"""Change-relatedness features: pure reference implementations on plain inputs.

A `Change` is what the code under test differs from its base by: changed paths, line counts and the token counts
of paths + patch text. All features compare a test id with a change; none uses history or outcomes.

  test_file_in_diff     the test's own source file is among the changed files (exact suffix mapping, testmap.py)
  same_top_module       the test's top module (first normalised directory) is a top module of some changed file
  path_prefix_overlap   max over changed files of aligned_prefix_overlap(test dirs, file dirs) in [0, 1]
  name_token_overlap    |tokens(test path) ∩ tokens(changed paths)|  (EDA §F)
  bm25_test_vs_diff     BM25 of the test's tokens (document) against the diff tokens (query); corpus = the tests
                        of the run, so IDF uses only what is known when the run starts
  chg_n_files, chg_additions, chg_deletions, chg_n_top_modules   change size
"""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from stp.features.testmap import suffix_index, test_path_suffixes
from stp.features.tokens import aligned_prefix_overlap, file_dirs, test_dirs, test_text, tokenize, top_module


@dataclass
class Change:
    files: list[str]                                  # changed paths (current names)
    additions: int = 0
    deletions: int = 0
    token_counts: dict[str, int] = field(default_factory=dict)   # diff tokens: paths (+ old names) + patch text
    has_data: bool = True


def change_size_features(change: Change, stop: frozenset[str] = frozenset()) -> dict:
    tops = {top_module(file_dirs(f, stop)) for f in change.files} - {None}
    return {"chg_n_files": len(change.files), "chg_additions": change.additions, "chg_deletions": change.deletions,
            "chg_n_top_modules": len(tops), "has_change_data": change.has_data}


def change_features(test_id: str, change: Change, stop: frozenset[str] = frozenset()) -> dict:
    idx = suffix_index(change.files)
    t_dirs = test_dirs(test_id, stop)
    f_dirs = [file_dirs(f, stop) for f in change.files]
    tops = {top_module(d) for d in f_dirs} - {None}
    t_top = top_module(t_dirs)
    path_tokens = set()
    for f in change.files:
        path_tokens.update(tokenize(f, stop))
    return {
        "test_file_in_diff": any(s in idx for s in test_path_suffixes(test_id)),
        "same_top_module": t_top is not None and t_top in tops,
        "path_prefix_overlap": max((aligned_prefix_overlap(t_dirs, d) for d in f_dirs), default=0.0),
        "name_token_overlap": len(set(tokenize(test_text(test_id), stop)) & path_tokens),
    }


def query_weight(count: int) -> float:
    """Sub-linear weight of a diff token that occurs `count` times (long patches should not drown short ones)."""
    return 1.0 + math.log(count)


def bm25_scores(test_ids: Sequence[str], change: Change, stop: frozenset[str] = frozenset(),
                k1: float = 1.2, b: float = 0.75) -> list[float]:
    """BM25 score of every test in `test_ids` (the run's tests = the corpus) against the change's diff tokens.

    idf(w) = ln(1 + (N - n_w + 0.5) / (n_w + 0.5)); doc term weight tf (k1+1) / (tf + k1 (1 - b + b dl/avgdl));
    each query token w contributes query_weight(count_w). Tokens are summed in sorted order (fixed float order).
    """
    docs = [Counter(tokenize(test_text(t), stop)) for t in test_ids]
    n = len(docs)
    if n == 0:
        return []
    dl = [sum(d.values()) for d in docs]
    avgdl = sum(dl) / n
    df: Counter = Counter()
    for d in docs:
        df.update(d.keys())
    out = []
    for d, L in zip(docs, dl):
        s = 0.0
        if avgdl > 0:
            for w in sorted(d):
                c = change.token_counts.get(w, 0)
                if c <= 0:
                    continue
                idf = math.log(1.0 + (n - df[w] + 0.5) / (df[w] + 0.5))
                tf = d[w]
                s += query_weight(c) * idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * L / avgdl))
        out.append(s)
    return out
