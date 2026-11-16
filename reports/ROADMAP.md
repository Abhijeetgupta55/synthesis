# ROADMAP: where smartci can go

*What exists today, what would make it production-grade, and the research questions it opens. Written for the team and for anyone judging the project's scope.*

## Today

- A study on 108,366 real CI runs: leak-free features, five classifiers, ensembles, calibration, honest comparison with every simple rule, error analysis (RESULTS.md).
- `smartci`: an installable pytest plugin and CLI. `smartci evaluate` replays a repository's own past bugs and recommends the model, a simple rule (`--smartci-rule`), or nothing. Shadow mode records rankings without changing anything. Every run writes an auditable receipt.
- A dashboard that runs offline, including a live model page and a guided demo.

## Next: production-grade (weeks)

1. **Shadow mode in CI first.** Install the GitHub Action (`action.yml`) in shadow mode for a few weeks. It ranks every run without changing the order and records outcomes. That builds the history the full model needs (today NetworkX runs on the cold-start model because it has almost no recorded CI history) and gives a before/after measurement on real pull requests.
2. **Test-level ordering.** Today smartci reorders whole test files. Ordering individual tests inside a file would help large files.
3. **Parallel CI.** Most CI splits tests across machines. Putting the likeliest failures in every machine's first slot turns the same idea into wall-clock savings.
4. **Per-repository tuning.** The probability floor that helped first-time failures on the research data hurt on NetworkX (RESULTS.md §4.3); tune such settings per repository with `smartci evaluate`.
5. **Flaky-test signal.** Flag tests whose outcome changes without a code change, and keep them out of training and out of the 'likely to fail' list.

## Later: bigger bets (months)

- **Safe test selection.** Run only the top-ranked tests on every change and the full suite nightly, as Facebook does ([Machalica et al.](https://arxiv.org/abs/1810.05286)). This saves machine time, not just waiting time, but it can delay finding a bug, so it needs a measured safety bound per repository.
- **Other languages.** The research data is mostly Java; a JUnit/Gradle front end would reuse the same model and features.
- **Learning online.** Update the per-repository adapter after every CI run instead of from mined bugs.
- **In the editor.** Show "tests most likely affected by your edit" before the developer even pushes.

## Open research questions

- First-time failures: which signals (code coverage, semantic similarity of code and test, change type) beat 'fastest first' where history is silent?
- When does ML stop being worth it? A cost model that includes the tool's own start-up, suite length and failure rate would tell a team in advance.
- Combining rules and models: a learned switch that picks the model or a rule per change, rather than per repository.
