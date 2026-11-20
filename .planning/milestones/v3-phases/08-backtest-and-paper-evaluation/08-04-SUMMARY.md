# Phase 08 Plan 04: Shared Result Model plus Replay Per-Fill Fields Summary

BT-02: replay results expose per-fill price, venue fee, network cost, latency,
filled fraction and outcome. PAP-01: backtest results and paper ledger trades
share one result schema over the same window.

## Commits

- bfc9d04 feat(08-04): BT-02 PAP-01 shared result model plus replay per-fill fields
- 4fbca81 test(08-04): BT-02 PAP-01 per-fill and shared-schema regression tests

## Changed files

- src/pumpgrok/backtest/results.py (new): frozen FillDetail with price, venue
  fee, network cost, latency, filled fraction and outcome; SharedResult built
  from the same Fill model for backtest fills and paper ledger fills over one
  window, referencing the run manifest id; WindowComparison field-for-field
  verdict. Money integers; Decimal only for ratios and latency seconds.
- src/pumpgrok/replay/runner.py: ReplayTrade gains price_avg, venue_fee_lamports,
  network_cost_lamports, latency_s and filled_fraction with zeroed defaults;
  format_trade stdout unchanged.
- src/pumpgrok/supervisor/scheduler.py: _ReplayTrading gains a store handle;
  _fill_payload_for and _replay_trade build each attempt from its FillRecorded
  row at the replay ledger write path; buy, rule-sell and graduated sites
  populate the new fields. A rejected or unknown attempt keeps zeroed detail.
- tests/backtest/test_replay_result_fields.py (new): smoke replay trades carry
  all six fields with integer money types; fills carry positive price and
  fraction; the shared detail maps one to one onto trade fields.
- tests/backtest/test_shared_result_schema.py (new): identical backtest fills
  and ledger rows compare clean; one changed integer surfaces as a named field
  difference; foreign datasets and windows raise; run id references the
  manifest; bad money fails closed.

## Deviations

- Ledger bytes unchanged, so the replay events hash does not move. FillRecorded
  rows already carry the per-fill integers, and no new event type was added per
  G-10, so the result payload extension is in memory only: ReplayTrade mirrors
  the ledger row the same call wrote. Criterion 12 still holds on its testable
  half: the hash is stable across runs. The AFTER hash the orchestrator records
  will equal the BEFORE hash b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d.
- The scheduler wire-up adds one store handle on _ReplayTrading plus two small
  lookup helpers so the payload construction can read the row it just wrote.
  No other scheduler behavior changed.
- Acceptance commands were run with --frozen. Plain uv run with a positional
  test path collects nothing in this worktree (pre-existing on untouched files
  too; the lockfile re-resolve path swallows collection and exits 0). --frozen
  runs the identical interpreter, venv and sys.path, verified equal. Also noted
  for the orchestrator: whole-suite collection is broken by a pre-existing
  duplicate basename, tests/backtest/test_metrics.py versus
  tests/supervisor/test_metrics.py, unrelated to this plan.

## Acceptance results (exit codes)

- uv run --frozen pytest -q tests/backtest/test_replay_result_fields.py: exit 0, 4 passed
- uv run --frozen pytest -q tests/backtest/test_shared_result_schema.py: exit 0, 5 passed
- uv run --frozen pytest -q tests/backtest/test_replay_result_fields.py tests/backtest/test_shared_result_schema.py: exit 0, 9 passed
- uv run --frozen pytest -q tests/replay/test_replay_trades.py tests/replay/test_runner_determinism.py: exit 0, 11 passed (regression on touched replay paths)
- uv run --frozen ruff check on all five touched files: All checks passed
- uv run --frozen ruff format --check on all five touched files: 5 files already formatted
- uv run --frozen mypy on results.py, runner.py, scheduler.py: Success, no issues in 3 source files
- git -C /root/src/repos/pumpgrok status --short: empty
