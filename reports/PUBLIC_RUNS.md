# PUBLIC_RUNS

**No public run yet.** The workflow (`.github/workflows/smartci-compare.yml`: jobs `default`, `rule`, `model`,
`report`) and the branch script are ready; the fork, the push and the pull requests are account actions
(HUMAN_TODO item 2). This file is overwritten by `live_demo/public_ci/collect_runs.py` with the run links and
GitHub's own job and step durations.

Local check of the same three job commands (2026-11-17, on battery, so these times do not count), NetworkX bug
d8081795 ("BUG: Fix k_components losing or truncating k-components"), tests limited to
`networkx/algorithms/connectivity`:

| Order | Queue position of the failing file | Test s until it fails | pytest launch → exit s |
|---|---|---|---|
| default | 6 of 8 | 2.67 | 4.7 |
| rule (changed_files_first) | 2 of 8 | 1.25 | 3.2 |
| model | 1 of 8 | 0.24 | 2.2 |
