"""Tokenisation and path normalisation shared by every change-relatedness feature (LRTS and smartci).

A test id and a changed file are both turned into a normalised *directory path* and a *token bag*:
  test 'org.apache.kafka.streams.kstream.FooTest' -> dirs (streams, kstream)      [project stopword 'kafka']
  test 'tests/python/relay/test_op.py'            -> dirs (relay,)
  file 'streams/src/main/java/org/apache/kafka/streams/kstream/Foo.java' -> dirs (streams, streams, kstream)
Layout-only segments (src, main, test, java, ...), generic tokens (org, apache, util, ...) and the caller's
project-name stopwords are dropped so that test and source trees line up. Nothing else is project-specific.
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


def _keep_dir(d: str, extra_stop: frozenset[str]) -> bool:
    dl = d.lower()
    return bool(dl) and dl not in ROOT_SEGMENTS and dl not in STOPWORDS and dl not in extra_stop


def file_dirs(path: str, extra_stop: frozenset[str] = frozenset()) -> tuple[str, ...]:
    """Normalised directory components of a file path: lowercase, layout-only and generic segments removed."""
    parts = path.replace("\\", "/").split("/")[:-1]
    return tuple(p.lower() for p in parts if _keep_dir(p, extra_stop))


def test_dirs(test_id: str, extra_stop: frozenset[str] = frozenset()) -> tuple[str, ...]:
    """Normalised directory/package components of a test id, via its mapped file path."""
    sufs = test_path_suffixes(test_id)
    return file_dirs(sufs[0], extra_stop) if sufs else ()


def test_text(test_id: str) -> str:
    """Text whose tokens describe a test: its mapped file path without extension, else the raw id."""
    sufs = test_path_suffixes(test_id)
    return sufs[0].rsplit(".", 1)[0] if sufs else test_id


def top_module(dirs: tuple[str, ...]) -> str | None:
    """First normalised directory component (e.g. 'streams' for Kafka Streams, 'relay' for TVM Relay)."""
    return dirs[0] if dirs else None


def aligned_prefix_overlap(t_dirs: tuple[str, ...], f_dirs: tuple[str, ...]) -> float:
    """Longest common prefix between the test's directory path and any suffix of the file's directory path,
    divided by the test path length. Aligning on suffixes lets 'streams/.../streams/kstream' match a test in
    package 'streams.kstream' although the file path starts with a module directory. Value in [0, 1]."""
    if not t_dirs:
        return 0.0
    best = 0
    for s in range(len(f_dirs)):
        n = 0
        for a, b in zip(t_dirs, f_dirs[s:]):
            if a != b:
                break
            n += 1
        best = max(best, n)
    return best / len(t_dirs)


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
