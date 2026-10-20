"""Phase 1.4b: the LRTS feature store, one row per (run, test class), built by a streaming as-of pass.

For each project, runs are visited in start order (run_idx). Before computing the features of run r (start t), every
run whose end <= t is *applied* to per-test state in end order (`end` = start + capped build_duration, see
stp.data.splits). Sliding counts (failures known in the last 7 / 30 days) are decremented when a failure's end falls
out of the window. A run's own outcomes and durations are applied only after it ends, so they can never be its
features. The values equal the pure reference functions in history.py / change.py / cofail.py; tests/test_leakage.py
checks this by brute force on random real runs.

Outputs (resumable: a finished project is skipped; work happens in project=<p>.tmp and is renamed at the end):
  data/processed/features/project=<p>/part-*.parquet   run_idx, test_id, FEATURES..., labels, y_duration_s
  data/processed/features/project=<p>/runs.parquet     run_idx -> run keys, split, rolling window, start/end, change
  data/processed/features/project=<p>/tests.parquet    test_id -> testclass

Usage: python -m stp.features.store [--projects a,b] [--limit-runs N]
"""
from __future__ import annotations

import argparse
import math
import shutil
import time
from collections import OrderedDict

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from stp import paths
from stp.data.build_diffs import CHANGE_KEY, DIFFS_DIR
from stp.features.change import query_weight
from stp.features.cofail import parent_dir
from stp.features.history import DAY, HistoryParams
from stp.features.schema import FEATURES
from stp.features.testmap import test_path_suffixes
from stp.features.tokens import file_dirs, test_dirs, test_text, tokenize, top_module
from stp.results import connect, save_result

WORK = paths.PROCESSED / "_work"
FLUSH_ROWS = 1_000_000
RUN_KEY = ["project", "pr_name", "build_id", "stage_id"]


# ------------------------------------------------------------------------------------------ readers
def store_dir(project: str):
    return paths.FEATURES_DIR / f"project={project}"


def parts_glob(project: str) -> str:
    """DuckDB glob of a project's feature rows (runs.parquet / tests.parquet in the same folder are not rows)."""
    return (store_dir(project) / "part-*.parquet").as_posix()


def store_ready(project: str) -> bool:
    return (store_dir(project) / "_SUCCESS").exists()


# ------------------------------------------------------------------------------------------ preparation
def project_runs(project: str) -> pd.DataFrame:
    s = pd.read_parquet(paths.SPLITS_BUILD_PQ, filters=[("project", "==", project)])
    r = pd.read_parquet(paths.RUNS_PQ, columns=RUN_KEY + ["trunk_sha", "build_head_sha", "in_paper_subset"],
                        filters=[("project", "==", project)])
    s = s.merge(r, on=RUN_KEY, how="left", validate="1:1")
    s = s.sort_values(["start_ts", "pr_name", "build_id", "stage_id"]).reset_index(drop=True)
    s.insert(0, "run_idx", np.arange(len(s), dtype=np.int32))
    ch = pd.read_parquet(DIFFS_DIR / f"project={project}" / "changes.parquet", columns=["change_idx"] + CHANGE_KEY)
    s = s.merge(ch, on=CHANGE_KEY, how="left", validate="m:1")
    s["change_idx"] = s["change_idx"].fillna(-1).astype(np.int32)
    return s.sort_values("run_idx").reset_index(drop=True)


