"""Small formatting helpers for generated markdown."""
from __future__ import annotations


def f3(x) -> str:
    return "–" if x is None else f"{x:.3f}"


def pct(x, d: int = 1) -> str:
    return "–" if x is None else f"{100 * x:.{d}f}%"


def sgn(x, d: int = 3) -> str:
    return "–" if x is None else f"{x:+.{d}f}"


def ci(c: dict, d: int = 3) -> str:
    """'0.812 [0.80, 0.82]' from a macro_ci dict; marks small samples with '†'."""
    if not c or c.get("mean") is None:
        return "–"
    s = f"{c['mean']:.{d}f} [{c['lo']:.{d}f}, {c['hi']:.{d}f}]"
    return s + (" †" if c.get("small_n") else "")


def diff_ci(c: dict, d: int = 3) -> str:
    if not c or c.get("mean") is None:
        return "–"
    s = f"{c['mean']:+.{d}f} [{c['lo']:+.{d}f}, {c['hi']:+.{d}f}]"
    return s + (" *" if c.get("excludes_zero") else "")


def table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)
