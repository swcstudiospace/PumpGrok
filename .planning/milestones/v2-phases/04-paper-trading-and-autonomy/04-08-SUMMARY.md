---
phase: 04-paper-trading-and-autonomy
plan: 08
subsystem: supervisor
tags: [paper-trading, supervisor, ten-seat-loop, heartbeats, bounded-restarts, graceful-shutdown, degraded-modes, observe-only]
requires:
  - phase: 04-01
    provides: LedgerStore append/batch plus snapshot and export primitives the shutdown path uses
  - phase: 04-02
    provides: FixtureClock timeout and sleep primitives every supervisor wait uses
  - phase: 04-04
    provides: PaperAdapter simulate path and RiskEngine check the replay cycle exercises
  - phase: 04-07
    provides: state resume and autonomy CLI verbs this plan's latch and level semantics drive
provides:
  - Ten-seat roster-order scheduler with per-seat cadences and cycle timeouts
  - Heartbeat wrapper with bounded restarts, backoff gating, and observe-only latches
  - Health/readiness server plus atomic health.json writer
  - Signal handling, virtual-time drain, and orderly shutdown returning 0
  - AUTO-005 degraded-mode matrix and AUTO-006 offline ten-seat replay cycle
affects: [04-09]
actuals:
  tokens: 62000
  tasks: 3
  commits: 1
tech-stack:
  added: []
  patterns: [backoff-gates-rescheduling-not-sleep, replay-hermetic-to-host-kill-state, read-only-replay-seat-cycles]
key-files:
  created:
    - src/pumpgrok/supervisor/__init__.py
    - src/pumpgrok/supervisor/scheduler.py
    - src/pumpgrok/supervisor/seat_task.py
    - src/pumpgrok/supervisor/health.py
    - src/pumpgrok/supervisor/lifecycle.py
    - tests/supervisor/test_scheduler.py
    - tests/supervisor/test_restarts.py
    - tests/supervisor/test_lifecycle.py
    - tests/supervisor/test_degraded.py
  modified:
    - src/pumpgrok/cli.py
    - src/pumpgrok/risk/engine.py
    - tests/test_skip_cycle.py
key-decisions:
  - "Backoff gates not_before rescheduling instead of sleeping: a virtual clock only advances when the loop advances it, so sleeping inside the cycle path would stall replay ticks"
  - "Replay RiskEngine is hermetic to host kill state (env={}): env/file/alert kill inputs would leak non-deterministic rows into the checkpoint ledger; ledger KillSwitchSet rows are still honored"
  - "Replay seat cycles are strictly read-only: the smoke checkpoint keeps exactly one JournalNote row; the sniper cycle exercises risk.check (refusal path) and never places"
  - "doctor now reports supervisor present: the absence pin was plan-stale, updated to ok while gateway/reports stay absent"
requirements-completed: [RISK-006, AUTO-001, AUTO-002, AUTO-003, AUTO-004, AUTO-005, AUTO-006]
coverage:
  - id: D1
    description: "One seat schedules in roster order, heartbeats, times out honestly, health degrades and recovers"
    requirement: "AUTO-001"
    verification:
      - kind: unit
        ref: "tests/supervisor/test_scheduler.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Bounded restarts, latches, resume, shutdown, readyz, observe-only matrix"
    requirement: "AUTO-002"
    verification:
      - kind: unit
        ref: "tests/supervisor/test_restarts.py, tests/supervisor/test_lifecycle.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every 6.7 degraded row behaves with recovery; ten-seat smoke cycle exits 0 offline"
    requirement: "AUTO-005"
    verification:
      - kind: unit
        ref: "tests/supervisor/test_degraded.py"
        status: pass
      - kind: cli
        ref: "pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke"
        status: pass
    human_judgment: false
duration: 2026-10-21 single session
completed: 2026-10-21
status: complete
---

# Phase 04 Plan 08: Supervised Ten-Seat Loop Summary

**Roster-order asyncio scheduler with heartbeats, bounded restarts with observe-only latches, graceful shutdown, /healthz + /readyz + atomic health.json, the full AUTO-005 degraded-mode matrix, and an offline ten-seat replay cycle. Suite, lint, format, and types green.**

## Performance

- **Completed:** 2026-10-21
- **Tasks:** 3 of 3 (tracer, restarts/latches/shutdown, degraded + ten-seat cycle)
- **Files:** 9 created, 3 modified
- **Commits:** 1 implementation commit `40cbb93` (interleaved source forced one atomic commit; see Deviations)

## Accomplishments

- Task 1 tracer: scheduler starts due seats in roster order within a 1 s tick, the SeatTask wrapper records heartbeats and counts `clock.timeout(max(30 s, 4 x cadence))` as a crash; stale seats degrade health (`/healthz` 503) and recover to 200; health.json rewrites atomically every 10 virtual seconds.
- Task 2 restarts/lifecycle: token-bucket 5 restarts/hour with `min(16, 2**n)` + seeded jitter gating `not_before`; exhaustion latches observe-only with one edge-triggered `bot_restart_exhausted` Escalation while other seats tick; sniper latch stops buys desk-wide, risk latch rejects buys while exit sells continue at `seat_may_trade`, exit latch appends `HaltSet(reason=manual)`; resume clears via the `state resume` ledger note; every Escalation relays to notify.alert. SIGTERM/SIGINT stops scheduling, drains within 30 s, writes a reducer snapshot, flushes the JSONL export, writes `health.json status=stopped`, exits 0; second signal never forces. `/readyz` 200 only after CONSISTENT reconcile plus one cycle per seat. RiskEngine gained an additive `set_observe_only` mirror.
- Task 3 degraded/cycle: each 6.7 row holds with recovery (LLM rule-fallback vs observe-only-buys via `require_llm`, replay missing-record failure, RPC failover/BLIND, WS DataStale at 120 s, 1000-event ledger buffer with ordered drain, skew refusal with `clock_skew`). `run --mode paper --once --replay` runs `run_replay` (verdict row/stdout/cycle_end byte-identical) then all ten seats through engine fold, risk check, and simulate-only paths with zero extra rows, exiting 0 offline.

