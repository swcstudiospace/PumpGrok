---
phase: 12-event-runtime-core
plan: 04
subsystem: events
tags: [sources, backoff, staleness, cursor, import-guard]
requires:
  - phase: 12-03
    provides: sidecar sqlite with a cursors table
provides:
  - SourceSupervisor for backoff, staleness, resync, and cursors
  - proof that the desk loop does not import the bus
affects: [12-event-runtime-core]
actuals:
  tokens: 9000
  tasks: 2
  commits: 1
tech-stack:
  added: []
  patterns:
    - injected Clock and seeded random.Random
    - corrupt cursor replaced inside the constructor
key-files:
  created:
    - src/pumpgrok/events/sources.py
    - tests/events/test_sources.py
    - tests/degradation/test_event_source_faults.py
    - tests/events/test_models_v4_kinds.py
    - tests/safety/test_events_not_wired.py
  modified:
    - src/pumpgrok/cli/dispatch.py
key-decisions:
  - "SourceSupervisor is the events-package staleness owner and is not wired into the desk supervisor."
  - "Backoff resets only after a continuous healthy span of STABLE_S. Jitter is rng.random() in [0, 1)."
  - "The events verb imports the bus only when that verb is selected, so verify and run do not import it."
requirements-completed: [EVT-09, EVT-14]
coverage:
  - id: D1
    description: Silence of 120.0 is not stale. Silence of 121.0 is stale. A source that has never framed is not stale.
    requirement: EVT-09
    verification:
      - kind: unit
        ref: tests/events/test_sources.py
        status: pass
    human_judgment: false
  - id: D2
    description: Backoff stays on the second step through a healthy span shorter than STABLE_S and resets after a continuous span of STABLE_S.
    requirement: EVT-09
    verification:
      - kind: unit
        ref: tests/events/test_sources.py
        status: pass
    human_judgment: false
  - id: D3
    description: resync records the caller mint list and stays resyncing until the next good frame. It does not open the paper ledger.
    requirement: EVT-09
    verification:
      - kind: unit
        ref: tests/events/test_sources.py
        status: pass
    human_judgment: false
  - id: D4
    description: Invalid cursor JSON or a bad schema version loads empty, writes a clean cursor, and does not raise out of the constructor.
    requirement: EVT-09
    verification:
      - kind: unit
        ref: tests/events/test_sources.py
        status: pass
    human_judgment: false
  - id: D5
    description: FaultyEventSource disconnect opens no socket. sources.py does not import httpx or websockets.
    requirement: EVT-09
    verification:
      - kind: unit
        ref: tests/degradation/test_event_source_faults.py
        status: pass
    human_judgment: false
  - id: D6
    description: class EventKind appears in events/models.py only. SourceStatus is not a second EventKind.
    requirement: EVT-14
    verification:
      - kind: unit
        ref: tests/events/test_models_v4_kinds.py
        status: pass
    human_judgment: false
  - id: D7
    description: supervisor, execution, engine, the replay runner, and verify/run do not import the bus.
    requirement: EVT-14
    verification:
      - kind: unit
        ref: tests/safety/test_events_not_wired.py
        status: pass
    human_judgment: false
duration: 20min
completed: 2026-11-08
status: complete
plan_head_before: b8de019
commits: 1
---

# Phase 12 Plan 04: Source Supervisor Summary

**SourceSupervisor owns backoff, 121-second staleness, resync, and cursor repair inside the events package, and the desk loop does not import the bus.**

## What shipped

- `SourceSupervisor` takes a `Clock` and a `random.Random`. It loads and saves the `source` cursor on the sidecar.
- Silence uses a strict greater-than check against `STALE_AFTER_S`. `last_frame_at is None` is not stale.
- One failure advances to the second backoff step. A healthy span shorter than `STABLE_S` does not reset. A continuous span of `STABLE_S` returns the next delay to the initial step plus jitter in `[0, 1)`.
- `resync` stores the caller mint tuple and stays `resyncing` until the next good frame. It does not import the ledger.
- A corrupt cursor or a bad schema version is replaced with `{"schema": 1}` and sets `cursor_reset`. The constructor does not raise.
- `dispatch.py` loads the events verb only when that verb is selected, so building the parser and importing verify/run does not import `pumpgrok.events.bus`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Lazy-import the events verb**
- **Found during:** Task 2
- **Issue:** `pumpgrok.cli` imports `dispatch`, which imported `events_verb` at module level, so building the parser imported the bus.
- **Fix:** `_events_handler` imports `events_verb` only when the events verb runs.
- **Files modified:** `src/pumpgrok/cli/dispatch.py`
- **Commit:** `6b137a9`

## Verification

`uv run pytest -q tests/events/test_sources.py tests/degradation/test_event_source_faults.py tests/events/test_models_v4_kinds.py tests/safety/test_events_not_wired.py` exited 0. Summary line: 12 passed. No SKIPPED.

`degraded.py` was not edited. `FixtureEventSource` was not replaced. No socket client was added.

## Self-Check: PASSED

- FOUND: `src/pumpgrok/events/sources.py`
- FOUND: `6b137a9`

## PLAN COMPLETE

**Plan:** 12-04
**Tasks:** 2/2
**SUMMARY:** `.planning/phases/12-event-runtime-core/12-04-SUMMARY.md`

**Commits:**
- `6b137a9`: feat(events): add source supervisor and import guard

**Duration:** 20min
