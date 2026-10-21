---
phase: 04-paper-trading-and-autonomy
plan: 05
subsystem: risk
tags: [risk-engine, kill-switch, breakers, halts, paper-trading, ledger]
requires:
  - phase: 04-01
    provides: ledger store and event folding the risk engine drives
  - phase: 04-02
    provides: replay clock and fixtures the risk tests run on
provides:
  - 19-step RiskEngine.check with bound RiskDecision rows
  - Latching daily-loss/drawdown halts with human-only clear path
  - Three domain breakers with half-open probe, persistence, rebuild
  - Kill-switch state machine with flatten plan and tool backends
affects: [04-06, 04-07]
actuals:
  tokens: 34183
  tasks: 2
  commits: 3
tech-stack:
  added: []
  patterns: [first-failure-wins step walk, half-open single-probe gate, ledger-persisted breaker transitions, human-only clear with seat-signature refusal]
key-files:
  created: [src/pumpgrok/risk/breakers.py, src/pumpgrok/risk/killswitch.py, tests/risk/test_breakers.py, tests/risk/test_killswitch.py]
  modified: [src/pumpgrok/risk/engine.py, src/pumpgrok/risk/__init__.py, src/pumpgrok/tools/risk/kill_switch.py, src/pumpgrok/tools/risk/halt_status.py, tests/characterization/test_vendor_ops.py]
key-decisions:
  - "KILL verdicts scope to the order mint: only buys of the killed mint refuse with breaker_open risk_kill:<mint>"
  - "A human halt clear suppresses same-day re-detection; a fresh day re-evaluates from the day-start baseline"
  - "Fresh breaker trips anchor at the live clock so the open state is never skipped by a stale event time"
  - "Alert is a live kill-switch source in poll(); precedence test corrected to active/alert_command"
requirements-completed: [RISK-001, RISK-002, RISK-003, RISK-004, RISK-005]
coverage:
  - id: D1
    description: "19-step RiskEngine.check to bound RiskDecision"
    requirement: "RISK-001"
    verification:
      - kind: unit
        ref: "tests/risk/test_engine.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Latching halts with human-only clear"
    requirement: "RISK-002"
    verification:
      - kind: unit
        ref: "tests/risk/test_killswitch.py::test_halt_latches_and_clears_only_via_human"
        status: pass
    human_judgment: false
  - id: D3
    description: "Breaker thresholds, cooldowns, probe, ledger rebuild"
    requirement: "RISK-003"
    verification:
      - kind: unit
        ref: "tests/risk/test_breakers.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Kill switch blocks buys, flatten closes every position, KILL blocks the mint"
    requirement: "RISK-004"
    verification:
      - kind: unit
        ref: "tests/risk/test_killswitch.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "Killswitch replay run exits 0 with zero OrderPlaced"
    requirement: "RISK-005"
    verification:
      - kind: integration
        ref: "PUMPGROK_KILLSWITCH=1 pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke-10m"
        status: pass
    human_judgment: false
duration: continuation run
completed: 2026-10-21
status: complete
---

# Phase 04 Plan 05: Risk Engine Summary

**19-step RiskEngine with latching halts, tripping breakers, one-cycle kill switch with flatten, and per-mint KILL blocks**

## Performance

- **Duration:** continuation run (resumed after Task 1 commit 33e4ed4)
- **Completed:** 2026-10-21T20:04:24Z
- **Tasks:** 2 (19-step check tracer; halts/breakers/killswitch) plus vendor-mirror rewire
- **Files modified:** 9

## Accomplishments

- RiskEngine.check runs the 19 R34 steps in order with first-failure-wins and binds RiskDecision to order_hash
- Daily-loss (0.05 of day-start) and drawdown (0.15 of peak) halts latch until a human halt_clear approval clears them
- DataStale/LossVelocity/ExecErrors breakers reject buys while open, admit one half-open probe, persist trips/resets, rebuild from ledger
- Kill switch (env/file/alert/ledger) blocks buys within one cycle; plan_flatten closes every position with kill_flatten sells
- RISK KILL verdict on a mint refuses later buys desk-wide for that mint; sells still pass
- Vendor CircuitBreaker characterization rewired to the Breaker port (Breaker(failures=..., cooldown_s=..., now=...)); test-local mirror removed

## Task Commits

1. **Task 1: Tracer one order through the 19-step check** - `33e4ed4` (feat, prior executor)
2. **Task 2: Halts, breakers, kill switch, KILL tokens** - `da5e319` (feat)

**Plan metadata:** docs commit follows (docs: complete plan)

## Verify runs (exit codes)

- `uv run pytest -q tests/risk/` exit 0, 48 passed
- `uv run pytest -q` exit 0, 1070 passed, 2 skipped
- `uv run ruff check .` exit 0, no issues
- `uv run ruff format --check .` exit 0, all formatted
- `uv run mypy src/` exit 0, no issues
- `PUMPGROK_KILLSWITCH=1 uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke-10m` exit 0, OrderPlaced count 0

