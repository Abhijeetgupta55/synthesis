"""Tokenisation and path normalisation shared by every change-relatedness feature (LRTS and smartci).

A test id and a changed file are both turned into a *directory path* and a *token bag*:
  test 'org.apache.kafka.streams.kstream.FooTest' -> dirs [org, apache, kafka, streams, kstream], name 'FooTest'
  test 'tests/python/relay/test_op.py'            -> dirs [relay] (root segments dropped), name 'test_op'
  file 'streams/src/main/java/org/apache/kafka/streams/kstream/Foo.java'
                                                  -> dirs [streams, org, apache, kafka, streams, kstream], name 'Foo'
Root segments that only encode build layout (src, main, test, java, ...) are dropped so that test and source trees
line up; nothing here is project-specific except the optional extra stopwords a caller passes in.
"""
from __future__ import annotations

import re
from collections import Counter

from stp.features.testmap import test_path_suffixes

# Layout-only directory names, dropped before comparing paths.
ROOT_SEGMENTS = frozenset({
    "src", "main", "test", "tests", "testing", "java", "scala", "python", "py", "unit", "integration", "it",
    "lib", "source", "sources", "resources", "kotlin", "groovy",
})
# Generic tokens with no information about *which* code is involved.
STOPWORDS = frozenset({
    "org", "apache", "com", "net", "io", "src", "main", "test", "tests", "testing", "java", "scala", "python",
    "resources", "impl", "internal", "util", "utils", "common", "core", "the", "and", "for", "with", "api",
    "junit", "jar", "xml", "json", "yaml", "yml", "properties", "txt", "gradle", "pom", "md", "http", "https",
    "init", "py", "cc", "cpp", "h", "hpp", "out", "conftest",
})
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
_SPLIT = re.compile(r"[^A-Za-z0-9]+")


def tokenize(s: str, extra_stop: frozenset[str] = frozenset()) -> list[str]:
    """camelCase / snake_case / path split, lowercase, len >= 3, drop digits and stopwords. Keeps duplicates."""
    out = []
    for part in _SPLIT.split(s):
        for t in _CAMEL.findall(part):
            t = t.lower()
            if len(t) >= 3 and not t.isdigit() and t not in STOPWORDS and t not in extra_stop:
                out.append(t)
    return out


def token_set(s: str, extra_stop: frozenset[str] = frozenset()) -> set[str]:
    return set(tokenize(s, extra_stop))


def file_dirs(path: str) -> list[str]:
    """Directory components of a file path with layout-only segments removed."""
    parts = path.replace("\\", "/").split("/")[:-1]
    return [p for p in parts if p and p.lower() not in ROOT_SEGMENTS]


def test_dirs(test_id: str) -> list[str]:
    """Directory/package components of a test id (via its mapped file path), layout segments removed."""
    sufs = test_path_suffixes(test_id)
    if not sufs:
        return []
    return file_dirs(sufs[0])


def test_name(test_id: str) -> str:
    sufs = test_path_suffixes(test_id)
    if sufs:
        return sufs[0].rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return test_id


def top_module(dirs: list[str], extra_stop: frozenset[str] = frozenset()) -> str | None:
    """First directory component that is not a generic token (org, apache, the project name, ...)."""
    for d in dirs:
        dl = d.lower()
        if dl not in STOPWORDS and dl not in extra_stop and dl not in ROOT_SEGMENTS:
            return dl
    return None


def aligned_prefix_overlap(t_dirs: list[str], f_dirs: list[str]) -> float:
    """Longest common directory prefix of the test path and a file path, normalised by the test path length.

    The file path is aligned at the first occurrence of the test's first component (so a leading module directory
    such as 'streams/' in 'streams/.../org/apache/...' does not break the match); with no occurrence, both paths
    are compared from their start. Returns a value in [0, 1]; 0 if the test has no directory path.
    """
    if not t_dirs:
        return 0.0
    tl = [d.lower() for d in t_dirs]
    fl = [d.lower() for d in f_dirs]
    starts = [i for i, d in enumerate(fl) if d == tl[0]] or [0]
    best = 0
    for s in starts:
        n = 0
        for a, b in zip(tl, fl[s:]):
            if a != b:
                break
            n += 1
        best = max(best, n)
    return best / len(tl)


def diff_token_counts(paths: list[str], patches: list[str | None], max_chars: int = 200_000,
                      extra_stop: frozenset[str] = frozenset()) -> Counter:
    """Token counts of a change: changed paths plus patch text (added/removed lines and context), capped in length."""
    c: Counter = Counter()
    for p in paths:
        c.update(tokenize(p, extra_stop))
    budget = max_chars
    for patch in patches:
        if not patch or budget <= 0:
            continue
        chunk = patch[:budget]
        budget -= len(chunk)
        c.update(tokenize(chunk, extra_stop))
    return c