def write_rows_file(con, project: str, runs: pd.DataFrame, tests: pd.DataFrame, out: str) -> None:
    """(run_idx, test_id, duration_s, fail) sorted by run_idx, test_id: the input stream of the pass."""
    con.register("rmap", runs[["pr_name", "build_id", "stage_id", "run_idx"]])
    con.register("tmap", tests)
    src = (paths.TEST_RESULTS_DIR / f"project={project}").as_posix()
    con.execute(f"""
        COPY (SELECT r.run_idx, m.test_id, t.duration_s, t.outcome::VARCHAR = 'fail' AS fail
              FROM read_parquet('{src}/*.parquet') t
              JOIN rmap r ON t.pr_name::VARCHAR = r.pr_name AND t.build_id = r.build_id AND t.stage_id::VARCHAR = r.stage_id
              JOIN tmap m ON t.testclass = m.testclass
              ORDER BY r.run_idx, m.test_id)
        TO '{out}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 500000)""")
    con.unregister("rmap")
    con.unregister("tmap")


def iter_runs(rows_path: str, n_runs: int):
    """Yield (test_ids, duration, fail) for run_idx 0..n_runs-1 in order (empty arrays for runs with no rows)."""
    pf = pq.ParquetFile(rows_path)
    left = None
    nxt = 0

    def emit(r, t, d, f):
        nonlocal nxt
        u, starts = np.unique(r, return_index=True)
        ends = np.r_[starts[1:], len(r)]
        for ri, a, b in zip(u, starts, ends):
            while nxt < ri:
                yield np.empty(0, np.int64), np.empty(0), np.empty(0, bool)
                nxt += 1
            yield t[a:b].astype(np.int64), d[a:b].astype(np.float64), f[a:b]
            nxt += 1

    for batch in pf.iter_batches(batch_size=1_000_000):
        cols = [batch.column(i).to_numpy(zero_copy_only=False) for i in range(4)]
        if left is not None:
            cols = [np.concatenate([a, b]) for a, b in zip(left, cols)]
        r = cols[0]
        cut = np.searchsorted(r, r[-1], "left")
        left = [c[cut:] for c in cols]
        if cut:
            yield from emit(*[c[:cut] for c in cols])
    if left is not None and len(left[0]):
        yield from emit(*left)
    while nxt < n_runs:
        yield np.empty(0, np.int64), np.empty(0), np.empty(0, bool)
        nxt += 1


# ------------------------------------------------------------------------------------------- static data
class TestStatic:
    """Per-test precomputation: token CSR (sorted by token string), dirs, top module, own-file suffixes."""

    def __init__(self, testclasses: list[str], stop: frozenset[str]):
        self.n = len(testclasses)
        self.vocab: dict[str, int] = {}
        ind, tf, ptr = [], [], [0]
        for tc in testclasses:
            c: dict[str, int] = {}
            for w in tokenize(test_text(tc), stop):
                c[w] = c.get(w, 0) + 1
            for w in sorted(c):
                ind.append(self.vocab.setdefault(w, len(self.vocab)))
                tf.append(c[w])
            ptr.append(len(ind))
        self.ind = np.asarray(ind, np.int64)
        self.tf = np.asarray(tf, np.float64)
        self.ptr = np.asarray(ptr, np.int64)
        self.seg = np.repeat(np.arange(self.n), np.diff(self.ptr))
        self.dl = np.bincount(self.seg, weights=self.tf, minlength=self.n).astype(np.int64)
        dirs = [test_dirs(tc, stop) for tc in testclasses]
        self.dir_tuples: dict[tuple, int] = {}
        self.dir_id = np.asarray([self.dir_tuples.setdefault(d, len(self.dir_tuples)) for d in dirs], np.int64)
        self.dir_list = list(self.dir_tuples)
        self.tops: dict[str, int] = {}
        self.top_id = np.asarray([self.tops.setdefault(top_module(d), len(self.tops)) if d else -1 for d in dirs],
                                 np.int64)
        self.by_suffix: dict[str, list[int]] = {}
        for i, tc in enumerate(testclasses):
            for s in test_path_suffixes(tc):
                self.by_suffix.setdefault(s, []).append(i)

    def gather(self, ids: np.ndarray):
        """Flat CSR positions of the given tests' tokens and the local segment (row in `ids`) of each."""
        lens = self.ptr[ids + 1] - self.ptr[ids]
        total = int(lens.sum())
        if total == 0:
            return np.empty(0, np.int64), np.empty(0, np.int64)
        seg = np.repeat(np.arange(len(ids)), lens)
        offs = np.repeat(self.ptr[ids] - np.r_[0, np.cumsum(lens)[:-1]], lens)
        return np.arange(total) + offs, seg


