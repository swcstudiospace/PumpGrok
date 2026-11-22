# Phase 19 Plan 02: Health and Metrics Summary

**Phase:** 19-observability · **Plan:** 02
**Status:** complete
**Date:** 2026-11-22

## What was built

- `src/pumpgrok/supervisor/health.py`: `build_status` gains `events` (depth, sources, DLQ), `strategies` (stage, slice per strategy), `promotion` (stage counts, recent decisions) sections. Defaults preserve every existing field; health write path gains no write into runtime state.
- `src/pumpgrok/supervisor/metrics_events.py`: per-strategy families `pumpgrok_strategy_p_total` (P), `pumpgrok_strategy_l_total` (live L), `pumpgrok_strategy_stage` (labels strategy/stage only). `EVENT_FAMILIES` unchanged; strategy families follow the same event-mode-only emission rule. Nine existing families untouched (names/labels asserted byte-identical).

## Tests

- `tests/desk/test_health_event_sections.py` (new): sections render, values carried, existing fields unchanged, zero-skip.
- `tests/desk/test_metrics_strategy.py` (new): strategy families appear in event mode, absent in cadence, nine unchanged, labels ids-only, zero-skip.
- Gate: `uv run pytest tests/supervisor/test_metrics.py tests/desk/test_health_event_sections.py tests/desk/test_metrics_strategy.py` → 13 passed.

## Deviations

None — plan executed as written.

## Requirements

OBS-02.
