# Presenter guide: the Streamlit demo, page by page

Start: `scripts\run_demo.ps1`, open http://localhost:8501. Pages are in the **left sidebar** (click **>** at the
top-left if it is hidden). Screenshots of every page: `reports/demo_screenshots/`.

**Suggested order for the professor (about 10 minutes):** Start here → ML Lab → Real PRs → Break the code →
The ML pipeline → Results. Skip Predict live and Limits unless asked.

## Words you will use (say them once, early)

- **Test / CI:** automatic checks a server runs after every code change. A "build" or "CI run" = one such run.
- **Fails / failure:** a test that turned red because the change broke something.
- **Order:** the sequence in which tests run. We never skip tests; we only change the order.
- **Simple rule:** an order with no ML, e.g. "tests of the files you changed first" or "fastest test first".
- **PR-AUC:** how well a model puts the failing rows above the passing ones (0 to 1). A random guess scores the
  failure rate (here about 0.002), so 0.2 is about 100 times better than random.
- **APFDc:** how early *all* failures come in an order, weighted by test time (0 to 1). 1 = failures first,
  0.5 ≈ random order.
- **Held-out / later builds:** data from after the training period. The model never saw it.

## 1. Start here

What is on it: the one-line idea, the keys analogy, a list of the pages, and **The honest verdict** (three points).
No buttons. The expander at the bottom ("For the technical audience") shows the pipeline diagram and four headline
numbers.

Say: "When code changes, thousands of tests run in a fixed order, often for hours. We predict which tests will fail
and run them first. Nothing is skipped. Our honest finding: ML helps on big projects with long history, a simple
rule is enough on small ones, and ML loses on tests failing for the first time."

## 2. ML Lab

The top paragraph says what data is bundled: 100,000 real training rows and 100,189 rows from 122 later CI builds.
One row = one test in one CI run; the label = did it fail. **Everything on this page is trained when you press a
button.** There are two tabs.

### Tab "Four guided experiments"

Each experiment has a question, a **Run this experiment** button, then for each model a table and a green
**Takeaway** box computed from that fit.

The table, row by row:
- **train**: rows the model learned from; **validation**: rows held back from training; **later builds**:
  CI runs after the whole training period (the real test of the model).
- **rows**: how many rows. **accuracy** or **PR-AUC**: the model's score.
- **always 'pass' scores** / **random ranking scores**: what a model with no intelligence gets. Always compare with it.
- **× better than random** (PR-AUC only): score ÷ random.

1. **The accuracy trap** (one run). Accuracy on later builds ≈ 99.67 %, but always answering "pass" gets 99.82 %.
   Say: "A 99.7 % accurate model that is worse than doing nothing. Only 0.18 % of tests fail, so accuracy is
   useless. That is why we use PR-AUC."
2. **Overfitting without regularization** (two runs). Unregularized LightGBM: train ≈ 1.00, later builds ≈ 0.06.
   Regularized: train ≈ 0.64, later ≈ 0.19. Say: "With no brakes it memorises its training data and fails on new
   builds. Regularization (fewer leaves, minimum rows per leaf, early stopping) trades training score for real
   performance."
3. **A random split inflates the score** (two runs). Random split validation ≈ 0.45, split by time ≈ 0.24, later
   builds lower still. Say: "If you split randomly, tests from the same CI run end up in training and validation,
   so the model looks better than it is. In real use the model always predicts the future, so we split by time."
4. **History alone vs history + change** (two runs). History only ≈ 0.24, adding cost and change features ≈ 0.20
   on this small sample. Say: "Past failures carry most of the signal. Change features matter for tests that
   never failed before, but there are only 9 such failures here, too few to conclude." (Honest: this is a small
   sample; the full-data ablation is on the ML pipeline page.)

### Tab "Train your own"

Controls (top to bottom):
- **Model**: logistic regression (linear), random forest (many trees averaged = bagging), LightGBM (trees built one
  after another to fix errors = boosting).
