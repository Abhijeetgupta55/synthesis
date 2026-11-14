# Claude Code prompt: verify, finish and make smartci demo-ready

**How to use it.** Open Claude Code in `A:\ML\smart-ci-tcp`, with the laptop plugged in, and paste everything below the line. The work will take more than one session. For every later session, paste only:

> "Continue finishing smartci. Read docs/PROMPT_FINISH.md, STATUS.md and reports/AUDIT.md, then resume from the next unfinished step."

---

# What this project is

You are finishing **smartci**, a group project for a university **Machine Learning course**. First save this whole prompt verbatim to `docs/PROMPT_FINISH.md` and commit it. Where it conflicts with the older `docs/PROMPT.md`, this prompt wins.

**The project in one sentence:** predict which tests will fail for a given code change, and run those tests first, so a broken change is caught in seconds instead of after the whole suite. Nothing is ever skipped; only the order changes.

**It has two halves that share one codebase:**

1. **The ML study (this is what the course grades).** A binary classifier trained on the LRTS dataset: 108,366 real CI runs from 10 Apache projects, about 104M (run, test class) rows. For each row it predicts "will this test fail in this run?". Tests are then ordered by predicted probability ÷ expected duration.
2. **The tool.** `smartci`, a Python package with a command-line interface and a pytest plugin. It applies the trained model to any Python repo that uses pytest, and measures itself against simple ordering rules.

**The course rubric** has seven items. Each must be visible in the final demo and explainable by the students: (1) EDA, (2) feature derivation, (3) classification, (4) regularization, (5) hyperparameter tuning, (6) ensembles, (7) performance analysis. The rubric also says students must show they understand every technique: what it is, why it was chosen, and what the result means.

**The audience for the demo** is a professor who knows ML but has little CI/CD experience. The demo has to make the problem obvious in one minute, show the ML clearly, and be honest about results.

**The honest headline, which the whole presentation is built around:**

> Reordering tests helps enormously. ML gives a modest gain over simple rules on recurring failures, and loses to "fastest test first" on tests that fail for the first time.

So the project is framed as a question it tested: **"When does ML beat simple rules for ordering tests, and when doesn't it?"** A mixed result with a clear explanation is the goal. Never present the ML as better than the numbers show.

**Naming.** The project was originally called a "self-healing CI/CD pipeline". It does not heal anything, so remove that phrase everywhere. Use: **"smartci: predicting CI test failures to run the right tests first"**.

# What the finished product looks like

This is not a browser extension and it has no web server or database. It is four things:

| Part | What it is | How it is shown |
|---|---|---|
| The engine | The `smartci` Python package: CLI + pytest plugin + the exported model | In a terminal, live, on a real open-source repo (NetworkX) |
| The front end | A Streamlit dashboard, `app/demo.py`, reading only a small bundle of precomputed results | In a browser on the laptop, offline (`streamlit run app/demo.py`) |
| The evidence | Generated reports in `reports/` | Linked from the README and the app |
| The home | A GitHub repository with a README, screenshots and a CI workflow | Shared as a link |

# State of the repo (believed; Phase A verifies it)

Last commit is `d5c2b48` (2026-10-22). There is no git remote. The working tree was clean. About 9.6 GB of disk is free. RAM is tight: often only about 2 GB of 16 GB is free.

**Believed done:** feature store (104M rows, about 1.7 GB), leakage tests, paper reproduction, baselines, three tuned classifiers, calibration, voting and stacking, ablations, TVM transfer, model export, the smartci tool, NetworkX mining (68 reproducible bugs), 300 NetworkX mutants, backtest, a five-page Streamlit app, a 48 MB demo bundle, setup/run scripts, and these reports: `EDA_REPORT`, `FEATURES`, `BASELINES`, `MODELING`, `RESULTS`, `REAL_WORLD`, `VIVA_NOTES`, `SLIDE_NUMBERS`.

**Believed unfinished or wrong:**

- GATE 5 (simulated vs real timing) failed 11/20, because the laptop was on battery and Windows throttled the CPU.
- The second repo (sympy) was started and never finished; its results are empty.
- `STATUS.md` is out of date.
- The app has no page that walks through the seven rubric items.
- Nothing is on GitHub.

**Numbers the reports are believed to contain** (from `reports/SLIDE_NUMBERS.md`):

