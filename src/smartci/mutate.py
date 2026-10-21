"""`smartci mutate --n N --seed S`: seeded single-point mutants as a never-seen-bug benchmark.

Mutation operators (Python `ast`, one node on one line):
  compare   <  <-> >=,  >  <-> <=,  == <-> !=,  is <-> is not,  in <-> not in
  boolop    and <-> or
  arith     +  <-> -
  constant  integer n -> n + 1   (off-by-one)
  return    return x -> return None
  negate    if c: -> if not (c):
Sites are drawn (seeded) only from source lines the suite covers (coverage_map.json). For each mutant, only the
test files that cover the mutated line are run (capped at MAX_COVERING files; sites covered by more are skipped,
since running most of the suite per mutant does not fit the time budget). A mutant is kept iff >= 1 existing test
fails; its diff is the mutation, its kill set the failing node ids.
Caveats: mutants are small and synthetic, and drawing sites from covered lines favours the coverage-first baseline.
Output: .smartci/mutants.jsonl, .smartci/mutate_log.jsonl
"""
from __future__ import annotations

import ast
import json
import random
import time
from pathlib import Path

from smartci import coverage_map, history, runner
from smartci.gitdiff import git

MAX_COVERING = 25
CMP_SWAP = {ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt, ast.Eq: ast.NotEq,
            ast.NotEq: ast.Eq, ast.Is: ast.IsNot, ast.IsNot: ast.Is, ast.In: ast.NotIn, ast.NotIn: ast.In}


def sites(src: str, covered: set[int]) -> list[tuple[int, int, int, int, str]]:
    """(lineno, col, end_lineno, end_col, operator) for every mutable single-line node on a covered line."""
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):            # the if statement spans lines; its *test* must be on one line
            t = node.test
            if t.lineno == t.end_lineno and t.lineno in covered:
                out.append((t.lineno, t.col_offset, t.end_lineno, t.end_col_offset, "negate"))
            continue
        if not hasattr(node, "lineno") or node.lineno != getattr(node, "end_lineno", None):
            continue
        if node.lineno not in covered:
            continue
        pos = (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in CMP_SWAP:
            out.append((*pos, "compare"))
        elif isinstance(node, ast.BoolOp):
            out.append((*pos, "boolop"))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            out.append((*pos, "arith"))
        elif isinstance(node, ast.Constant) and type(node.value) is int:
            out.append((*pos, "constant"))
        elif isinstance(node, ast.Return) and node.value is not None and not (
                isinstance(node.value, ast.Constant) and node.value.value is None):
            out.append((*pos, "return"))
    return sorted(set(out))


def mutate_segment(seg: str, op: str) -> str | None:
    """New source text for the node segment `seg`, or None if it cannot be mutated."""
    try:
        node = ast.parse(seg, mode="eval").body if op != "return" else ast.parse(seg).body[0]
    except SyntaxError:
        return None
    if op == "compare":
        node.ops = [CMP_SWAP[type(node.ops[0])]()]
    elif op == "boolop":
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif op == "arith":
        node.op = ast.Sub() if isinstance(node.op, ast.Add) else ast.Add()
    elif op == "constant":
        node.value = node.value + 1
    elif op == "return":
        return "return None"
    elif op == "negate":
        return f"not ({seg})"
    return ast.unparse(node)


def apply(src: str, site: tuple) -> str | None:
    ln, c0, _, c1, op = site
    lines = src.splitlines(keepends=True)
    line = lines[ln - 1]
    b = line.encode("utf-8")
    seg = b[c0:c1].decode("utf-8")
    new = mutate_segment(seg, op)
    if new is None or new == seg:
        return None
    lines[ln - 1] = (b[:c0].decode("utf-8") + new + b[c1:].decode("utf-8"))
    out = "".join(lines)
    try:
        ast.parse(out)
    except SyntaxError:
        return None
    return out


def generate(repo: Path, n: int = 300, seed: int = 42, timeout: float = 300, python: str | None = None,
             max_attempts: int | None = None) -> dict:
    repo = Path(repo).resolve()
    d = history.smartci_dir(repo)
    cmap = coverage_map.load(repo)
    if cmap is None:
        raise SystemExit("smartci mutate: run `smartci coverage-map` first")
    sha = cmap["base_sha"]
    rng = random.Random(seed)
    pool = []
    for f, lines in sorted(cmap["lines"].items()):
        if not f.endswith(".py"):
            continue
        cov = {int(k): v for k, v in lines.items() if len(v) <= MAX_COVERING}
        if not cov:
            continue
        src = git(repo, "show", f"{sha}:{f}", check=False)
        if not src:
            continue
        try:
            for s in sites(src, set(cov)):
                pool.append((f, s))
        except SyntaxError:
            continue
    rng.shuffle(pool)
    print(f"smartci mutate: {len(pool):,} candidate sites in {len(cmap['lines'])} files; target {n} killed mutants",
          flush=True)
    out_f, log_f = d / "mutants.jsonl", d / "mutate_log.jsonl"
    kept = sum(1 for _ in open(out_f, encoding="utf-8")) if out_f.exists() else 0
    tried = {json.loads(x)["mutant_id"] for f in (out_f, log_f) if f.exists()
             for x in open(f, encoding="utf-8")}
    wt = runner.worktree(repo, "mutate", sha)
    attempts = 0
    try:
        for f, s in pool:
            if kept >= n or (max_attempts and attempts >= max_attempts):
                break
            mid = f"m{seed}-{f.replace('/', '.')}-{s[0]}-{s[1]}-{s[4]}"
            if mid in tried:
                continue
            attempts += 1
            src = (wt / f).read_text(encoding="utf-8")
            new = apply(src, s)
            if new is None:
                continue
            tests = sorted({cmap["tests"][i] for i in cmap["lines"][f][str(s[0])]})
            (wt / f).write_text(new, encoding="utf-8")
            diff = git(wt, "diff", "--no-color", "HEAD", "--", f)
            junit = d / "mutants" / f"{mid}.xml"
            t0 = time.time()
            r = runner.run_pytest(wt, ["-q", *tests], junit=junit, timeout=timeout, python=python)
            runner.reset_worktree(wt, sha)
            cases = history.junit_cases(junit) if junit.exists() else []
            kills = [c["nodeid"] for c in cases if c["failed"] and c["kind"] == "test"]
            rec = {"mutant_id": mid, "file": f, "line": s[0], "operator": s[4], "seed": seed, "base_sha": sha,
                   "covering_test_files": tests, "seconds": time.time() - t0}
            if r.timed_out:
                rec.update(status="excluded", reason="timeout")
            elif not kills:
                rec.update(status="excluded", reason="survived" if r.returncode in (0, 5) else "error")
            else:
                rec.update(status="kept", diff=diff, failing_nodeids=kills,
                           failing_files=sorted({k.split("::", 1)[0] for k in kills}))
                kept += 1
            with open(out_f if rec["status"] == "kept" else log_f, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
            print(f"  [{kept}/{n}] {mid}: {rec['status']} {rec.get('reason', '')} ({rec['seconds']:.0f}s)", flush=True)
    finally:
        runner.remove_worktree(repo, wt)
    return {"kept": kept, "attempts_this_call": attempts, "candidate_sites": len(pool)}


def load_mutants(repo: Path) -> list[dict]:
    f = history.state_dir(repo) / "mutants.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []
