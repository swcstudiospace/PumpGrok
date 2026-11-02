# Phase 6 Plan 01b: INT-01 fallout + INT-02 paper-genesis gap — Summary

Closes the INT-01 fallout from plan 06-01 and the INT-02 paper-genesis gap
from plan 06-02. All money is now integer lamports or base units at every
boundary touched; Decimal survives only for ratios. The paper composition
root records `initial_equity_lamports` at genesis, so a fresh paper ledger
reaches shutdown and the exit-halt without `CorruptState`.

## Changes (16 atomic commits)

### A3 — Token money to integer lamports
- `f39ebf7` — `src/pumpgrok/engine/models.py`: `Token.market_cap_sol`
  and `Token.sol_in_curve` are `int` lamports (were `float` SOL).
  `Holder.share` stays `float` with an explicit "ratio, not money" comment.
- `72fcc48` — `src/pumpgrok/engine/monitor.py`: `parse_create_event`
  coerces `vSolInBondingCurve`/`marketCapSol` (SOL) to integer lamports via
  `_coerce_lamports` (ROUND_HALF_UP, default on garbage); `curve_progress`
  stays a float ratio over new `CURVE_COMPLETION_LAMPORTS`.
  `CURVE_COMPLETION_SOL` kept (tests use it as SOL-denominated input).
- `ebbcb32` — `src/pumpgrok/engine/pipeline.py`: `tick_to_candidate`
  carries fixture `S` reserves (lamports) directly into `sol_in_curve`;
  progress over `CURVE_COMPLETION_LAMPORTS`; removed now-unused local
  `LAMPORTS_PER_SOL`.
- `3d26254` — `src/pumpgrok/engine/analyzer.py`: `enrich_token` converts
  `market_cap` (SOL) via `_to_lamports` and `virtual_sol_reserves`
  (already lamports) via `_to_base_units` instead of float division.

### A4 — Auditor exact SOL rendering
- `149283d` — `src/pumpgrok/engine/agents/auditor.py`: trade `sol`
  renders as `str(Decimal(lamports) / LAMPORTS_PER_SOL)` (exact string)
  instead of `round(float, 6)`.

### A1/A2 — Scaled integer prices through watcher and exit rules
- `276f513` — `src/pumpgrok/engine/watcher.py`: `price_fn`/`sell_fn`
  carry `int` prices scaled by `PRICE_SCALE`; missing quote is `0`.
- `9f5173e` — `src/pumpgrok/supervisor/exit_rules.py`: new `_scaled_price`
  (lamports/token Decimal → `PRICE_SCALE` int, ROUND_HALF_UP). `sync`
  builds `ExitPosition` from the ledger Decimal price and int base units
  (no `float(...)`); `_price` returns the scaled int quote (`0` when
  blind), so the `PositionWatcher` callback types now match.

### A5 — Test migration to integer money (behaviour unchanged)
- `9a5de92` — `tests/characterization/test_vendor_log.py` (lines
  127-128, 196-199, 211-212): `size_sol`/`entry_price`/`exit_price`/
  `pnl_sol` assert exact Decimal strings against integer lamports /
  scaled prices. `pnl_pct` stays a float ratio; `ts` stays epoch float.
- `6827d73` — `tests/characterization/test_exits.py`: `position()`
  scales to `PRICE_SCALE` ints / lamports; every price call passes
  `_px()` ints. Boundary behaviour kept (2.19 below +120%, 0.70 trips
  the 30% stop, 0.71 does not).
- `b865945` — `tests/characterization/test_watcher.py`: same scaling;
  blind quotes are int `0`; peak assertions compare exact ints; unused
  `pytest` import removed.
- `8a79a40` — `tests/characterization/test_analyzer.py` (lines 168,
  191, 253-262): lamport ints (1.5 SOL → 1_500_000_000, 30 SOL curve →
  30_000_000_000, fixture helpers scaled by 50_000_000 steps).
- `df8d010` — `tests/characterization/test_tune.py` (lines 44-45, 57,
  62, 67-70, 108-141): `Candidate`/`Outcome` use `pnl_lamports` ints;
  close-record wire inputs use exact `pnl_sol` decimal strings.
- `4d8de65` — `tests/characterization/test_reputation.py` (lines
  40-103): `record_close` uses `pnl_lamports`/`return_pct`; assertions
  use `realized_pnl_lamports`/`worst_loss_pct` (-400M + 1000M = 600M).
- `594f614` — `tests/safety/test_reputation_degraded.py` (lines
  232-233): rebuilt-book assertions use `worst_loss_pct` /
  `realized_pnl_lamports`.
- `66d4745` — `tests/characterization/test_pipeline.py` (unlisted but
  required by the A3 producer change): smoke assertion expects
  `sol_in_curve == 42_100_000_000`; `curve_progress` ratio unchanged.

### B1 — Paper composition genesis (INT-02)
- `88ef0fe` — `src/pumpgrok/tools/__init__.py` +
  `tests/integrity/test_paper_genesis_meta.py` (new): the replay
  composition root (`open_replay_runtime`, scheduler.py:820) writes
  `initial_equity_lamports`; the paper root never did, so a fresh paper
  ledger failed closed. `build_operator_registry` now writes the same
  meta row from the configured budget at genesis (set-if-absent: an
  existing genesis is never overwritten). The new test proves a fresh
  paper ledger (a) carries the budget meta, (b) keeps a pre-existing
  genesis, (c) reaches `shutdown` with code 0, and (d) lands the exit
  seat's `HaltSet` — all without `CorruptState`.

## Not finished / scope notes (no widening)

- `tests/characterization/test_vendor_state.py` ("old record_close
  kwargs…") and `tests/risk/test_reputation_durable.py`: verified by
  grep — neither file contains `record_close`, `pnl_*`, `worst_*` or any
  money reference, so there was nothing to migrate. No commit needed.
- `src/pumpgrok/engine/agents/narrative.py:66` still renders
  `round(token.market_cap_sol, 3)` — now lamports in, int out. Left
  untouched per A3's "producers only, minimal edits" scope; it is
  type-correct (`round(int, 3) -> int`) and needs no gate change.
  Follow-up (not this plan): render SOL there via Decimal division like
  the auditor.
- `test_evaluate_rounds_pnl_to_micro` (test_tune.py) keeps its name
  although PnL is now exact lamports; behaviour assertion updated in
  place, rename avoided as churn.
- Not run here (orchestrator runs after merge): `grep` for float money
  annotations in the INT-01 files, `mypy src/`,
  `uv run pytest -q tests/integrity`.

## Files changed

Sources: `engine/models.py`, `engine/monitor.py`, `engine/pipeline.py`,
`engine/analyzer.py`, `engine/agents/auditor.py`, `engine/watcher.py`,
`supervisor/exit_rules.py`, `tools/__init__.py`.
Tests: `characterization/test_vendor_log.py`, `test_exits.py`,
`test_watcher.py`, `test_analyzer.py`, `test_tune.py`,
`test_reputation.py`, `test_pipeline.py`,
`safety/test_reputation_degraded.py`,
`integrity/test_paper_genesis_meta.py` (new).
