# Phase 17 Plan 03: Entry checks Summary

**Phase:** 17-risk-hardening | **Plan:** 17-03 | **Wave:** 2
**Commit:** `9093f22` feat(17-03): fail-closed entry checks on mint authority, extensions, holders, lists and BLIND

## One-liner

Fail-closed pre-order entry checks: mint authority, Token-2022 extensions, holder concentration, allow/block lists, and BLIND cases rejected before any order is placed.

## What shipped

- `src/pumpgrok/risk/entry_checks.py` (new): one check per case class plus missing-file fail-closed; list files parsed as TOML.
- `src/pumpgrok/config/mint_lists.toml` (new): version-controlled allow/block lists.
- `src/pumpgrok/execution/entry_hook.py`: mint checks run before any adapter call; bad mints raise `EntryRefusedError`.
- Tests: one case per rejection class plus passing control mints, missing-file fail-closed, TOML parse check.

## Verification (at commit time)

- Targeted pytest suites passed at commit time (see git history).

## Requirements

RSK-05, PRC-01.