## Files Created/Modified

- `src/pumpgrok/risk/engine.py` - 19-step check, halt/breaker/kill integration, KILL verdicts, flatten plan, halt clear
- `src/pumpgrok/risk/breakers.py` - Breaker port plus DataStale/LossVelocity/ExecErrors and BreakerSet persistence
- `src/pumpgrok/risk/killswitch.py` - KillSwitch poll/observe/clear, FlattenOrder, InflightBarrier
- `src/pumpgrok/risk/__init__.py` - risk package exports
- `src/pumpgrok/risk/limits.py` - EngineLimits (Task 1)
- `src/pumpgrok/tools/risk/kill_switch.py` - set/flatten_request tool backend (non-blocking file write)
- `src/pumpgrok/tools/risk/halt_status.py` - combined halt view
- `tests/risk/test_engine.py` - 19-step acceptance (Task 1)
- `tests/risk/test_breakers.py` - thresholds, cooldowns, probes, rebuild
- `tests/risk/test_killswitch.py` - halts, kill sources, KILL verdicts, flatten, barrier
- `tests/characterization/test_vendor_ops.py` - breaker tests run against the port

## Decisions Made

- KILL verdict refusal is per-mint (order.mint in killed set), not desk-wide for all mints
- Human halt clear suppresses same-day re-detection; next UTC day re-evaluates (rollover never clears the flag itself)
- Fresh DataStale trips anchor at the live clock; rebuild/sync keep event-time anchors to resume cooldowns
- KillSwitch.live_sources consults the start-env snapshot as well as current env so injected-env clears refuse correctly

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test tool invocations were sync with get_event_loop**
- **Found during:** Task 2 verification
- **Issue:** test_kill_switch_tool and test_halt_status_reports_breaker used asyncio.get_event_loop (plus a nested import time, PLC0415)
- **Fix:** async def tests with await; import time moved to top level
- **Files modified:** tests/risk/test_killswitch.py
- **Verification:** tests/risk/ green
- **Committed in:** da5e319

**2. [Rule 1 - Bug] Stray halt-clear block would clear the halt it asserts**
- **Found during:** Task 2 verification
- **Issue:** first pytest.raises(ValueError) block passed a valid human approval, which would have cleared the halt
- **Fix:** deleted the stray block, kept the seat-forgery block
- **Files modified:** tests/risk/test_killswitch.py
- **Verification:** tests/risk/ green
- **Committed in:** da5e319

**3. [Rule 1 - Bug] rug_alert sell used the sniper seat**
- **Found during:** Task 2 verification
- **Issue:** sells only pass from bot-06-exit; seat_may_trade is not skipped for exit sells
- **Fix:** seat="bot-06-exit" for the rug_alert sell
- **Files modified:** tests/risk/test_killswitch.py
- **Verification:** tests/risk/ green
- **Committed in:** da5e319

**4. [Rule 1 - Bug] Second observe() asserted not-None**
- **Found during:** Task 2 verification
- **Issue:** observe() returns None once a KillSwitchSet exists; the repeat call returns None
- **Fix:** assert None on the second observe
- **Files modified:** tests/risk/test_killswitch.py
- **Verification:** tests/risk/ green
- **Committed in:** da5e319

**5. [Rule 1 - Bug] Missing breaker threshold constants**
- **Found during:** Task 2 verification (collection NameError)
- **Issue:** DataStale/LossVelocity/ExecErrors defaults referenced undefined constants
- **Fix:** defined the 13 REVIEW defaults (120s/3-miss/60s/3-ok/30s; 2pct/15min/30min/5min/0.5pct; 3-reject/10min/15min)
- **Files modified:** src/pumpgrok/risk/breakers.py
- **Verification:** tests/risk/ green
- **Committed in:** da5e319

**6. [Rule 1 - Bug] Missing imports and dataclass field defects in new code**
- **Found during:** Task 2 verification (collection errors)
- **Issue:** engine.py lacked re and pathlib imports and had a default-before-nondefault _StepCtx field plus a dropped evaluated field; killswitch.py lacked kill_file_text
- **Fix:** added imports, reordered half_blocked after non-default fields, restored evaluated, added kill_file_text
- **Files modified:** src/pumpgrok/risk/engine.py, src/pumpgrok/risk/killswitch.py
- **Verification:** tests/risk/ green
- **Committed in:** da5e319

**7. [Rule 1 - Bug] BreakerSet.refresh never persisted exec_errors trips**
- **Found during:** Task 2 verification (rebuild test empty)
- **Issue:** per-breaker before-state was captured after feeding observations, so fresh trips compared open-to-open and no BreakerTripped row was appended
- **Fix:** capture all before-states before feeding observations, then evaluate and transition
- **Files modified:** src/pumpgrok/risk/breakers.py
- **Verification:** test_breaker_set_rebuild_survives_restart passes
- **Committed in:** da5e319

