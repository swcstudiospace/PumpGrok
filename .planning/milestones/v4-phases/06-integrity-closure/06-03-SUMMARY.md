# Phase 6 Plan 3: Single SOL Conversion + Live Gate Clock — Summary

One SOL-to-lamports implementation in `core/units.py` (ROUND_HALF_UP) used by
every module with all duplicate constants removed (INT-04); the live gate
receives `now` from its caller and reads no wall clock (INT-06).

## Tasks completed

- Task 1 — Single SOL-to-lamports helper and duplicate removal — commit `039e57e`
- Task 2 — Live gate clock injection — commit `edfed07`

## Changes

Task 1 (INT-04):
- New `src/pumpgrok/core/units.py`: `LAMPORTS_PER_SOL` (sole definition),
  `sol_to_lamports` (ROUND_HALF_UP), `lamports_to_sol` (exact downscale),
  `split_lamports` (whole/remainder split for 9dp rendering).
- Migrated: `core/risk_budget.py`, `core/approvals.py`, `cli.py`
  (`size_sol_to_lamports` kept as a thin wrapper; cap site uses the helper),
  `risk/sizing.py` (unused constant deleted), `tools/_common.py` (unused
  constant deleted), `tools/market/trades.py`, `reporting/render.py`,
  `ledger/export.py`, `engine/reputation.py` (unused constant deleted),
  `engine/monitor.py` (threshold and best-effort coercion share the helper),
  `tools/onchain/curve_layout.py`, `engine/agents/auditor.py`,
  `risk/__init__.py` (re-export dropped; no importers).
- `engine/pipeline.py` (listed in the plan) holds no literal or constant and
  needed no change.
- New `tests/integrity/test_single_sol_conversion.py`: half-up boundary values
  plus cross-entry agreement.

Task 2 (INT-06):
- `LiveGate.evaluate`/`check` take keyword-only `now` (YYYY-MM-DD date or
  ISO-8601 timestamp; only the date part is used); `_paper_window`/`_paper_days`
  thread it through. No `WallClock` import remains in `live_gate.py`.
- `WeeklyReport.build` takes optional `now` (defaults to the report `day`);
  `cli.py` passes the UTC day to the gate and the week date to the report;
  `LiveAdapterStub._refuse` checks the gate at its injected clock.
- Updated existing gate callers (`tests/test_live_gate.py`,
  `tests/execution/test_live_gate_fails_fast.py`,
  `tests/safety/test_live_adapter_raises.py`, incl. monkeypatched lambdas).
- New `tests/integrity/test_live_gate_clock.py`: byte-identical output across
  two evaluations, day count following the injected `now`, timestamp/date
  form equivalence.

All conversions keep the exact operation order of the originals; the gate
keeps the same `max(0, span.days)` day math, only the source of "today"
changed from `WallClock` to the caller.

## Deviations from plan

- Extra files touched (required by the plan's own acceptance greps, which ban
  the literal and constant name everywhere outside `core/units.py`):
  `engine/monitor.py`, `tools/onchain/curve_layout.py`,
  `engine/agents/auditor.py`, `risk/__init__.py` (duplicate copies the plan's
  file list missed), `execution/live/live_adapter.py` plus the three existing
  gate test files (further on-tree `evaluate`/`check` callers the plan's
  "every on-tree caller" rule covers).
- `engine/pipeline.py` (in the plan's file list) needed no edit: it holds no
  SOL literal or constant.

## Acceptance commands (for the orchestrator)

Run from the worktree root:

- `! grep -rn "1_000_000_000" src/pumpgrok --include='*.py' | grep -v "src/pumpgrok/core/units.py"`
- `! grep -rn "LAMPORTS_PER_SOL" src/pumpgrok --include='*.py' | grep -v "src/pumpgrok/core/units.py"`
- `! grep -nE "time\.time|datetime\.(now|utcnow)" src/pumpgrok/execution/live/live_gate.py`
- `! grep -n "WallClock" src/pumpgrok/execution/live/live_gate.py`
- `uv run pytest -q tests/integrity/test_single_sol_conversion.py tests/integrity/test_live_gate_clock.py`

Full gates (`make lint`, `make typecheck`, `make test`, existing gate/safety
suites) were not run here per the wave instructions; the orchestrator runs
them after merge.
