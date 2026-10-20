"""pytest plugin (entry point `pytest11: smartci`). Inactive unless --smartci is passed or SMARTCI=1.

When active it only *reorders* whole test files (pytest's order inside a file is kept); nothing is deselected,
so the worst case is no speed-up. A receipt is written to .smartci/receipts/.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

_STATE: dict = {}


def pytest_addoption(parser):
    g = parser.getgroup("smartci")
    g.addoption("--smartci", action="store_true", default=False,
                help="run the test files most likely to fail for the current change first (never skips)")
    g.addoption("--smartci-base", default=None, help="git base to diff against (default: origin/HEAD, main, master)")
    g.addoption("--smartci-shadow", action="store_true", default=False,
                help="compute and record the ranking but keep pytest's order (for CI shadow mode)")
    g.addoption("--smartci-timing", default=None, metavar="PATH",
                help="only record when the first failure is reported (JSON at PATH); no ranking, no reordering")


def pytest_configure(config):
    path = config.getoption("smartci_timing")
    if path and not active(config):
        _STATE.update(timing_only=path, start=None, first_fail=None, results={})


def active(config) -> bool:
    return bool(config.getoption("smartci") or config.getoption("smartci_shadow")
                or os.environ.get("SMARTCI") == "1")


def _file_of(item, root: Path) -> str:
    p = Path(str(item.fspath)).resolve()
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return p.as_posix()


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(session, config, items):
    if not active(config) or not items:
        return
    from smartci import gitdiff, receipts
    from smartci.scoring import GlobalModel, score, stable_order

    root = Path(str(config.rootpath)).resolve()
    t0 = time.time()
    files, by_file = [], {}
    for it in items:
        f = _file_of(it, root)
        if f not in by_file:
            by_file[f] = []
            files.append(f)
        by_file[f].append(it)
    try:
        diff = gitdiff.compute(root, config.getoption("smartci_base"))
        model = GlobalModel()
        scored = score(root, files, diff.change, t=t0, model=model)
    except Exception as e:  # noqa: BLE001  (never break a test run: fall back to pytest's order)
        tw = config.pluginmanager.get_plugin("terminalreporter")
        if tw:
            tw.write_line(f"smartci: disabled for this run ({type(e).__name__}: {e}); pytest order kept")
        return
    order = stable_order(scored)
    shadow = config.getoption("smartci_shadow")
    if not shadow:
        items[:] = [it for i in order for it in by_file[scored[i].test_file]]
    ranking = [{"rank": r + 1, "test_file": scored[i].test_file, "p_fail": scored[i].p_fail,
                "expected_duration_s": scored[i].expected_duration, "priority": scored[i].priority,
                "features": scored[i].features} for r, i in enumerate(order)]
    rec = receipts.new_receipt(root, diff.base_sha, diff.head_sha, diff.diff_hash, model.version,
                               scored[0].model if scored else "", files, ranking, diff.change.files)
    rec["shadow"] = bool(shadow)
    path = receipts.path_for(root, rec)
    _STATE.update(receipt=rec, path=path, start=None, first_fail=None, results={}, file_dur={}, root=root)
    receipts.write(path, rec)
    tw = config.pluginmanager.get_plugin("terminalreporter")
    if tw:
        top = ", ".join(f"{x['test_file']} ({x['p_fail']:.2f})" for x in ranking[:5])
        mode = "shadow (order unchanged)" if shadow else "reordered"
        tw.write_line(f"smartci: {len(files)} test files ranked, {mode}; model {model.version}/{rec['model_variant']}; "
                      f"top 5: {top}")
        tw.write_line(f"smartci: receipt {path}")


def pytest_runtest_logstart(nodeid, location):
    if _STATE and _STATE.get("start") is None:
        _STATE["start"] = time.time()


def pytest_runtest_logreport(report):
    if not _STATE:
        return
    f = report.nodeid.split("::", 1)[0].replace("\\", "/")
    r = _STATE["results"].setdefault(f, {"outcome": "passed", "duration_s": 0.0, "n_failed": 0})
    r["duration_s"] += float(report.duration or 0.0)
    failed = report.failed and not getattr(report, "wasxfail", False)
    if failed:
        r["outcome"] = "failed"
        r["n_failed"] += 1
        if _STATE["first_fail"] is None:
            _STATE["first_fail"] = {"nodeid": report.nodeid, "test_file": f,
                                    "elapsed_s": time.time() - (_STATE["start"] or time.time())}


def pytest_sessionfinish(session, exitstatus):
    if not _STATE:
        return
    if _STATE.get("timing_only"):
        import json
        Path(_STATE["timing_only"]).write_text(json.dumps({
            "first_failure": _STATE["first_fail"], "first_test_start": _STATE["start"], "end": time.time(),
            "exitstatus": int(exitstatus), "results": _STATE["results"]}), encoding="utf-8")
        _STATE.clear()
        return
    from smartci import receipts

    rec = _STATE["receipt"]
    rec["results"] = _STATE["results"]
    rec["first_failure"] = _STATE["first_fail"]
    rec["session"] = {"first_test_start": _STATE["start"], "end": time.time(), "exitstatus": int(exitstatus)}
    receipts.write(_STATE["path"], rec)
    _STATE.clear()
