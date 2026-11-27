---
phase: 14-event-driven-desk
plan: "04"
status: complete
commit: 257f74e
---

# Phase 14 Plan 04: Ten seat cycles + drain parity — Summary

`event_cycles.py`: one cycle body per seat (ten seats) invoked on wakes with
only the waking event's typed fields; unknown seat fails loudly; one wake
invokes at most one cycle per seat. `journal_rollup.py` counts journal wakes
by kind. `event_cycles_aux.py` wraps the Phase 12 drain as DeterministicBus
(fixture_compat required). Golden hashes pinned for smoke
(e31e667c...), smoke-10m (888e1849...), and soak-3d (c08ad0dd...); the
legacy smoke-10m `events.hash` b69c... parity proof passes exactly via
`verify_fixture` with zero skipped tests.

## Gates

- `uv run pytest -q tests/desk/test_event_cycles.py tests/desk/test_event_cycles_aux.py tests/desk/test_journal_rollup_event.py tests/desk/test_event_golden_hashes.py` — exit 0 (11 passed)
- `uv run pytest -q tests/replay/test_event_drain_parity.py` — exit 0 (4 passed)
- `! uv run pytest tests/desk/test_event_cycles.py -rs | grep -q SKIPPED` — exit 0

## Deviations

- `tests/replay/test_event_drain_parity.py` already existed (Phase 12
  drain tests); the parity test was appended rather than created.
- No `DeterministicBus`/`fixture_compat` existed in `src/`; it is implemented
  as a thin wrapper over the Phase 12 `drain` (no second drain).
