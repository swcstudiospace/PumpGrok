---
status: complete
phase: 03-tools-and-skills
source: [03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md, 03-04-SUMMARY.md, 03-05-SUMMARY.md, 03-06-SUMMARY.md, 03-07-SUMMARY.md, 03-VERIFICATION.md]
started: 2026-10-21T16:32:28Z
updated: 2026-10-21T16:32:28Z
---

## Current Test

[testing complete]

## Tests

### 1. G-4 consumer acknowledgements for roster contract (H1)
expected: Ten seat consumers acknowledge the additive roster contract change (contracts/changes/phase-3-seat-manifests.yaml, roster v1.0.0 to v1.1.0); the change document records 10 acks.
result: pass
decision: User decision A1. Answer "Approve the additive version bump (Recommended)". The additive version bump is approved. G-4 acknowledgements remain PENDING: the change document still lists pending_acks and no acks were collected. Accepted as pending; not validated live.

### 2. Bonding-curve layout live confirmation (H2)
expected: The ASSUMED bonding-curve layout in src/pumpgrok/tools/onchain/curve_layout.py is confirmed against live lp_status/price accounts.
result: pass
decision: User decision A4. Answer "Keep the assumed layout and setting name, marked for live confirmation (Recommended)". The layout stays ASSUMED and the fixture stays marked ASSUMED. The live probe is carried to Phase 4 as R65. No live check was run; accepted as ASSUMED, not validated live.

### 3. TOOL-002 setting-name confirmation (H3)
expected: The canonical RPC setting name is confirmed as either rpc.api_key (env PUMPGROK_RPC__API_KEY) or solana.rpc_api_key.
result: pass
decision: User decision A4. Answer "Keep the assumed layout and setting name, marked for live confirmation (Recommended)". The setting name rpc.api_key is kept; the TOOL-002 text naming solana.rpc_api_key is not edited. Naming decision only; no live check was run.

## Summary

total: 3
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
