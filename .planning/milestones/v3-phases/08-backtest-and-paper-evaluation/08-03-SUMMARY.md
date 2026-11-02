# 08-03 SUMMARY: Bounded metrics with stated annualisation (BT-05)

## Result

Complete. Created `src/pumpgrok/backtest/metrics.py` with the contract
names `ANNUALIZATION_DAYS_PER_YEAR = 365`, `MetricsContext`,
`MetricsReport` and `summarize`, plus the regression test
`tests/backtest/test_metrics.py` with 7 passing tests.

## Design

`summarize` takes the fill list plus a context carrying initial equity in
lamports, the post-fill equity curve in lamports (same order and length as
the fills) and the window length in days as a Decimal. It reports return,
maximum drawdown from a running peak, a Sharpe-style ratio annualized with
the named 365-day constant for the 24/7 market, win rate, trade count,
exposure as the largest single-fill notional and turnover as the notional
sum. Money stays integer; Decimal is used only for ratios. Core adapter
`Fill` carries no side field, so direction-dependent figures derive from
the equity-curve steps ordered by the fill list; every field documents its
inputs and assumptions in the `MetricsReport` docstring. No forecast
language anywhere; American z-spellings (annualized, annualization) so the
acceptance grep matches.

## Commits

- a9cac56 feat(08-03): bounded metrics with stated annualisation [BT-05]
  (src/pumpgrok/backtest/__init__.py, src/pumpgrok/backtest/metrics.py)
- b3f35ba test(08-03): metrics regression with exact expectations [BT-05]
  (tests/backtest/test_metrics.py)

## Changed files

- src/pumpgrok/backtest/__init__.py (new, byte-identical to 08-01 text)
- src/pumpgrok/backtest/metrics.py (new)
- tests/backtest/test_metrics.py (new)

## Deviations

1. Created `src/pumpgrok/backtest/__init__.py`, which is outside the
   listed `files_modified`. Required: `pumpgrok` is a regular package, so
   the new module is not importable without it. Coordinated with
   Exec8Plan01 (08-01 owns the package); used their exact minimal-docstring
   text so both trees add the identical file and the merge stays clean.
2. `[Rule 1 - Bug] Fixed delta pairing off-by-one found by the new tests`:
   `zip(curve, (initial, *curve))` paired n points against n+1 previous
   points; corrected to `(initial, *curve[:-1])` with `strict=True`.
   Commit b3f35ba test run caught it; fixed before committing Task 2.
3. `uv run pytest` output is summarized by the tool wrapper as
   `Pytest: No tests collected` for `-q` output; the venv binary
   `.venv/bin/pytest -q` runs the same 7 tests green with exit 0. Used the
   venv binary for the acceptance evidence below.

## Acceptance results (exit codes)

- `.venv/bin/pytest -q tests/backtest/test_metrics.py` exit 0, 7 passed.
- `grep -rnE "annualiz" src/pumpgrok/backtest --include=*.py` exit 0,
  matches in metrics.py module docstring and annualization comment.
- `! grep -rniE "expected (return|profit|pnl)|will earn"
  src/pumpgrok/backtest src/pumpgrok/reporting --include=*.py` exit 0,
  no forbidden language.
- `uv run ruff check` on both touched files exit 0, no issues.
- `uv run ruff format --check` on both touched files exit 0.
- `uv run mypy --strict src/pumpgrok/backtest/metrics.py` exit 0.
