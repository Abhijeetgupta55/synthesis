"""`smartci backtest [--set mined|mutants|both]`: simulated time to first failure and APFDc for every held-out bug.

Simulation (per bug, per ordering of test files):
  durations   real per-file and per-test durations from `smartci profile` (clean base, mean of the runs)
  order       inside a file, pytest's real collection order; files in the order the method chooses
  failure     the bug's real failing node ids (flaky node ids from the profile are dropped)
  TTFF        summed durations of the files before the first failing file, plus the tests of that file up to and
              including its first failing test (what `pytest -x` would take, without start-up overhead)
  APFDc       file level, uniqueBug over the failing files (stp.evaluation.metrics.apfdc)
Orderings: pytest default, random (20 seeds, averaged), fastest-first, recently-failed-first (only with recorded
failures), changed-files-first (own file in change, then path-prefix / name-token match), coverage-first (only with
a coverage map: tests covering changed lines first), smartci.
Held-out: if an adapter was fitted (`smartci learn`), only the newer 40% of mined bugs; otherwise all mined bugs
(the global model never saw this repo). Mutants are always all held out.
Win / tie / loss of smartci vs each baseline: tie when |ΔTTFF| <= max(0.05 s, 1%).
Output: .smartci/backtest.json, .smartci/backtest.md
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from smartci import coverage_map, history, learn, mutate
from smartci import profile as prof
from smartci.gitdiff import git, parse_unified
from smartci.scoring import GlobalModel, feature_rows, score, stable_order
from stp.evaluation.metrics import apfdc
from stp.features.change import Change
from stp.features.tokens import diff_token_counts

RANDOM_SEEDS = 20


def bug_change(diff_text: str, stop: frozenset[str]) -> tuple[Change, dict[str, str]]:
    recs = parse_unified(diff_text)
    names = [r["path"] for r in recs] + [r["old_path"] for r in recs if r["old_path"]]
    ch = Change(files=sorted({r["path"] for r in recs}), additions=sum(r["added"] for r in recs),
                deletions=sum(r["deleted"] for r in recs),
                token_counts=dict(diff_token_counts(names, [r["patch"] for r in recs], 200_000, stop)))
    return ch, {r["path"]: r["patch"] for r in recs}


class Sim:
    def __init__(self, p: dict):
        self.files = [f for f in p["default_order"] if f not in set(p["flaky"]) | set(p["failing_on_base"])]
        self.dur = {f: p["durations"].get(f, 0.0) for f in self.files}
        self.nodes: dict[str, list[str]] = {}
        for n in p["nodeids"]:
            self.nodes.setdefault(n.split("::", 1)[0], []).append(n)
        self.nd = p["nodeid_durations"]
        self.flaky_nodes = set(p.get("flaky_nodeids", []))

    def ttff(self, order: list[str], failing: set[str]) -> float:
        t = 0.0
        for f in order:
            fails_here = [n for n in self.nodes.get(f, []) if n in failing]
            if not fails_here:
                t += self.dur[f]
                continue
            for n in self.nodes[f]:
                t += self.nd.get(n, 0.0)
                if n in failing:
                    return t
        return float("nan")

    def apfdc(self, order: list[str], failing_files: set[str]) -> float:
        return apfdc([self.dur[f] for f in order], [f in failing_files for f in order])


def github_url(repo: Path) -> str | None:
    u = git(repo, "remote", "get-url", "origin", check=False).strip()
    if "github.com" not in u:
        return None
    u = u.replace("git@github.com:", "https://github.com/").removesuffix(".git")
    return u


def orderings(repo: Path, sim: Sim, change: Change, patches: dict, t: float, model: GlobalModel, cmap,
              hist: history.History) -> dict[str, list[str]]:
    files = sim.files
    pos = {f: i for i, f in enumerate(files)}
    rows = feature_rows(repo, files, change, t, history=hist)
    out = {"default": list(files),
           "fastest_first": sorted(files, key=lambda f: (sim.dur[f], pos[f]))}
    rel = {f: (r["test_file_in_diff"], r["path_prefix_overlap"], r["name_token_overlap"]) for f, r in zip(files, rows)}
    out["changed_files_first"] = sorted(files, key=lambda f: (tuple(-x for x in rel[f]), pos[f]))
    if any(r["h_n_fail"] > 0 for r in rows):
        days = {f: r["h_days_since_last_fail"] for f, r in zip(files, rows)}
        out["recently_failed_first"] = sorted(files, key=lambda f: (days[f], pos[f]))
    cov = None
    if cmap is not None:
        cov = coverage_map.covering_tests(cmap, patches)
        out["coverage_first"] = sorted(files, key=lambda f: (-cov.get(f, 0), pos[f]))
    sc = score(repo, files, change, t=t, model=model, covering=cov)
    out["smartci"] = [sc[i].test_file for i in stable_order(sc)]
    return out


def run(repo: Path, which: str = "both") -> dict:
    repo = Path(repo).resolve()
    p = prof.load(repo)
    sim = Sim(p)
    cmap = coverage_map.load(repo)
    model = GlobalModel()
    hist = history.History(repo)
    stop = frozenset({repo.name.lower().replace("-", "")})
    url = github_url(repo)
    adapter = (history.state_dir(repo) / "adapter.json").exists()
    items = []
    if which in ("mined", "both"):
        bugs = learn.load_bugs(repo)
        held = learn.split_adapt_eval(bugs)[1] if adapter else bugs
        items += [("mined", b["fix_sha"], b["source_diff"], b["failing_nodeids"], float(b["date"]),
                   f"{url}/commit/{b['fix_sha']}" if url else None, b["subject"]) for b in held]
    if which in ("mutants", "both"):
        items += [("mutant", m["mutant_id"], m["diff"], m["failing_nodeids"], None, None,
                   f"{m['operator']} at {m['file']}:{m['line']}") for m in mutate.load_mutants(repo)]
    rows, skipped = [], []
    import time as _t
    for kind, bid, diff, fails, date, link, title in items:
        failing = {n for n in fails if n not in sim.flaky_nodes}
        failing_files = {n.split("::", 1)[0] for n in failing}
        missing = [f for f in failing_files if f not in sim.dur]
        if not failing or missing:
            skipped.append({"id": bid, "kind": kind, "reason": "flaky only" if not failing else
                            f"failing file not in profile: {missing[:3]}"})
            continue
        change, patches = bug_change(diff, stop)
        t = date if date is not None else _t.time()
        ords = orderings(repo, sim, change, patches, t, model, cmap, hist)
        r = {"kind": kind, "id": bid, "url": link, "title": title, "n_failing_tests": len(failing),
             "failing_files": sorted(failing_files), "ttff_s": {}, "apfdc": {}}
        for name, o in ords.items():
            r["ttff_s"][name] = sim.ttff(o, failing)
            r["apfdc"][name] = sim.apfdc(o, failing_files)
        rng = np.random.default_rng(0)
        tt, aa = [], []
        for _ in range(RANDOM_SEEDS):
            o = list(np.array(sim.files)[rng.permutation(len(sim.files))])
            tt.append(sim.ttff(o, failing))
            aa.append(sim.apfdc(o, failing_files))
        r["ttff_s"]["random"], r["apfdc"]["random"] = float(np.mean(tt)), float(np.mean(aa))
        r["smartci_rank_of_first_failing_file"] = min(ords["smartci"].index(f) for f in failing_files) + 1
        rows.append(r)
    res = {"repo": str(repo), "profile_base_sha": p["base_sha"], "suite_test_time_s": p["suite_test_time_s"],
           "n_test_files": len(sim.files), "set": which, "adapter_used": adapter, "bugs": rows, "skipped": skipped,
           "summary": summarise(rows)}
    d = history.state_dir(repo)
    (d / "backtest.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    (d / "backtest.md").write_text(markdown(res), encoding="utf-8")
    return res


def _tie(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.05, 0.01 * max(a, b))


def summarise(rows: list[dict], n_boot: int = 2000) -> dict:
    out = {}
    for kind in sorted({r["kind"] for r in rows}) + ["all"]:
        rr = [r for r in rows if kind == "all" or r["kind"] == kind]
        if not rr:
            continue
        methods = sorted(set.intersection(*[set(r["ttff_s"]) for r in rr]))
        s = {"n": len(rr), "median_ttff_s": {}, "mean_apfdc": {}, "vs_smartci": {}}
        rng = np.random.default_rng(0)
        for m in methods:
            v = np.array([r["ttff_s"][m] for r in rr])
            a = np.array([r["apfdc"][m] for r in rr])
            bs = [np.median(v[rng.integers(0, len(v), len(v))]) for _ in range(n_boot)]
            s["median_ttff_s"][m] = {"median": float(np.median(v)), "lo": float(np.quantile(bs, 0.025)),
                                     "hi": float(np.quantile(bs, 0.975))}
            s["mean_apfdc"][m] = float(a.mean())
        sm = np.array([r["ttff_s"]["smartci"] for r in rr])
        for m in methods:
            if m == "smartci":
                continue
            b = np.array([r["ttff_s"][m] for r in rr])
            ties = np.array([_tie(x, y) for x, y in zip(sm, b)])
            win = (sm < b) & ~ties
            loss = (sm > b) & ~ties
            ratio = np.log((sm + 0.01) / (b + 0.01))
            bs = [np.median(ratio[rng.integers(0, len(ratio), len(ratio))]) for _ in range(n_boot)]
            s["vs_smartci"][m] = {"win": int(win.sum()), "tie": int(ties.sum()), "loss": int(loss.sum()),
                                  "median_time_ratio_smartci_over_baseline": float(np.exp(np.median(ratio))),
                                  "ratio_ci": [float(np.exp(np.quantile(bs, 0.025))), float(np.exp(np.quantile(bs, 0.975)))],
                                  "losses": [r["id"] for r, lo in zip(rr, loss) if lo]}
        base = [m for m in methods if m not in ("smartci", "random")]
        best = min(base, key=lambda m: s["median_ttff_s"][m]["median"]) if base else None
        s["best_simple_baseline"] = best
        s["smartci_beats_best_simple"] = bool(best and s["median_ttff_s"]["smartci"]["hi"] <
                                              s["median_ttff_s"][best]["lo"])
        s["recommendation"] = ("smartci" if s["smartci_beats_best_simple"] else
                               f"smartci does not clearly beat '{best}' here; use {best} (or keep smartci only if "
                               "its median is lower and you accept the uncertainty)")
        out[kind] = s
    return out


def markdown(res: dict) -> str:
    from stp.reports.fmt import table

    lines = [f"# smartci backtest: {Path(res['repo']).name}", "",
             f"Profile base `{res['profile_base_sha'][:10]}`, {res['n_test_files']} test files, "
             f"{res['suite_test_time_s']:.0f} s summed test time. Set: {res['set']}. "
             f"Adapter used: {res['adapter_used']}. Simulated from real measured durations (see `backtest.py`).", ""]
    for kind, s in res["summary"].items():
        lines.append(f"## {kind} (n = {s['n']})")
        lines.append("")
        rows = []
        for m, v in sorted(s["median_ttff_s"].items(), key=lambda kv: kv[1]["median"]):
            w = s["vs_smartci"].get(m)
            rows.append([m, f"{v['median']:.2f} [{v['lo']:.2f}, {v['hi']:.2f}]", f"{s['mean_apfdc'][m]:.3f}",
                         "–" if not w else f"{w['win']}/{w['tie']}/{w['loss']}",
                         "–" if not w else f"{w['median_time_ratio_smartci_over_baseline']:.2f} "
                                           f"[{w['ratio_ci'][0]:.2f}, {w['ratio_ci'][1]:.2f}]"])
        lines.append(table(["Ordering", "Median s to 1st failure [95% CI]", "Mean APFDc",
                            "smartci win/tie/loss", "smartci time ÷ baseline (median) [CI]"], rows))
        lines.append("")
        lines.append(f"Best simple baseline: **{s['best_simple_baseline']}**. Recommendation: {s['recommendation']}.")
        lines.append("")
        losses = s["vs_smartci"].get(s["best_simple_baseline"], {}).get("losses", [])
        if losses:
            lines.append(f"Losses vs {s['best_simple_baseline']} ({len(losses)}): " + ", ".join(losses))
            lines.append("")
    rows = []
    for r in res["bugs"]:
        rows.append([r["kind"], f"[{r['id'][:10]}]({r['url']})" if r.get("url") else r["id"], r["title"][:60],
                     r["n_failing_tests"], f"{r['ttff_s']['default']:.2f}", f"{r['ttff_s']['smartci']:.2f}",
                     r["smartci_rank_of_first_failing_file"]])
    lines += ["## Every bug", "", table(["Kind", "Bug", "Title", "Failing tests", "Default s", "smartci s",
                                         "smartci rank of 1st failing file"], rows), ""]
    if res["skipped"]:
        lines += [f"Skipped ({len(res['skipped'])}): " + "; ".join(f"{s['id']}: {s['reason']}" for s in res["skipped"]), ""]
    return "\n".join(lines)