| Quantity | Value |
|---|---|
| Failure rate per (run, test class) | 0.243% |
| Accuracy of always predicting "pass" | 99.76% |
| PR-AUC on the held-out test set: LR / RF / LightGBM / vote / stack | 0.193 / 0.195 / 0.218 / 0.220 / 0.227 |
| APFDc, all failed runs: stack / LightGBM / ChangedOrNewFirst / cbt_LastFail | 0.880 / 0.871 / 0.863 / 0.851 |
| LightGBM − ChangedOrNewFirst, all failed runs | +0.008, CI [−0.002, +0.019] |
| LightGBM − cbt_LastFail, all failed runs | +0.020, CI [+0.008, +0.032] |
| APFDc, first-time failures of existing tests: LightGBM / QTF | 0.708 / 0.800 (Δ −0.092, CI [−0.134, −0.053]) |
| NetworkX, 318 bugs, median seconds to first failure: default / smartci / changed-files-first | 124.74 / 0.09 / 0.08 |
| TVM-only model PR-AUC, validation / test | 0.680 / 0.037 |

# Rules for all of this work

1. **Verify before you build.** Phase A comes first and changes nothing except writing the audit.
2. **Never type a number by hand.** Every number in a report, the README, the app or the demo script is generated from `reports/results/*.json` or from a repo's `.smartci/` outputs.
3. **Do not rebuild the feature store, retrain the models or rerun tuning** unless the audit proves a result is wrong. Those jobs take many hours on this machine. If you believe a rerun is needed, stop and explain why in `reports/AUDIT.md`.
4. **Timing work needs mains power.** Before any step that measures time, check that the laptop is on AC power. If it is on battery, skip the timing steps, add a line to `HUMAN_TODO.md`, and continue with other work.
5. **Memory and disk are tight.** Run one heavy job at a time. Check free disk before writing large files.
6. **Show losses.** Wherever smartci or the model is compared with something, the cases it loses stay visible.
7. **Write for students.** Every explanation in the app and the reports must be understandable by a third-year student in three sentences. Prefer plain words.
8. **Commit after each step** with a clear message. Keep `STATUS.md` current. Anything only a person can do goes into `HUMAN_TODO.md` with exact steps.

# Phase A: audit what exists

Write `reports/AUDIT.md`: one table with a row per item below and the columns *claim*, *how checked*, *result (pass / fail / partly)*, *evidence (file or command)*.

1. **Tests.** Run the full test suite. Report passed, failed and skipped counts, and why anything is skipped.
2. **Gates 0–4.** For each, find the result file and confirm it says what `STATUS.md` and `WORKLOG.md` claim.
3. **Numbers.** Regenerate `SLIDE_NUMBERS.md`, `RESULTS.md`, `MODELING.md`, `BASELINES.md` and `REAL_WORLD.md` with their generators and diff against the committed versions. Then confirm every value in the table above. Report any difference.
4. **Independent spot checks.** For three randomly chosen held-out LRTS runs (log the seed), recompute APFDc for one baseline and for the shipped model directly from the raw `test_class.csv.zip` and the stored scores, without using the evaluation harness. They must match the stored per-run values.
5. **Rubric deliverables.** For each of the seven rubric items, list the report section, the figure files and the result file that cover it. Open each figure to confirm it exists and is not empty. Flag anything thin or missing.
6. **The exported model.** In a fresh virtual environment with no access to the LRTS data, `pip install -e .`, load the model and score a small synthetic example.
7. **The tool.** On the small fixture repo, run `smartci profile`, `learn`, `backtest` and `compare` end to end.
8. **The app.** Run `python -m stp.demo.smoke`. Start the app and confirm that each page renders.
9. **Leftovers.** List everything that is stale, empty or half-done: sympy outputs, `external/cand_*` clones and their sizes, stale STATUS lines, placeholder `OWNER` strings, any remaining "self-healing" wording.

**GATE A:** `reports/AUDIT.md` exists and every row has a result. Summarize the failures at the top. If a headline number is wrong, stop here and report.

# Phase B: clean up and reframe

1. **Drop sympy.** Remove it from the reports, the bundle, the app and `real_world.json`, so that nothing shows an empty second repo. State once in `REAL_WORLD.md` that a second repo was attempted and not completed.
2. **Free disk.** Delete the candidate clones `external/cand_attrs`, `external/cand_black`, `external/cand_pydantic` and `external/cand_sympy`, after confirming they are git-ignored and nothing references them. Report the space freed.
3. **Rename and reframe.** Apply the name and the headline from the top of this prompt to `README.md`, `RESULTS.md`, the app and the model card.
4. **Explain the two losses with evidence, not assertion.** Add a short error-analysis section to `RESULTS.md`:
   - **Why the model loses to QTF on first-time failures.** Test this hypothesis: the model ranks tests that have failed before ahead of tests that have never failed, and that costs time when the failing test is one that has never failed. Show where first-time-failing tests land in the model's order compared with QTF's order, and what share of test time is spent before them.
   - **Why the TVM-only model collapses from validation to test** (0.680 → 0.037). Check for drift: failure rate, share of unseen test classes, and feature distributions across the split.

   If the data does not support a hypothesis, say so and report what it does show.

