---
phase: 12-event-runtime-core
plan: 02
subsystem: events
tags: [events, lanes, occurred_at]
requirements-completed: [EVT-01, EVT-02, EVT-03, EVT-14]
status: complete
key-files:
  created:
    - src/pumpgrok/events/__init__.py
    - src/pumpgrok/events/constants.py
    - src/pumpgrok/events/errors.py
    - src/pumpgrok/events/models.py
    - src/pumpgrok/events/bus.py
    - docs/design/events-grok.md
    - tests/events/test_models.py
    - tests/events/test_bus_lanes.py
    - tests/events/test_bus_backpressure.py
  modified:
    - tests/harness/faults.py
    - tests/harness/__init__.py
key-decisions:
  - "event_id hashes kind, entity_id, payload, and required occurred_at. correlation_id is excluded."
  - "P0 dispatches on its own per-entity task. P1 overflow calls the injected DLQ sink."
coverage:
  - id: D1
    description: "Event ids include required occurred_at; identical payloads at different times differ"
    requirement: EVT-01
    verification:
      - kind: unit
        ref: "tests/events/test_models.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "P0 is not blocked by a slow P1 handler; P1 overflow reaches a sink; P2 coalesces"
    requirement: EVT-02
    verification:
      - kind: unit
        ref: "tests/events/test_bus_backpressure.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Per-entity FIFO and P0 isolation"
    requirement: EVT-03
    verification:
      - kind: unit
        ref: "tests/events/test_bus_lanes.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "One EventKind class in events/models.py"
    requirement: EVT-14
    verification:
      - kind: unit
        ref: "tests/events/test_models.py"
        status: pass
    human_judgment: false
metrics:
  tasks: 2
  commits: 1
  duration: "one session"
---

# Phase 12 Plan 02: Catalog, lanes, and occurred_at ids Summary

One EventKind catalog, named lane constants, and an in-memory lane bus whose ids include required occurred_at.

## Commit

- `bace4d7` (`bace4d765e41ff4e6333abd57dd13051496205a6`): feat(events): add catalog, lanes, and occurred_at ids
- Branch: `bot-02-risk/phase-12-event-runtime`
- Worktree: `/root/src/repos/pumpgrok-wt/phase-12-risk`
- This summary is not on that branch.

## Pytest

```
uv run pytest -q tests/events/test_models.py tests/events/test_bus_lanes.py tests/events/test_bus_backpressure.py
..............                                                           [100%]
exit 0
```

Coverage verification status: pass.

## What landed

- `EventKind` exists only in `src/pumpgrok/events/models.py`. Members are the twelve locked names. There is no `tick` member.
- `occurred_at` is a required `str`. It is not optional and it is not defaulted. A missing value raises `ValidationError`.
- `event_id` is sha256 of `canonical_json` of kind, entity_id, payload, and occurred_at, first 32 hex chars. `correlation_id` is excluded. Two kill_switch events with payload `{"reason":"daily_loss"}` and different `occurred_at` values have different ids, and the bus delivers both. A second delivery of the same id is the only dedup.
- Money fields are strict int. A float payload raises `TypeError`.
- Constants match the locked table, including `P0_LANE_CAP = None` and `P1_LANE_CAP = 1000`. The bus reads those names.
- P0 is unbounded and is not blocked by a slow P1 handler. The 1001st P1 event is handed to the injected DLQ sink. P2 keeps one coalesced event per key. `curve_tick` is latest-wins. `mark` waits `P2_DEBOUNCE_S` on the injected clock.
- Importing `pumpgrok.events` does not open sqlite or a socket. The package does not import `LedgerStore`.
- `FaultyEventSource` and `FaultyGrokTransport` are raising fakes. No gateway.
- `docs/design/events-grok.md` locks the kind table, priority function, occurred_at id rule, and constants, and states the library is not wired into the supervisor.

## Deviations from Plan

### Auto-fixed Issues

None.

The red run failed at collection (`ModuleNotFoundError: No module named 'pumpgrok.events'`), then the green run passed after the import probe stopped replacing `socket.socket` with a non-class (that broke `ssl` during import). The probe now records connect and socket construction and asserts neither happened.

## Known Stubs

`EventBus.retry`, `EventBus.shutdown`, and `EventBus.recover` raise `NotImplementedError`. This plan does not implement retry, shutdown, or recover.

## Self-Check: PASSED

- Commit `bace4d7` exists on `bot-02-risk/phase-12-event-runtime`.
- Pytest exit 0, 14 passed, no skips.
