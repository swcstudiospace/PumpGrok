---
phase: 01-foundation
fix_scope: critical_warning
findings_in_scope: 8
fixed: 8
partial: 0
skipped: 0
failed: 0
iteration: 2
status: complete
---

# Phase 1: Code Review Fix Report

**Source review:** 01-REVIEW.md (committed f471efb, depth standard, 1 Critical, 7 Warning, 8 Info)
**Fix scope:** critical_warning (CR-01, WR-01 to WR-07). Info findings (IN-01 to IN-08) were not in scope and were not touched.
**Applied by:** inline fixer. No sub-agent could be spawned, so each fix was applied in the orchestrator context, one atomic commit per finding.
**Verification:** targeted pytest on the modules changed (`ci/tests/test_gates.py`, `tests/safety/test_static_guards.py`, `tests/test_logging.py`, `tests/replay/`). The canonical gate runner was not run, per the run contract. The `scripts/check.sh` emoji change was exercised with a scratch harness, not with the full script.

## Per-finding outcome

| Finding | Severity | Outcome | Commit | Files |
|---------|----------|---------|--------|-------|
| CR-01 | Critical | fixed: G-1 half in 104e708; G-4 half closed per binding resolution R56 in plan 01-11 | 104e708, 6af62c3, 0d31c12 | `ci/gates/check_ownership.py`, `ci/gates/check_contracts.py`, `ci/tests/test_gates.py`, `SECURITY.md`, `docs/cross-bot-protocol.md` |
| WR-01 | Warning | fixed | adea028 | `ci/gates/check_secrets.py`, `ci/gates/check_contracts.py`, `ci/tests/test_gates.py` |
| WR-02 | Warning | fixed | 5136509 | `ci/gates/check_ownership.py`, `ci/gates/check_contracts.py`, `ci/tests/test_gates.py` |
| WR-03 | Warning | fixed | f51db58 | `ci/gates/check_rollback.py`, `ci/tests/test_gates.py` |
| WR-04 | Warning | fixed | 6ff569a | `tests/safety/test_static_guards.py` |
| WR-05 | Warning | fixed | c12770d | `src/pumpgrok/logging/json.py`, `tests/test_logging.py` |
| WR-06 | Warning | fixed | 6fca20c | `src/pumpgrok/replay/fixtures.py`, `tests/replay/test_fixtures.py` |
| WR-07 | Warning | fixed | af36e17 | `scripts/check.sh` |

Skipped: none. Failed: none. Partial: none (CR-01 closed by R56, see below).

## CR-01: what was fixed and what was not

**Fixed (commit 104e708):** `check_ownership.main` classified contract surfaces before checking ownership, so a non-owner editing a shared contract got a G-1 NOTE and passed. Ownership is now checked first. `contracts/tool-rosters/bot-03-whale.yaml` edited from `bot-04-sniper` now fails with FOREIGN (owned by bot-02-risk). A regression test covers it.

**Closed (R56, plan 01-11).** The G-4 decisions are resolved by binding resolution R56 in 01-CONTEXT.md. Required acknowledgers are `contract_consumers(surface)` minus `proposed_by`. An acknowledgement from the proposer is ignored, not rejected. G-4 passes when every required acknowledger has an ack in the change file. The gate proves presence, not authorship; this residual limit is stated in SECURITY.md and docs/cross-bot-protocol.md. The earlier `proposed_by == --bot` requirement is superseded and is not implemented.

## Iterations (--auto)

- **Iteration 1 (fix pass):** the eight in-scope findings above, one commit each. CR-01 is partial, WR-01 to WR-07 are fixed.
- **Iteration 2 (re-review, inline):** the changed modules were re-read in full and the cumulative diff f471efb..HEAD was reviewed. No new Critical or Warning finding was found. `check_ownership --validate-manifest` self-test passes through `ci/tests/test_gates.py`, so every tracked path still has exactly one owner. Remaining in-scope item: CR-01 G-4 half, blocked on the decisions above.
- **Stop:** the loop stopped after iteration 2, before the cap of 3. The only open in-scope item has no derivable fix, so a further fixer pass would have nothing to apply. This is a decision block, not a cap.
- **REVIEW.md:** not rewritten. The iteration-2 result is recorded here; 01-REVIEW.md still holds the original review, and this report is the record of what changed since.

## Warnings that were reviewed and still apply (not in this fix run)

- `check_contracts._surface_match` (declared-surface matching) still uses `fnmatch` across `/`. It is the same class of defect as WR-02, but it was not in the cited finding and is not changed here. Its effect is lenient, so it can over-cover declared surfaces.
- `check_ownership._match` and `check_contracts._match` still ignore the literal prefix before `**/` (for example `a/**/b` matches `b` anywhere). This predates WR-02 and is unchanged.

## Files changed by the fix commits

`ci/gates/check_ownership.py`, `ci/gates/check_contracts.py`, `ci/gates/check_secrets.py`, `ci/gates/check_rollback.py`, `ci/tests/test_gates.py`, `tests/safety/test_static_guards.py`, `src/pumpgrok/logging/json.py`, `tests/test_logging.py`, `src/pumpgrok/replay/fixtures.py`, `tests/replay/test_fixtures.py`, `scripts/check.sh`.

Not committed by this run: `01-REVIEW.iter2.md` and `.planning/state.json` (untracked, pre-existing, left as found).
