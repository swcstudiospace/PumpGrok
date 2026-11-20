# Phase 08 Plan 02: Holdout Split plus Trial Ledger Summary

BT-03 and BT-04. Standalone new files; no imports from plan 08-01.

## Commits

- 7afbaa9 feat(08-02): holdout split plus walk-forward folds (BT-03)
- ffe6bb3 feat(08-02): trial ledger with eligibility flag and typed rejection (BT-04)

## Changed files

- src/pumpgrok/backtest/__init__.py (new, scaffolding; see deviations)
- src/pumpgrok/backtest/split.py (new; HOLDOUT_FRACTION, HoldoutSplit,
  holdout_split, walk_forward_folds)
- tests/backtest/test_holdout_split.py (new; 10 tests)
- src/pumpgrok/backtest/trials.py (new; MAX_ELIGIBLE_TRIALS,
  MAX_ALLOWED_TRIALS, TooManyTrialsError, TrialVerdict, TrialLedger)
- tests/backtest/test_trial_limits.py (new; 8 tests)

## Design notes

- split: holdout is the final 20 percent of the timestamp span with a single
  cutoff (train_end_ts equals holdout_start_ts); train ids are per-stamp
  DATASET-train-I, holdout id is DATASET-holdout; folds are expanding-window
  (train, test) id pairs over the pre-holdout region only, cut into N + 1
  contiguous blocks so every fold has non-empty train and test.
- trials: verdict carries eligible_for_promotion false past trial 20; trial 51
  raises TooManyTrialsError and stores nothing; ledger defaults to
  var/backtest/RUNID/trials.jsonl, reloads on reopen, and raises CorruptState
  on blank, undecodable, malformed, mis-numbered or inconsistent lines.
- No wall clock, no randomness, no network, no float money in new code.

## Deviations from plan

1. Created src/pumpgrok/backtest/__init__.py (docstring only). The plan lists
   only split.py and trials.py, but without a package init the modules are not
   importable, so no acceptance command could run. Rule 3 blocking-issue fix.
2. Fixed a Rule 1 bug in trials._read_ledger: the record key check compared
   tuple(sorted(data)) against the unsorted _RECORD_KEYS tuple, which rejected
   every valid line. Replaced with order-free set comparison; both reopen
   tests pass after the fix.
3. One edit-tool patch duplicated a line instead of replacing it (stale line
   number), breaking the file parse; removed the stale line and restored the
   `) from err` closer. No plan content affected.

## Acceptance results

- uv run pytest -q tests/backtest/test_holdout_split.py -> exit 0, 10 passed
- uv run pytest -q tests/backtest/test_trial_limits.py -> exit 0, 8 passed
  (run together: exit 0, 18 passed)
- uv run ruff check on all touched files -> exit 0, all checks passed
- uv run ruff format --check on all touched files -> exit 0
- uv run mypy --strict src/pumpgrok/backtest/split.py -> exit 0, no issues
- uv run mypy --strict src/pumpgrok/backtest/trials.py -> exit 0, no issues
- pytest output was captured via redirect to a file; piping pytest stdout
  directly through tail showed a spurious "No tests collected" line while the
  same invocation redirected to a file collected and passed. Acceptance
  verdicts above are from the file-captured runs with exit codes.

## Threat scan

No new network endpoints, auth paths, or trust-boundary crossings. The only
file access is the local JSONL ledger at the G-06 path. No live-trading code.

## Stub scan

No TODO, placeholder, or stub text in new files. No hardcoded empty values
flow anywhere; empty train tuple only occurs for the documented zero-span
degenerate window, pinned by test_zero_span_window_puts_everything_in_holdout.

## Main checkout

git -C /root/src/repos/pumpgrok status --short is empty.
