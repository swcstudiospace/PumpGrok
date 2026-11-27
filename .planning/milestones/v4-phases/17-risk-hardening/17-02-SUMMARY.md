# Phase 17 Plan 02: Feed health and live failure classes Summary

**Phase:** 17-risk-hardening | **Plan:** 17-02 | **Wave:** 1
**Commit:** `e36dff8` feat(17-02): lazy idle-quiet feed health and live failure classes in exec_errors breaker

## One-liner

Lazy, idle-quiet feed-health checks and exec-error breaker routing for live failure classes.

## What shipped

- `src/pumpgrok/risk/feed_health.py` (new): required-feed staleness evaluated on read; never-ticked required feed fails closed in live mode; optional-feed degradation is per-stream; idle desk stays healthy after 24 virtual hours with no events.
- `src/pumpgrok/risk/breakers.py`: `note_live_failure` routes transient classes into the exec-error counter; `UNKNOWN` sets an un-retried halt requiring a human clear.
- `src/pumpgrok/risk/engine/core.py`: feed-health verdict enforced on `data_stale` before the slice check.
- Tests: feed health (fault injection), exec-failure breaker.

## Verification (at commit time)

- Targeted pytest suites passed at commit time (see git history).

## Requirements

RSK-03, RSK-04, PRC-01.
