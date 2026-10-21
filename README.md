# smart-ci-tcp — smartci: run the tests most likely to fail first

Two things on one codebase:

1. **A research pipeline on LRTS** (ISSTA 2024; 108,366 real CI test-suite runs from 10 Apache projects, ~104M
   (run, test class) results): leak-free *as-of* features, baselines (paper reproduction), and a classification model
   (LR / RF / LightGBM, ensembles) that ranks test classes by P(fail) / expected duration.
2. **`smartci`, an installable pytest tool** for any Python + pytest git repository. It reorders test *files* so the
   ones most likely to fail for your change run first — **it never skips a test; the worst case is no speed-up** —
   and proves itself on *your* repo against simple baselines, with real pytest runs and auditable receipts.

Results: [`reports/RESULTS.md`](reports/RESULTS.md) (story), [`BASELINES.md`](reports/BASELINES.md),
[`FEATURES.md`](reports/FEATURES.md), [`MODELING.md`](reports/MODELING.md), [`REAL_WORLD.md`](reports/REAL_WORLD.md),
[`VIVA_NOTES.md`](reports/VIVA_NOTES.md), [`SLIDE_NUMBERS.md`](reports/SLIDE_NUMBERS.md),
EDA: [`EDA_REPORT.md`](reports/EDA_REPORT.md). Every number in those reports is generated from
`reports/results/*.json` by `src/stp/reports/*`. Progress log: [`reports/WORKLOG.md`](reports/WORKLOG.md),
[`STATUS.md`](STATUS.md); tasks for humans: [`HUMAN_TODO.md`](HUMAN_TODO.md).

## smartci

### Install (into the venv you run your tests with)

```bash
pip install -e path/to/smart-ci-tcp        # or: pip install "smartci @ git+https://github.com/<owner>/smart-ci-tcp.git"
```

The pytest plugin is registered automatically but **does nothing unless you pass `--smartci`** (or set `SMARTCI=1`).

### The five commands

```bash
smartci profile          # run the suite twice on the clean base commit: per-test durations, pytest's real order,
                         # flaky tests (inconsistent outcomes) — excluded from every benchmark
smartci learn            # mine your history for test-backed bug fixes, reproduce each one (fix commit with the
                         # source reverted), keep only real failures; fit a small per-repo adapter (≥ 20 bugs)
smartci backtest         # for every held-out bug: time to the first failure under pytest's default order, random,
                         # fastest-first, recently-failed-first, changed-files-first, coverage-first and smartci
smartci compare --bug X  # really run `pytest -x` twice (default order vs --smartci) in two git worktrees
smartci explain          # why the top-ranked test files are ranked where they are, in plain sentences
```

Then use it: `pytest --smartci` (prioritise) or `pytest --smartci-shadow` (rank and record, keep the order; see
`smartci report`). Optional: `smartci coverage-map` (enables coverage-first and the coverage signal),
`smartci mutate --n 300 --seed 42` (synthetic never-seen bugs). In CI: `action.yml`,
`.github/workflows/smartci-compare.yml` (default vs smartci on the same commit), `smartci-shadow.yml`.

### Safety

