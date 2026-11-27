---
phase: 13-curve-truth-live-market-data-and-recorder
status: complete
merged: 2026-11-26 (local main 8354ee6, PRs #64-#70 + #73; local-only, GitHub OPEN until push)
---
# Phase 13 summary: curve truth, live market data and recorder

## Plans
- 13-01: Read-only observation-to-recording tracer and event-bus bridge; read-only transport boundary.
- 13-02: Token-first curve decoder, deny-by-default source admission, live paper price and held-position marks.
- 13-03: Source-bound replay and entry authority with v1 replay retained; live-source composition deferred to 13-04.
- 13-04: Portal creation/migration and Solana trade logs connected to the event runtime with bounded recovery.
- 13-05: Truthful read-only probe evidence and mandatory human decision before any verification status change.
- 13-06: Replay-compatible sealed recordings and isolated durable ledger mechanics; no production authority activated.
- 13-07: Integrated paper-only pipeline proof and both replay hash pairs recorded.

## Evidence
- 13-VERIFICATION.md: status passed, verified head 27cdcd9 (bot-00-chief/v4-phase-13).

## Per-plan summaries
- Per-plan SUMMARY files exist only for 13-01. No per-plan summaries were written for 13-02..13-07 (no evidence base); phase rollup only.

## Known gaps carried forward
- Portal frame field names are ASSUMED until a live probe confirms them.
- No live-feed provenance type exists; live held positions degrade to gaps.
- The supplied-mark branch in datafeed/marks.py is unreachable under the strict gate and should be removed when a feed provenance exists.
- Recorder crash recovery resumes a dataset that was previously fresh-only (flagged for review).
- Object-identity provenance check in marks can be bypassed by patching an instance method in a test; production cannot.
- RISK edited execution/__init__.py (SNIPER-owned); owner confirmation pending.
- Strict-gate tests that pass only because fixture snapshots are refused (tests/datafeed live-labelled desk cases) need a reviewer pass.
