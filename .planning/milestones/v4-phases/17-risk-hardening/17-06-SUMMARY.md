# Phase 17 Plan 06: Restart recovery Summary

**Phase:** 17-risk-hardening | **Plan:** 17-06 | **Wave:** 4
**Commit:** `cb91cf6` feat(17-06): ledger-backed restart recovery re-arming exit deadlines, tapes, peaks, probation and watch set

## One-liner

Ledger-backed restart recovery: re-arms exit deadlines and restores tapes, peaks, probation, and the watch set; resume proves no second sniper BUY and no second fill.

## What shipped

- `src/pumpgrok/supervisor/recovery.py` (new): idempotent recovery; crash mid-recovery followed by a second recovery converges to identical state; duplicate-buy guard.
- `src/pumpgrok/supervisor/event_desk.py`: restored-state property.
- Tests: kill-the-process restart recovery (corrupt ledger fails closed, crash-during-recovery resumes clean, resume places no second buy and no second fill, fresh candidate has no decision link), exit-deadline re-arming.

## Verification (at commit time)

- Targeted pytest suites passed at commit time (see git history).

## Requirements

RT-04, PRC-01.
