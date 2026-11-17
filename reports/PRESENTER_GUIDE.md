# Presenter guide: the Streamlit demo, page by page

Start: `scripts\run_demo.ps1`, then open http://localhost:8501. Pages are in the **left sidebar** (if it is hidden,
click the small `>` at the top-left). Screenshots of every page: `reports/demo_screenshots/`.

## The one idea to keep in your head

A CI server re-runs all tests after every code change, in a fixed order. If the change broke something, the test
that notices may be near the end of the list. We predict which tests will fail and **run those first**. Nothing is
skipped; only the order changes. Three words come back on every page:

- **Queue position**: where the first failing test sits in the list (1 = first). Smaller is better.
- **Test time until it fails**: how long you wait, adding up the tests that run before it.
- **APFDc**: one score from 0 to 1 for how early *all* failures come. 1 = all failures first, about 0.5 = random order.

## Suggested order (about 8 minutes)

Start here → ML Lab → Real PRs → Break the code → The ML pipeline → Results.

---

## 1. Start here (30 seconds)

**What is on it:** the keys analogy, a 4-step walkthrough, and "The honest verdict" (three numbered points).
No buttons. The expander at the bottom ("For the technical audience") shows a pipeline diagram and four headline numbers.

**Say:** "When you lose your keys you look first where you last had them. We do the same for software tests: run
first the tests most likely to fail. Every test still runs. Our honest finding: ML helps on big projects with long
history, a simple rule is enough on small projects, and ML loses on tests that fail for the first time."

---

## 2. ML Lab (2–3 minutes): "everything here is trained live"

**Top paragraph:** the data. 100,000 real training rows and 100,189 rows from 122 later CI builds. One row = one
test in one CI run of a real Apache project; the label is "did it fail?". Only 0.18% of later rows fail.

Two tabs: **Four guided experiments** and **Train your own**.

### Tab "Four guided experiments"

Each experiment has a question and a **Run this experiment** button. Pressing it trains the model(s) now (a few
seconds) and shows one table per model plus a green **Takeaway** box that is written from the numbers just computed.

**How to read each table** (rows):
- **train**: the rows the model learned from (its "homework").
- **validation**: rows held back, chosen by the split (the "practice exam").
- **later builds**: CI runs that happened after all training data (the "real exam", what matters).

Columns: **rows** (how many), the **score** (accuracy or PR-AUC), and the **baseline** to compare with: "always
'pass' scores" for accuracy, "random ranking scores" for PR-AUC. "× better than random" = score ÷ baseline.

**Experiment 1, The accuracy trap.** Press it.
Say: "The model is 99.67% accurate on later builds, but a model that always says 'pass' scores 99.82%. When only
0.18% of tests fail, accuracy is meaningless. That is why we use PR-AUC: it measures whether the failing tests are
ranked above the passing ones."

**Experiment 2, Overfitting without regularization.** Press it. Two tables: no regularization vs regularized.
Say: "Without regularization LightGBM scores 1.00 on its training rows, it memorised them, but only about 0.06 on
later builds. With regularization (smaller trees, minimum rows per leaf, early stopping) it scores less on training
but about three times better on the real exam."

**Experiment 3, A random split inflates the score.** Press it. Two tables: random split vs split by time.
Say: "If we hold out a random 20% of rows, validation says about 0.45. If we hold out the latest 20% of CI runs,
it says about 0.24, and later builds give even less. A random split puts rows of the same CI run on both sides, so
it promises more than the model delivers on the future. Real use is always on future builds, so we split by time."

**Experiment 4, History alone vs history + change.** Press it.
Say: "Features about a test's past failures carry most of the signal. Adding features about the code change did
not help on this small sample. On first-time failures, which have no history, everything is close to random."

### Tab "Train your own" (optional, 30 seconds)

- **Model**: logistic regression (a weighted sum), random forest (many trees voting), LightGBM (trees built one
  after another, each fixing the previous errors).
- **Validation split**: by time (correct) or random (leaky).
- **Metric**: PR-AUC or accuracy.
- **Feature groups** (checkboxes): history (past failures), cost (how long the test takes), change (is the test
  related to the changed files), cofail (did it fail before when these files changed).
- **Regularization** (sliders change per model): logistic regression: penalty L1/L2 and C (smaller C = stronger
  penalty; L1 can set weights to exactly zero). Random forest: number of trees, max depth, min rows per leaf.
  LightGBM: leaves per tree, max depth, min rows per leaf, max rounds, early stopping.
- **Train** button: fits now. Shows the three-row score table, the time taken and the train − validation gap
  (big gap = overfitting), then **Top features** (which inputs the model relied on; for logistic regression the
  sign says whether it raises or lowers the risk). **Your fits this session** lists every fit so you can compare.

Say: "Pick anything, press Train: it trains right now on real data."

---

## 3. Real PRs (2 minutes): "real builds the model never saw"

**Blue box:** these are replays of real recorded builds from Apache Kafka and TVM, from the test period the model
never saw. Nothing is animated; the numbers are the recorded test times and results.

**Top numbers:**
- **model − best rule (APFDc)**: +0.041 on Kafka, +0.050 on TVM, over all held-out builds. Positive = the model
  orders tests better than the best simple rule.
- **builds won · tied · lost**: Kafka 6,264 won, 121 tied, 1,693 lost. TVM 144 / 82 / 51.

**Paragraph "Do the model's wins come from recurring or flaky failures?"** Answer: recurring. Wins contain tests
that had failed before; flaky tests are not what makes it win. Losses are recurring too.

