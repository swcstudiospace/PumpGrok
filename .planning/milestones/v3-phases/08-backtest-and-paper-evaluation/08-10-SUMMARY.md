# 08-10 SUMMARY: Report and verb (correction set, BT-05, BT-06, PAP-02)

## Commits

- 6a391c7 feat(08-10): BT-05 BT-06 deterministic report on real fills
  (src/pumpgrok/backtest/report.py, tests/backtest/test_report_render.py)
- 53b9737 feat(08-10): BT-06 PAP-02 backtest verb with eligibility and breach exit
  (src/pumpgrok/cli.py)

## Changed files

- src/pumpgrok/backtest/report.py (rewrote manifest-only render)
- tests/backtest/test_report_render.py (new)
- src/pumpgrok/cli.py (reworked _backtest_verb, added --paper-ledger)

## What was built

Task 1: BacktestReport now carries the data window (first/last recorded
event timestamps), holdout id and split ids, trial count with both
limits, realized slippage and fee totals summed from holdout fills, the
BT-05 metrics (total return, max drawdown from a running peak,
Sharpe-style ratio naming ANNUALIZATION_DAYS_PER_YEAR with the 24-7
assumption, win rate, trade count, exposure, turnover) with inputs and
assumptions stated, promotion_eligible plus promotion_reason, and an
optional paper comparison section. Zero-trade windows render the four
ratios as not-applicable and counts as 0. Render stays byte-identical
for identical inputs (sorted keys, fixed formatting, no wall clock).

Task 2: _backtest_verb validates --params through CandidateParams
(unknown keys and scoring knobs fail closed; file bytes stay the
manifest hash), records one trial, replays the holdout once under the
winning overrides, rebuilds fills/latencies/cash-deltas from the
holdout ledger, summarizes them into window metrics, and renders the
Task 1 report. --paper-ledger builds the paper SharedResult from its
FillRecorded rows over the same window, enforces window equality via
SharedResult.compare before divergence.check, and sets
promotion_eligible true only when trials are at most 20 and the D7
verdict passes; a breach prints DIVERGENCE BREACH on stderr and exits
1. Without --paper-ledger promotion stays false with reason
divergence not compared. Fixture containment, idempotent ledger
rewrite, and deterministic stdout are kept.

## Deviations

None - plan executed exactly as written. Two extra probes beyond the
acceptance commands, both passing, not committed: paper happy path
(promotion true on identical ledgers) and a crafted divergent paper
ledger (exit 1 with DIVERGENCE BREACH on stderr); bad --params files
(scoring section, unknown key) fail closed with exit 1 usage errors.

## Acceptance (exit codes)

- Task 1: uv run pytest tests/backtest/test_report_render.py
  tests/backtest/test_divergence.py -> exit 0, 10 passed.
- Task 1: uv run ruff check + ruff format --check on the three
  touched files -> exit 0. mypy --strict on report.py and cli.py ->
  exit 0 each.
- Task 2: smoke backtest twice byte-identical with holdout, trial,
  slippage, fees, and not-applicable/not-compared greps -> exit 0.
- Task 2: smoke-10m backtest twice byte-identical with holdout,
  trial, slippage, fees greps -> exit 0.

## Self-Check

PASSED. test_divergence.py still constructs BacktestReport with the
old fields (all kept, new fields defaulted). No deletions.
git -C /root/src/repos/pumpgrok status --short is empty.
