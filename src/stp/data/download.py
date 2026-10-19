"""Idempotent data acquisition: shallow-clone LRTS, download the processed LRTS zip from Google Drive, extract.

Usage:  python -m stp.data.download [--skip-gdrive]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from stp import paths

EXTRACT_MARKER = ".extracted_ok"


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def clone_lrts() -> None:
    if (paths.LRTS_REPO / ".git").exists():
        print(f"[lrts] already cloned at {paths.LRTS_REPO}")
        return
    paths.LRTS_REPO.parent.mkdir(parents=True, exist_ok=True)
    url = paths.config()["sources"]["lrts_git"]
    subprocess.run(["git", "clone", "--depth", "1", url, str(paths.LRTS_REPO)], check=True)


def find_zip() -> Path | None:
    zips = sorted(paths.RAW.glob("*.zip"))
    return zips[0] if zips else None


def download_processed() -> Path:
    paths.RAW.mkdir(parents=True, exist_ok=True)
    existing = find_zip()
    if existing:
        print(f"[gdrive] already downloaded: {existing.name} ({human(existing.stat().st_size)})")
        return existing
    free = shutil.disk_usage(paths.RAW).free
    print(f"[gdrive] free disk space: {human(free)}")
    import gdown  # gdown>=5 takes the id positionally; `--id` was removed

    file_id = paths.config()["sources"]["lrts_gdrive_id"]
    out = gdown.download(id=file_id, output=str(paths.RAW) + "/", quiet=False, resume=True)
    if not out:
        sys.exit("gdown failed. Download manually from "
                 f"{paths.config()['sources']['lrts_gdrive_url']} and put the file in {paths.RAW}")
    out = Path(out)
    print(f"[gdrive] downloaded {out.name}: {human(out.stat().st_size)}")
    return out


def extract(zpath: Path) -> Path:
    dest = paths.RAW / zpath.stem
    if (dest / EXTRACT_MARKER).exists():
        print(f"[extract] already extracted to {dest}")
        return dest
    print(f"[extract] {zpath.name} -> {dest}")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(dest)
    (dest / EXTRACT_MARKER).write_text("ok")
    return dest


def tree_summary(root: Path, depth: int = 3) -> None:
    """Print dirs up to `depth` with recursive file counts and sizes (the prompt asks for depth-3 tree)."""
    stats: dict[Path, list[int]] = {}
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(root)
        size = f.stat().st_size
        for k in range(0, min(depth, len(rel.parts) - 1) + 1):
            key = Path(*rel.parts[:k]) if k else Path(".")
            s = stats.setdefault(key, [0, 0])
            s[0] += 1
            s[1] += size
    for key in sorted(stats, key=lambda p: p.parts):
        n, size = stats[key]
        indent = "  " * len(key.parts)
        print(f"{indent}{key.name or root.name}/  files={n:,}  size={human(size)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-gdrive", action="store_true")
    args = ap.parse_args()
    clone_lrts()
    if args.skip_gdrive:
        return
    dest = extract(download_processed())
    tree_summary(dest, depth=3)


if __name__ == "__main__":
    main()
