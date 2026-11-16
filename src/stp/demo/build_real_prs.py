"""Build demo_bundle/real_prs/: replays of real, held-out Apache builds of Kafka and TVM for the 'Real PRs' page.

These two projects are where the stacked model beats the best simple rule on the test split (models.json →
vs_best_simple → All → kafka / tvm → stack). For a seeded sample of their held-out failed builds, each record has:
  - the build: Apache PR link, changed files (from the PR's diff), number of tests, total test time
  - every test class once (`names`), its real duration and real outcome in that build
  - four orders as indices into `names`: random, fastest first (QTF), the best simple rule (ChangedOrNewFirst,
    chosen on validation) and the model (stacking); per order the position of the first failing test, test
    minutes before it, test minutes until it fails, approximate wall-clock minutes, and APFDc
  - the model's top 10 tests with P(fail) and the three largest reasons (LightGBM SHAP; LightGBM is a member of
    the stack), marking the ones that really failed
  - outcome vs the best simple rule: win / tie / loss (|ΔAPFDc| < 0.001 is a tie)
Tie-breaks follow the evaluation harness (seed [11, 0, run_idx]), so the stacked model's APFDc here equals the
stored per-run value in data/processed/eval/models_runs (checked at build time).
`python -m stp.demo.verify --bundle real_prs ...` recomputes every number from the raw LRTS csv.zip.

Also writes reports/results/real_prs_wins.json: over *all* held-out Kafka/TVM failed builds, what kind of failures
the model's wins and losses contain (recurring, known-flaky, first-time).

Usage: python -m stp.demo.build_real_prs [--per-project 40] [--seed 11]
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from stp import paths
from stp.baselines import heuristics as H
from stp.demo.build_bundle import GITHUB
from stp.evaluation.harness import EVAL_COLS, eval_runs, iter_runs, jira_flaky_ids
from stp.evaluation.metrics import DURATION_EPS
from stp.features.store import store_dir
from stp.models.common import load_model
from stp.models.evaluate import model_methods
from stp.results import load_result, save_result

OUT = paths.ROOT / "demo_bundle" / "real_prs"
PROJECTS = ("kafka", "tvm")
TIE = 0.001
ORDERS = {"random": "Random order", "fastest_first": "Fastest first (QTF)",
          "best_rule": "Best simple rule (changed or new first)", "model": "Model (stacking)"}


def metrics(order: np.ndarray, dur: np.ndarray, fail: np.ndarray, factor: float) -> dict:
    d = dur[order] + DURATION_EPS
    f = fail[order]
    pos = np.flatnonzero(f)
    total = d.sum()
    suffix = np.cumsum(d[::-1])[::-1]
    first = int(pos[0])
    before = float(d[:first].sum())
    until = float(d[: first + 1].sum())
    return {"order": order.tolist(), "first_fail_position": first + 1,
            "test_min_before": before / 60, "test_min_until": until / 60, "wall_min_approx": until * factor / 60,
            "ttff_s": until, "apfdc": float((suffix[pos] - d[pos] / 2).sum() / (len(pos) * total))}


def changed_files(p: str) -> tuple[pd.Series, pd.DataFrame]:
    files = pd.read_parquet(paths.PROCESSED / "diffs" / f"project={p}" / "files.parquet",
                            columns=["change_idx", "filename"])
    return files.groupby("change_idx").filename.apply(list), files


def reasons_for(booster, cols, d: dict, idx: np.ndarray, change: list[str]) -> list[list[str]]:
    from smartci.explain import sentence
    X = np.column_stack([np.asarray(d[c], dtype=np.float64)[idx] for c in cols]).astype(np.float32)
    contrib = booster.predict(X, pred_contrib=True)
    out = []
    for k, i in enumerate(idx):
        feats = {c: float(np.asarray(d[c])[i]) for c in cols}
        top = sorted(((c, v) for c, v in zip(cols, contrib[k][:-1]) if v > 0), key=lambda cv: -cv[1])
        rs = []
        for c, _ in top:
            s = sentence(c, feats, change)
            if s and s not in rs:
                rs.append(s)
            if len(rs) == 3:
                break
        out.append(rs or ["No strong signal; ranked by low cost."])
    return out


def build(per_project: int, seed: int) -> list[dict]:
    methods, cols = model_methods()
    cal = load_model("cal_lgbm")
    booster, lcols = cal.entry["model"], cal.entry["cols"]
    factor = load_result("baselines")["wallclock_factor"]
    stored = pd.concat([pd.read_parquet(paths.PROCESSED / "eval" / "models_runs" / f"main_{p}.parquet")
                        for p in PROJECTS])
    stored = stored[(stored.method == "stack") & (stored.subset == "All")].set_index(["project", "run_idx"]).apfdc
    need = sorted(set(cols) | set(H.COLUMNS) | set(EVAL_COLS) | set(lcols))
    index, checks = [], []
    for p in PROJECTS:
        runs = eval_runs(p, ("test",))
        pick = runs.iloc[np.sort(np.random.default_rng(seed).choice(len(runs), min(per_project, len(runs)),
                                                                    replace=False))]
        meta = pick.set_index("run_idx")
        tests = pd.read_parquet(store_dir(p) / "tests.parquet").set_index("test_id").testclass
        chg, _ = changed_files(p)
        (OUT / p).mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        for ri, d in iter_runs(p, set(pick.run_idx.tolist()), need):
            m = meta.loc[ri]
            dur = d["y_duration_s"].astype(np.float64)
            fail = d["y_fail"].astype(bool)
            n = len(dur)
            prio = {}
            rng = np.random.default_rng([11, 0, ri])                 # the harness's seed for this run
            pm = methods["stack"](d, rng)
            om = np.lexsort((rng.random(n), pm))
            r2 = np.random.default_rng([seed, ri])
            prio["random"] = np.lexsort((r2.random(n), H.random(d, r2)))
            prio["fastest_first"] = np.lexsort((r2.random(n), H.qtf(d, r2)))
            prio["best_rule"] = np.lexsort((r2.random(n), H.changed_or_new_first(d, r2)))
            prio["model"] = om
            res = {k: metrics(o, dur, fail, factor[p]) for k, o in prio.items()}
            checks.append(abs(res["model"]["apfdc"] - float(stored.loc[(p, ri)])))
            files = chg.get(int(m.change_idx), []) if pd.notna(m.change_idx) else []
            top = om[:10]
            reasons = reasons_for(booster, lcols, d, top, files)
            diff = res["model"]["apfdc"] - res["best_rule"]["apfdc"]
            outcome = "win" if diff > TIE else "loss" if diff < -TIE else "tie"
            names = tests.loc[d["test_id"]].tolist()
            pr = m.pr_name
            rec = {"project": p, "pr_name": pr, "build_id": int(m.build_id), "stage_id": m.stage_id, "run_idx": int(ri),
                   "start": pd.to_datetime(m.start_ts, unit="s").strftime("%Y-%m-%d %H:%M"),
                   "pr_url": f"https://github.com/{GITHUB[p]}/pull/{pr.split('-')[-1]}" if pr.startswith("PR-") else None,
                   "changed_files": files[:60], "n_changed_files": len(files),
                   "n_tests": n, "n_fail": int(fail.sum()), "suite_min": float((dur + DURATION_EPS).sum() / 60),
                   "wallclock_factor": factor[p], "names": names, "duration_s": dur.round(4).tolist(),
                   "fail": fail.astype(int).tolist(), "orders": res,
                   "methods": {ORDERS[k]: {"order": v["order"], "apfdc": v["apfdc"], "ttff_s": v["ttff_s"]}
                               for k, v in res.items()},
                   "model_top10": [{"test": names[i], "failed": bool(fail[i]), "reasons": rs}
                                   for i, rs in zip(top.tolist(), reasons)],
                   "delta_vs_best_rule": diff, "outcome": outcome}
            fname = f"{pr}_{int(m.build_id)}_{m.stage_id}.json".replace("/", "_")
            (OUT / p / fname).write_text(json.dumps(rec), encoding="utf-8")
            index.append({k: rec[k] for k in ("project", "pr_name", "build_id", "stage_id", "start", "n_tests",
                                              "n_fail", "suite_min", "outcome", "delta_vs_best_rule")}
                         | {"file": f"real_prs/{p}/{fname}"})
        print(f"  [real_prs] {p}: {len(pick)} builds in {time.time() - t0:.0f}s", flush=True)
    print(f"  [real_prs] stacked-model APFDc vs stored per-run value: max |diff| {max(checks):.2e}")
    (OUT / "index.json").write_text(json.dumps(index, indent=0), encoding="utf-8")
    return index


def wins_analysis() -> dict:
    """Over all held-out failed builds of Kafka and TVM: which failures do the model's wins and losses contain?"""
    mr = pd.concat([pd.read_parquet(paths.PROCESSED / "eval" / "models_runs" / f"main_{p}.parquet") for p in PROJECTS])
    br = pd.concat([pd.read_parquet(paths.PROCESSED / "eval" / "baselines_runs" / f"{p}.parquet") for p in PROJECTS])
    key = ["project", "run_idx"]
    a = mr[(mr.method == "stack") & (mr.subset == "All") & (mr.split == "test")][key + ["apfdc"]]
    b = br[(br.method == "ChangedOrNewFirst") & (br.subset == "All") & (br.split == "test")][key + ["apfdc"]]
    x = a.merge(b, on=key, suffixes=("_m", "_r"))
    x["outcome"] = np.where(x.apfdc_m - x.apfdc_r > TIE, "win", np.where(x.apfdc_m - x.apfdc_r < -TIE, "loss", "tie"))
    rows = []
    for p in PROJECTS:
        runs = set(x[x.project == p].run_idx.tolist())
        t = ds.dataset(sorted(str(f) for f in store_dir(p).glob("part-*.parquet")), format="parquet").to_table(
            filter=(ds.field("y_fail") == True) & ds.field("run_idx").isin(list(runs)),  # noqa: E712
            columns=["run_idx", "test_id", "h_n_fail", "h_n_transitions", "h_n_runs_seen", "y_ftf_asof"]).to_pandas()
        tests = pd.read_parquet(store_dir(p) / "tests.parquet")
        flaky = jira_flaky_ids(p, tests)
        t["project"] = p
        t["known_flaky"] = t.test_id.map(lambda i: int(i) in flaky)
        t["recurring"] = t.h_n_fail > 0
        t["first_time"] = t.y_ftf_asof.astype(bool)
        t["flip_rate"] = t.h_n_transitions / t.h_n_runs_seen.clip(lower=1)
        rows.append(t)
    f = pd.concat(rows).merge(x[key + ["outcome"]], on=key)
    f["unstable"] = f.flip_rate > 0.2
    out = {"definition": {
        "outcome": "per held-out failed build: stacked model vs ChangedOrNewFirst APFDc (stored harness values), "
                   f"tie if |diff| < {TIE}",
        "recurring": "the failing test had failed before in a finished earlier run (h_n_fail > 0)",
        "first_time": "the failing test had never failed before (as-of)",
        "known_flaky": "the test class is on the LRTS JIRA flaky list (any date)",
        "unstable": "the test flipped between pass and fail in more than 20% of its earlier runs"},
        "projects": {}}
    for p, g in f.groupby("project"):
        res = {}
        for o, h in g.groupby("outcome"):
            res[o] = {"n_builds": int(h.run_idx.nunique()), "n_failing_tests": int(len(h)),
                      "share_recurring": float(h.recurring.mean()), "share_first_time": float(h.first_time.mean()),
                      "share_known_flaky": float(h.known_flaky.mean()), "share_unstable": float(h.unstable.mean()),
                      "share_recurring_not_flaky_not_unstable": float((h.recurring & ~h.known_flaky
                                                                       & ~h.unstable).mean())}
        out["projects"][p] = res
    save_result("real_prs_wins", out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-project", type=int, default=40)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--skip-build", action="store_true")
    a = ap.parse_args()
    w = wins_analysis()
    for p, r in w["projects"].items():
        for o, v in r.items():
            print(f"  {p} {o:4s} builds {v['n_builds']:5d}: recurring {v['share_recurring']:.0%}, first-time "
                  f"{v['share_first_time']:.0%}, known flaky {v['share_known_flaky']:.0%}, unstable "
                  f"{v['share_unstable']:.0%}")
    if not a.skip_build:
        idx = build(a.per_project, a.seed)
        print(f"demo_bundle/real_prs: {len(idx)} builds; outcomes "
              f"{pd.Series([i['outcome'] for i in idx]).value_counts().to_dict()}")


if __name__ == "__main__":
    main()
