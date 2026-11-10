---
phase: 12-event-runtime-core
plan: 05
subsystem: events
tags: [drain, fixture-clock, dlq, sqlite, determinism]

requires:
  - phase: 12-event-runtime-core
    provides: EventBus, EventStore sidecar, FixtureClock.advance_to, trading-smoke fixture
provides:
  - Synchronous deterministic drain returning equal bytes for the same events and seed
  - Atomic DLQ-to-pending replay without a noop bus
affects: [12-event-runtime-core, journal CHANGELOG pins]

actuals:
  tokens: 3200
  tasks: 1
  commits: 1

tech-stack:
  added: []
  patterns:
    - "drain(events, clock, rng) is synchronous and advances FixtureClock; it does not sleep"
    - "DLQ replay moves a row to pending in one sqlite transaction"

key-files:
  created:
    - src/pumpgrok/events/drain.py
    - tests/replay/test_event_drain_parity.py
  modified:
    - src/pumpgrok/events/bus.py
    - src/pumpgrok/events/dlq.py
    - src/pumpgrok/events/store.py
    - src/pumpgrok/cli/events.py
    - tests/cli/test_events_cli.py

key-decisions:
  - "Risk commit does not include CHANGELOG.md. Journal pin lines are not done in this commit."
  - "Replay parks the event on pending for a later recover() instead of publishing onto a noop handler."
  - "Settings is imported only under TYPE_CHECKING so events/ does not import pumpgrok.config at runtime."

patterns-established:
  - "Fixture kind tick is mapped to EventKind.curve_tick only in the drain parity test."

requirements-completed: [EVT-08]

coverage:
  - id: D1
    description: "Two drains of the same in-memory events and seed 20260101 return equal bytes and pending count 0."
    requirement: EVT-08
    verification:
      - kind: unit
        ref: "tests/replay/test_event_drain_parity.py#test_determinism"
        status: pass
    human_judgment: false
  - id: D2
    description: "Five smoke fixture rows mapped from tick to curve_tick drain to equal bytes with seed 20260101, with no skip and no events.jsonl rewrite."
    requirement: EVT-08
    verification:
      - kind: unit
        ref: "tests/replay/test_event_drain_parity.py#test_smoke_trading"
        status: pass
    human_judgment: false
  - id: D3
    description: "events dlq replay moves the row from dlq to pending in one transaction. A failed move leaves the DLQ row."
    requirement: EVT-08
    verification:
      - kind: unit
        ref: "tests/cli/test_events_cli.py#test_dlq_list_replay_and_purge"
        status: pass
      - kind: unit
        ref: "tests/cli/test_events_cli.py#test_failed_replay_move_leaves_dlq_row"
        status: pass
    human_judgment: false
  - id: D4
    description: "Journal CHANGELOG Phase 12 hash pins are not in this risk commit."
    verification: []
    human_judgment: true
    rationale: "Task 2 is owned by bot-09-journal and was not committed on bot-02-risk/phase-12-event-runtime."

duration: 25min
completed: 2026-11-08
status: complete
plan_head_before: 6b137a9
---

# Phase 12 Plan 05: Deterministic drain Summary

**Synchronous FixtureClock drain returns byte-identical delivery logs, and DLQ replay parks the row on pending instead of dropping it on a noop bus.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-11-08
- **Completed:** 2026-11-08
- **Tasks:** 1 of 2 (risk half only)
- **Files modified:** 7

## Accomplishments

- `drain(events, clock, rng)` advances `FixtureClock` with `advance_to`, does not sleep, and returns equal bytes for the same events and seed.
- After drain returns, pending count is 0. A second drain of the same input, including a repeated id list, does not append again.
- Trading-smoke test maps fixture kind `tick` to `EventKind.curve_tick` and does not rewrite `events.jsonl`. No `fixture_compat` test and no skip.
- `events dlq replay` moves the sidecar row from `dlq` to `pending` in one transaction. The CLI no longer builds a noop bus, `FixtureClock(0.0)`, or `make_rng(1)`.
- `EventBus.from_settings` is annotated as `Settings` via a `TYPE_CHECKING` import. The `sidecar_path` type ignore is gone. `events/` does not import `pumpgrok.config` at runtime.

## Task Commits

1. **Task 1: deterministic drain and DLQ replay fix** - `66246aa` (feat)

Task 2 (journal CHANGELOG pin lines) is not done in this commit.

## Files Created/Modified

- `src/pumpgrok/events/drain.py` - synchronous drain
- `tests/replay/test_event_drain_parity.py` - `test_determinism` and `test_smoke_trading` only
- `src/pumpgrok/events/store.py` - `move_dlq_to_pending`
- `src/pumpgrok/events/dlq.py` - replay no longer takes a bus
- `src/pumpgrok/cli/events.py` - replay without noop bus, clock, or rng
- `src/pumpgrok/events/bus.py` - `Settings` annotation, no type ignore
- `tests/cli/test_events_cli.py` - failed move leaves the DLQ row

## Decisions Made

- Journal CHANGELOG lines stay off the risk branch.
- Republish is a pending insert, not a live handler call, because nothing is wired yet.
- Same-id input is ignored before the clock moves so a second copy does not append and does not rewind virtual time.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DLQ replay deleted the row then published onto a noop bus**
- **Found during:** Task 1
- **Issue:** `take_dlq` deleted the row, then `cli/events.py` published onto `handler=_noop` with `FixtureClock(0.0)` and `make_rng(1)`. Success was reported even when dedup suppressed delivery.
- **Fix:** One sqlite transaction inserts pending and deletes the DLQ row only if that insert commits. CLI no longer constructs a bus.
- **Files modified:** `src/pumpgrok/events/store.py`, `src/pumpgrok/events/dlq.py`, `src/pumpgrok/cli/events.py`, `tests/cli/test_events_cli.py`
- **Verification:** `uv run pytest -q tests/cli/test_events_cli.py` exit 0
- **Committed in:** 66246aa

**2. [Rule 1 - Bug] `from_settings` used `object` and a type ignore on `sidecar_path`**
- **Found during:** Task 1
- **Issue:** The ignore hid a missing `Settings` annotation and would have required a runtime config import if fixed naively.
- **Fix:** Import `Settings` under `TYPE_CHECKING` only and annotate the argument.
- **Files modified:** `src/pumpgrok/events/bus.py`
- **Verification:** `uv run mypy src/pumpgrok/events src/pumpgrok/cli/events.py` exit 0
- **Committed in:** 66246aa

---

**Total deviations:** 2 auto-fixed (2 bug)
**Impact on plan:** Both fixes are in the risk commit. CHANGELOG.md was not edited.

## Issues Encountered

The journal CHANGELOG task is not done in this commit. It remains for `bot-09-journal/phase-12-event-runtime`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Drain parity for the trading-smoke fixture is in place without claiming smoke-10m `fixture_compat`. Phase 13 was not started.

## Self-Check: PASSED

- FOUND: src/pumpgrok/events/drain.py
- FOUND: tests/replay/test_event_drain_parity.py
- FOUND: 66246aa
- CHANGELOG.md not in the risk commit
- Summary written outside the risk branch commit

## EXECUTION COMPLETE
