"""Phase 3.1: label distribution per project and split, and why accuracy is useless here.

Writes reports/results/labels.json:
  positive rate of y_fail and y_ftf_asof per project x split, pooled and macro;
  accuracy of the trivial "always pass" classifier (= 1 − positive rate);
  share of rows that fall in each evaluation subset's target set (test split, failed runs).
Usage: python -m stp.models.labels
"""
from __future__ import annotations

from stp import paths
from stp.eda.common import with_macro
from stp.features.store import parts_glob, store_dir, store_ready
from stp.results import connect, save_result


def main() -> None:
    con = connect()
    per, tot = {}, {"rows": 0, "fail": 0, "ftf": 0}
    for p in paths.PROJECTS:
        if not store_ready(p):
            continue
        con.execute(f"CREATE OR REPLACE TEMP VIEW r AS SELECT run_idx, split, failed FROM "
                    f"read_parquet('{(store_dir(p) / 'runs.parquet').as_posix()}')")
        d = con.sql(f"""
            SELECT r.split, count(*) n, sum(y_fail::INT) n_fail, sum(y_ftf_asof::INT) n_ftf,
                   sum(CASE WHEN r.failed THEN 1 ELSE 0 END) n_in_failed_runs,
                   sum((y_fail AND NOT is_new_test AND NOT test_file_in_diff AND y_ftf_asof)::INT) n_ftf_old,
                   sum((y_fail AND (is_new_test OR test_file_in_diff))::INT) n_new_edited
            FROM read_parquet('{parts_glob(p)}') JOIN r USING (run_idx) GROUP BY 1""").df().set_index("split")
        per[p] = {s: {"rows": int(x.n), "pos_rate_fail": x.n_fail / x.n, "pos_rate_ftf_asof": x.n_ftf / x.n,
                      "always_pass_accuracy": 1 - x.n_fail / x.n,
                      "pos_rate_fail_within_failed_runs": x.n_fail / max(1, x.n_in_failed_runs),
                      "n_fail": int(x.n_fail), "n_ftf_asof": int(x.n_ftf), "n_ftf_old": int(x.n_ftf_old),
                      "n_new_edited_fail": int(x.n_new_edited)} for s, x in d.iterrows()}
        tot["rows"] += int(d.n.sum())
        tot["fail"] += int(d.n_fail.sum())
        tot["ftf"] += int(d.n_ftf.sum())
    out = {"per_project": per,
           "pooled": {"rows": tot["rows"], "pos_rate_fail": tot["fail"] / tot["rows"],
                      "pos_rate_ftf_asof": tot["ftf"] / tot["rows"],
                      "always_pass_accuracy": 1 - tot["fail"] / tot["rows"]},
           "macro_pos_rate_fail": with_macro({p: sum(v[s]["n_fail"] for s in v) / sum(v[s]["rows"] for s in v)
                                              for p, v in per.items()}),
           "macro_pos_rate_ftf_asof": with_macro({p: sum(v[s]["n_ftf_asof"] for s in v) / sum(v[s]["rows"] for s in v)
                                                  for p, v in per.items()})}
    save_result("labels", out)
    print(out["pooled"], out["macro_pos_rate_fail"]["macro"])


if __name__ == "__main__":
    main()
