# Phase 19 Plan 05: Event-Mode Soak Summary

**Phase:** 19-observability · **Plan:** 05
**Status:** complete
**Date:** 2026-11-22

## What was built

- `tests/soak/test_soak_event_mode.py`: `@pytest.mark.slow` soak that drains the smoke fixture, asserts the golden hash `c5871bc0c40361aa3e0425a9745764f3787f70b0537f001f2c48b1e7762b6335`, runs the event desk with no admitted candidates and asserts `gateway.transport_calls == 0`. Skips fast runs (slow-marked + `PUMPGROK_REQUIRE_SOAK=1` guard).
- `.github/workflows/ci.yml`: the nightly schedule entry that runs the soak under `PUMPGROK_REQUIRE_SOAK=1` with `-m slow` already exists (runs `tests/soak` on schedule); no edit was needed. The default `make test` path stays fast (slow-marked, never in the fast path).

## Gates

- `PUMPGROK_REQUIRE_SOAK=1 uv run pytest tests/soak/test_soak_event_mode.py -m slow` → 1 passed.
- Fast run `uv run pytest tests/soak/test_soak_event_mode.py` → 1 deselected (exit 5, slow-marked; never in the fast path).

## Deviations

None — plan executed as written (the nightly schedule entry was verified present rather than re-added).

## Requirements

OBS-06.