class ChangeCache:
    """Per-change precomputation, LRU-cached (stages of one build share a change)."""

    def __init__(self, project: str, ts: TestStatic, stop: frozenset[str], k1: float, b: float):
        d = DIFFS_DIR / f"project={project}"
        self.meta = pd.read_parquet(d / "changes.parquet").set_index("change_idx")
        f = pd.read_parquet(d / "files.parquet", columns=["change_idx", "filename"])
        self.files = {k: sorted(set(g.filename)) for k, g in f.groupby("change_idx")}
        tk = pd.read_parquet(d / "tokens.parquet")
        tk["vid"] = tk.token.astype(str).map(ts.vocab)
        tk = tk.dropna(subset=["vid"])
        self.tokens = {k: (g.vid.to_numpy(np.int64), g["count"].to_numpy(np.int64)) for k, g in tk.groupby("change_idx")}
        self.ts, self.stop, self.k1, self.b = ts, stop, k1, b
        self.file_ids: dict[str, int] = {}
        self.dir_ids: dict[str, int] = {}
        self._lru: OrderedDict[int, dict] = OrderedDict()

    def file_id(self, f: str) -> int:
        return self.file_ids.setdefault(f, len(self.file_ids))

    def dir_id(self, d: str) -> int:
        return self.dir_ids.setdefault(d, len(self.dir_ids))

    def get(self, cidx: int) -> dict:
        if cidx in self._lru:
            self._lru.move_to_end(cidx)
            return self._lru[cidx]
        ts, stop = self.ts, self.stop
        files = self.files.get(cidx, []) if cidx >= 0 else []
        fdirs = [file_dirs(f, stop) for f in files]
        tfd: set[int] = set()
        for fn in files:
            parts = fn.replace("\\", "/").split("/")
            for i in range(len(parts)):
                tfd.update(ts.by_suffix.get("/".join(parts[i:]), ()))
        tops = {top_module(x) for x in fdirs} - {None}
        trie: dict = {}
        for fd in set(fdirs):
            for s in range(len(fd)):
                node = trie
                for comp in fd[s:]:
                    node = node.setdefault(comp, {})
        mask = np.zeros(len(ts.vocab) + 1, np.int64)
        for fn in files:
            for w in set(tokenize(fn, stop)):
                v = ts.vocab.get(w)
                if v is not None:
                    mask[v] = 1
        name_ov = np.bincount(ts.seg, weights=mask[ts.ind], minlength=ts.n).astype(np.int64)
        qw = np.zeros(len(ts.vocab), np.float64)
        if cidx in self.tokens:
            vid, cnt = self.tokens[cidx]
            qw[vid] = [query_weight(int(c)) for c in cnt]
        if cidx >= 0 and cidx in self.meta.index:
            m = self.meta.loc[cidx]
            size = (int(m.n_files), int(m.additions), int(m.deletions), True)
        else:
            size = (0, 0, 0, False)
        entry = {
            "files": files, "file_ids": np.asarray([self.file_id(f) for f in files], np.int64),
            "file_dir_ids": np.asarray([self.dir_id(parent_dir(f)) for f in files], np.int64),
            "tfd": np.fromiter(tfd, np.int64, len(tfd)),
            "top_ids": np.asarray([ts.tops[t] for t in tops if t in ts.tops], np.int64),
            "n_tops": len(tops), "trie": trie, "ppo": {}, "name_ov": name_ov, "qw": qw, "size": size,
        }
        self._lru[cidx] = entry
        if len(self._lru) > 256:
            self._lru.popitem(last=False)
        return entry

    def prefix_overlap(self, entry: dict, dir_ids: np.ndarray) -> np.ndarray:
        u, inv = np.unique(dir_ids, return_inverse=True)
        vals = np.empty(len(u))
        for k, di in enumerate(u):
            v = entry["ppo"].get(di)
            if v is None:
                t = self.ts.dir_list[di]
                node, depth = entry["trie"], 0
                for comp in t:
                    if comp not in node:
                        break
                    node = node[comp]
                    depth += 1
                v = depth / len(t) if t else 0.0
                entry["ppo"][di] = v
            vals[k] = v
        return vals[inv]

    def bm25(self, entry: dict, ids: np.ndarray) -> np.ndarray:
        n = len(ids)
        out = np.zeros(n)
        pos, seg = self.ts.gather(ids)
        if n == 0 or len(pos) == 0:
            return out
        dl_run = self.ts.dl[ids]
        avgdl = int(dl_run.sum()) / n
        if avgdl <= 0:
            return out
        tok = self.ts.ind[pos]
        tf = self.ts.tf[pos]
        qw = entry["qw"][tok]
        keep = qw > 0
        df = np.bincount(tok, minlength=len(self.ts.vocab))
        tok, tf, qw, seg = tok[keep], tf[keep], qw[keep], seg[keep]
        dfv = df[tok]
        idf = np.log(1.0 + (n - dfv + 0.5) / (dfv + 0.5))
        L = dl_run[seg]
        term = qw * idf * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * L / avgdl))
        return np.bincount(seg, weights=term, minlength=n)


