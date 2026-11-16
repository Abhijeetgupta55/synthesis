# AI use disclosure (DRAFT: the students must complete and correct this before submitting)

This is a factual draft. It states only what the repository itself shows. Everything marked **[STUDENTS: …]** must
be filled in by the team; do not leave a blank unfilled and do not keep a sentence you cannot stand behind.
Check your course's policy on AI assistance before submitting.

## What the repository shows

- **All commits carry an AI co-author line.** Every commit in the git history (`git log`) ends with
  `Co-Authored-By: Claude …`, i.e. it was made in a session with an AI coding assistant (Claude Code). The
  history starts 2026-09-28.
- **Prompts given to the assistant are in the repository:** `docs/PROMPT.md` (research pipeline, tool, demo) and
  `docs/PROMPT_FINISH.md` (audit, cleanup, dashboard, presentation pack). They define the phases, gates, rules and
  deliverables the assistant worked to.
- **Work produced with AI coding assistance** (code written, run and debugged in those sessions):
  - the research pipeline in `src/stp/` (data download and tables, EDA, as-of feature store, leakage tests,
    evaluation harness, baselines and paper reproduction, model training, tuning, calibration, ensembles,
    ablations, transfer, export, error analysis, probability-floor study);
  - the `smartci` tool in `src/smartci/` (CLI, pytest plugin, scoring, mining, mutation, backtest, compare);
  - the dashboard `app/demo.py` and the demo bundle builder;
  - all generated reports in `reports/` (their text templates live in `src/stp/reports/`), figures, the README,
    the demo script, the rubric map and the viva notes;
  - this draft.
- **Checks that are automated and repeatable** (anyone can re-run them): `pytest` (unit, leakage and parity tests),
  `python -m stp.demo.smoke`, `scripts/audit_spotcheck.py` (independent recomputation from raw data),
  `scripts/audit_runs.py` + `python -m stp.reports.audit_md` (reports/AUDIT.md), `scripts/publish_check.py`.

## What the students decided and checked themselves

**[STUDENTS: replace this section with your own account. Examples of what to state, only if true:]**

- **[STUDENTS: who chose the project topic and the LRTS dataset, and why]**
- **[STUDENTS: which design decisions you made or changed (e.g. the as-of rule, the subsets, the metrics, the
  choice of NetworkX, the honest framing), and which you accepted from the assistant after review]**
- **[STUDENTS: which results you checked by hand, how (e.g. re-ran `python -m stp.demo.verify` on builds you picked,
  read the error analysis, compared a report number with its JSON), and what you found]**
- **[STUDENTS: which parts of the code each member read and can explain in the viva]**
- **[STUDENTS: what you wrote or rewrote yourselves (slides, report text, code), if anything]**
- **[STUDENTS: anything the assistant got wrong that you caught, and anything it got wrong that it caught itself;
  `reports/WORKLOG.md` and `reports/AUDIT.md` record several self-corrections you can cite]**

## Team

| Member | Role in the project | Parts you can explain in the viva |
|---|---|---|
| **[STUDENTS]** | | |
| **[STUDENTS]** | | |
| **[STUDENTS]** | | |
