# 08-05 Summary: Holdout-aware harness plus tune removal (BT-07)

## Outcome

`run_search` in `src/pumpgrok/backtest/harness.py` is now the only search
entry point. It tunes over walk-forward folds confined to the pre-holdout
region, records every trial in the `TrialLedger`, and evaluates the winning
parameter set on the holdout exactly once, returning a `HarnessResult`
with the winning parameter-set hash, the holdout id, the trial count, the
eligibility verdict, and a digest-based holdout score reported for
completeness. The retired weight-and-threshold search module and its
characterization pin are deleted.

## Commits

- 542557a feat(08-05): BT-07 holdout-aware harness as only search entry point
- cc3fb71 fix(08-05): BT-07 remove weight-and-threshold search module

## Changed files

- src/pumpgrok/backtest/harness.py (created): `run_search`, `HarnessResult`,
  `ParamSpace`, tuning and holdout scorers with cutoff asserts
- tests/backtest/test_single_search_engine.py (created): 10 tests covering
  single-entry-point scan, holdout isolation probe, eligibility limits,
  typed rejection, determinism, recorded-fixture end to end
- src/pumpgrok/engine/tune.py (deleted, 319 lines)
- tests/characterization/test_tune.py (deleted, 149 lines)
- src/pumpgrok/engine/__init__.py (modified): docstring no longer names tune

## Design notes

- Candidates are explicit JSON-stable mappings (ints, strings, bools, None,
  lists, dicts); float leaves are rejected because `canonical_json` raises
  on them. Draw order uses the seeded replay RNG, so identical inputs
  select the identical winner.
- Scores are deterministic digests of seed, params hash and fold ids, not
  performance claims; the holdout score never feeds back into selection.
- Trial accounting delegates to `TrialLedger`: past 20 trials the result
  flags ineligible, past 50 recording raises `TooManyTrialsError` through
  `run_search` with the 50 stored trials intact.

## Deviations

None. Plan executed as written. One ordering note: the Task 1 entry-point
test pins the post-removal state, so it first passed after the Task 2
deletion landed; both tasks are committed separately above.

## Acceptance results

- `uv run pytest -q tests/backtest/test_single_search_engine.py` exits 0,
  10 tests pass
- `grep -rnE` for the retired search pattern over `src/pumpgrok/engine`
  and `src/pumpgrok/backtest` exits 1 (no matches)
- `uv run ruff check` on touched files: all checks pass
- `uv run ruff format --check` on touched files: clean
- `uv run mypy --strict src/pumpgrok/backtest/harness.py`: no issues
- `grep -rn engine.tune src tests skills docs scripts`: only docs history
  banners, the deliberate negative test assertion, and removed bytecode
  remain; no importer in source
