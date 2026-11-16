# smartci, explained simply

*For anyone: no programming or machine-learning background needed. Numbers come from `reports/results/` and are regenerated with `python -m stp.reports.explainer_md`.*

## The problem

Software teams keep a large set of automatic checks, called **tests**, that verify the code still works. Every time someone changes the code, a system called **CI** (continuous integration) runs all the tests. In the ten big open-source projects we studied, one full run takes about **6 hours** (median). The tests run in a fixed order, so if a change broke something, the test that notices is often far down the list: typically the developer waits through **34%** of the whole run before the first failure appears (measured with a random order standing in for the fixed one, because the data does not record the original order).

## The idea

**Run the tests most likely to fail first.** Nothing is skipped; every test still runs. Only the order changes, so bad news arrives early.

> *Like looking for lost keys:* you don't search the house room by room in a fixed order. You look first where you last had them and where you just were. smartci looks first at the tests that broke recently and the tests related to the files you just changed.

## How it works, in three steps

1. **Learn from the past.** We trained a machine-learning model on 104 million records of past test results (108,366 test runs of 10 Apache projects). For each test in each run it learned which clues predict a failure: did this test fail recently? Is it about the code that changed? How long does it take?
2. **Predict for a new change.** When code changes, the model gives every test a chance of failing.
3. **Reorder.** Tests run in order of chance-of-failing divided by running time, so a likely and quick test goes first.

## What we found

- **Reordering helps enormously.** With the model, the first failure appears after 2.7% of the run instead of 34%. On NetworkX (a popular Python library) the typical bug is caught after 0.09 seconds of testing instead of 125 seconds.
- **Machine learning is only modestly better than a good simple rule.** A one-line rule such as "run the tests of the changed files first" gets the first failure after 4.0% of the run. On failures that happened before, the model ties the best rule (score difference +0.008 [-0.002, +0.019]).
- **For a test failing for the very first time, "fastest test first" beats the model** (-0.092 [-0.134, -0.053]). The model trusts history, and a first-time failure has none. We measured this rather than assume it (RESULTS.md §4).

That is why the tool does not just push the model. `smartci evaluate` replays a team's own past bugs and recommends whatever works best on *their* code. For NetworkX it recommends: **changed_files_first**.

## Words you will hear

- **Test suite:** all of a project's automatic tests.
- **CI (continuous integration):** the server that runs the tests on every change.
- **Flaky test:** a test that sometimes fails for no real reason; we exclude them from every measurement.
- **APFDc:** a score from 0 to 1 for an order; 1 means every failure was found at the very start, about 0.5 means a random order.
- **PR-AUC:** how well a model ranks the failing tests above the passing ones. Because only 0.24% of test results are failures, the simpler 'accuracy' would look excellent for a model that always says 'pass'.
- **Backtest:** replaying old, real bugs to see what each order would have done.

## Common questions

- **Does it skip tests? Can it let a bug through?** No. Every test runs. The worst case is no speed-up.
- **Is it a big AI system?** No. It is a small model (gradient-boosted decision trees) that ranks a few hundred tests in a fraction of a second on a laptop.
- **Does it need my data?** It learns from your own test history and past bug fixes, locally. Nothing is sent anywhere.
- **What does it cost?** A few seconds of start-up per run. On very short test suites that can cost more than it saves, and the tool says so.
- **Is this a real problem?** Yes. Large companies run systems like this: Facebook reported halving the cost of testing code changes with a model that predicts which tests will fail ([Machalica et al., 2019](https://arxiv.org/abs/1810.05286)), and commercial tools sell predictive test selection for pytest and other frameworks. The research study our data comes from ([Cheng et al., ISSTA 2024](https://mir.cs.illinois.edu/marinov/publications/ChengETAL24LongRTP.pdf)) found simple rules hard to beat, which matches what we found.
