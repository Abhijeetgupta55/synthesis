"""GitHub Actions reporting for the three-job comparison (default order, simple rule, model).

    python -m smartci.ci_report job --name default --timing timing_default.json --start S --end E --out default.json
    python -m smartci.ci_report job --name rule    --receipt-dir .smartci/receipts --start S --end E --out rule.json
    python -m smartci.ci_report comment --dir summaries --jobs jobs.json --out comment.md

`job` runs at the end of each job. From the job's own record it takes the first failing test, the queue position of
its test file in the order that job used (out of all test files), the test time until it failed (first test start →
failure, from the pytest plugin), and the pytest step's wall time (launch → exit, start-up included, from the shell
clock). It writes a JSON summary (uploaded as an artifact) and appends a Markdown table to $GITHUB_STEP_SUMMARY.

`comment` runs in a final job after the three. It adds each job's end-to-end time as GitHub records it
(job started_at → completed_at from the Actions API, passed in as jobs.json) and the model's top 10 test files with
P(fail) and reasons (exact LightGBM SHAP contributions recomputed from the receipt's stored features).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from datetime import datetime
from pathlib import Path

LABELS = {"default": "pytest's default order", "rule": "simple rule (changed_files_first)", "model": "smartci model"}


def _latest_receipt(d: str) -> dict:
    files = sorted(glob.glob(os.path.join(d, "*.json")), key=os.path.getmtime)
    if not files:
        raise SystemExit(f"no receipt in {d}")
    return json.loads(Path(files[-1]).read_text(encoding="utf-8"))


def job_summary(name: str, timing: str | None, receipt_dir: str | None, start: float, end: float,
                exit_code: int | None) -> dict:
    if receipt_dir:
        rec = _latest_receipt(receipt_dir)
        order = [x["test_file"] for x in rec.get("ranking", [])]
        ff = rec.get("first_failure") or {}
    else:
        rec = json.loads(Path(timing).read_text(encoding="utf-8")) if timing and Path(timing).exists() else {}
        order = rec.get("order") or []
        ff = rec.get("first_failure") or {}
    f = (ff.get("nodeid") or "").split("::")[0].replace("\\", "/")
    out = {"name": name, "label": LABELS.get(name, name), "first_failure": ff.get("nodeid"),
           "first_failing_file": f or None, "queue_position": order.index(f) + 1 if f in order else None,
           "n_test_files": len(order), "test_s_to_first_failure": ff.get("elapsed_s"),
           "pytest_step_s": round(end - start, 2), "exit_code": exit_code,
           "github": {k: os.environ.get(k) for k in ("GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_SHA",
                                                     "GITHUB_HEAD_REF", "GITHUB_BASE_REF")}}
    if receipt_dir:
        from smartci.explain import top_from_receipt
        out["rule"] = rec.get("rule")
        out["model_variant"] = rec.get("model_variant")
        out["top10"] = top_from_receipt(rec, 10) if not rec.get("rule") else \
            [{"rank": x["rank"], "test_file": x["test_file"], "p_fail": x["p_fail"], "reasons": []}
             for x in rec.get("ranking", [])[:10]]
    return out


def _fmt(x, d=1, unit=" s"):
    return "–" if x is None else f"{x:.{d}f}{unit}"


def job_markdown(s: dict) -> str:
    q = f"{s['queue_position']} of {s['n_test_files']}" if s["queue_position"] else "–"
    lines = [f"### smartci comparison · {s['label']}", "",
             "| first failing test | queue position of its file | test time until it fails | pytest step, launch → exit |",
             "|---|---|---|---|",
             f"| `{s['first_failure'] or 'none'}` | {q} | {_fmt(s['test_s_to_first_failure'], 2)} | "
             f"{_fmt(s['pytest_step_s'])} |", ""]
    if s.get("top10"):
        lines += _top10_md(s["top10"], s.get("first_failing_file"))
    return "\n".join(lines) + "\n"


def _top10_md(top: list[dict], failing: str | None) -> list[str]:
    out = ["| # | test file | P(fail) | reasons |", "|---|---|---|---|"]
    for r in top:
        mark = " ❌" if failing and r["test_file"] == failing else ""
        out.append(f"| {r['rank']} | `{r['test_file']}`{mark} | {r['p_fail']:.3f} | "
                   f"{' · '.join(r.get('reasons') or []) or '–'} |")
    return out + [""]


def _job_seconds(jobs: list[dict]) -> dict[str, dict]:
    f = "%Y-%m-%dT%H:%M:%SZ"
    out = {}
    for j in jobs:
        s, e = j.get("started_at"), j.get("completed_at")
        sec = (datetime.strptime(e, f) - datetime.strptime(s, f)).total_seconds() if s and e else None
        out[j["name"]] = {"seconds": sec, "url": j.get("html_url"), "conclusion": j.get("conclusion")}
    return out


def comment(summary_dir: str, jobs_json: str | None) -> str:
    sums = {}
    for p in sorted(Path(summary_dir).rglob("*.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        if "name" in s and "queue_position" in s:
            sums[s["name"]] = s
    jobs = _job_seconds(json.loads(Path(jobs_json).read_text(encoding="utf-8")).get("jobs", [])) \
        if jobs_json and Path(jobs_json).exists() else {}
    lines = ["## smartci: same commit, three test orders", "",
             "Three parallel jobs ran `pytest -x` (stop at the first failure) on this commit. Times are GitHub's own.",
             "", "| order | first failing test | queue position of its file | test time until it fails | "
             "pytest step (incl. start-up) | whole job, GitHub's clock |", "|---|---|---|---|---|---|"]
    for k in ("default", "rule", "model"):
        s = sums.get(k)
        if not s:
            lines.append(f"| {LABELS[k]} | (no summary) | | | | |")
            continue
        j = next((v for n, v in jobs.items() if n.split(" ")[0] == k), {})
        q = f"{s['queue_position']} of {s['n_test_files']}" if s["queue_position"] else "–"
        lines.append(f"| {s['label']} | `{s['first_failure'] or 'none'}` | {q} | {_fmt(s['test_s_to_first_failure'], 2)} "
                     f"| {_fmt(s['pytest_step_s'])} | " + (f"[{_fmt(j.get('seconds'), 0)}]({j['url']})" if j.get("url")
                                                           else "–") + " |")
    m = sums.get("model")
    if m and m.get("top10"):
        lines += ["", f"**The model's top 10 test files** (model variant `{m.get('model_variant')}`; ❌ = the file "
                  "that failed in this run):", ""] + _top10_md(m["top10"], m.get("first_failing_file"))
    lines += ["Whole job = checkout, Python set-up, installing NetworkX and smartci, and pytest. Queue position is where "
              "the first failing test's file sat in that job's own order. "
              "Generated by `python -m smartci.ci_report`."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("job")
    j.add_argument("--name", required=True, choices=list(LABELS))
    j.add_argument("--timing")
    j.add_argument("--receipt-dir")
    j.add_argument("--start", type=float, required=True)
    j.add_argument("--end", type=float, required=True)
    j.add_argument("--exit-code", type=int)
    j.add_argument("--out", required=True)
    c = sub.add_parser("comment")
    c.add_argument("--dir", required=True)
    c.add_argument("--jobs")
    c.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "job":
        s = job_summary(a.name, a.timing, a.receipt_dir, a.start, a.end, a.exit_code)
        Path(a.out).write_text(json.dumps(s, indent=1), encoding="utf-8")
        md = job_markdown(s)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
                fh.write(md)
        print(md)
    else:
        md = comment(a.dir, a.jobs)
        Path(a.out).write_text(md, encoding="utf-8")
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
                fh.write(md)
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
