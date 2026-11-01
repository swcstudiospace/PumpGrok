# Phase 08 Plan 06: Backtest Verb plus Divergence Check Summary

One-liner: pumpgrok backtest verb with byte-identical report plus D7 divergence check.

## Commits

- 871a4c3: feat(08-06): backtest verb plus deterministic report [BT-06]
- eb58fe3: feat(08-06): divergence check on D7 defaults [PAP-02]

## Changed files

- src/pumpgrok/cli.py (modified): backtest verb, fixture and params resolution, handler
- src/pumpgrok/backtest/report.py (created): BacktestReport, render, with_divergence
- src/pumpgrok/backtest/divergence.py (created): D7 constants, check, breach_line, enforce
- src/pumpgrok/backtest/report.py render path uses fee constants from
  src/pumpgrok/execution/fees.py with no changes to that file
- tests/backtest/test_divergence.py (created): 6 tests

## Decisions

- Digest evaluation places no orders, so realized slippage and fee totals
  are zero by construction; the report states the desk schedule instead.
- Ledger write is idempotent: identical inputs rewrite the identical single
  trial, which keeps reruns byte-identical.
- Divergence check takes same-window MetricsReport pairs; the promotion
  gate is the caller that prints the breach line and exits 1.

## Deviations

None. Plan executed exactly as written.

## Acceptance results

- Backtest byte-identity plus holdout, trial, slippage, fees greps: exit 0.
- pytest -q tests/backtest/test_divergence.py: exit 0, 6 passed.
- ruff check and ruff format --check on touched files: clean.
- mypy --strict on cli.py, report.py, divergence.py: clean.

## Self-check

- Report file created and byte-identical across two runs: yes.
- Divergence thresholds alert at 2.0pp and 0.5 and pass inside: yes.
- Main checkout git status empty: yes.
