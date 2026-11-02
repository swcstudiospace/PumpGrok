---
phase: 06-integrity-closure
plan: 8
subsystem: exits
tags: [trailing-stop, ledger, restart, INT-09]
status: complete

# Dependency graph
requires:
  - phase: 06-integrity-closure
    provides: 06-CONTEXT.md shared decisions (D-10: persist peaks through an existing type, restore before first exit check)
provides:
  - exits.restore_peak: pure ledger-peak to PRICE_SCALE restore, never below entry
  - LedgerExitBook.sync restores the persisted peak for fresh tracks (serve restart)
  - tests/integrity/test_peaks_survive_restart.py restart proof (INT-09)
affects: [06-integrity-closure closing plan (replay hash compare)]

# Actuals (#2632)
actuals:
  tokens: 9000
  tasks: 1
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns: ["restore-from-fold: in-memory ratchet plus ledger-persisted peak, max() on re-sync"]

key-files:
  created:
    - tests/integrity/test_peaks_survive_restart.py
  modified:
    - src/pumpgrok/engine/exits.py
    - src/pumpgrok/supervisor/exit_rules.py

key-decisions:
  - "No new ledger event type: peaks already persist via MarkToMarket spot (reducer ratchets price_peak); the gap was restore-only"
  - "Restore lives in LedgerExitBook.sync (the rebuild before every exit pass); same-position tracks keep max(in-memory, persisted)"
  - "exit_signal stays pure; apply_price stays the single in-memory ratchet; no signature changes"

metrics:
  duration: single session
  completed: 1/1 tasks
  files: 3
---

# Phase 06 Plan 08: Trailing-stop peaks survive a serve restart (INT-09) — Summary

One-liner: serve-restart peak restore from the MarkToMarket fold, no new event type.

## What was built

**Persist (verified on-tree, no change needed):** the serve loop already writes
one combined `MarkToMarket` row per instant (`scheduler.refresh_marks` ->
`adapter.mark_open_positions`), and the reducer already ratchets
`price_peak = max(peak, spot)` from each row (`reducer._on_mtm`), raising
`CorruptState` on an undecodable spot (fail-closed, INT-02). `events.py` is
untouched: the eighteen R32 types stay eighteen.

**Restore (the gap, now closed):**

- `src/pumpgrok/engine/exits.py`: new pure `restore_peak(entry_price, ledger_peak)`
  converts the folded Decimal peak to the integer `PRICE_SCALE` price (half-up,
  matching `_scaled_price`) and floors at entry. `exit_signal` stays pure;
  `apply_price` stays the single in-memory ratchet; public signatures unchanged.
- `src/pumpgrok/supervisor/exit_rules.py`: `LedgerExitBook.sync` — the rebuild
  that runs before every exit pass, including the first after a restart — now
  restores the persisted peak for fresh tracks (restart, or re-entry after a
  close) and keeps `max(prior, persisted)` for the continuing position, so a
  lagging mark never drags a live peak down. `persist()` stays a no-op with a
  corrected docstring (persistence flows through the mark rows); the module
  docstring no longer claims restarts re-learn from the next curve read.

**Proof:** `tests/integrity/test_peaks_survive_restart.py` (deterministic,
real `LedgerStore`, no network):

1. Marks at spots 120/150 ratchet the fold peak; a fresh book restores
   `peak == 150 * PRICE_SCALE`; a post-restart fresh book restores the same.
2. First exit check after restart: a slide to 90 (40% off the restored peak)
   fires `trailing_stop` through `PositionWatcher.check_once`.
3. Control: an unmarked position restarts at entry and holds on a 10% dip.
4. A re-sync keeps the higher in-memory peak (160) when the latest mark (155) lags.

## Deviations from Plan

**Files list extension (plan action required it):** the plan's `files_modified`
omitted the wiring point. The `<action>` explicitly says "wire into the
serve/supervisor restart path that rebuilds state" — that path is
`LedgerExitBook.sync` in `src/pumpgrok/supervisor/exit_rules.py`, so it carries
the one-line restore plus docstring corrections. `src/pumpgrok/ledger/reducer.py`
and `src/pumpgrok/risk/engine.py` needed no edits (verified: reducer already
ratchets + fail-closes; risk engine holds no exit-peak state) — listed but
intentionally unchanged.

## Acceptance commands (for the orchestrator gates)

```bash
uv run pytest -q tests/integrity/test_peaks_survive_restart.py
test "$(grep -cE '\(_ClosedModel\)' src/pumpgrok/ledger/events.py)" = 18
```

Not run in-worktree per assignment (no make/pytest/ruff/mypy/check.sh here);
left for post-merge gates.

## Commits

- `8f610a3` feat(06-08): restore trailing-stop peaks from ledger fold on sync (INT-09)
- `69a0ff2` test(06-08): serve-restart peak restore through MarkToMarket (INT-09)

## Self-Check: PASSED

- `src/pumpgrok/engine/exits.py` restores via `restore_peak`: present.
- `src/pumpgrok/supervisor/exit_rules.py` sync restores persisted peak: present.
- `tests/integrity/test_peaks_survive_restart.py`: present (191 lines, 4 tests).
- `events.py` untouched (no new type) — verified via `git status` (only the
  two source files plus the new test).
- Commits `8f610a3`, `69a0ff2` exist in this worktree.