# --------------------------------------------------------------------------------------- streaming state
class HistState:
    """As-of outcome/duration state for one scope (all-stage: key = test; same-stage: key = (stage, test))."""

    def __init__(self, n: int):
        self.n_runs = np.zeros(n, np.int64)
        self.n_fail = np.zeros(n, np.int64)
        self.n_trans = np.zeros(n, np.int64)
        self.last = np.zeros(n, bool)
        self.lfs = np.full(n, -np.inf)            # max start of a known failure
        self.lf_stage = np.full(n, -1, np.int64)  # stage of that failure
        self.f7 = np.zeros(n, np.int64)
        self.f30 = np.zeros(n, np.int64)
        self.dur_last = np.zeros(n)
        self.dur_ema = np.zeros(n)

    def apply(self, k: np.ndarray, fail: np.ndarray, dur: np.ndarray, start: float, stage: int, alpha: float):
        seen = self.n_runs[k] > 0
        self.n_trans[k] += (seen & (self.last[k] != fail)).astype(np.int64)
        self.last[k] = fail
        self.n_runs[k] += 1
        self.n_fail[k] += fail.astype(np.int64)
        self.dur_ema[k] = np.where(seen, alpha * dur + (1 - alpha) * self.dur_ema[k], dur)
        self.dur_last[k] = dur
        kf = k[fail]
        upd = start >= self.lfs[kf]
        self.lfs[kf[upd]] = start
        self.lf_stage[kf[upd]] = stage
        self.f7[kf] += 1
        self.f30[kf] += 1

    def query(self, k: np.ndarray, t: float, p: HistoryParams, prefix: str) -> dict:
        nr, nf = self.n_runs[k], self.n_fail[k]
        lfs = self.lfs[k]
        return {
            f"{prefix}_n_fail": nf,
            f"{prefix}_days_since_last_fail": np.where(np.isfinite(lfs), (t - lfs) / DAY, p.days_never),
            f"{prefix}_fails_last_7d": self.f7[k], f"{prefix}_fails_last_30d": self.f30[k],
            f"{prefix}_last_outcome": self.last[k].copy(), f"{prefix}_n_transitions": self.n_trans[k],
            f"{prefix}_n_runs_seen": nr,
            f"{prefix}_fail_rate": (nf + p.fail_rate_strength * p.fail_rate_prior) / (nr + p.fail_rate_strength),
        }