smartci only reorders whole test files (pytest's order inside a file is kept); it never deselects or skips a test.
If anything goes wrong while ranking, it prints one line and keeps pytest's order. It works in git worktrees under
`.smartci/worktrees/` and never touches your checkout (`.smartci/` is excluded via `.git/info/exclude`).

### Reading a receipt (`.smartci/receipts/*.json`)

Each `--smartci` session writes one: base and head SHAs, a hash of the diff, the model version, pytest's original
file order, and for every test file its rank, features, calibrated P(fail), expected duration and priority
(= P / duration); after the run, each file's real outcome and duration and when the first failure was reported.
You can recompute every rank from the stored features with the published model in `src/smartci/model/`.

### What the baselines mean and when to trust them

`backtest` always reports the best *simple* rule next to smartci, with win/tie/loss and bootstrap CIs, and lists
every loss. **If a simple rule is as good or better on your repo, the report says so and recommends it.** On
NetworkX, for example, smartci reaches the first failure about 100× sooner than pytest's default order but only ties
coverage-first / changed-files-first (REAL_WORLD.md).

### Limitations

Mined bugs are reintroduced known bugs (regression catching); mutants are synthetic; the global model was trained on
Apache CI data (Java/Scala + TVM's Python suites); smartci's own start-up cost (imports, git diff, scoring: a few
seconds) is paid on every run, so very short suites gain nothing.

## Research pipeline (LRTS)

```bash
uv venv --python 3.11 .venv && uv pip install --python .venv -e ".[research,dev]"
python -m stp.data.download            # LRTS repo + 3 GB data (14.8 GB extracted)
python -m stp.data.build_tables        # data/interim/*.parquet
python -m stp.data.verify_facts        # Phase 0 facts -> reports/results/phase0_facts.json
python -m stp.data.splits              # build-level chronological split + rolling windows
python -m stp.data.build_diffs         # per-change files and diff tokens from the raw compare JSON
python -m stp.features.store           # as-of feature store, 104M rows (streaming, per project, resumable)
python -m stp.features.verify_store    # leakage checks (brute force on 50 random runs, single-feature scan)
python -m stp.baselines.lrts_repro     # GATE 2: paper reproduction, start-order vs as-of
python -m stp.baselines.run_baselines  # as-of baselines on val/test with PR-clustered CIs
python -m stp.models.pipeline          # data, scope, LR/RF/LightGBM tuning, calibration, evaluation, variants, export
python -m stp.models.figures
python -m stp.reports.baselines_md && python -m stp.reports.features_md && python -m stp.reports.modeling_md
python -m stp.reports.real_world_md && python -m stp.reports.results_md && python -m stp.reports.viva_md
pytest
```

Memory: every stage streams per project and caps DuckDB at 1.5 GB (the development machine had ~2 GB free).

## Running the demo

```powershell
scripts\setup_demo.ps1        # .venv-demo with pinned requirements-demo.txt (once)
scripts\run_demo.ps1          # http://localhost:8501, fully offline
```

(`scripts/setup_demo.sh` / `run_demo.sh` on Linux/macOS.) The app reads only `demo_bundle/` (committed, 36 MB) and,
optionally, a `.smartci/` folder you point it at. Pages: *Try it on a real repo* (bug table with commit links and a
three-lane race), *The 108k-build study* (random held-out Apache build, real PR link, full ordered list, CSV download,
and a `python -m stp.demo.verify …` command that recomputes everything from the raw LRTS `test_class.csv.zip`),
*Why this test?*, *Scoreboard*, *Honesty*.

- Fallback without a browser: `python -m stp.demo.cli --seed 42`.
- Screenshots of every page: `python scripts/capture_screenshots.py` (needs Playwright).
- Smoke test: `python -m stp.demo.smoke` (renders every page headlessly, checks scoreboard numbers against
  `reports/results/`, recomputes 20 random replays from raw files and 5 backtest rows per repo).
- Live side-by-side runs: `scripts\run_live_compare.ps1 -Repo external\networkx -Bug <id>` (see `live_demo/README.md`).

**Fresh-clone test** (what a teammate does): `git clone …`, `scripts\setup_demo.ps1`, `scripts\run_demo.ps1`. The
demo pages need nothing else; `stp.demo.verify` additionally needs the raw LRTS data (`python -m stp.data.download`).

## Layout

| Path | What |
|---|---|
| `src/stp/` | research pipeline: `data/`, `eda/`, `features/` (pure as-of functions + store), `evaluation/`, `baselines/`, `models/`, `reports/`, `demo/` |
| `src/smartci/` | the tool: `cli`, `plugin`, `gitdiff`, `history`, `scoring`, `treemodel`, `receipts`, `profile`, `learn`, `coverage_map`, `mutate`, `backtest`, `compare`, `explain`, `shadow`, `runner`, `repair`; `model/` = packaged model |
| `models/global/` | exported model, calibrators, schema, MODEL_CARD.md |
| `app/demo.py`, `demo_bundle/` | Streamlit demo and its data |
| `live_demo/` | NetworkX setup, GATE 5 script, public-CI scripts |
| `reports/` | generated reports, `results/*.json`, `figures/` |
| `data/`, `external/` | git-ignored (LRTS data, LRTS repo, NetworkX / sympy clones) |