**8. [Rule 2 - Missing Critical] KILL verdict refused every mint**
- **Found during:** Task 2 verification
- **Issue:** _step_breaker_open refused when any killed mint existed, even for unrelated mints; detail did not name the mint
- **Fix:** refuse only when order.mint is killed, detail risk_kill:<mint>
- **Files modified:** src/pumpgrok/risk/engine.py
- **Verification:** test_kill_verdict_blocks_mint_for_all_seats passes
- **Committed in:** da5e319

**9. [Rule 2 - Missing Critical] Cleared halt re-tripped on the same condition**
- **Found during:** Task 2 verification
- **Issue:** _detect_breach re-fired right after a human clear, making the clear a no-op (day-start never re-baselines without rollover)
- **Fix:** _cleared_today suppresses same-day re-detection after a HaltCleared row
- **Files modified:** src/pumpgrok/risk/engine.py
- **Verification:** test_halt_latches_and_clears_only_via_human passes
- **Committed in:** da5e319

**10. [Rule 1 - Bug] DataStale trips anchored at stale event time skipped open**
- **Found during:** Task 2 verification
- **Issue:** note_miss/evaluate anchored trip() at the passed event ts while is_open measures against the live clock, so trips landed straight in half-open
- **Fix:** fresh trips anchor at the live clock; rebuild/sync keep event-time anchors
- **Files modified:** src/pumpgrok/risk/breakers.py
- **Verification:** DataStale trip/cooldown/probe tests pass
- **Committed in:** da5e319

**11. [Rule 1 - Bug] live_sources ignored the start-env snapshot**
- **Found during:** Task 2 verification (clear DID NOT RAISE)
- **Issue:** request_clear consults live_sources (current os.environ) while poll uses the construction snapshot, so injected-env clears succeeded while live
- **Fix:** live_sources also reports the start snapshot
- **Files modified:** src/pumpgrok/risk/killswitch.py
- **Verification:** test_clear_refused_while_live_then_accepted passes
- **Committed in:** da5e319

**12. [Rule 1 - Bug] Precedence test contradicted documented alert polling**
- **Found during:** Task 2 verification
- **Issue:** design 5.2 step 2 re-polls file and alert sources, but the test asserted poll inactive with a KILL alert line present
- **Fix:** assert active True with source alert_command (alert < file < env chain intact)
- **Files modified:** tests/risk/test_killswitch.py
- **Verification:** tests/risk/ green
- **Committed in:** da5e319

**13. [Rule 1 - Bug] Lint, type, and static-guard fallout in new code**
- **Found during:** closing gates
- **Issue:** PLR0917 (6 positional params), F821 (missing pathlib), PLR0911 (poll returns), ASYNC240 (blocking write_text), mypy dict-unpack and Side str/enum, static guard datetime.now in InflightBarrier
- **Fix:** keyword-only markers, pathlib import, _file_state helper, asyncio.to_thread write, dict[str, Any] annotations, Side.SELL, Condition.wait_for with no clock read, dropped unused datetime import
- **Files modified:** src/pumpgrok/risk/breakers.py, src/pumpgrok/risk/engine.py, src/pumpgrok/risk/killswitch.py, src/pumpgrok/tools/risk/kill_switch.py
- **Verification:** ruff check, ruff format --check, mypy, and safety suite green
- **Committed in:** da5e319

---

**Total deviations:** 13 auto-fixed (11 bugs, 2 missing-critical)
**Impact on plan:** All fixes required for correctness or green gates. No scope creep; TOOL-004 wiring, CLI verbs, and R62 stay in 04-06/04-07 as planned.

## Issues Encountered

- Harness display intermittently reports "No tests collected" on quiet runs with exit 0; verbose runs show the true counts (48 risk, 1070 full). Counts above come from verbose runs.
- Prior-executor notes preserved: manual sells fail closed (only exit-reason sells skip steps 2-4 and 9-19); mint-KILL maps to breaker_open detail risk_kill:<mint>; the step-14 reject branch is shadowed by already_open and covered by a zero-unit basis row; DataStale reset needs 3 consecutive fresh ticks; probe admission happens post-pass so failed orders never consume the probe.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Risk decisions, halts, breakers, and kill-switch backends ready for 04-07 CLI wiring (halt --clear, killswitch verbs, TOOL-004 atomic consume-and-order)
- R62 degraded-reputation refusal belongs to 04-06
- No blockers

## Self-Check: PASSED

- SUMMARY file exists at .planning/phases/04-paper-trading-and-autonomy/04-05-SUMMARY.md
- Task 2 commit da5e319 verified via git rev-parse
- Task 1 commit 33e4ed4 present in history
- All gate exit codes recorded above from exercised runs

---
*Phase: 04-paper-trading-and-autonomy*
*Completed: 2026-10-21*
