---
phase: 04-paper-trading-and-autonomy
plan: 06
subsystem: risk
tags: [reputation, risk-engine, fail-closed, ledger-rebuild, paper-trading]
requires:
  - phase: 04-01
    provides: ledger store and PositionOpened/PositionClosed rows the rebuild scans
  - phase: 04-05
    provides: 19-step RiskEngine.check the degraded-book reason plugs into
provides:
  - Degraded reputation book that refuses buys with reputation_degraded plus Escalation
  - Ledger rebuild restoring per-creator losses from PositionOpened/PositionClosed rows
  - Safety tests corrupting the reputation file and asserting fail-closed behavior
affects: [04-07, 04-08]
actuals:
  tokens: 5038
  tasks: 1
  commits: 2
tech-stack:
  added: []
  patterns: [breaker-scope refusal reason without a 20th step, day-scoped idempotent Escalation, ledger-derived reputation rebuild]
key-files:
  created: [tests/safety/test_reputation_degraded.py]
  modified: [src/pumpgrok/engine/reputation.py, src/pumpgrok/risk/engine.py]
key-decisions:
  - "reputation_degraded surfaces as a breaker-scope reason that fails the breaker_open evaluated row, keeping the 19 R34 step ids unchanged"
  - "Degraded refusal is buy-only: exit sells skip the step, manual sells are not new entries, so exits and kill-flatten still run"
  - "One Escalation per UTC day per ledger while degraded; repeat refusals dedupe via the idempotency key"
  - "Rebuild joins PositionClosed to PositionOpened by mint for the creator and converts ledger fraction pnl to book percent; orphan closes are skipped and an empty rebuild stays degraded"
requirements-completed: [RISK-003]
coverage:
  - id: D1
    description: "Degraded reputation book refuses buys with reputation_degraded plus Escalation while exits execute"
    requirement: "RISK-003"
    verification:
      - kind: unit
        ref: "tests/safety/test_reputation_degraded.py::test_corrupt_file_degraded_book_refuses_buy_with_escalation"
        status: pass
      - kind: unit
        ref: "tests/safety/test_reputation_degraded.py::test_exit_and_kill_flatten_execute_on_degraded_book"
        status: pass
    human_judgment: false
  - id: D2
    description: "Reputation book rebuilds per-creator losses from ledger PositionOpened and PositionClosed rows"
    requirement: "RISK-003"
    verification:
      - kind: unit
        ref: "tests/safety/test_reputation_degraded.py::test_rebuild_restores_book_from_ledger"
        status: pass
      - kind: unit
        ref: "tests/safety/test_reputation_degraded.py::test_unrestorable_book_stays_degraded_and_refuses"
        status: pass
    human_judgment: false
duration: continuation run
completed: 2026-10-21
status: complete
---

# Phase 04 Plan 06: Degraded Reputation Fail-Closed Summary

**Corrupt reputation book quarantines to degraded, RiskEngine refuses buys with reputation_degraded plus Escalation while exits run, and the book rebuilds from ledger fills**

## Performance

- **Duration:** continuation run
- **Completed:** 2026-10-21T22:30:00Z
- **Tasks:** 1 (tracer: degraded fail-closed plus ledger rebuild)
- **Files modified:** 3

## Accomplishments

- Corrupt reputation file quarantines to a degraded empty book; buys refuse with reason reputation_degraded and one Escalation per UTC day
- Exit-rule sells and kill_flatten sells execute on the same degraded book; read-only views (summary, verdict) still run
- Rebuild scans ledger PositionOpened rows for the creator and PositionClosed rows for realized_pnl_lamports plus fractional pnl_pct, reconstructing per-creator losses; unrestorable books stay degraded and keep refusing

## Task Commits

Each task was committed atomically:

1. **Task 1: R62 degraded reputation fail-closed plus ledger rebuild** - `2a49b8d` (feat)

**Plan metadata:** follows (docs: complete plan)

## Verify runs (exit codes)

- `uv run pytest tests/safety/test_reputation_degraded.py -v` exit 0, 5 passed (quiet `-q` run prints the known harness "No tests collected" line; verbose shows the true count)
- `uv run pytest tests/safety/test_reputation_degraded.py tests/risk/ -v` exit 0, 53 passed
- `uv run pytest -p no:cacheprovider -v` exit 0, 1104 passed, 2 skipped
- `uv run ruff check .` exit 0, no issues
- `uv run ruff format --check .` exit 0, all formatted
- `uv run mypy src/` exit 0, no issues

