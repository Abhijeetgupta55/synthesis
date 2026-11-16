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

1. **Done 2026-11-17: repository pushed; NetworkX fork CI running.** Fork `Abhijeetgupta55/networkx`, branch
   `smartci-base` (workflow + `.smartci-baseline/`), five bug branches, PRs #1–#5 against `smartci-base`
   (https://github.com/Abhijeetgupta55/networkx/pulls), each with the three-job comparison and its PR comment.
   To add more bugs later: `make_branches.py --fork-dir A:\ML
etworkx-fork --smartci-dir external
etworkx\.smartci
   --n 10 --seed 2 --push`, open PRs against `smartci-base`, then
   `$env:GITHUB_TOKEN = (gh auth token); .venv\Scripts\python.exe live_demo\public_ci\collect_runs.py --repo Abhijeetgupta55/networkx`.

2. **Optional: put the dashboard online (free).** https://share.streamlit.io → sign in with GitHub → **Create app**
   → repository `Abhijeetgupta55/synthesis`, branch `main`, main file `app/demo.py`, Python 3.11 → Deploy.
   It reads only `demo_bundle/`; ML Lab trains live there too. Without the NetworkX clone, *Break the code* shows
   the recordings from item 0.

3. **Complete `reports/AI_USE_DISCLOSURE.md`.** Fill every **[STUDENTS: …]** blank with what the team decided,
   checked and wrote, and the member table.

4. **Before the presentation:** read `reports/DEMO_SCRIPT.md`; rehearse once plugged in; learn the questions at the
   top of `reports/VIVA_NOTES.md`; each member should explain the rubric items in `reports/RUBRIC_MAP.md`.
