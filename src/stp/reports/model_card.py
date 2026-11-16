"""Generate models/global/MODEL_CARD.md (and the packaged copy) from schema.json and reports/results/*.json."""
from __future__ import annotations

import json
import shutil

from stp.reports.fmt import HEADLINE, NAME
from stp import paths
from stp.results import load_result

OUT = paths.ROOT / "models" / "global"


def main() -> None:
    sch = json.loads((OUT / "schema.json").read_text(encoding="utf-8"))
    tr = load_result("transfer") if (paths.RESULTS / "transfer.json").exists() else {}
    models = load_result("models") if (paths.RESULTS / "models.json").exists() else {}
    head = models.get("headline", {})
    lines = [
        f"# smartci global model {sch['version']}", "", f"Part of **{NAME}**. {HEADLINE}", "",
        f"Exported {sch['exported']} from git `{sch['git_sha']}`; variant `{sch['main_variant']}`.", "",
        "## Intended use",
        "Rank the test files of a Python + pytest repository so that the ones most likely to fail for the current "
        "change run first. The ranking only reorders; nothing is skipped, so the worst case is no speed-up.", "",
        "## Not intended for",
        "- deciding which tests to skip (test selection) — the model gives no guarantee any test is safe to skip;",
        "- judging code quality, people or teams;",
        "- non-pytest suites without adapting the test-to-file mapping.", "",
        "## Training data",
        f"{sch['training_data']['source']}. {sch['training_data']['split']}.",
        "LRTS test *classes* (JVM) and pytest *modules* (TVM) are the training unit; smartci scores pytest test files.",
        "", "Date ranges per project and split: see `reports/results/splits.json`.", "",
        "## Inputs",
        f"{len(sch['features'])} features (main model), {len(sch['features_coldstart'])} for the cold-start variant used "
        "while a repository has fewer than 5 recorded CI runs (no outcome history, no co-failure memory). "
        "Names, order, dtypes and missing-value defaults: `schema.json`.", "",
        "## Output and ordering",
        "Isotonic-calibrated P(test file fails in this run). " + sch["ordering"] + "."
        + (" " + sch["ordering_floor_note"] if sch.get("ordering_floor_note") else ""), "",
        "## Evaluation (held-out, time-respecting; numbers generated from reports/results)", "",
    ]
    if head:
        for k, v in head.items():
            lines.append(f"- {k}: {v}")
    if tr:
        lines.append("")
        lines.append("Python transfer (TVM pytest suites), test PR-AUC: " + ", ".join(
            f"{k} {v['testC_pr_auc']:.3f}" for k, v in tr.get("variants", {}).items()))
        lines.append(f"Chosen by TVM validation PR-AUC: `{tr.get('chosen')}`; confirmed on TVM test: "
                     f"{tr.get('confirmed_on_test')}; shipped: `{tr.get('shipped')}`. {tr.get('rule', '')}")
    lines += ["", "## Limits",
              "- Trained on 10 Apache projects' CI (9 Java/Scala, 1 Python). Signals such as name/path overlap and "
              "recent-failure history transfer; project-specific base rates do not (no project id is used).",
              "- Durations come from the repo's own profile/history; without them every test costs 1 s.",
              "- A simple rule (e.g. changed-files-first or coverage-first) can match or beat the model on a given "
              "repo; `smartci backtest` measures this on *your* repo and says so.",
              "- Concurrency-safe history: only runs that finished before the current one started are used.", ""]
    text = "\n".join(lines)
    (OUT / "MODEL_CARD.md").write_text(text, encoding="utf-8")
    pkg = paths.ROOT / "src" / "smartci" / "model"
    pkg.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT / "MODEL_CARD.md", pkg / "MODEL_CARD.md")
    print("wrote models/global/MODEL_CARD.md")


if __name__ == "__main__":
    main()
