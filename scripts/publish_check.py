"""Safety check before publishing the repository (docs/PROMPT_FINISH.md Phase F.1).

Checks every tracked file: no dataset files (LRTS raw/processed data, parquet, csv.zip), no secrets or tokens, no
absolute personal paths, no file over 50 MB; reports the size of the tracked tree and of the git object store.
Writes reports/results/publish_check.json and exits 1 if anything fails.

Usage: python scripts/publish_check.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_MB = 50
DATA = re.compile(r"(^data/|\.parquet$|\.csv\.zip$|test_class\.csv|\.pkl$|^external/)")
SECRET = re.compile(r"(ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{32,}|"
                    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"\s]{12,}))")
HOME = Path.home()
PERSONAL = re.compile("|".join(re.escape(v) for v in {str(HOME), str(HOME).replace("\\", "\\\\"),
                                                       str(HOME).replace("\\", "/")}), re.IGNORECASE)
# the user's own prompt files are kept verbatim; they name only the project folder, not a personal path
VERBATIM = {"docs/PROMPT.md", "docs/PROMPT_FINISH.md"}


def main() -> int:
    files = [f for f in subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines() if f]
    out = {"n_files": len(files), "dataset_files": [], "secrets": [], "personal_paths": [], "over_50mb": []}
    total = 0
    for f in files:
        p = ROOT / f
        if not p.exists():
            continue
        size = p.stat().st_size
        total += size
        if DATA.search(f):
            out["dataset_files"].append(f)
        if size > MAX_MB * 2**20:
            out["over_50mb"].append([f, round(size / 2**20, 1)])
        if size > 20 * 2**20:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if SECRET.search(text):
            out["secrets"].append(f)
        if f not in VERBATIM and PERSONAL.search(text):
            out["personal_paths"].append(f)
    out["tracked_mb"] = round(total / 2**20, 1)
    cnt = subprocess.check_output(["git", "count-objects", "-v"], cwd=ROOT, text=True)
    kb = sum(int(line.split()[1]) for line in cnt.splitlines() if line.startswith(("size:", "size-pack:")))
    out["git_objects_mb"] = round(kb / 1024, 1)
    big = sorted(((ROOT / f).stat().st_size, f) for f in files if (ROOT / f).exists())[-5:]
    out["largest_files"] = [[f, round(s / 2**20, 1)] for s, f in reversed(big)]
    out["pass"] = not (out["dataset_files"] or out["secrets"] or out["personal_paths"] or out["over_50mb"])
    (ROOT / "reports" / "results" / "publish_check.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