# Phase C: timing truth and the live demo

Only on AC power, with no other heavy job running.

1. Re-run `smartci profile` on NetworkX (pinned `abf2feda2252`).
2. Re-run `python live_demo/gate5.py --repo external/networkx --seed 5`. Record the result as it is. If it still fails, find out why and fix the simulation or state the limit clearly. Do not loosen the rule to make it pass.
3. **Measure the live demo end to end.** For five mined bugs and five mutants (seeded draw), record the real wall-clock time of both lanes of `smartci compare`, including pytest start-up and test collection.
4. **Make the live demo fit in a presentation.** The default-order lane can take several minutes, mostly start-up and collection. Measure two variants and report both in `reports/DEMO_SCRIPT.md`:
   - the full suite
   - a documented subset, for example `networkx/algorithms`, if the tool supports a path filter or one can be added cleanly

   For each variant give the time of each lane. Recommend one for the presentation.
5. Update `scripts/run_live_compare.ps1` so that one command runs the recommended variant on a bug chosen by number from a short printed list. It should also accept the user's own edit to a NetworkX source file.

**GATE C:** the live comparison has been run for real at least three times on AC power with consistent results, and the timings are written down.

# Phase D (optional, limit to one session): the trade-off curve

The model wins on recurring failures and loses on first-time failures. This step shows whether that trade-off can be tuned.

- Add one parameter, a probability floor `f`: the ordering score becomes `max(p, f) ÷ duration`. With `f = 0` this is the model's order. As `f` grows it approaches "fastest first".
- Using stored predictions only, compute APFDc on "all failed runs" and on "first-time failures of existing tests" across a grid of `f`, on the **validation** split.
- Plot the curve of one metric against the other. Pick `f` by a rule fixed before looking at the test split, and report the test result once.
- This is untested and may show no useful middle point. Report whatever it shows. Ship the floor in smartci only if it wins on validation and holds on test.

If stored predictions are not sufficient and this would need hours of rescoring, skip the phase and say so.

# Phase E: rebuild the dashboard

Rebuild `app/demo.py` with six pages. It reads only `demo_bundle/`, works offline, uses one colour per ordering method on every page, and shows the results version (git SHA and date) in the footer.

1. **Overview.**
   - The problem in three sentences, with a simple picture: tests running in a fixed order, with the failing one near the end.
   - What the project built, as a small pipeline diagram.
   - Four headline numbers: the failure rate, the best model's PR-AUC, model vs best simple rule on all failures, and NetworkX default vs reordered seconds.
   - One line on what each page shows.
2. **The ML pipeline.** This is the most important page for grading. Seven tabs, one per rubric item, in rubric order. Each tab has:
   - two or three plain sentences on what was done
   - the figure or table
   - the key numbers
   - a short "why we chose this" note

   Content of the tabs:
   - *EDA:* the label imbalance, suite durations, the history-rule collapse on first-time failures.
   - *Features:* the four feature groups, each feature's measured signal, and the rejected features with reasons.
   - *Classification:* the three models side by side, and why accuracy is the wrong metric here.
   - *Regularization:* the logistic-regression curve across strengths with the coefficients L1 sets to zero; random-forest depth vs train/validation; LightGBM train vs validation by round.
   - *Tuning:* the search space, the trial history and the best parameters, with one sentence on why validation is by time.
   - *Ensembles:* bagging vs boosting, voting and stacking results, and the error-correlation matrix that explains why ensembles add little.
   - *Performance:* PR-AUC, precision and recall at the top 10/50/100, calibration, then APFDc against every baseline with confidence intervals.
3. **Predict live.** A playground that runs the real exported model in the app, with no precomputed answers.
   - The user picks one to five NetworkX source files from a list.
   - The app builds a change from those file paths, computes features with the same functions smartci uses, scores every test file, and shows the ranked list: probability of failing, expected duration, priority, and the top three reasons in plain sentences.
   - Next to it, show the order that "changed files first" and "fastest first" would give.
   - Bundle whatever inputs this needs (test file list, durations, coverage map, history).
   - State on the page that the change contains file paths only, with no patch text.
   - Add a test that the app's scores equal the smartci command line's scores for the same input.
