# Phase 17 Plan 07: Phase closure Summary

**Phase:** 17-risk-hardening | **Plan:** 17-07 | **Wave:** 5
**Commit:** `67e9346` style(17-07): lint/type repairs across touched files

## One-liner

Lint/type repair pass over all Phase 17 touched files plus the full PRC-01 gate set: all gates green, both replay hash pairs unchanged, contracts untouched, live still refused.

## Repairs (this plan)

- `thresholds.py`: `load_thresholds` split into `_read_section` / `_int_threshold` / `_decimal_threshold` helpers (C901 11 → ≤10, E501 wraps).
- `strategy_slice.py`: `load_slice_config` reduced to 4 returns (PLR0911), `SliceError` still propagates.
- `engine/core.py`: long kill-check line wrapped; `killed_strategies` stays lazy (only called for buys with a strategy id).
- `event_desk.py`: `metrics is None` guard for `StageRow` (mypy arg-type); stale `type: ignore` removed.
- Tests: inline `itertools`/`sqlite3`/`tomllib` imports hoisted to top level (PLC0415), `try/except/pass` → `contextlib.suppress` (SIM105), unused `clock` removed (F841), `dict(...)` → dict literals (C408), long lines wrapped (E501) in `test_gate_reuse`, `test_entry_checks`, `test_feed_health`, `test_thresholds`.
- `ruff check .` and `ruff format --check .` clean; `mypy` strict clean on `src/`.

## Gates

| Gate | Result |
|------|--------|
| `make lint` | exit 0 |
| `make typecheck` | exit 0 |
| `make test` | exit 0 |
| `make audit` | exit 0 |
| `./scripts/check.sh` | exit 0 |
| paper replay smoke | exit 0 |
| live refusal | exit 3 |
| `git diff v4-base -- contracts` | empty |
| pin tests (8) | pass |

## Deviations (auto-fixed)

**[Rule 1 — stale safety guard]** `tests/safety/test_events_not_wired.py` predates the event desk (RT-03): it asserted no `supervisor/` module imports the bus, but the desk is the sanctioned composition root that wires it. Only `supervisor/event_desk.py` imports the bus; every desk-loop root still avoids it. The guard now exempts `event_desk.py` with an RT-03 comment. Commit `1774132`.

## Hash pairs (no hash move)

See [17-VERIFICATION.md](./17-VERIFICATION.md) for the four journal lines.

## Requirements

PRC-01, PRC-03, LIV-07, PRM-01.

## Notes

- CHANGELOG.md untouched (journal-owned): the four Phase 17 lines are computed in this plan and recorded in 17-VERIFICATION.md for the journal seat to add.
