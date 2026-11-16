"""`smartci explain`: the three largest reasons behind each of the top-ranked test files, as plain sentences.

Contributions are LightGBM's exact per-feature TreeSHAP values (log-odds); only features that *raise* the risk are
turned into reasons. Sentences quote the feature values, so each one can be checked against the receipt.
"""
from __future__ import annotations

from pathlib import Path

from smartci import gitdiff
from smartci.scoring import GlobalModel, score, stable_order


def sentence(feat: str, f: dict, change_files: list[str]) -> str | None:
    v = f.get(feat)
    if feat == "test_file_in_diff" and v:
        return "This test's file is in your change."
    if feat == "is_new_test" and v:
        return "This test file has never run in recorded history (new)."
    if feat == "same_top_module" and v:
        return "It is in the same top-level package as a changed file."
    if feat == "path_prefix_overlap" and v and v > 0:
        return f"Its directory path overlaps a changed file's path ({v:.0%} of its package path matches)."
    if feat == "name_token_overlap" and v:
        return f"Its name shares {int(v)} word(s) with the changed paths."
    if feat == "bm25_test_vs_diff" and v and v > 0:
        return f"Its name matches words in your diff (BM25 {v:.1f})."
    if feat in ("h_days_since_last_fail", "hs_days_since_last_fail") and v is not None and v < 9999:
        return f"It failed {v:.1f} days ago." if v >= 1 else f"It failed {v * 24:.1f} hours ago."
    if feat in ("h_n_fail", "hs_n_fail") and v:
        return f"It failed {int(v)} time(s) in recorded history."
    if feat in ("h_fails_last_7d", "hs_fails_last_7d") and v:
        return f"It failed {int(v)} time(s) in the last 7 days."
    if feat in ("h_last_outcome", "hs_last_outcome") and v:
        return "It failed in the most recent finished run."
    if feat in ("cof_count_max", "cof_max", "cof_sum") and (f.get("cof_count_max") or 0) > 0:
        return (f"When files in this change were changed before, this test failed "
                f"{int(f['cof_count_max'])} time(s).")
    if feat in ("dur_last_asof", "dur_ema_asof"):
        return f"It is quick to run ({f.get('dur_ema_asof', 0):.2f} s), so checking it first is cheap."
    if feat in ("chg_n_files", "chg_additions", "chg_deletions", "chg_n_top_modules"):
        return f"The change is large ({int(f.get('chg_n_files', 0))} files), which raises every test's risk a little."
    return None


def explain(repo: Path, test_files: list[str], base: str | None = None, top: int = 10) -> list[dict]:
    diff = gitdiff.compute(Path(repo), base)
    sc = score(Path(repo), test_files, diff.change, model=GlobalModel(), explain=True)
    out = []
    for rank, i in enumerate(stable_order(sc)[:top], 1):
        s = sc[i]
        rs, contrib = reasons(s, diff.change.files)
        out.append({"rank": rank, "test_file": s.test_file, "p_fail": s.p_fail, "expected_duration_s":
                    s.expected_duration, "reasons": rs, "top_contributions": contrib[:3]})
    return out


def reasons(s, change_files: list[str], n: int = 3) -> tuple[list[str], list[tuple[str, float]]]:
    """Up to n plain sentences for the features that raise this test's risk most (SHAP > 0), plus those features."""
    contrib = sorted(((k, v) for k, v in s.contributions.items() if k != "_bias" and v > 0), key=lambda kv: -kv[1])
    out: list[str] = []
    for k, _ in contrib:
        t = sentence(k, s.features, change_files)
        if t and t not in out:
            out.append(t)
        if len(out) == n:
            break
    return out or ["No strong signal; ranked by low cost."], contrib