**Buttons and filters:**
- **Random build**: picks a random build (the seed is shown so you can get the same one again).
- **Show me a loss**: picks a build where the model did worse than the simple rule.
- **Project** / **Outcome** filters, and the **Build** dropdown to choose one directly.

**For the chosen build:**
- Link **Open the real Apache pull request** (the real PR on GitHub), date, and outcome (win / tie / loss).
- Four numbers: how many test classes, how many failed, total test time, how many files the PR changed.
- **Changed files in this PR**: click to see the file list.

**The main table** (one row per order):
- **Random order** stands in for a fixed order (the dataset does not record the real one).
- **Fastest first**: shortest tests first.
- **Best simple rule**: tests of changed or new files first.
- **Model (stacking)**: our model.

Columns: **first failing test at position** (queue position, e.g. "18 of 80"); **test min before it** (minutes of
tests that ran before it); **test min until it fails**; **≈ wall-clock min** (real CI runs tests in parallel, so the
real waiting time is shorter; we scale by this project's measured ratio); **APFDc** (0–1, how early all failures come).

**The model's top 10 tests:** the 10 tests the model ranked first, with **really failed? ❌ yes** on the ones that
actually failed, and **why** (the three strongest reasons, e.g. "it failed 4 days ago", "its file is in your change").

**Full order for one method** (expander): the whole list in that order, downloadable as CSV.

Say: "Here's a real Kafka build. The random order reaches the failing test after N minutes; the model puts it near
the top. And it doesn't always win: [press Show me a loss] here it lost. Over all builds it won 6,264 and lost 1,693."

---

## 4. Break the code (1–2 minutes): "a real bug, a model that never saw it"

**Choose a bug** dropdown: every real NetworkX bug we tested, with its result in brackets (smartci earlier, simple
rule earlier, or tie, and the queue positions).

- **Step 1 · The change**: a real old NetworkX bug put back into today's code. The box shows the code change
  (red lines removed, green lines added).
- **Step 2 · Ask the model**: turn on **Run the model now**. The real model scores all 263 NetworkX test files now
  and shows its top 10, with **really fails? ❌ yes** on the test that truly fails and **why**.
- **Step 3 · Where did the truly failing test land?** Three orders: pytest's normal order, changed files first,
  smartci. Columns: queue position (e.g. 197 of 263 vs 1 of 263), test seconds until it fails, and ≈ end-to-end
  seconds (adds about 112 s that pytest spends starting up and collecting tests, which every order pays).
- **Step 4 · Run it for real**: runs two real pytest processes. **Skip it in class**: the full suite takes several
  minutes.

Say: "The model never saw this bug. Here's its top 10, and the real failing test is second. pytest's normal order
finds it at position 197 out of 263; ours at position 1 or 2. On this small project the simple rule does just as well."

---

## 5. The ML pipeline (1–2 minutes): the course rubric

Seven tabs, one per rubric item. Each has figures, numbers and a blue **Why we chose this** box: read that box.

1. **EDA**: only 0.243% of test results are failures; suites take hours; history rules collapse on first-time failures.
2. **Features**: 25 features in four groups, all computed "as-of" (a run only sees runs that had finished before it
   started, so no peeking into the future).
3. **Classification**: logistic regression, random forest, LightGBM; PR-AUC 0.19–0.22 vs 0.003 for random.
4. **Regularization**: L1/L2 for logistic regression (14 coefficients set to zero), tree depth 10 for random forest,
   early stopping for LightGBM; curves show training going up while validation goes down without it.
5. **Tuning**: Optuna, 60 trials, scored on validation data split by time.
6. **Ensembles**: voting and stacking (best PR-AUC 0.227), but small gains: LightGBM and random forest errors
   correlate at 0.98, they make the same mistakes.
7. **Performance**: APFDc against every simple rule with confidence intervals.

---

## 6. Results (1 minute): the honest verdict

- **LRTS scoreboard**: per type of failure, the best simple rule, its APFDc, LightGBM's APFDc, the difference
  with a 95% interval, and the verdict. All failures: a tie with the best simple rule (and a win over the
  paper's best history rule). First-time failures: ML loses to "fastest first".
- **NetworkX** tables: same comparison on the real Python library (queue position, test seconds, end-to-end).
- **Why the model loses where it loses**: the error analysis.
- **What `smartci evaluate` tells the NetworkX team**: the tool's own verdict card; it recommends the simple rule.
- **Green box**: what a team should actually use.

Close: "ML helps on large projects with long history. On a small Python repo a simple rule is enough. On brand-new
failures the model loses. Our tool measures this on each project and recommends the right order."

## Pages you can skip

- **Predict live**: pick NetworkX files you might change; the model ranks the tests now and compares with two
  simple rules. Good if asked "can you show it live?".
- **Limits and honesty**: what is real, what is replayed, every caveat. Good if asked "what are the limitations?".

## If your professor asks

- *Why not accuracy?* Only 0.24% fail; "always pass" is 99.76% accurate and useless. PR-AUC.
- *Why split by time?* The model is always used on future builds; a random split leaks the future (ML Lab exp. 3).
- *Does ML beat simple rules?* Modestly, on big projects with recurring failures (Kafka, TVM); not on first-time
  failures; not on a small repo.
- *Is anything faked?* No. ML Lab and Break the code step 2 compute live; Real PRs replays real recorded data, and
  `python -m stp.demo.verify` recomputes it from the raw files.
