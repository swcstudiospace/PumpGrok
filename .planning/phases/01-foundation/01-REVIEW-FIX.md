---
phase: 01-foundation
fix_scope: critical_warning
findings_in_scope: 10
fixed: 10
skipped: 0
failed: 0
iteration: 2
status: all_fixed
---

# Phase 1: Code Review Fix Report

**Source review:** 01-REVIEW.md (iteration 1, reviewed 2026-10-21T03:11:18Z)
**Fix scope:** critical_warning (1 Critical, 9 Warning). Info findings were not in scope.
**Applied by:** inline fixer. No sub-agent could be spawned, so each fix was applied in the orchestrator context, one atomic commit per finding.
**Verification:** diff inspection and a parse check of every changed module. The test suite was not run, per the run contract. The orchestrator should run it.

## Per-finding outcome

| Finding | Severity | Outcome | Commit | Files |
|---------|----------|---------|--------|-------|
| CR-01 | Critical | fixed | 3b4e1ea | `.env.example`, `tests/config/test_settings.py` |
| WR-01 | Warning | fixed | 8101b38 | `src/pumpgrok/core/risk_budget.py` (new), `src/pumpgrok/core/bot.py`, `src/pumpgrok/config/settings.py`, `src/pumpgrok/core/__init__.py`, `tests/core/test_models.py` |
| WR-02 | Warning | fixed | 6d054e0 | `src/pumpgrok/config/settings.py`, `tests/config/test_secret_refusal.py` |
| WR-03 | Warning | fixed | 57994bf | `src/pumpgrok/core/atomic_write.py`, `tests/core/test_ids.py` |
| WR-04 | Warning | fixed | e55ec46 | `src/pumpgrok/ledger/store.py`, `tests/ledger/test_store.py` |
| WR-05 | Warning | fixed | 5c0afd0 | `src/pumpgrok/ledger/store.py`, `tests/ledger/test_store.py` |
| WR-06 | Warning | fixed | 0b51828 | `src/pumpgrok/core/tool.py`, `src/pumpgrok/core/registry.py`, `tests/core/test_registry.py` |
| WR-07 | Warning | fixed | 3e90d15 | `src/pumpgrok/core/ids.py`, `tests/core/test_ids.py` |
| WR-08 | Warning | fixed | 3df5aae | `src/pumpgrok/core/approvals.py`, `tests/core/test_models.py` |
| WR-09 | Warning | fixed | a7a76eb | `src/pumpgrok/config/settings.py`, `tests/config/test_settings.py` |

Skipped: none. Failed: none.

## Decisions taken where the review offered options or the suggested snippet needed adjustment

- **WR-01:** The shared class is the bot definition, which is the superset (it has `paper_equity_sol` and the INV-C-06 validator). `paper_equity_sol` is therefore now an accepted `[risk]` overlay and `PUMPGROK_RISK__PAPER_EQUITY_SOL` key.
- **WR-05:** Implemented the review snippet. The stored payload is the validated model dump, so defaults are materialised. `JournalNote` requires `source` in its payload, so the test fixture was corrected.
- **WR-06:** Took the review's second option. The registry does not apply retry, rate limiting or alerts, so `ToolSpec` refuses `retry.attempts > 1` and the docstrings no longer claim them. Nothing implemented retry or alerts.
- **WR-07:** The review snippet resets the span counter on every bind. That would restart nested child spans at `.1` under the same root and collide with siblings. The counter now resets only when the bound root changes.
- **WR-08:** `token_units` is required for `human_sell` and `exit_rule` (all sell kinds bind quantity). `matches()` requires the kind-to-side mapping to match the order side.
- **WR-09:** The refusal lives in `load_settings()` after construction, because `collect_startup_problems` receives no kwargs. Tests that asserted live loads now assert the refusal. Precedence is checked on `Settings` directly.

## Open follow-up (not a finding)

- `ApprovalRecorded` in `ledger/events.py` has no `token_units` field. Approvals persisted to the ledger therefore cannot carry the sell quantity that WR-08 now binds in memory. No production code constructs `ApprovalRecord` yet, so nothing is affected today, but the ledger model should gain the field before a human-approval path is wired.

## Iterations (--auto)

- Iteration 1: fix pass (all 10 in-scope findings, commits above).
- Iteration 2: inline re-review (`01-REVIEW.md` overwritten; iteration-1 copy kept as `01-REVIEW.iter2.md`). Result: Critical 0, Warning 0, Info 14 open. The Info items are out of the fix scope.
- The loop stopped after iteration 2. No in-scope findings remain, so another fix pass would have nothing to apply. The workflow's `clean` convergence test is not met only because Info items remain.

## Files changed by the fix commits

`.env.example`, `src/pumpgrok/config/settings.py`, `src/pumpgrok/core/__init__.py`, `src/pumpgrok/core/approvals.py`, `src/pumpgrok/core/atomic_write.py`, `src/pumpgrok/core/bot.py`, `src/pumpgrok/core/ids.py`, `src/pumpgrok/core/registry.py`, `src/pumpgrok/core/risk_budget.py` (new), `src/pumpgrok/core/tool.py`, `src/pumpgrok/ledger/store.py`, `tests/config/test_secret_refusal.py`, `tests/config/test_settings.py`, `tests/core/test_ids.py`, `tests/core/test_models.py`, `tests/core/test_registry.py`, `tests/ledger/test_store.py`.

Not committed by the fixer: `01-REVIEW.md` (iteration 2 re-review result), `01-REVIEW.iter2.md` (iteration-1 backup), `01-REVIEW-FIX.md`. The orchestrator commits the docs artifacts.