class CofailState:
    def __init__(self):
        self.nchg: dict[int, int] = {}
        self.nchg_d: dict[int, int] = {}
        self.cof: dict[int, dict[int, int]] = {}
        self.cof_d: dict[int, dict[int, int]] = {}

    def apply(self, file_ids: np.ndarray, dir_ids: np.ndarray, failing: np.ndarray):
        dirs = set(dir_ids.tolist())
        for f in file_ids.tolist():
            self.nchg[f] = self.nchg.get(f, 0) + 1
        for d in dirs:
            self.nchg_d[d] = self.nchg_d.get(d, 0) + 1
        if len(failing):
            fl = failing.tolist()
            for f in file_ids.tolist():
                dct = self.cof.setdefault(f, {})
                for x in fl:
                    dct[x] = dct.get(x, 0) + 1
            for d in dirs:
                dct = self.cof_d.setdefault(d, {})
                for x in fl:
                    dct[x] = dct.get(x, 0) + 1

    def query(self, entry: dict, ids: np.ndarray, n_tests: int, buf: dict) -> tuple:
        mx, sm, cm = buf["mx"], buf["sm"], buf["cm"]
        touched = []
        for f, d in zip(entry["file_ids"].tolist(), entry["file_dir_ids"].tolist()):  # files in sorted order
            nf = self.nchg.get(f, 0)
            if nf > 0:
                dct, denom = self.cof.get(f), nf + 1
            else:
                dct, denom = self.cof_d.get(d), self.nchg_d.get(d, 0) + 1
            if dct:
                keys = np.fromiter(dct.keys(), np.int64, len(dct))
                vals = np.fromiter(dct.values(), np.float64, len(dct))
                sc = vals / denom
                np.maximum.at(mx, keys, sc)
                np.add.at(sm, keys, sc)
                touched.append(keys)
            if nf > 0 and dct:
                np.maximum.at(cm, keys, vals)
        out = mx[ids].copy(), sm[ids].copy(), cm[ids].astype(np.int64)
        for k in touched:
            mx[k] = 0.0
            sm[k] = 0.0
            cm[k] = 0.0
        return out


