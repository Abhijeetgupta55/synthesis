"""Remove machine-specific absolute paths from text before it is committed or bundled.

The repository root becomes `<repo>`, the user's home `<home>` and the temp folder `<tmp>`, in every spelling that
appears in JSON/JSONL/Markdown (backslashes, escaped backslashes, forward slashes; any letter case).
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _variants(p: Path) -> list[str]:
    s = str(p.resolve())
    return sorted({s, s.replace("\\", "\\\\"), s.replace("\\", "/")}, key=len, reverse=True)


def scrub(text: str) -> str:
    for p, token in ((Path(tempfile.gettempdir()), "<tmp>"), (ROOT, "<repo>"), (Path.home(), "<home>")):
        for v in _variants(p):
            text = re.sub(re.escape(v), token.replace("\\", "\\\\"), text, flags=re.IGNORECASE)
    return text


def scrub_file(src: Path, dst: Path | None = None) -> None:
    """Copy src to dst (default: in place) with paths scrubbed; binary files are copied unchanged."""
    dst = dst or src
    data = Path(src).read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        Path(dst).write_bytes(data)
        return
    Path(dst).write_text(scrub(text), encoding="utf-8", newline="")


if __name__ == "__main__":
    import sys
    for f in sys.argv[1:]:
        scrub_file(Path(f))
        print("scrubbed", f)
    _ = os
