---
phase: 06-integrity-closure
plan: 4
requirements: [INT-07]
files_modified: []
files_created:
  - tests/integrity/test_wr07_replay_ledger_removed.py
  - tests/integrity/test_ledger_mark_fee_partial_sell.py
commits:
  - dea531a
  - e20a621
status: complete
---

# Phase 6 Plan 4 (INT-07): Feature-lineage review fixes — Summary

Re-applied the two feature-lineage fixes (WR-07 replay-ledger cleanup,
commit 4c19fd9; partial-sell venue-fee scaling, commit 76975bb) against this
tree's code, each with a regression test under tests/integrity/ that fails
on the pre-fix behaviour (established by reading, not by running).

## Completed Tasks

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | WR-07 replay ledger cleanup on failed append or verify | dea531a | tests/integrity/test_wr07_replay_ledger_removed.py |
| 2 | Partial-sell venue fee scaling on the ledger-mark fallback | e20a621 | tests/integrity/test_ledger_mark_fee_partial_sell.py |

## Findings (verified by reading before writing)

- Both fix behaviours are already present verbatim in this tree's sources
  (arrived via the ef2f2f6 modernize port; neither 4c19fd9 nor 76975bb is an
  ancestor of HEAD):
  - `src/pumpgrok/replay/runner.py:15` imports `contextlib` and lines
    215-221 wrap `append_batch` + `verify` in `except Exception` that calls
    `recreate_ledger_db(target)` (which unlinks sqlite plus -wal/-shm,
    `src/pumpgrok/ledger/store.py:71-76`) and re-raises — identical to the
    4c19fd9 hunk.
  - `src/pumpgrok/ledger/reducer.py:252` computes `venue_share` and stores
    `last_mtm_venue_fee_lamports` on the partial-sell path — identical to
    the 76975bb hunk.
- The original regression tests also already exist on this tree
  (`tests/replay/test_runner_determinism.py:138`,
  `tests/ledger/test_review_partial_exit.py:111`). The new integrity tests
  add coverage the originals lack: the append-failure mode for WR-07, and
  an integrity-scope copy of the fee-scaling case with the full mark
  expectation derived from the reducer arithmetic
  (min(990*60//100, 990-400) = min(594, 590) = 590).

## Deviations from Plan

None requiring approval. No source edits were needed: the plan's
`files_modified` entries `src/pumpgrok/replay/runner.py` and
`src/pumpgrok/ledger/reducer.py` were verified (read + marker greps below)
to already carry the exact feature-lineage behaviour, so changing them
would have been churn. Only the two new test files were created.

## Known Stubs

None.

## Acceptance Commands (for the orchestrator to run after merge)

```bash
uv run pytest -q tests/integrity/test_wr07_replay_ledger_removed.py
uv run pytest -q tests/integrity/test_ledger_mark_fee_partial_sell.py
! git show 4c19fd9^:src/pumpgrok/replay/runner.py | grep -q 'contextlib' && grep -q 'contextlib' src/pumpgrok/replay/runner.py
! git show 76975bb^:src/pumpgrok/ledger/reducer.py | grep -q 'venue_share' && grep -q 'venue_share' src/pumpgrok/ledger/reducer.py
```

Pre-fix markers confirmed during execution (read-only `git show`, no
worktree, no out-of-repo copy): the `4c19fd9^` parent has no `contextlib`
import, and the `76975bb^` parent has no `venue_share`, so the new tests
target real regressions.
