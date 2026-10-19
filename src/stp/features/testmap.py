"""Exact mapping from a test identifier to the source-file path(s) it lives in.

Shared by the LRTS pipeline and smartci. A mapping returns *path suffixes*; a changed file matches a test when
the file path equals a suffix or ends with '/' + suffix (repos differ in their module prefix, e.g. Kafka's
`core/src/test/scala/unit/kafka/...` vs FQN `kafka....`).

  JVM     a.b.C$Inner                       -> a/b/C.java, a/b/C.scala      (inner classes live in the outer file)
  TVM     ctypes.tests.python.x.test_y[p]   -> tests/python/x/test_y.py     (ctypes./cython. = the FFI the suite ran under)
  pytest  tests/test_x.py[::Cls]            -> tests/test_x.py              (smartci: the id already is a path)
Anything else (e.g. TVM shard labels such as 'python-frontend-tensorflow-5-shard-5-cython') maps to nothing.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

_FFI_PREFIX = re.compile(r"^(ctypes|cython)\.")
_JVM_FQN = re.compile(r"^[A-Za-z_][\w]*(\.[A-Za-z_$][\w$]*)+$")
# Kafka/Gradle shard suffixes: 'GetOffsetShellTest15', 'RaftCluster2Test', 'Foo78Test' (used only by the
# documented *fallback* mapping, never by the exact one).
_SHARD_DIGITS = re.compile(r"(?<=[A-Za-z])\d+(?=Test$)|(?<=Test)\d+$")


def test_path_suffixes(test_id: str, fallback: bool = False) -> tuple[str, ...]:
    """Path suffixes for a test id. `fallback=True` also strips Gradle shard digits from JVM class names."""
    t = test_id.split("[", 1)[0].split("::", 1)[0].strip()
    if not t:
        return ()
    if t.endswith(".py") or "/" in t:  # already a file path (pytest node id)
        return (t.replace("\\", "/"),)
    m = _FFI_PREFIX.match(t)
    if m:
        return (t[m.end():].replace(".", "/") + ".py",)
    if not _JVM_FQN.match(t):
        return ()
    outer = t.split("$", 1)[0]
    pkg, _, cls = outer.rpartition(".")
    names = [cls]
    if fallback:
        stripped = _SHARD_DIGITS.sub("", cls)
        if stripped != cls:
            names.append(stripped)
    base = [f"{pkg.replace('.', '/')}/{n}" for n in names]
    return tuple(f"{b}{ext}" for b in base for ext in (".java", ".scala"))


def suffix_index(paths: Iterable[str]) -> set[str]:
    """All '/'-delimited suffixes of the given paths, so `suffix in index` is an O(1) exact-suffix match."""
    idx: set[str] = set()
    for p in paths:
        parts = p.replace("\\", "/").split("/")
        for i in range(len(parts)):
            idx.add("/".join(parts[i:]))
    return idx


def test_file_in_paths(test_id: str, index: set[str], fallback: bool = False) -> bool:
    """True iff one of the test's own source files is among the paths summarised by `index`."""
    return any(s in index for s in test_path_suffixes(test_id, fallback))


def matched_path(test_id: str, paths: Iterable[str], fallback: bool = False) -> str | None:
    """The first path in `paths` that is this test's source file, or None."""
    sufs = test_path_suffixes(test_id, fallback)
    for p in paths:
        q = p.replace("\\", "/")
        if any(q == s or q.endswith("/" + s) for s in sufs):
            return q
    return None