## Files Created/Modified

- `src/pumpgrok/engine/reputation.py` - added `ReputationBook.rebuild_from_ledger` plus `_mint_creators`, `_replay_event`, `_replay_close` helpers and `LAMPORTS_PER_SOL`
- `src/pumpgrok/risk/engine.py` - optional `reputation` constructor param with property plus `set_reputation`, degraded-buy refusal in `_step_breaker_open`, day-scoped `_write_reputation_escalation`, `reputation_degraded` mapped onto the `breaker_open` evaluated row
- `tests/safety/test_reputation_degraded.py` - five tests: buy refusal with Escalation and dedupe, exit plus kill_flatten pass, read-only views run, rebuild restores rug history and re-enables buys, orphan-only ledger stays degraded

## Decisions Made

- reputation_degraded is a breaker-scope reason, not a 20th R34 step: the 19 STEP_IDS are untouched and the `breaker_open` evaluated row reads `fail` (D-k disposition from 04-RESEARCH)
- The refusal fires only for buys; exit sells skip `breaker_open` and manual sells are not new entries, so reducing risk is never blocked
- The Escalation uses a day-scoped idempotency key (`reputation-degraded|<utc-day>`) with integrity suppression, so one degraded day writes one row no matter how many buys refuse
- Rebuild converts ledger lamports to SOL and fractional pnl to percent; closes whose mint never opened are skipped; `rug_loss_pct` defaults to the 60.0 desk setting
- `set_reputation` exists so a rebuilt book takes effect on a live engine without constructing a new one

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Constructor body deleted by a misranged patch**
- **Found during:** Task 1 verification (collection AttributeError on `_decisions`)
- **Issue:** A patch with a wrong line range replaced the `__init__` tail, dropping the killswitch, breaker set, reserve hook, and decision-cache assignments
- **Fix:** Restored the deleted assignments verbatim after `self._reputation`
- **Files modified:** src/pumpgrok/risk/engine.py
- **Verification:** `git diff` shows no unintended deletions; safety plus risk suites green
- **Committed in:** 2a49b8d (part of task commit)

**2. [Rule 1 - Bug] Import lines consumed by range replaces**
- **Found during:** Task 1 verification (`git diff` review)
- **Issue:** Two range patches each restated one line above the range and dropped the line below it, removing the `ledger.reducer` and `ledger.views` imports in turn
- **Fix:** Re-added both imports in isort order
- **Files modified:** src/pumpgrok/risk/engine.py
- **Verification:** `git diff` deletions limited to intended lines; full suite green
- **Committed in:** 2a49b8d (part of task commit)

**3. [Rule 1 - Bug] Rebuild helpers landed inside the class body**
- **Found during:** Task 1 verification (ruff PLR0912 plus misplaced module functions)
- **Issue:** The branch-count refactor inserted module-level helpers between `rebuild_from_ledger` and the class accounting section, and ruff flagged 13 branches in one method
- **Fix:** Moved `_mint_creators`, `_replay_event`, `_replay_close` to module level after the class, removing the duplicate section comment
- **Files modified:** src/pumpgrok/engine/reputation.py
- **Verification:** ruff check and format clean, mypy clean
- **Committed in:** 2a49b8d (part of task commit)

---

**Total deviations:** 3 auto-fixed (3 bugs)
**Impact on plan:** All fixes restore intended behavior or satisfy lint; no scope creep. No new packages; legitimacy gate not applicable.

## Issues Encountered

- Quiet `pytest -q` runs intermittently print "No tests collected" with exit 0 while verbose runs show the true counts (same harness behavior noted in the 04-05 summary); all counts above come from verbose runs
- The edit-tool range/body discipline needed care: overlapping ranges silently drop adjacent lines, so every patch was followed by a `git diff` deletion review

## Threat Flags

None - the reputation-to-risk path crosses the T-04-11 boundary exactly as the plan's threat register prescribes (corrupt book quarantines, buys refuse with Escalation, never silent-clean).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- R62 refusal and rebuild ready for 04-07 CLI wiring (restore/rebuild verbs can call `rebuild_from_ledger` plus `set_reputation`)
- No blockers

## Self-Check: PASSED

- SUMMARY file exists at .planning/phases/04-paper-trading-and-autonomy/04-06-SUMMARY.md
- Task commit 2a49b8d verified via git rev-parse
- All gate exit codes recorded above from exercised runs

---
*Phase: 04-paper-trading-and-autonomy*
*Completed: 2026-10-21*
