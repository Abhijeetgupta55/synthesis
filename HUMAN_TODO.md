# HUMAN_TODO

Tasks Claude Code cannot do itself (account actions, pushing, publishing, hardware, course-policy decisions).
Each item has exact steps. Remove an item once it is done.

## Open

0. **Phase C timing: plug the laptop into mains power, close other heavy programs, then run one command.**
   On battery Windows throttles the CPU (~42% of nominal measured), so GATE 5 and the live-demo timings cannot be
   judged. The script refuses to start on battery.
   ```powershell
   cd <your clone of this repository>
   .venv\Scripts\python.exe live_demo\phase_c.py --repeats 3     # ~2-3 hours: profile, GATE 5, 3x live-demo timings
   ```
   Then tell Claude Code "Phase C timings are done" so it writes the timings into `reports/DEMO_SCRIPT.md`,
   regenerates REAL_WORLD.md (GATE 5) and picks the recommended demo variant (full suite vs `networkx/algorithms`).
   Set Windows to never sleep while it runs (item 1).
1. **Keep the machine awake during long jobs.** The Phase 1 feature-store build and Phase 3 tuning run for hours.
   On Windows: Settings → System → Power → "When plugged in, put my device to sleep after" → **Never**, while jobs run.
   (Jobs are resumable per project, so an interruption costs only the unfinished project.)
2. **Free RAM if possible.** Often only about 1-2 GB of 16 GB is free. Closing browsers and IDE windows during
   long jobs (Phase C timing included) makes them faster and the timings cleaner. Nothing breaks if you don't.
3. **Publish the repository on GitHub** (Claude Code does not push). Check your course policy first. The LRTS data,
   the NetworkX clone and all model pickles are git-ignored; `python scripts/publish_check.py` confirms that nothing
   unsafe is tracked (last result: `reports/results/publish_check.json`).
   1. On github.com: **New repository** → name `smart-ci-tcp` → Public (or Private) → **do not** add a README,
      .gitignore or licence → Create.
   2. Replace the placeholder `OWNER` with your GitHub user name (PowerShell, in the repository root):
      ```powershell
      $u = "your-github-name"
      foreach ($f in "action.yml", ".github\workflows\smartci-compare.yml", ".github\workflows\smartci-shadow.yml",
                     "live_demo\public_ci\collect_runs.py", "src\stp\reports\readme_md.py") {
        (Get-Content $f -Raw) -replace 'OWNER', $u | Set-Content $f -Encoding utf8 -NoNewline }
      .venv\Scripts\python.exe -m stp.reports.readme_md        # README badge and install URL
      git commit -am "Set GitHub owner"
      ```
   3. Push:
      ```powershell
      git remote add origin https://github.com/$u/smart-ci-tcp.git
      git branch -M main
      git push -u origin main
      ```
   4. On GitHub → **Actions**: the `tests` workflow runs on the push and should turn green within ~10 minutes; the
      README badge then shows "passing". (`smartci-compare` / `smartci-shadow` are for item 5 and can stay idle.)
4. **Optional, speeds up the NetworkX runs:** WSL's VM holds ~0.8 GB (`vmmemWSL`). If you don't need WSL right now,
   run `wsl --shutdown` in PowerShell. Closing Chrome frees another ~1 GB. Collecting NetworkX's 10,120 tests took
   289 s under the current memory pressure.
5. **Public CI proof (Phase 5.3).** After item 3 and after the NetworkX backtest exists:
   ```bash
   # a) fork https://github.com/networkx/networkx on GitHub (button "Fork"), then:
   git clone https://github.com/<you>/networkx.git ../networkx-fork
   # b) in .github/workflows/smartci-compare.yml (this repo) the install step uses
   #    "smartci @ git+https://github.com/<you>/smart-ci-tcp.git": the owner must be set first (item 3)
   python live_demo/public_ci/make_branches.py --fork-dir ../networkx-fork --smartci-dir external/networkx/.smartci --n 10 --seed 1 --push
   # c) on GitHub, open one pull request per pushed branch against your fork's main (or run the workflow manually
   #    from the Actions tab: "smartci-compare" -> Run workflow -> pick the branch)
   # d) when the runs finish:
   set GITHUB_TOKEN=<read-only token>          # PowerShell: $env:GITHUB_TOKEN="..."
   python live_demo/public_ci/collect_runs.py --repo <you>/networkx
   ```
   This writes `reports/PUBLIC_RUNS.md` with links to every public run.
6. **Optional: put the dashboard online (free).** After item 3: go to https://share.streamlit.io → sign in with
   GitHub → **Create app** → repository `<you>/smart-ci-tcp`, branch `main`, main file `app/demo.py`, Python 3.11
   → Deploy. It installs only `requirements.txt` (streamlit, pandas, numpy, matplotlib, lightgbm) and reads only
   `demo_bundle/`; it needs about 275 MB of memory (`reports/results/app_memory.json`), within the free tier.
   Put the app's URL at the top of README (edit `src/stp/reports/readme_md.py`, regenerate, commit, push).
7. **Complete `reports/AI_USE_DISCLOSURE.md`.** It is a factual draft: fill every **[STUDENTS: …]** blank with what
   the team decided, checked and wrote, and the member table. Do not leave invented or untrue sentences.
8. **Before the presentation:** read `reports/DEMO_SCRIPT.md` (60-second pitch, 7-minute demo, general-audience
   variant) and `reports/EXPLAINER.md`; rehearse once with the laptop plugged in;
   learn the eight answers at the top of `reports/VIVA_NOTES.md`. Each member should be able to explain the rubric
   items in `reports/RUBRIC_MAP.md` in their own words.
