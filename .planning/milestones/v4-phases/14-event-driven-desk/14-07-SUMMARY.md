---
phase: 14-event-driven-desk
plan: "07"
status: complete
commit: bf5958c
---

# Phase 14 Plan 07: Metrics + measurement — Summary

`scripts/measure_grok_calls.py` runs the gateway (prefilter + cache) over a
recorded dataset on FixtureClock and prints before/after JSON (counts only).
The `evidence-50` fixture carries 320 tick events over 60 distinct mints
(60 admitted candidates, loads via `load_dataset`). No production behavior
change.

## Gates

- `uv run pytest -q tests/replay/test_evidence50_fixture.py` — exit 0 (3 passed, incl. budget-too-small negative control)
- `uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/evidence-50 --min-candidates 50 --max-ratio 0.2` — exit 0 (`calls_before=320, calls_after=60, ratio=0.1875`)
- `uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/soak-3d --max-ratio 0.2` — exit 0 (`calls_before=4320, calls_after=2, ratio=0.0005`)
