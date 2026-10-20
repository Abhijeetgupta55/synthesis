# Live demo: smartci on a real repository

Everything here runs real pytest on a real open-source repository. Nothing is precomputed for the repo you pick.

## NetworkX (pinned)

| | |
|---|---|
| Repository | https://github.com/networkx/networkx (BSD-3-Clause) |
| Pinned commit | `abf2feda2252ee4e0d5a66964addf179225dfe76` (2026-10-17) |
| Location | `external/networkx` (git-ignored) |
| Python | 3.12 (NetworkX requires ≥ 3.12), its own venv at `external/networkx/.venv` |

Setup (Windows PowerShell or Git Bash; `uv` from https://docs.astral.sh/uv/):

```bash
git clone https://github.com/networkx/networkx.git external/networkx
git -C external/networkx checkout abf2feda2252ee4e0d5a66964addf179225dfe76
cd external/networkx
uv venv --python 3.12 .venv
uv pip install --python .venv -e ".[default,test]"
uv pip install --python .venv -e ../..          # smartci (this repository), editable
```

Then, from `external/networkx` with that venv's Python (`.venv/Scripts/python` on Windows, `.venv/bin/python` elsewhere):

```bash
smartci profile                      # two full runs on the clean base: durations, default order, flaky tests
smartci coverage-map                 # one run under coverage: which test files execute which lines
smartci learn --since 2024-01-01     # mine and reproduce test-backed bug fixes (all candidates, no hand-picking)
smartci mutate --n 300 --seed 42     # seeded mutants killed by existing tests
smartci backtest --set both          # simulated time to first failure vs the simple baselines
smartci compare --bug <fix-sha>      # real side-by-side pytest -x runs for one bug (default vs --smartci)
```

`scripts/run_live_compare.ps1` / `.sh` wraps the last command for any bug in the backtest table.

## Second repository

Selection criteria and the chosen repository are documented in `reports/REAL_WORLD.md` (Phase 5.2).

## Public CI proof

`live_demo/public_ci/` creates one branch per held-out bug on *your* fork, with the `smartci-compare` workflow,
so the timings come from GitHub's machines (steps in `HUMAN_TODO.md`).
