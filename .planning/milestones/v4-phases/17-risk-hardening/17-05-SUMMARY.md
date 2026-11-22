# Phase 17 Plan 05: Event desk Summary

**Phase:** 17-risk-hardening | **Plan:** 17-05 | **Wave:** 3
**Commit:** `c96e993` feat(17-05): paper-only event desk composition root wiring bus, sources, runtime, gateway, router and promotion

## One-liner

Paper-only event desk composition root wiring the bus, sources, runtime, gateway, router, risk, and promotion edges end to end on recorded data.

## What shipped

- `src/pumpgrok/supervisor/event_desk.py` (new): builds the desk on recorded data; refuses to build unless the mode is paper; promotion evaluation is event-triggered with no timers and no Grok calls.
- `src/pumpgrok/supervisor/live_paper.py`: paper strategy factory wiring risk into the desktop.
- Tests: event-desk e2e on recorded data, idle desk makes zero Grok calls and zero trade ledger writes, live-paper risk wiring, no-timers promotion test, golden digest fixture.

## Verification (at commit time)

- Targeted pytest suites passed at commit time (see git history).

## Requirements

PRM-05, RT-03, PRC-01.
