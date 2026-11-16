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
- **E dashboard:** done. Eight pages (Start here, ML Lab, Real PRs, Break the code, pipeline, Predict live, Results, Limits), offline, smoke test passing, screenshots in `reports/demo_screenshots/`.
- **F GitHub readiness:** done except the push (students). README generated, `tests.yml`, `requirements.txt`,
  `scripts/publish_check.py` passes.
- **G presentation pack:** done. DEMO_SCRIPT.md (timing section fills itself after Phase C), RUBRIC_MAP.md,
  VIVA_NOTES.md (eight framing questions), AI_USE_DISCLOSURE.md draft.

## Demo rework (2026-11-16/17): nothing decorative or staged

- **0 measured first:** `reports/results/lab_check.json` (300k rows). Random vs time split: LightGBM unregularized
  PR-AUC 0.677 vs 0.349, regularized 0.565 vs 0.401; LR 0.399 vs 0.373. Later builds (valA): LightGBM 0.141 without
  vs 0.189 with regularization. Gaps are large for LightGBM, small for LR, so the Lab was built.
- **1 Real PRs page:** 80 held-out Kafka/TVM builds (`demo_bundle/real_prs`, stack APFDc equals stored values,
  `verify --bundle real_prs` matches raw LRTS); W/T/L over all held-out builds Kafka 6,264/121/1,693, TVM 144/82/51;
  wins come from recurring failures, not flaky (`reports/results/real_prs_wins.json`). Animated race, race replay
  page and savings calculator removed.
- **2 ML Lab page:** live LR / RF / LightGBM on a 4.5 MB bundled sample; each fit ≤ 17 s on battery; four guided
  experiments with computed takeaways; `notebooks/lab_by_hand.ipynb` (56 code lines).
- **3 GitHub CI:** remote `Abhijeetgupta55/synthesis` (no `OWNER` left). `.github/workflows/smartci-compare.yml`
  (jobs default / rule / model + report: job summary and PR comment via `smartci.ci_report`), baseline committed to
  the fork's `smartci-base` as `.smartci-baseline/` by `make_branches.py` (dry run on a local clone OK; the three job
  commands checked locally). Fork, push and PRs: HUMAN_TODO 1–2. `reports/PUBLIC_RUNS.md` has no run yet.
- **4 Break the code:** two real pytest processes streamed with a stopwatch incl. start-up, real traceback
  (`stp.demo.live_run`); recordings fallback. **Recordings pending mains power** (HUMAN_TODO 0).
- **5** queue position + test time + end-to-end shown together everywhere a time is shown.
- **6** README and DEMO_SCRIPT in the order ML Lab → Real PRs → GitHub PR → honest verdict; VIVA_NOTES has five new
  questions; smoke test covers the eight pages (presses Train, the four experiments and Show me a loss).

## Next

1. On mains power: HUMAN_TODO 0 (recordings, optionally Phase C), then regenerate reports and commit.
2. Students: HUMAN_TODO 1 (push), 2 (fork + PRs + collect runs), 4 (disclosure), 5 (rehearse).

## How to resume

"Continue finishing smartci. Read docs/PROMPT_FINISH.md, STATUS.md and reports/AUDIT.md, then resume from the next
unfinished step."
