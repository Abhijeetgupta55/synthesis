"""Build demo_bundle/ (< 100 MB): everything the Streamlit demo shows, precomputed *only* for the LRTS study.

  demo_bundle/lrts/<project>/<pr>_<build>_<stage>.json   one held-out failed test-split run: test class names
        once ("names"), their durations and outcomes, and per method the real ordering (indices into "names"),
        APFDc and time to first failure; the model's top
        SHAP reasons for its first 10 tests; the Apache PR link. `python -m stp.demo.verify` recomputes these numbers
        from the raw LRTS csv.zip.
  demo_bundle/lrts/index.json                            list of bundled runs (seeded stratified sample)
  demo_bundle/scoreboard.json                            copies of baselines / models / classification / leakage
                                                         / transfer / gate results (numbers shown on the Scoreboard)
  demo_bundle/repos/<name>/backtest.json, backtest.md, profile.json, bugs.jsonl, mutants.jsonl
                                                         copies of the smartci outputs of the real repos
  demo_bundle/results/*.json, results/eda/*.json         copies of reports/results and reports/eda_json
  demo_bundle/figures/*.png                              copies of reports/figures
  demo_bundle/live/networkx/.smartci/, live_meta.json    inputs of the 'Predict live' page (same files smartci reads)
Repos the *user* picks are never precomputed: the app reads their .smartci/ folder directly.
Usage: python -m stp.demo.build_bundle [--per-project 30] [--seed 7] [--parts scoreboard,results,figures,repos,live]
"""
from __future__ import annotations

import argparse
import json
import shutil
import time

import numpy as np
import pandas as pd

from stp import paths
from stp.baselines import heuristics as H
from stp.evaluation.harness import EVAL_COLS, iter_runs
from stp.evaluation.metrics import DURATION_EPS
from stp.features.store import store_dir
from stp.models.common import load_model
from stp.results import git_sha, load_result

OUT = paths.ROOT / "demo_bundle"
METHODS = ["Random", "QTF", "cbt_LastFail", "ChangedOrNewFirst", "smartci (LightGBM)", "Oracle"]
GITHUB = {"activemq": "apache/activemq", "hadoop": "apache/hadoop", "hbase": "apache/hbase", "hive": "apache/hive",
          "jackrabbit-oak": "apache/jackrabbit-oak", "james": "apache/james-project", "kafka": "apache/kafka",
          "karaf": "apache/karaf", "log4j": "apache/logging-log4j2", "tvm": "apache/tvm"}
REPOS = {"networkx": paths.ROOT / "external" / "networkx"}  # a second repo (sympy) was attempted, not completed


def _metrics(order: np.ndarray, dur: np.ndarray, fail: np.ndarray) -> tuple[float, float]:
    d = dur[order] + DURATION_EPS
    f = fail[order]
    total = d.sum()
    suffix = np.cumsum(d[::-1])[::-1]
    pos = np.flatnonzero(f)
    return float((suffix[pos] - d[pos] / 2).sum() / (len(pos) * total)), float(d[: pos[0] + 1].sum())


