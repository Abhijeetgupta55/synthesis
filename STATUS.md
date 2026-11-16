# STATUS

**Name:** smartci: predicting CI test failures to run the right tests first.
**Working to:** `docs/PROMPT_FINISH.md` (supersedes `docs/PROMPT.md` where they conflict). Updated 2026-11-16.

## Gates

| Gate | State | Evidence |
|---|---|---|
| 0–3 (data facts, leakage, paper reproduction, rubric deliverables) | PASS | `reports/AUDIT.md` A2 |
| 4 (fresh venv; tool end to end) | fixture PASS; NetworkX part waits for mains power | AUDIT A6–A7 |
| 5 (simulated vs real timing, NetworkX) | FAIL on battery (11/20); re-run on mains power pending | `reports/REAL_WORLD.md` |
| A (audit complete, no headline number wrong) | PASS | `reports/AUDIT.md` |
| C (live comparison timed ≥ 3× on AC power) | **pending**: laptop was on battery all session | HUMAN_TODO 0 |
| E (fresh clone → setup_demo → run_demo, six pages, no data) | PASS | WORKLOG 2026-11-16 |

## Phases of PROMPT_FINISH

- **A audit:** done (`reports/AUDIT.md`, regenerable: `scripts/audit_runs.py`, `scripts/audit_spotcheck.py`).
- **B cleanup and reframe:** done. sympy dropped, candidate clones deleted, name and headline applied, error analysis
  in RESULTS.md §4.
- **C timing:** scripts ready (`live_demo/phase_c.py`, `scripts/run_live_compare.ps1 -Pick N | -Edit`); measurements
  pending mains power.
- **D trade-off:** done. Floor f* chosen on validation, held on LRTS test; failed a NetworkX deployment check, so it is
  opt-in (`SMARTCI_FLOOR`), off by default.
- **E dashboard:** done. Six pages, offline, smoke test passing, screenshots in `reports/demo_screenshots/`.
- **F GitHub readiness:** done except the push (students). README generated, `tests.yml`, `requirements.txt`,
  `scripts/publish_check.py` passes.
- **G presentation pack:** done. DEMO_SCRIPT.md (timing section fills itself after Phase C), RUBRIC_MAP.md,
  VIVA_NOTES.md (eight framing questions), AI_USE_DISCLOSURE.md draft.

## Added after the finishing prompt (2026-11-16)

- `smartci evaluate` (one command → verdict card: smartci, a simple rule, or not enough evidence) and
  `pytest --smartci --smartci-rule <rule>` so a team can run whichever order wins on its code.
- Dashboard: *Start here* (analogy, animated race on a real bug, savings calculator from 9,301 held-out runs) and
  *Break the code* (guided demo on a held-out real bug, live model, reveal); Results shows the NetworkX verdict.
- `reports/EXPLAINER.md` (plain language + FAQ), `reports/ROADMAP.md` (scope), DEMO_SCRIPT.md rewritten as a story with
  a 60-second pitch and a general-audience variant.

## Next

1. On mains power: `.venv\Scripts\python.exe live_demo\phase_c.py --repeats 3` (HUMAN_TODO 0). Then regenerate:
   `python -m stp.reports.real_world_md`, `results_md`, `presentation_md`, `readme_md`, `audit_md`; rebuild the bundle
   (`python -m stp.demo.build_bundle --parts results,repos`); `python -m stp.demo.smoke`; commit.
2. Students: HUMAN_TODO 3 (publish), 6 (optional hosting), 7 (disclosure), 8 (rehearse).

## How to resume

"Continue finishing smartci. Read docs/PROMPT_FINISH.md, STATUS.md and reports/AUDIT.md, then resume from the next
unfinished step."
