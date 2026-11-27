# 06-02 SUMMARY — Typed fail-closed errors + integer daily loss (INT-02, INT-03)

## Status

- Task 1 (typed fail-closed errors at the three silent fallbacks): **complete**, committed as `8b117db`.
- Task 2 (integer daily-loss halt, non-positive start equity fails): **complete**, committed as `94d63d5`.
- Working tree clean after both commits. No test runner, linter, or typechecker
  was executed in this worktree (per work order; the orchestrator runs all gates
  after merging).

## What was built

**INT-02 — new typed error `CorruptState` (`src/pumpgrok/core/errors.py`, code
`corrupt_state`, re-exported from `pumpgrok.core`).** Raised at all three sites:

1. `src/pumpgrok/ledger/reducer.py` (`_on_mtm`): an undecodable `spot` raises
   `CorruptState` instead of keeping the old peak. Catches
   `(ArithmeticError, ValueError, TypeError)` — `Decimal` failure modes only —
   so no broad except remains on the peak read.
2. `src/pumpgrok/supervisor/seat_task.py` (`_initial_equity`): missing meta,
   unreadable meta (`sqlite3.Error`), or non-integer meta raises instead of
   returning 0. The read is outside the exit-halt append `try`, so the failure
   propagates (seat crash path reports it via the restart/exhaustion
   escalation).
3. `src/pumpgrok/supervisor/lifecycle.py` (shutdown genesis): new
   `_shutdown_initial_equity()` helper replaces both `or 0` fallbacks (the
   with-events branch and the empty-ledger branch). A `except CorruptState:
   raise` clause precedes the existing snapshot `except Exception`, so only the
   typed error escapes; unreadable-ledger and export/health write behavior is
   unchanged, and `serve`'s `_finish_serve` still catches it for orderly close.

**INT-03 — `src/pumpgrok/risk/engine.py` (`_detect_breach`):** day-start equity
of zero or less raises `CorruptState` (failed check, never zero loss) before
either halt is evaluated; the daily-loss comparison is integer
cross-multiplication (`loss_lamports * limit.denominator >= day_start *
limit.numerator` with `Fraction(str(fraction))`, exact for the `Decimal`
budget). The drawdown formula is byte-identical.

**Tests (new, deterministic, no network):**

- `tests/integrity/test_fail_closed_state.py` — corrupt spot raises (valid spot
  still moves the peak); missing/corrupt seat meta raises (valid meta returns
  the value); missing genesis meta raises at shutdown with events and with an
  empty ledger; recorded meta still shuts down cleanly with exit 0.
- `tests/integrity/test_daily_loss_integer.py` — exactly 5 % trips;
  one lamport below passes with reason `pass` and no `HaltSet`; zero start
  equity raises via `check()`; negative start equity raises via
  `_detect_breach` (see deviation 5).

## Deviations from the plan

1. **Added files outside `files_modified`:** `src/pumpgrok/core/errors.py` and
   `src/pumpgrok/core/__init__.py` (one new error + re-export). The plan's
   `<action>` explicitly authorizes adding a new typed error when none fits.
   None fits: `LedgerUnavailable` means unreachable, `DataStale` means stale,
   `LedgerInconsistent` means hash-chain mismatch; a missing/corrupt
   equity/peak/genesis value is none of those.
2. **Five existing supervisor test helpers updated (one line each):**
   `test_lifecycle.py`, `test_restarts.py`, `test_latch_rebuild.py`,
   `test_review_seat_task.py`, `test_supervisor_bounded_restart.py` now record
   `initial_equity_lamports` meta. Required cutover: the new contract makes the
   meta mandatory, and every production composition path that reaches these
   code paths records it (`build_serve_replay` always sets it). Without this,
   shutdown/exit-halt tests fail on the new raise.
3. **Kept `_append_exit_halt`'s write-failure swallow.** D-03 forbids swallowing
   *reads*; that `except Exception` guards the ledger *write* and has an
   explicit retry design covered by dedicated tests
   (`test_exit_halt_retried_after_its_write_fails`, `..._escalation_write_fails`).
   Removing it would break the retry contract. The equity *read* it depends on
   now raises.
4. **Two docstring lines in `engine.py` reworded** (`daily-loss/drawdown` →
   `daily-loss and drawdown`; `(...)/(...)` → `(... or ...)`). The plan's
   `grep -nE "daily.*loss.*/|loss.*daily.*/"` proxy matches prose slashes too,
   including one pre-existing docstring line, so the literal acceptance command
   could never pass without this. No behavior change.
5. **Negative start equity is covered via `_detect_breach` directly**, not via
   `check()`: with negative equity the order size-cap steps (13/14) reject the
   order before step 15 runs, so `check()` cannot reach the daily-loss step.
   Zero start equity *is* covered end-to-end via `check()` (caps go to 0/0 and
   pass through to the raise).
6. **Committed on the assigned branch `bot-00-chief/p6-02`** although the
   generic worktree protocol wants an `agent-*` namespace. The work order names
   this branch explicitly and forbids creating branches; assignment wins.
7. **Stray-edit incident, corrected:** my first edits resolved relative paths
   against the main checkout (`/root/src/repos/pumpgrok`) instead of the
   worktree. I saved the diff, reverted the main repo to clean (verified with
   `git status`), and applied the identical patch inside the worktree
   (`git apply --check` clean). Main repo is untouched; no other branches,
   worktrees, tags, or pushes were created.

## Out-of-scope observations (not blockers)

- `RiskEngine._fold`, `Scheduler._day_start_equity`, `tools/_common.py`, and
  `ledger/reconcile.py` keep their documented fallbacks (budget default / 0)
  and were intentionally not touched — different call sites, other plans'
  scope. None of them feed `_detect_breach` with a silent zero in a way this
  plan covers.
- Only the replay composition root writes `initial_equity_lamports` today
  (`scheduler.py:820`); the paper path relies on the untouched `_fold`
  fallback. If paper serve must survive the new strict shutdown/exit-halt, a
  follow-up should record the meta at paper composition.

## Acceptance commands for the orchestrator

```bash
uv run pytest -q tests/integrity/test_fail_closed_state.py
uv run pytest -q tests/integrity/test_daily_loss_integer.py
test "$(git diff -U0 base...HEAD -- src/pumpgrok/ledger/reducer.py src/pumpgrok/supervisor/seat_task.py src/pumpgrok/supervisor/lifecycle.py | grep -cE '^\+.*except Exception')" -eq 0
! grep -nE "daily.*loss.*/|loss.*daily.*/" src/pumpgrok/risk/engine.py
```

(The `git diff` verify was exercised pre-commit against the working tree and
passes; run it against the merge range after merging. Both grep verifies pass
on the final tree. Then the phase gates: `make lint`, `make typecheck`,
`make test`.)

## Commits

- `8b117db` — `fix(integrity): fail closed with typed errors at silent fallbacks (INT-02)`
- `94d63d5` — `fix(integrity): integer daily-loss halt, non-positive start equity fails (INT-03)`
