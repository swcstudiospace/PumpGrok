---
phase: 12-event-runtime-core
plan: 03
subsystem: events
tags: [sqlite, sidecar, dlq, retry, cli]
requires:
  - phase: 12-02
    provides: event catalog, lane caps, dedup TTLs, and occurred_at ids
provides:
  - sidecar sqlite for dedup, pending, applied, and DLQ
  - transient retry from an injected RNG and one-shot recover
  - events dlq list, replay, and purge
affects: [12-event-runtime-core]
actuals:
  tokens: 14000
  tasks: 2
  commits: 1
tech-stack:
  added: []
  patterns:
    - caller-supplied sidecar path
    - stdlib sqlite3 only
key-files:
  created:
    - src/pumpgrok/events/store.py
    - src/pumpgrok/events/dlq.py
    - src/pumpgrok/cli/events.py
    - tests/events/test_bus_dedup_coalesce.py
    - tests/events/test_bus_retry_dlq.py
    - tests/events/test_handler_idempotency.py
    - tests/events/test_bus_shutdown.py
    - tests/cli/test_events_cli.py
  modified:
    - src/pumpgrok/events/bus.py
    - src/pumpgrok/cli/parsing.py
    - src/pumpgrok/cli/dispatch.py
key-decisions:
  - "EventStore opens only the caller path and refuses a resolved PAPER_LEDGER_PATH before connect."
  - "Transient handlers run RETRY_ATTEMPTS times. Jitter is rng.random() in [0, 1) with no host sleep."
  - "The events verb refuses when events.enabled is false and does not open a socket or the paper ledger."
requirements-completed: [EVT-04, EVT-05, EVT-06, EVT-07]
coverage:
  - id: D1
    description: P0 and P1 dedup survive reopen and expire only after the named TTL on the injected clock.
    requirement: EVT-04
    verification:
      - kind: unit
        ref: tests/events/test_bus_dedup_coalesce.py
        status: pass
    human_judgment: false
  - id: D2
    description: Transient errors retry from the injected RNG. Poison writes one DLQ row and stops.
    requirement: EVT-05
    verification:
      - kind: unit
        ref: tests/events/test_bus_retry_dlq.py
        status: pass
    human_judgment: false
  - id: D3
    description: A duplicate derived id appends once. Two kill_switch events with different occurred_at values append twice.
    requirement: EVT-06
    verification:
      - kind: unit
        ref: tests/events/test_handler_idempotency.py
        status: pass
    human_judgment: false
  - id: D4
    description: shutdown persists pending events. recover delivers each pending event once.
    requirement: EVT-07
    verification:
      - kind: unit
        ref: tests/events/test_bus_shutdown.py
        status: pass
    human_judgment: false
  - id: D5
    description: pumpgrok events dlq list, replay, and purge use settings.events.sidecar_path and refuse when disabled.
    requirement: EVT-07
    verification:
      - kind: unit
        ref: tests/cli/test_events_cli.py
        status: pass
    human_judgment: false
duration: 25min
completed: 2026-11-08
status: complete
plan_head_before: bace4d7
commits: 1
---

# Phase 12 Plan 03: Sidecar, Retry, and DLQ Summary

**Sidecar sqlite stores dedup, pending, and DLQ; the bus retries transient errors from an injected RNG and the events CLI republishes or drops named rows without opening the paper ledger.**

## Performance

- **Duration:** 25 min
- **Completed:** 2026-11-08
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- EventStore opens a caller path, refuses a resolved `PAPER_LEDGER_PATH` before connect, and creates pending, applied, dedup, dlq, cursors, and meta.
- Transient handler failures retry `RETRY_ATTEMPTS` times with jitter from the injected RNG. Poison writes one DLQ row and stops.
- shutdown persists queued events. recover delivers each pending event once. A second recover is a no-op.
- `pumpgrok events dlq list|replay|purge` uses `settings.events.sidecar_path`. A disabled section refuses without a socket and without opening the paper ledger.

## Task Commits

1. **Task 1 and Task 2: sidecar, retry, shutdown, and events CLI** - `b8de019` (feat)

**Plan metadata:** not committed on `bot-02-risk/phase-12-event-runtime`.

## Files Created/Modified

- `src/pumpgrok/events/store.py` - sidecar sqlite
- `src/pumpgrok/events/dlq.py` - list, replay, purge
- `src/pumpgrok/events/bus.py` - dedup, retry, shutdown, recover
- `src/pumpgrok/cli/events.py` - events verb
- `src/pumpgrok/cli/parsing.py` - events parser
- `src/pumpgrok/cli/dispatch.py` - events registration
- `tests/events/test_bus_dedup_coalesce.py`
- `tests/events/test_bus_retry_dlq.py`
- `tests/events/test_handler_idempotency.py`
- `tests/events/test_bus_shutdown.py`
- `tests/cli/test_events_cli.py`

## Decisions Made

- The constructor takes the path. `EVENTS_SIDECAR_PATH` remains the `EventsSettings.sidecar_path` default.
- Product code under `src/pumpgrok/events` does not import the paper ledger store class.
- No tenacity, no host sleep, no hash chain, and no table named events.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Mark debounce test yielded before advancing the fixture clock**
- **Found during:** Task 1
- **Issue:** The clock advanced before the debounce sleep was scheduled, so the latest mark was never delivered.
- **Fix:** Yield to the loop before `advance_to`, matching the existing mark test.
- **Files modified:** tests/events/test_bus_dedup_coalesce.py
- **Verification:** mark debounce assertion passed
- **Committed in:** b8de019

**Total deviations:** 1 auto-fixed
**Impact on plan:** Test timing only. No product behavior change beyond the planned bus.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Sidecar, retry, shutdown, and the events verb are on `bot-02-risk/phase-12-event-runtime` at `b8de019`. The bus is not wired into the supervisor.

## Self-Check: PASSED

- FOUND: src/pumpgrok/events/store.py
- FOUND: src/pumpgrok/events/dlq.py
- FOUND: src/pumpgrok/cli/events.py
- FOUND: b8de019

## Verification

`.venv/bin/pytest -q` on the five plan test files exited 0 with 13 passed. The equivalent `uv run pytest -q` rerun was intercepted by the harness and did not collect tests.

---
*Phase: 12-event-runtime-core*
*Completed: 2026-11-08*
