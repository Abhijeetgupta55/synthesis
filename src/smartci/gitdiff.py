"""The change under test: `git diff <base>...HEAD` plus uncommitted working-tree changes.

Returns a `stp.features.change.Change`: changed paths (renames give the new path; the old path is added to the
token bag), line counts, and diff-token counts from paths + patch text. Binary files contribute their path only.
Huge diffs are capped (MAX_FILES files, MAX_PATCH_CHARS characters of patch text), mirroring the LRTS pipeline.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from stp.features.change import Change
from stp.features.tokens import diff_token_counts

MAX_FILES = 300
MAX_PATCH_CHARS = 200_000


def git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def default_base(repo: Path) -> str:
    """origin/HEAD's branch if known, else main/master, else HEAD~1."""
    for ref in ("origin/HEAD", "origin/main", "origin/master", "main", "master"):
        if git(repo, "rev-parse", "--verify", "--quiet", ref, check=False).strip():
            return ref
    return "HEAD~1"


@dataclass
class DiffResult:
    change: Change
    base_sha: str
    head_sha: str
    diff_hash: str
    truncated: bool
    patch_by_file: dict[str, str]


_HDR = re.compile(r"^diff --git a/(.*?) b/(.*?)$", re.M)


def parse_unified(text: str) -> list[dict]:
    """Split `git diff` output into per-file records: path, old_path, added, deleted, binary, patch."""
    files = []
    starts = [m.start() for m in _HDR.finditer(text)] + [len(text)]
    for a, b in zip(starts, starts[1:]):
        block = text[a:b]
        m = _HDR.match(block)
        old, new = m.group(1), m.group(2)
        rn_from = re.search(r"^rename from (.*)$", block, re.M)
        rn_to = re.search(r"^rename to (.*)$", block, re.M)
        if rn_from and rn_to:
            old, new = rn_from.group(1), rn_to.group(1)
        deleted = re.search(r"^deleted file mode", block, re.M) is not None
        binary = re.search(r"^Binary files .* differ$", block, re.M) is not None or "GIT binary patch" in block
        hunk = block.find("\n@@")
        patch = block[hunk + 1:] if hunk >= 0 else ""
        add = sum(1 for ln in patch.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
        dele = sum(1 for ln in patch.splitlines() if ln.startswith("-") and not ln.startswith("---"))
        path = old if deleted else new
        files.append({"path": path, "old_path": old if old != new else None, "added": add, "deleted": dele,
                      "binary": binary, "patch": "" if binary else patch})
    return files


def compute(repo: Path, base: str | None = None, include_worktree: bool = True,
            extra_stop: frozenset[str] = frozenset()) -> DiffResult:
    repo = Path(repo)
    base = base or default_base(repo)
    head_sha = git(repo, "rev-parse", "HEAD").strip()
    base_sha = git(repo, "rev-parse", base).strip()
    merge_base = git(repo, "merge-base", base_sha, head_sha, check=False).strip() or base_sha
    text = git(repo, "diff", "-M", "--no-color", f"{merge_base}...{head_sha}")
    if include_worktree:
        # staged + unstaged vs HEAD (untracked files are listed by path only)
        text += git(repo, "diff", "-M", "--no-color", "HEAD")
        untracked = git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    else:
        untracked = []
    recs: dict[str, dict] = {}
    for f in parse_unified(text):
        if f["path"] in recs:   # same file changed in commits and in the working tree: merge
            r = recs[f["path"]]
            r["added"] += f["added"]
            r["deleted"] += f["deleted"]
            r["patch"] += f["patch"]
        else:
            recs[f["path"]] = f
    for u in untracked:
        recs.setdefault(u, {"path": u, "old_path": None, "added": 0, "deleted": 0, "binary": False, "patch": ""})
    truncated = len(recs) > MAX_FILES
    items = list(recs.values())[:MAX_FILES]
    names = [r["path"] for r in items] + [r["old_path"] for r in items if r["old_path"]]
    patches = [r["patch"] for r in items]
    counts = diff_token_counts(names, patches, MAX_PATCH_CHARS, extra_stop)
    change = Change(files=sorted({r["path"] for r in items}), additions=sum(r["added"] for r in items),
                    deletions=sum(r["deleted"] for r in items), token_counts=dict(counts), has_data=True)
    h = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]
    return DiffResult(change, base_sha, head_sha, h, truncated, {r["path"]: r["patch"] for r in items})


def changed_lines(patch: str) -> set[int]:
    """New-side line numbers touched by a patch (added lines, plus the line after a pure deletion)."""
    out: set[int] = set()
    new_ln = 0
    for ln in patch.splitlines():
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", ln)
        if m:
            new_ln = int(m.group(1))
            continue
        if ln.startswith("+") and not ln.startswith("+++"):
            out.add(new_ln)
            new_ln += 1
        elif ln.startswith("-") and not ln.startswith("---"):
            out.add(new_ln)
        else:
            new_ln += 1
    return out