4. **Race replay.** Two sources, chosen with a switch:
   - *NetworkX bugs:* pick a bug, or press a random button that shows its seed. See three lanes (default order, best simple rule, smartci) advance using real measured durations until the first failing test. Show the commit link and the command that re-runs this race for real in a terminal.
   - *LRTS held-out builds:* the same race, with a link to the real Apache pull request and the download-as-CSV and verify-command features that already exist.

   State clearly on the page what is replayed from recorded durations and what is a live run.
5. **Results: where ML wins and where it loses.**
   - The scoreboard by subset, with confidence intervals and win/tie/loss counts.
   - The error analysis from Phase B.
   - The trade-off curve from Phase D, if it was done.
   - Close with a plain statement of what a team should actually use: on a small Python repo, a simple rule is enough; on long suites with recurring failures, the model adds a modest gain.
6. **Limits and honesty.** What is simulated, what is real, each caveat in one line, and the data licences.

Then rebuild the bundle (keep it under 100 MB, and no single file over 50 MB), update `python -m stp.demo.smoke` to cover all six pages and the playground parity test, and capture a screenshot of every page into `reports/demo_screenshots/`.

**GATE E:** the smoke test passes, and a fresh clone followed by `scripts/setup_demo.ps1` and `scripts/run_demo.ps1` opens the app with all six pages working and no access to `data/` or `external/`.

# Phase F: make it ready for GitHub

Do not push; the student does that. Prepare everything else.

1. **Safety check before publishing.** Confirm that no dataset files, no secrets or tokens, no absolute personal paths and no files over 50 MB are tracked. Report the size of the repository.
2. **README.** In this order:
   - the name and the one-sentence description
   - a screenshot of the app
   - the honest headline result with its small table
   - "Run the demo" in three commands
   - "Use smartci on your own repo" in five commands
   - how the ML pipeline maps to the seven rubric items, with links
   - limitations
   - data sources and licences
3. **A CI workflow for this repository:** `.github/workflows/tests.yml` runs the tests that need no dataset on every push, so the repository shows a passing badge. Mark the dataset-dependent tests so that they are skipped cleanly when the data is absent.
4. **A root `requirements.txt`** containing only what the dashboard needs, so the app can also be deployed from the repository to a hosting service. Check that the app starts with only those packages installed, and note its memory use.
5. **`HUMAN_TODO.md`:** write exact steps for creating the GitHub repository, adding the remote, pushing, replacing the `OWNER` placeholders, and optionally deploying the dashboard to a free Streamlit host from the repository.

# Phase G: the presentation pack

1. **`reports/DEMO_SCRIPT.md`:** a minute-by-minute script for a 7–8 minute demo. For each step give what to click or type, what appears, and one or two sentences to say. Start the live comparison first, so it runs while the presenter talks. Include what to do if each step fails, pointing at the screenshots and the text-only fallback.
2. **`reports/RUBRIC_MAP.md`:** one table. For each of the seven rubric items: what was done, the app tab, the report section, the key number, and the one-sentence justification.
3. **Update `reports/VIVA_NOTES.md`** with the questions this framing invites, each with a short honest answer backed by a number:
   - "Isn't this just a scheduler?"
   - "Why does the model lose on first-time failures?"
   - "Why is a simple rule as good on NetworkX?"
   - "Why PR-AUC and not accuracy?"
   - "Why do ensembles add so little?"
   - "Why did the TVM model collapse on the test period?"
   - "Was any future information used?"
   - "Who would actually use this?"
4. **`reports/AI_USE_DISCLOSURE.md`:** a factual draft for the students to edit, listing which parts of the work were produced with AI coding assistance and which decisions and checks the students made themselves. Leave clearly marked blanks for the students to fill in. Do not invent their contributions.
5. Regenerate `SLIDE_NUMBERS.md`, and update `STATUS.md` and `README.md`.

# Definition of done

- [ ] `reports/AUDIT.md` complete; every failure fixed or explained
- [ ] No "self-healing" wording, and no empty sympy sections anywhere
- [ ] GATE 5 re-run on AC power and reported as it is
- [ ] The live comparison rehearsed with written timings and a recommended variant
- [ ] Six-page app working offline from a fresh clone; smoke test passing
- [ ] The playground runs the real model and matches the command line
- [ ] README, CI workflow and requirements ready; nothing unsafe tracked
- [ ] `DEMO_SCRIPT.md`, `RUBRIC_MAP.md`, updated `VIVA_NOTES.md` and the disclosure draft written
- [ ] `HUMAN_TODO.md` lists every step left for the students

Finish by printing: the audit summary, each gate's result, the headline numbers as regenerated, anything in this prompt the repository contradicted, and the open items in `HUMAN_TODO.md`.
