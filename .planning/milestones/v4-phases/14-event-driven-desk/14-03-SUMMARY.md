---
phase: 14-event-driven-desk
plan: "03"
status: complete
commit: c0081d2
---

# Phase 14 Plan 03: Supervisor event wake — Summary

`wake.py` maps every `EventKind` to seat wakes through the closed
`SEAT_WAKES` table; only the `wake` timer is allowed and `assert_allowed_timers`
fails closed on anything else. `--wake-mode {cadence,event}` added to `run`
(default cadence); cadence modules do not import `wake`. `metrics_events.py`
registers five event/Grok families only in event mode; the nine existing
families are unchanged.

## Gates

- `uv run pytest -q tests/desk/test_event_wake.py tests/desk/test_event_mode_run_once.py tests/supervisor/test_scheduler.py` — exit 0 (12 passed)
- `uv run pytest -q tests/supervisor/test_metrics.py tests/desk/test_metrics_events.py` — exit 0 (7 passed)
- Plan `<verification>` — exit 0

## Notes

- A pre-existing full-suite pytest run timed out at 300 s in the agent shell
  (baseline suite is slow; the phase gate re-runs it within the 1500 s
  window at 14-09 with `make test`).