- **Validation split**: by time (honest) or random (inflated, see experiment 3).
- **Metric**: PR-AUC or accuracy.
- **Feature groups** (checkboxes): history (did it fail before, 9 features), cost (how long it takes, 3), change
  (is it related to the changed files, 10), cofail (did it fail when these files changed before, 3).
- **Regularization** (changes with the model): LR → penalty L1/L2 and **C** (smaller C = stronger penalty; L1 can
  set coefficients to exactly zero). Random forest → number of trees, max depth, min rows per leaf. LightGBM →
  leaves per tree, max depth, min rows per leaf, max rounds, early stopping.
- **Train** button.

After Train:
- The same three-row score table (train / validation / later builds).
- A grey line: seconds taken, number of features, **train − validation gap** (big gap = overfitting), boosting
  rounds used or coefficients set to zero.
- **Top features**: for LR the coefficient (raises or lowers the risk); for trees the importance. The bar shows size.
- **Your fits this session**: every model you trained, side by side.

Good live demo: let the professor choose. Example: LightGBM, leaves 255, min rows per leaf 1, early stopping off →
train near 1.0, later builds low (overfitting). Then turn early stopping on and min leaf 50 → gap shrinks.

## 3. Real PRs

What it is: **replays of real recorded builds** of two big Apache projects, Kafka and TVM, from the held-out test
period. We take the real recorded duration and result of every test and compute what would have happened under each
order. Nothing is re-run (the blue box says so).

Top of the page:
- **+0.041 (Kafka), +0.050 (TVM)**: how much better the model's APFDc is than the best simple rule, over all
  held-out builds. These are the two projects where ML wins.
- **builds won · tied · lost**: Kafka 6,264 / 121 / 1,693, TVM 144 / 82 / 51. Say: "It wins most builds, but it
  loses about one in five on Kafka."
- The paragraph answers "**do the wins come from flaky tests?**" No: the wins come from tests that failed before
  (recurring failures), not from flaky tests. But losses are recurring too.

Buttons and filters:
- **Random build**: picks another build at random (the seed number is shown so it can be repeated).
- **Show me a loss**: picks a build where the model did worse than the simple rule.
- **Project** / **Outcome vs best simple rule**: filters. **Build** dropdown: pick a build by hand
  ([win]/[tie]/[loss] is shown in front).

For the chosen build:
- **Open the real Apache pull request**: the real PR on GitHub.
- Four numbers: **test classes**, **failing**, **total test time** (all tests one after another), **changed files**
  (click the box to list them).
- **The orders table** (the key table), one row per order:
  - *Random order*: stands in for the normal fixed order (the dataset does not record the real order).
  - *Fastest first*: shortest tests first. *Best simple rule*: tests of changed or new files first.
    *Model (stacking)*: our ML model.
  - **first failing test at position**: where the first red test was, e.g. "1 of 80".
  - **test min before it**: minutes of testing spent before reaching it.
  - **test min until it fails**: including the failing test itself.
  - **≈ wall-clock min**: the same, scaled to real elapsed time (CI runs tests in parallel).
  - **APFDc**: how early *all* failures came (1 = best). Win/tie/loss is decided on this.
  Say: "Lower position and fewer minutes are better. Here the model found the failure at position X after Y
  minutes; the normal order needed Z minutes."
- **The model's top 10 tests, with reasons**: the 10 tests the model put first, ❌ = really failed in this build,
  and *why* in plain sentences (from SHAP: which features pushed the prediction up).
- **Full order for one method**: the whole list, downloadable as CSV.
- The grey command: anyone with the dataset can recompute every number on the page from the raw file.

Demo: click Random build, explain the orders table and the top 10, then click **Show me a loss** and say "we show
losses too".

## 4. Break the code (guided demo)

What it is: a **real bug from NetworkX's history** (a popular Python library) put back into today's code. The model
was trained only on Apache projects and has never seen NetworkX bugs.

