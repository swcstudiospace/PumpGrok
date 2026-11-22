---
phase: 14-event-driven-desk
plan: "01"
status: complete
commit: 29a0b9b
---

# Phase 14 Plan 01: Grok gateway core — Summary

Single gateway in `src/pumpgrok/grok/`: deterministic prefilter (skip before
budget spend), sanitizer + strict JSON parse, canonical cache key of
ints/strings with per-agent TTLs, in-flight coalescing, layered persisted
budget with reserve share, hash-only gateway ledger, replay backend that
raises on a miss. `BudgetSurface` added to `core/llm.py` (no transport, no
HTTP); `config/sections/grok_gateway.py` re-exports the off-by-default
`GrokGatewaySettings`. Exit rules/risk/execution do not import the gateway.

## Gates

- `uv run pytest -q tests/grok/test_prefilter.py tests/grok/test_cache.py tests/grok/test_cache_key_payload.py tests/grok/test_coalesce.py` — exit 0 (11 passed)
- `uv run pytest -q tests/grok/test_budget.py tests/grok/test_replay_backend.py tests/replay/test_replay_determinism.py` — exit 0 (9 passed)
- Plan `<verification>` — exit 0 (15 passed)

## Notes

- Test harness quirk: piping pytest output through a pipe in the agent shell
  yields "No tests collected"; redirecting to a file gives full collection.
  No test, source, or config change needed for this.