# ------------------------------------------------------------------------------------------------ build
def build_project(project: str, limit_runs: int | None = None) -> dict:
    final = paths.FEATURES_DIR / f"project={project}"
    if final.exists() and (final / "_SUCCESS").exists() and limit_runs is None:
        print(f"[store] {project}: done already, skipping")
        return {}
    t0 = time.time()
    cfg = paths.config()
    stop = frozenset(cfg["project_stopwords"].get(project, []))
    hp = HistoryParams.from_config()
    k1, b = cfg["features"]["bm25_k1"], cfg["features"]["bm25_b"]
    con = connect()

    runs = project_runs(project)
    if limit_runs:
        runs = runs[runs.run_idx < limit_runs].copy()
    src = (paths.TEST_RESULTS_DIR / f"project={project}").as_posix()
    tests = con.sql(f"SELECT DISTINCT testclass FROM read_parquet('{src}/*.parquet') ORDER BY 1").df()
    tests["test_id"] = np.arange(len(tests), dtype=np.int32)
    WORK.mkdir(parents=True, exist_ok=True)
    rows_path = (WORK / f"rows_{project}.parquet").as_posix()
    write_rows_file(con, project, runs, tests, rows_path)
    print(f"[store] {project}: {len(runs):,} runs, {len(tests):,} tests, rows file in {time.time() - t0:.0f}s",
          flush=True)

    n_runs, n_tests = len(runs), len(tests)
    stages = {s: i for i, s in enumerate(sorted(runs.stage_id.unique()))}
    stage_of = runs.stage_id.map(stages).to_numpy(np.int64)
    start = runs.start_ts.to_numpy(np.float64)
    end = runs.end_ts.to_numpy(np.float64)
    cidx = runs.change_idx.to_numpy(np.int64)
    end_order = np.lexsort((np.arange(n_runs), end))   # by (end, run_idx)

    ts = TestStatic(tests.testclass.tolist(), stop)
    cc = ChangeCache(project, ts, stop, k1, b)
    H = HistState(n_tests)
    HS = HistState(n_tests * len(stages))
    C = CofailState()
    buf = {"mx": np.zeros(n_tests), "sm": np.zeros(n_tests), "cm": np.zeros(n_tests)}
    pending: dict[int, tuple] = {}     # started, not yet applied
    fails_of: dict[int, np.ndarray] = {}  # failing test ids of applied runs still inside the 30-day window
    pa_, p7, p30 = 0, 0, 0

    tmp = paths.FEATURES_DIR / f"project={project}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    out_cols: dict[str, list] = {}
    n_out, part = 0, 0
    stats = {"rows": 0, "rows_fail": 0, "rows_ftf_asof": 0}

    def flush():
        nonlocal out_cols, n_out, part
        if not n_out:
            return
        tbl = {}
        for k, v in out_cols.items():
            arr = np.concatenate(v)
            dt = FEATURES[k]["dtype"] if k in FEATURES else {"run_idx": "int32", "test_id": "int32",
                                                              "y_duration_s": "float32"}.get(k, "bool")
            tbl[k] = arr.astype(dt)
        pq.write_table(pa.table(tbl), tmp / f"part-{part:04d}.parquet", compression="zstd")
        part += 1
        out_cols, n_out = {}, 0

    def apply(j: int):
        ids, dur, fail = pending.pop(j)
        s = stage_of[j]
        H.apply(ids, fail, dur, start[j], s, hp.ema_alpha)
        HS.apply(s * n_tests + ids, fail, dur, start[j], s, hp.ema_alpha)
        e = cc.get(int(cidx[j]))
        C.apply(e["file_ids"], e["file_dir_ids"], ids[fail])
        fails_of[j] = ids[fail]

    def expire(j: int, attr: str):
        f = fails_of[j]
        getattr(H, attr)[f] -= 1
        getattr(HS, attr)[stage_of[j] * n_tests + f] -= 1

    it = iter_runs(rows_path, n_runs)
    for r in range(n_runs):
        ids, dur, fail = next(it)
        t = start[r]
        while pa_ < n_runs and end[end_order[pa_]] <= t:
            apply(int(end_order[pa_]))
            pa_ += 1
        while p7 < pa_ and end[end_order[p7]] <= t - 7 * DAY:
            expire(int(end_order[p7]), "f7")
            p7 += 1
        while p30 < pa_ and end[end_order[p30]] <= t - 30 * DAY:
            j = int(end_order[p30])
            expire(j, "f30")
            fails_of.pop(j, None)
            p30 += 1
        pending[r] = (ids, dur, fail)
        if len(ids) == 0:
            continue
        s = stage_of[r]
        feat = H.query(ids, t, hp, "h")
        feat.update(HS.query(s * n_tests + ids, t, hp, "hs"))
        feat["is_new_test"] = H.n_runs[ids] == 0
        feat["h_last_fail_same_stage"] = H.lf_stage[ids] == s
        # cost: same-stage -> all-stage -> run median of seen tests' EMA -> 1 s
        ss_seen, as_seen = HS.n_runs[s * n_tests + ids] > 0, H.n_runs[ids] > 0
        dl = np.where(ss_seen, HS.dur_last[s * n_tests + ids], H.dur_last[ids])
        de = np.where(ss_seen, HS.dur_ema[s * n_tests + ids], H.dur_ema[ids])
        src_ = np.where(ss_seen, 2, np.where(as_seen, 1, 0))
        seen = src_ > 0
        fb = float(np.median(de[seen])) if seen.any() else 1.0
        feat["dur_last_asof"] = np.where(seen, dl, fb)
        feat["dur_ema_asof"] = np.where(seen, de, fb)
        feat["dur_source"] = src_
        # change relatedness
        e = cc.get(int(cidx[r]))
        feat["test_file_in_diff"] = np.isin(ids, e["tfd"])
        feat["same_top_module"] = np.isin(ts.top_id[ids], e["top_ids"]) & (ts.top_id[ids] >= 0)
        feat["path_prefix_overlap"] = cc.prefix_overlap(e, ts.dir_id[ids]) if e["files"] else np.zeros(len(ids))
        feat["name_token_overlap"] = e["name_ov"][ids]
        feat["bm25_test_vs_diff"] = cc.bm25(e, ids)
        nf_, ad_, de_, has_ = e["size"]
        for k, v in (("chg_n_files", nf_), ("chg_additions", ad_), ("chg_deletions", de_),
                     ("chg_n_top_modules", e["n_tops"]), ("has_change_data", has_)):
            feat[k] = np.full(len(ids), v)
        mx, sm, cm = C.query(e, ids, n_tests, buf)
        feat["cof_max"], feat["cof_sum"], feat["cof_count_max"] = mx, sm, cm
        feat["semantic_sim"] = np.full(len(ids), np.nan)
        feat["run_idx"] = np.full(len(ids), r)
        feat["test_id"] = ids
        feat["y_fail"] = fail
        feat["y_ftf_asof"] = fail & (feat["h_n_fail"] == 0)
        feat["y_ftf_asof_ss"] = fail & (feat["hs_n_fail"] == 0)
        feat["y_duration_s"] = dur
        for k, v in feat.items():
            out_cols.setdefault(k, []).append(v)
        n_out += len(ids)
        stats["rows"] += len(ids)
        stats["rows_fail"] += int(fail.sum())
        stats["rows_ftf_asof"] += int(feat["y_ftf_asof"].sum())
        if n_out >= FLUSH_ROWS:
            flush()
        if r % 5000 == 0:
            print(f"  [store] {project}: run {r:,}/{n_runs:,}  rows {stats['rows']:,}  {time.time() - t0:.0f}s",
                  flush=True)
    flush()
    it.close()   # releases the rows file (Windows will not delete an open file)
    runs.to_parquet(tmp / "runs.parquet", index=False)
    tests.to_parquet(tmp / "tests.parquet", index=False)
    if limit_runs is None:
        if final.exists():
            shutil.rmtree(final)
        tmp.rename(final)
        (final / "_SUCCESS").write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
        try:
            (WORK / f"rows_{project}.parquet").unlink(missing_ok=True)
        except PermissionError:
            print(f"  [store] could not delete rows_{project}.parquet (still open); harmless, delete later")
    elapsed = time.time() - t0
    size = sum(f.stat().st_size for f in (final if limit_runs is None else tmp).glob("*.parquet"))
    stats.update(seconds=elapsed, bytes=size, n_runs=n_runs, n_tests=n_tests, n_stages=len(stages))
    print(f"[store] {project}: {stats['rows']:,} rows, {size / 1e6:.0f} MB, {elapsed:.0f}s", flush=True)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects", default=",".join(paths.PROJECTS))
    ap.add_argument("--limit-runs", type=int, default=None)
    a = ap.parse_args()
    import json
    log = paths.RESULTS / "feature_store_build.json"
    prev = json.loads(log.read_text())["projects"] if log.exists() else {}
    for p in a.projects.split(","):
        st = build_project(p, a.limit_runs)
        if st and a.limit_runs is None:
            prev[p] = st
            save_result("feature_store_build", {"projects": prev,
                                                "total_rows": sum(v["rows"] for v in prev.values()),
                                                "total_bytes": sum(v["bytes"] for v in prev.values()),
                                                "total_seconds": sum(v["seconds"] for v in prev.values())})


if __name__ == "__main__":
    main()
