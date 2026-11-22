---
phase: 13-curve-truth
plan: 06
status: complete
commit: 98877d8
---

# Phase 13 Plan 06: PumpPortal/logs feed, resync, readonly

## What shipped

- `datafeed/portal.py`: free methods only; shared 30/10s `RateLimiter` (shed, never burst); TIMEOUT reconnect via supervisor with gap events and signature dedup.
- `datafeed/logs.py`: `logsSubscribe` trades with bounded `getTransaction` follow-ups through the same limiter; malformed frames counted unknown.
- `datafeed/resync.py` seeds held mints via supervisor; `datafeed/readonly.py` five-method allowlist enforced before every outbound call; `datafeed/fallback.py` yields stale with no transport.
- `tests/datafeed/fake_feed.py` harness.

## Verification

- `uv run pytest -q tests/datafeed/test_feed.py tests/datafeed/test_readonly.py tests/datafeed/test_resync.py tests/test_network_block.py` — exit 0.

## Deviations

- `RateLimiter` lives in `portal.py` (shared by `logs.py`) instead of a separate module; no extra file beyond the plan list.