## Task Commits

1. **Tasks 1-3: supervised loop, restarts, degraded, ten-seat cycle** - `40cbb93` (feat)

## Verify runs (exit codes)

- `.venv/bin/python -m pytest -p no:cacheprovider -q` exit 0 (1172 passed, 2 skipped)
- `.venv/bin/pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exit 0 (`engine decision=skip reason=data_unavailable`)
- `.venv/bin/ruff check .` exit 0 (all checks passed)
- `.venv/bin/ruff format --check .` exit 0 (451 files already formatted)
- `.venv/bin/mypy src/` exit 0 (no issues found in 149 source files)

Note: the bare `pytest`/`uv run pytest` shim in this environment collects nothing ("Pytest: No tests collected"); the venv interpreter runs the same suite green. Plan commands map to the `.venv/bin/` equivalents above.

## Files Created/Modified

- `src/pumpgrok/supervisor/scheduler.py` - roster scheduler, Supervisor, DegradedState, replay cycles, run_once_replay
- `src/pumpgrok/supervisor/seat_task.py` - heartbeats, RestartPolicy, ObserveOnly RISK-006 matrix, escalation relay
- `src/pumpgrok/supervisor/health.py` - status builder, atomic writer, /healthz + /readyz server
- `src/pumpgrok/supervisor/lifecycle.py` - signals, virtual-time drain, cancel_and_wait, shutdown
- `src/pumpgrok/supervisor/__init__.py` - package exports
- `src/pumpgrok/cli.py` - `_skip_cycle` drives the ten-seat cycle (verdict line unchanged)
- `src/pumpgrok/risk/engine.py` - additive `set_observe_only` latch mirror
- `tests/supervisor/test_scheduler.py` - 7 tracer tests
- `tests/supervisor/test_restarts.py` - 8 restart/latch/relay tests
- `tests/supervisor/test_lifecycle.py` - 7 shutdown/signal/readyz/health tests
- `tests/supervisor/test_degraded.py` - 8 degraded-mode + ten-seat cycle tests
- `tests/test_skip_cycle.py` - doctor pins supervisor present (absence pin was plan-stale)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Replay risk cycle leaked host killswitch rows into the checkpoint ledger**
- **Found during:** Task 3 (full-suite regression: killswitch-env CLI test grew a second row)
- **Issue:** The replay risk seat called `evaluate_halts`, whose kill poll observes live-host env/file/alert state and appends `KillSwitchSet`, breaking replay hermeticity and the 1-row checkpoint pin.
- **Fix:** The replay RiskEngine is constructed with `env={}` (file/alert already unset in that path); ledger KillSwitchSet rows are still honored through the store.
- **Files modified:** `src/pumpgrok/supervisor/scheduler.py`
- **Commit:** `40cbb93`

**2. [Rule 2 - Correctness] Backoff slept inside the cycle path, stalling virtual time**
- **Found during:** Task 1 (hang analysis before first test run)
- **Issue:** `await clock.sleep(backoff)` inside `_on_crash` blocks the supervisor loop on virtual time that only advances when the loop advances it; a crash during `run_once` would hang forever.
- **Fix:** Backoff gates `SeatTask.not_before` rescheduling (`is_due` checks it); no sleep in the crash path.
- **Files modified:** `src/pumpgrok/supervisor/seat_task.py`
- **Commit:** `40cbb93`

**3. [Rule 1 - Bug] shutdown drain waited on the calling task itself**
- **Found during:** Task 2 (hang analysis)
- **Issue:** `running_tasks()` included the current task, so `drain` deadlocked awaiting itself.
- **Fix:** Exclude `asyncio.current_task()` from the drain set.
- **Files modified:** `src/pumpgrok/supervisor/scheduler.py`
- **Commit:** `40cbb93`

**4. [Rule 2 - Contract] doctor absence pin for supervisor went plan-stale**
- **Found during:** Task 3 (full-suite regression)
- **Issue:** `test_doctor_reports_absent_subsystems_as_warnings` pinned `supervisor` absent; this plan delivers it.
- **Fix:** Test now asserts `ok supervisor (pumpgrok.supervisor)`; gateway/reports stay absent. Not a weakening: the pin tracked absence, the plan is presence.
- **Files modified:** `tests/test_skip_cycle.py`
- **Commit:** `40cbb93`

Single atomic implementation commit (instead of per-task commits): the four source modules were rewritten as a unit across all three tasks (lint-driven top-level import restructure), so per-task file boundaries no longer existed; the commit message records all three tasks.

## Known Stubs

None.

## Threat Flags

None - no new network endpoints, auth paths, file access, or schema changes beyond the plan. Health payload carries status, ledger seq, and seat freshness only (T-04-18). No new packages (T-04-SC).

## Self-Check: PASSED

- All 9 created files exist; `40cbb93` present in `git log`.
- `run_once_replay` smoke exits 0 with the exact verdict line; replay ledger keeps exactly 1 row.
- Full suite 1172 passed, 2 skipped; ruff, format, mypy green.