def build_lrts(per_project: int, seed: int) -> list[dict]:
    model = load_model("var_tr_all_to_tvm")
    import lightgbm as lgb
    booster = model.booster if hasattr(model, "booster") else None
    cols = sorted(set(model.cols) | set(H.COLUMNS) | set(EVAL_COLS))
    rng = np.random.default_rng(seed)
    index = []
    for p in paths.PROJECTS:
        runs = pd.read_parquet(store_dir(p) / "runs.parquet")
        runs = runs[(runs.split == "test") & runs.failed]
        if runs.empty:
            continue
        pick = runs.iloc[np.sort(rng.choice(len(runs), min(per_project, len(runs)), replace=False))]
        tests = pd.read_parquet(store_dir(p) / "tests.parquet").set_index("test_id").testclass
        meta = pick.set_index("run_idx")
        d_out = OUT / "lrts" / p
        d_out.mkdir(parents=True, exist_ok=True)
        for ri, d in iter_runs(p, set(pick.run_idx.tolist()), cols):
            m = meta.loc[ri]
            dur = d["y_duration_s"].astype(np.float64)
            fail = d["y_fail"].astype(bool)
            names = tests.loc[d["test_id"]].tolist()
            r = np.random.default_rng([seed, ri])
            prio = {"Random": H.random(d, r), "QTF": H.qtf(d, r), "cbt_LastFail": H.cbt_lastfail(d, r),
                    "ChangedOrNewFirst": H.changed_or_new_first(d, r), "Oracle": H.oracle(d, r)}
            p_fail = model.predict(d)
            prio["smartci (LightGBM)"] = -(p_fail / (d["dur_ema_asof"].astype(np.float64) + 1e-3))
            methods = {}
            for name in METHODS:
                order = np.lexsort((r.random(len(dur)), prio[name]))
                a, t = _metrics(order, dur, fail)
                methods[name] = {"order": order.tolist(), "apfdc": a, "ttff_s": t}   # indices into "names"
            top = np.argsort(prio["smartci (LightGBM)"], kind="stable")[:10]
            from stp.models.prep import matrix
            contrib = booster.predict(matrix({c: d[c][top] for c in model.cols}, model.cols), pred_contrib=True,
                                      num_iteration=model.best_iteration) if booster is not None else None
            reasons = []
            for k, i in enumerate(top):
                cc = sorted(zip(model.cols, contrib[k][:-1]), key=lambda t: -abs(t[1]))[:3] if contrib is not None else []
                reasons.append({"test": names[i], "p_fail": float(p_fail[i]),
                                "top": [{"feature": f, "shap": float(v), "value": float(d[f][i])} for f, v in cc]})
            pr = str(m.pr_name)
            rec = {"project": p, "pr_name": pr, "build_id": int(m.build_id), "stage_id": str(m.stage_id),
                   "start": pd.to_datetime(m.start_ts, unit="s").strftime("%Y-%m-%d %H:%M"),
                   "pr_url": f"https://github.com/{GITHUB[p]}/pull/{pr.split('-')[-1]}" if pr.startswith("PR-") else None,
                   "names": names, "duration_s": [round(float(x), 4) for x in dur], "fail": [int(y) for y in fail],
                   "n_tests": len(names), "n_fail": int(fail.sum()), "suite_s": float(dur.sum()),
                   "methods": methods, "smartci_reasons": reasons}
            fname = f"{pr}_{int(m.build_id)}_{m.stage_id}.json".replace("/", "_")
            (d_out / fname).write_text(json.dumps(rec), encoding="utf-8")
            index.append({k: rec[k] for k in ("project", "pr_name", "build_id", "stage_id", "start", "n_tests",
                                              "n_fail", "suite_s")} | {"file": f"lrts/{p}/{fname}"})
        print(f"  [bundle] {p}: {len(pick)} runs", flush=True)
        _ = lgb
    (OUT / "lrts" / "index.json").write_text(json.dumps(index, indent=0), encoding="utf-8")
    return index


def build_scoreboard() -> None:
    names = ["baselines", "models", "models_classification", "leakage_bruteforce", "leakage_signal", "transfer",
             "gate2_reproduction", "phase0_facts", "labels", "ablations", "interpret", "rolling_origin_baselines"]
    sb = {}
    for n in names:
        if (paths.RESULTS / f"{n}.json").exists():
            sb[n] = load_result(n)
    for big in ("models_classification",):
        if big in sb:
            sb[big].pop("reliability", None)
    (OUT / "scoreboard.json").write_text(json.dumps(sb, default=float), encoding="utf-8")


def copy_repos() -> None:
    for name, repo in REPOS.items():
        src = repo / ".smartci"
        if not src.exists():
            continue
        dst = OUT / "repos" / name
        dst.mkdir(parents=True, exist_ok=True)
        for f in ("backtest.json", "backtest.md", "profile.json", "bugs.jsonl", "mutants.jsonl", "learn_summary.json"):
            if (src / f).exists():
                shutil.copyfile(src / f, dst / f)
        cmp_dir = src / "compare"
        if cmp_dir.exists():
            (dst / "compare").mkdir(exist_ok=True)
            for f in cmp_dir.glob("*.json"):
                shutil.copyfile(f, dst / "compare" / f.name)


