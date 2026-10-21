# HUMAN_TODO

Tasks Claude Code cannot do itself (account actions, pushing, publishing, hardware, course-policy decisions).
Each item has exact steps. Remove an item once it is done.

## Open

1. **Keep the machine awake during long jobs.** The Phase 1 feature-store build and Phase 3 tuning run for hours.
   On Windows: Settings → System → Power → "When plugged in, put my device to sleep after" → **Never**, while jobs run.
   (Jobs are resumable per project, so an interruption costs only the unfinished project.)
2. **Free RAM if possible.** Only about 2 GB of 16 GB is free. Closing browsers and IDE windows during the feature
   build and model training makes them faster. Nothing breaks if you don't.
3. **Publish the repository (needed by the GitHub Action and the public CI proof).**
   ```bash
   # create an empty repo on GitHub first, e.g. <you>/smart-ci-tcp, then:
   git remote add origin https://github.com/<you>/smart-ci-tcp.git
   git push -u origin master
   ```
   Then replace the placeholder `OWNER` with your GitHub user name in `action.yml`,
   `.github/workflows/smartci-compare.yml` and `.github/workflows/smartci-shadow.yml`, and commit.
   Check course policy first: the LRTS data itself is *not* in the repo (it is git-ignored); only code,
   generated results JSON and reports are.
4. **Optional, speeds up the NetworkX runs:** WSL's VM holds ~0.8 GB (`vmmemWSL`). If you don't need WSL right now,
   run `wsl --shutdown` in PowerShell. Closing Chrome frees another ~1 GB. Collecting NetworkX's 10,120 tests took
   289 s under the current memory pressure.
5. **Public CI proof (Phase 5.3).** After item 3 and after the NetworkX backtest exists:
   ```bash
   # a) fork https://github.com/networkx/networkx on GitHub (button "Fork"), then:
   git clone https://github.com/<you>/networkx.git ../networkx-fork
   # b) in .github/workflows/smartci-compare.yml (this repo) the install step uses
   #    "smartci @ git+https://github.com/OWNER/smart-ci-tcp.git": OWNER must be replaced first (item 3)
   python live_demo/public_ci/make_branches.py --fork-dir ../networkx-fork --smartci-dir external/networkx/.smartci --n 10 --seed 1 --push
   # c) on GitHub, open one pull request per pushed branch against your fork's main (or run the workflow manually
   #    from the Actions tab: "smartci-compare" -> Run workflow -> pick the branch)
   # d) when the runs finish:
   set GITHUB_TOKEN=<read-only token>          # PowerShell: $env:GITHUB_TOKEN="..."
   python live_demo/public_ci/collect_runs.py --repo <you>/networkx
   ```
   This writes `reports/PUBLIC_RUNS.md` with links to every public run.
