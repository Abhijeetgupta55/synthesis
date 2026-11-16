# HUMAN_TODO

Tasks Claude Code cannot do itself (account actions, pushing, hardware, course-policy decisions).
Each item has exact steps. Remove an item once it is done. Commands are PowerShell, run from the repository root.

## Open

0. **Timing on mains power (live recordings, Phase C, GATE 5).** On battery Windows throttles the CPU, so no timing
   from this laptop counts until it is plugged in. Plug in, close heavy programs, set Windows to never sleep
   (Settings → System → Power → "When plugged in, put my device to sleep after" → Never), then:
   ```powershell
   .venv\Scripts\python.exe -m stp.demo.live_run --mode sequential          # 3 seeded held-out bugs, ~10-15 min
   .venv\Scripts\python.exe -m stp.demo.live_run --mode side-by-side        # same bugs, as on the dashboard
   .venv\Scripts\python.exe live_demo\phase_c.py --repeats 3                # optional, ~2-3 h: GATE 5 + timing table
   ```
   The first two write `demo_bundle/recordings/*.json` (real logs, real stopwatch, queue positions). The *Break the
   code* page shows them when the NetworkX clone is absent (for example on Streamlit hosting). Then tell Claude Code
   "recordings are done" so it regenerates the reports and commits.

1. **Push this repository** (the fork's CI installs smartci from it). Remote: `github.com/Abhijeetgupta55/synthesis`
   (already set as `origin`; `OWNER` placeholders are already replaced).
   ```powershell
   .venv\Scripts\python.exe scripts\publish_check.py     # confirms no data, clones or pickles are tracked
   git push -u origin main
   ```
   On GitHub → **Actions**, the `tests` workflow should turn green in ~10 minutes.

2. **Real CI on a NetworkX fork (the "GitHub PR" part of the demo).**
   1. On github.com open https://github.com/networkx/networkx → **Fork** → owner `Abhijeetgupta55`, name `networkx`
      → Create fork.
   2. In the fork: **Actions** tab → "I understand my workflows, go ahead and enable them".
   3. Clone it next to this repository and make the branches (`smartci-base` with the workflow and the `.smartci`
      baseline, plus one branch per bug):
      ```powershell
      git clone https://github.com/Abhijeetgupta55/networkx.git ..\networkx-fork
      .venv\Scripts\python.exe live_demo\public_ci\make_branches.py --fork-dir ..\networkx-fork `
          --smartci-dir external\networkx\.smartci --n 5 --seed 1 --push
      ```
   4. For each pushed branch `smartci-bug-…`: on GitHub → **Pull requests** → **New pull request** → base
      repository **Abhijeetgupta55/networkx**, base **smartci-base** (not networkx/networkx, not main), compare
      `smartci-bug-…` → Create. Each PR starts the `smartci-compare` workflow: jobs `default`, `rule`, `model`,
      then `report`, which comments on the PR (top 10 tests with probability and reasons, the failing test's queue
      position in each order, each job's time) and writes the job summary.
   5. When the runs have finished (~10 minutes each), collect them:
      ```powershell
      $env:GITHUB_TOKEN = "<a fine-grained token with read access to Actions on the fork>"
      .venv\Scripts\python.exe live_demo\public_ci\collect_runs.py --repo Abhijeetgupta55/networkx
      git add reports\PUBLIC_RUNS.md reports\results\public_runs.json live_demo\public_ci\branches.json
      git commit -m "Public CI runs on the NetworkX fork"; git push
      ```
      `reports/PUBLIC_RUNS.md` then holds the run links and GitHub's own job and step durations.

3. **Optional: put the dashboard online (free).** https://share.streamlit.io → sign in with GitHub → **Create app**
   → repository `Abhijeetgupta55/synthesis`, branch `main`, main file `app/demo.py`, Python 3.11 → Deploy.
   It reads only `demo_bundle/`; ML Lab trains live there too. Without the NetworkX clone, *Break the code* shows
   the recordings from item 0.

4. **Complete `reports/AI_USE_DISCLOSURE.md`.** Fill every **[STUDENTS: …]** blank with what the team decided,
   checked and wrote, and the member table.

5. **Before the presentation:** read `reports/DEMO_SCRIPT.md`; rehearse once plugged in; learn the questions at the
   top of `reports/VIVA_NOTES.md`; each member should explain the rubric items in `reports/RUBRIC_MAP.md`.
