---
phase: 14-event-driven-desk
plan: "06"
status: complete
commit: ba5c190
---

# Phase 14 Plan 06: Idle-zero-Grok gate — Summary

`events/idle.py`: 24 virtual hours on FixtureClock with zero source events,
counting gateway calls through a counting transport fake. `check_idle_grok`
prints `idle-grok calls=0` and exits 0 on silence, non-zero otherwise. Wired
into `run_all.py`, `Makefile idle-grok`, and `ci.yml` idle-grok step (no
or-true masking). Degradation suite covers hung transport exit deadline
(ExitTrigger never delayed), poison/duplicate/P0-flood/gap paths, and the
no-grok-import guard for exit rules/risk/execution.

## Gates

- `uv run pytest -q tests/events/test_idle_zero_grok.py ci/tests/test_idle_grok_gate.py` — exit 0 (3 passed)
- `uv run python ci/gates/check_idle_grok.py` — exit 0 (`idle-grok calls=0`)
- `uv run pytest -q tests/degradation tests/events tests/grok` — exit 0 (160 passed)
- `grep -q check_idle_grok ci/gates/run_all.py`, `grep -q idle-grok .github/workflows/ci.yml`, `grep -q idle-grok Makefile` — all exit 0
