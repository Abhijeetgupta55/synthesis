"""Brute-force recomputation of a run's features from the interim/raw tables, using only the pure reference
functions (history.py, change.py, cofail.py). It never touches the streaming builder's state, so agreement
with the feature store is evidence that the builder obeys the as-of rule.

Sources: data/interim/test_results (outcomes, durations), data/processed/splits_build.parquet (start/end),
the run's change re-read from the raw GitHub compare JSON (shadata/), changed-file lists of *other* runs from
data/processed/diffs/*/files.parquet, failing tests from data/interim/failures.parquet.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from stp import paths
from stp.data.build_diffs import CHANGE_KEY, DIFFS_DIR, read_change
from stp.features.change import Change, bm25_scores, change_features, change_size_features
from stp.features.cofail import RunRecord, cofail_features, parent_dir
from stp.features.history import Event, HistoryParams, cost_features, history_features
from stp.features.tokens import diff_token_counts
from stp.results import connect

RUN_KEY = ["project", "pr_name", "build_id", "stage_id"]


def raw_change(project: str, pr_name: str, build_id: int, base: str, head: str) -> Change:
    cfg = paths.config()
    stop = frozenset(cfg["project_stopwords"].get(project, []))
    files, patches = read_change(project, pr_name, int(build_id), base, head)
    names = [f["filename"] for f in files] + [f["previous_filename"] for f in files if f["previous_filename"]]
    return Change(files=sorted({f["filename"] for f in files}), additions=sum(f["additions"] for f in files),
                  deletions=sum(f["deletions"] for f in files),
                  token_counts=dict(diff_token_counts(names, patches, cfg["features"]["patch_max_chars"], stop)),
                  has_data=True)


class ProjectContext:
    """Everything the brute force needs for one project, loaded once."""

    def __init__(self, project: str):
        self.project = project
        self.con = connect()
        s = pd.read_parquet(paths.SPLITS_BUILD_PQ, filters=[("project", "==", project)])
        r = pd.read_parquet(paths.RUNS_PQ, columns=RUN_KEY + ["trunk_sha", "build_head_sha"],
                            filters=[("project", "==", project)])
        s = s.merge(r, on=RUN_KEY).sort_values(["start_ts", "pr_name", "build_id", "stage_id"]).reset_index(drop=True)
        s["seq"] = np.arange(len(s))
        self.runs = s
        ch = pd.read_parquet(DIFFS_DIR / f"project={project}" / "changes.parquet", columns=["change_idx"] + CHANGE_KEY)
        files = pd.read_parquet(DIFFS_DIR / f"project={project}" / "files.parquet", columns=["change_idx", "filename"])
        files = files.merge(ch, on="change_idx")
        fl = files.groupby(CHANGE_KEY).filename.apply(frozenset).rename("files").reset_index()
        s2 = s.merge(fl, on=CHANGE_KEY, how="left")
        s2["files"] = s2["files"].apply(lambda x: x if isinstance(x, frozenset) else frozenset())
        fails = pd.read_parquet(paths.FAILURES_PQ, columns=RUN_KEY + ["testclass"], filters=[("project", "==", project)])
        fails = fails.groupby(["pr_name", "build_id", "stage_id"]).testclass.apply(frozenset).rename("failing").reset_index()
        fails["build_id"] = fails["build_id"].astype(s2["build_id"].dtype)
        s2 = s2.merge(fails, on=["pr_name", "build_id", "stage_id"], how="left")
        s2["failing"] = s2["failing"].apply(lambda x: x if isinstance(x, frozenset) else frozenset())
        self.records = [RunRecord(int(q), float(e), f, x) for q, e, f, x in
                        zip(s2.seq, s2.end_ts, s2.files, s2.failing)]
        self.stop = frozenset(paths.config()["project_stopwords"].get(project, []))
        self.hp = HistoryParams.from_config()
        self.src = (paths.TEST_RESULTS_DIR / f"project={project}").as_posix()

    def run_rows(self, run: pd.Series) -> pd.DataFrame:
        return self.con.sql(f"""
            SELECT testclass, duration_s, outcome::VARCHAR = 'fail' AS fail FROM read_parquet('{self.src}/*.parquet')
            WHERE pr_name::VARCHAR = '{run.pr_name}' AND build_id = {int(run.build_id)}
              AND stage_id::VARCHAR = '{run.stage_id}'""").df()

    def iter_events(self, tests: list[str]):
        """Yield (testclass, [Event...]) for each test, streaming one test at a time (Kafka tests have ~10^4 events)."""
        start = self.runs.start_ts.to_numpy()
        end = self.runs.end_ts.to_numpy()
        stage = self.runs.stage_id.to_numpy()
        self.con.register("tq", pd.DataFrame({"testclass": tests, "ord": np.arange(len(tests))}))
        self.con.register("rmap", self.runs[["pr_name", "build_id", "stage_id", "seq"]])
        rel = self.con.sql(f"""
            SELECT q.ord, r.seq, t.duration_s, t.outcome::VARCHAR = 'fail' AS fail
            FROM read_parquet('{self.src}/*.parquet') t JOIN tq q USING (testclass)
            JOIN rmap r ON t.pr_name::VARCHAR = r.pr_name AND t.build_id = r.build_id AND t.stage_id::VARCHAR = r.stage_id
            ORDER BY q.ord, r.seq""")
        cur, evs = None, []
        for batch in rel.fetch_record_batch(500_000):
            o = batch.column(0).to_numpy()
            q = batch.column(1).to_numpy()
            du = batch.column(2).to_numpy().astype(np.float64)
            fl = batch.column(3).to_numpy(zero_copy_only=False)
            for oi, qi, di, fi in zip(o.tolist(), q.tolist(), du.tolist(), fl.tolist()):
                if oi != cur:
                    if cur is not None:
                        yield tests[cur], evs
                    cur, evs = oi, []
                evs.append(Event(qi, float(start[qi]), float(end[qi]), stage[qi], bool(fi), di))
        if cur is not None:
            yield tests[cur], evs
        self.con.unregister("tq")
        self.con.unregister("rmap")

    def recompute(self, run: pd.Series, test_sample: list[str] | None = None) -> pd.DataFrame:
        """Features of the given tests (default: all) of one run, by brute force."""
        rows = self.run_rows(run)
        all_tests = rows.testclass.tolist()
        tests = test_sample if test_sample is not None else all_tests
        t, stage = float(run.start_ts), run.stage_id
        # History for the requested tests. The cost fallback (median EMA over all seen tests of the run) is only used
        # by tests with no finished history; if the sample contains one, history is computed for every test.
        hist = {tc: history_features([], t, stage, self.hp) for tc in all_tests}
        for tc, evs in self.iter_events(tests):
            hist[tc] = history_features(evs, t, stage, self.hp)
        if test_sample is not None and any(hist[tc]["_dur_src"] == 0 for tc in tests):
            rest = [tc for tc in all_tests if tc not in set(tests)]
            for tc, evs in self.iter_events(rest):
                hist[tc] = history_features(evs, t, stage, self.hp)
        elif test_sample is not None:
            # fallback unused by the sampled tests: give the others a dummy seen source so the median is not consulted
            for tc in all_tests:
                if tc not in set(tests):
                    hist[tc] = {**hist[tc], "_dur_src": 1, "_dur_last": 1.0, "_dur_ema": 1.0}
        cost = dict(zip(all_tests, cost_features([hist[tc] for tc in all_tests])))
        change = raw_change(self.project, run.pr_name, run.build_id, run.trunk_sha, run.build_head_sha)
        size = change_size_features(change, self.stop)
        bm = dict(zip(all_tests, bm25_scores(all_tests, change, self.stop, *self._bm25())))
        cfiles = set(change.files)
        cdirs = {parent_dir(f) for f in cfiles}
        rel = [r for r in self.records if r.end <= t and (r.files & cfiles or {parent_dir(f) for f in r.files} & cdirs)]
        out = []
        by = rows.set_index("testclass")
        for tc in tests:
            h = {k: v for k, v in hist[tc].items() if not k.startswith("_")}
            row = {"testclass": tc, **h, **cost[tc], **change_features(tc, change, self.stop), **size,
                   "bm25_test_vs_diff": bm[tc], **cofail_features(tc, change.files, rel, t)}
            row["y_fail"] = bool(by.loc[tc, "fail"])
            row["y_ftf_asof"] = row["y_fail"] and h["h_n_fail"] == 0
            row["y_ftf_asof_ss"] = row["y_fail"] and h["hs_n_fail"] == 0
            row["y_duration_s"] = float(by.loc[tc, "duration_s"])
            out.append(row)
        return pd.DataFrame(out)

    @staticmethod
    def _bm25():
        f = paths.config()["features"]
        return f["bm25_k1"], f["bm25_b"]
