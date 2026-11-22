---
phase: 14-event-driven-desk
plan: "02"
status: complete
commit: 1da3724
---

# Phase 14 Plan 02: Agents behind gateway + fallback ladder — Summary

`SignalSeat`, `ScoutSeat`, `WhaleSeat`, and `RugSeat` route every Grok call
through the single gateway entry with an event consequence id; no agent file
imports `agents.base` or constructs `GrokAgent`. `FallbackLadder` follows
`signal_scoring_mode` (primary, fast, deterministic) with a breaker that
opens on repeated failure and a single-flight half-open probe re-admitting
the primary after a cooldown on FixtureClock.

## Gates

- `uv run pytest -q tests/engine/test_gateway_agents.py` — exit 0 (9 passed)
- `uv run pytest -q tests/grok/test_fallback_ladder.py` — exit 0 (5 passed)
- Plan `<verification>` (`test_sanitize_injection.py + test_gateway_agents.py`) — exit 0 (19 passed)