def copy_results() -> None:
    """Every results JSON and EDA JSON (all small), so each app page reads its numbers from the source file."""
    dst = OUT / "results"
    dst.mkdir(parents=True, exist_ok=True)
    for f in paths.RESULTS.glob("*.json"):
        shutil.copyfile(f, dst / f.name)
    (dst / "eda").mkdir(exist_ok=True)
    for f in (paths.ROOT / "reports" / "eda_json").glob("*.json"):
        shutil.copyfile(f, dst / "eda" / f.name)


def copy_figures() -> None:
    dst = OUT / "figures"
    dst.mkdir(parents=True, exist_ok=True)
    for f in (paths.ROOT / "reports" / "figures").glob("*.png"):
        shutil.copyfile(f, dst / f.name)


def build_live() -> None:
    """Inputs for the app's 'Predict live' page: a copy of NetworkX's smartci state (the same files `smartci rank
    --files` reads), the list of NetworkX source files to pick from, and the as-of time used for history."""
    repo = REPOS["networkx"]
    src = repo / ".smartci"
    dst = OUT / "live" / "networkx" / ".smartci"
    dst.mkdir(parents=True, exist_ok=True)
    prof = json.loads((src / "profile.json").read_text(encoding="utf-8"))
    keep = {k: prof[k] for k in ("base_sha", "created", "durations", "default_order", "suite_test_time_s")}
    (dst / "profile.json").write_text(json.dumps(keep), encoding="utf-8")
    for f in ("history.jsonl", "runs.jsonl", "adapter.json", "coverage_map.json", "bugs.jsonl"):
        if (src / f).exists():
            shutil.copyfile(src / f, dst / f)
    import subprocess
    files = subprocess.check_output(["git", "-C", str(repo), "ls-files", "networkx/*.py"], text=True).split()
    sources = sorted(f for f in files if "/tests/" not in f and not f.endswith(("__init__.py", "conftest.py")))
    runs = [json.loads(x) for x in (src / "runs.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    as_of = max((r["end_ts"] for r in runs), default=time.time()) + 1.0
    (OUT / "live" / "networkx" / "live_meta.json").write_text(json.dumps(
        {"sources": sources, "as_of": as_of, "base_sha": prof["base_sha"],
         "note": "history is scored as of `as_of` (just after the last recorded run), so results are reproducible"}),
        encoding="utf-8")


PARTS = ("lrts", "scoreboard", "results", "figures", "repos", "live")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-project", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--parts", default=",".join(PARTS), help="rebuild only these parts (others are kept)")
    a = ap.parse_args()
    parts = a.parts.split(",")
    OUT.mkdir(exist_ok=True)
    old = json.loads((OUT / "meta.json").read_text(encoding="utf-8")) if (OUT / "meta.json").exists() else {}
    for part, d in (("lrts", "lrts"), ("results", "results"), ("figures", "figures"), ("repos", "repos"),
                    ("live", "live")):
        if part in parts and (OUT / d).exists():
            shutil.rmtree(OUT / d)
    n_lrts = old.get("n_lrts_runs")
    if "lrts" in parts:
        n_lrts = len(build_lrts(a.per_project, a.seed))
    if "scoreboard" in parts:
        build_scoreboard()
    if "results" in parts:
        copy_results()
    if "figures" in parts:
        copy_figures()
    if "repos" in parts:
        copy_repos()
    if "live" in parts:
        build_live()
    meta = {"git_sha": git_sha(), "generated": time.strftime("%Y-%m-%d %H:%M:%S"), "seed": a.seed,
            "per_project": a.per_project, "n_lrts_runs": n_lrts,
            "lrts_generated": time.strftime("%Y-%m-%d %H:%M:%S") if "lrts" in parts else old.get("lrts_generated",
                                                                                                old.get("generated"))}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    files = [f for f in OUT.rglob("*") if f.is_file()]
    size = sum(f.stat().st_size for f in files)
    big = max(files, key=lambda f: f.stat().st_size)
    print(f"demo_bundle: {n_lrts} LRTS runs, {size / 1e6:.1f} MB, largest file {big.name} {big.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