- **Choose a bug** dropdown: each entry shows the outcome first, e.g. "[tie: queue position smartci 1, rule 1,
  pytest 197]". All bugs are listed, including the ones the model loses.
- **Step 1 · The change**: the code change that brings the bug back. Red lines removed, green lines added. The link
  opens the original fix on GitHub.
- **Step 2 · Run the model now** (switch): the real model scores all 263 NetworkX test files right now. Table: rank,
  test file, **really fails?** (❌ = the test that truly breaks), **chance of failing**, **why**.
  Say: "The model has never seen this bug. It ranks the truly failing test number 2."
- **Step 3 · Where did the truly failing test land?** For three orders: pytest's normal order, the simple rule
  (changed files first), and smartci:
  - **failing file's queue position**: e.g. 197 of 263 vs 1 of 263.
  - **test s until it fails**: seconds of testing before the failure shows.
  - **≈ end-to-end s**: plus pytest's start-up (about 112 s on this laptop: Python loading and collecting 10,000
    tests), which every order pays.
  Say: "The normal order reaches the bug after 197 test files. Both the simple rule and our model put it first. On
  a small project like this, the simple rule is as good as ML."
- **Step 4 · Run it for real**: the **Start both pytest runs** button starts two real test runs side by side. It
  takes several minutes on the full suite. **Skip it in the presentation**, or choose the small subset in the
  "Tests" dropdown if you want to show it.

## 5. The ML pipeline (the course rubric)

Seven tabs, one per rubric item. Each has figures, numbers, and a blue **"Why we chose this"** box: read that box.

1. **EDA**: 0.243 % of rows are failures, so always saying "pass" is 99.76 % accurate and useless. Suites take hours.
   History rules collapse on first-time failures.
2. **Features**: 25 features in four groups, all computed *as-of* (only from runs that had finished before), so
   there is no leak from the future. The table shows each feature's signal alone.
3. **Classification**: logistic regression, random forest, LightGBM. PR-AUC on held-out rows: 0.193, 0.195, 0.218
   (random = 0.003).
4. **Regularization**: LR chose elastic net with C = 0.0001 (14 coefficients set to zero); random forest depth 10,
   min 20 rows per leaf; LightGBM uses L1/L2, subsampling and early stopping. Curves show train vs validation.
5. **Tuning**: Optuna, 60 trials, scored on time-ordered validation data, never on test data.
6. **Ensembles**: bagging (random forest) vs boosting (LightGBM), plus voting and stacking. Stacking is best
   (0.227) but only slightly: the models' errors correlate at 0.98, so they make the same mistakes.
7. **Performance**: precision/recall in the top 10, calibration, and APFDc vs the best simple rule with 95%
   confidence intervals.

## 6. Results

- **Scoreboard table**: for each kind of failure, the best simple rule, its APFDc, LightGBM's APFDc, the difference
  with a 95% confidence interval, the verdict, and runs won/tied/lost. Read the **verdict** column:
  all failures → tie with the best simple rule; vs the research paper's best rule → ML wins; first-time failures →
  ML loses to fastest-first.
- **NetworkX tables**: the same comparison on the real Python library: queue position, test seconds, end-to-end.
- **Why the model loses where it loses**: first-time failures have no history, and history is what the model relies on.
- **The `smartci evaluate` card**: what our tool tells the NetworkX team: use the simple rule.
- **Green box "What a team should actually use"**: say it as your conclusion.

## 7. Predict live (only if asked)

Pick 1–5 NetworkX source files you might change; the model ranks all test files now. Left: smartci's order with
chance of failing, expected seconds, priority (= chance ÷ seconds) and reasons. Right: the two simple rules for the
same change.

## 8. Limits and honesty (only if asked)

What is computed live, what is replayed from recorded data, and every caveat in one line each.

## Closing sentence

"Reordering tests helps enormously. Machine learning adds a real gain on big projects with long history, like
Kafka and TVM. On a small project a simple rule is enough, and for brand-new failures the fastest-first rule beats
the model. We show the wins and the losses."
