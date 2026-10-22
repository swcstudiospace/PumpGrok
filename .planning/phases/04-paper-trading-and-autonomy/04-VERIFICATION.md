---
phase: 04-paper-trading-and-autonomy
verified: 2026-10-22T00:30:17Z
status: gaps_found
score: 26/28 must-haves verified
gaps:
  - truth: PUMPGROK_KILLSWITCH=1 run over smoke-10m exits 0 with zero OrderPlaced rows
    status: failed
    reason: seat bot-04-sniper cycle crashes building OrderRequest with the 45-char fixture mint (max 44) before any risk or killswitch logic runs; scheduler raises RuntimeError, CLI exits 1
    artifacts:
      - path: tests/fixtures/replay/smoke-10m/generator.py
        issue: MINT_A and MINT_B are 45 chars; OrderRequest.mint caps at 44 (src/pumpgrok/core/adapter.py:36, predates phase)
      - path: tests/fixtures/replay/smoke-10m/events.jsonl
        issue: carries the same 45-char mints; manifest pins sha256 so a mint fix must regen the manifest and the canonical verify hash
      - path: src/pumpgrok/supervisor/scheduler.py
        issue: run_once_replay line 573 raises RuntimeError on the seat crash; no InvalidOrder containment at the seat boundary
    missing:
      - Shorten smoke-10m mints to valid 32-44 char base58 (or equivalent), regen manifest + canonical events.hash, re-run SC3 literally
---

# Phase 4: Paper Trading and Autonomy Verification Report

**Phase Goal:** The desk runs autonomously in paper mode on fixture data: curve-faithful fills, a risk engine with halts, breakers and kill switch, deterministic replay under virtual time, a supervised ten-seat loop with health and reports, live mode refused, and the vendor tree retired.
**Verified:** 2026-10-22T00:30:17Z
**Status:** gaps_found
**Re-verification:** No — initial verification (no prior 04-VERIFICATION.md existed)

## Goal Achievement

One of five roadmap success criteria fails on its literal command (SC3 exits 1, not 0). Root cause is a single fixture defect, not a missing subsystem: both smoke-10m mints are 45 characters while OrderRequest.mint allows max 44 (src/pumpgrok/core/adapter.py:36, introduced pre-phase in 0de6062; fixture authored in-phase in d8d879c). The sniper seat builds the order before any risk/killswitch logic, so the crash precedes the behavior SC3 intends to test. All other criteria pass as written, the full suite (1186 tests) exits 0, and no product files were modified by this verification.

### Observable Truths (roadmap success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | 164+ characterization tests collected; full suite exits 0 | VERIFIED | `uv run pytest --collect-only -q tests/characterization` exit 0, 244 tests (19 files); `uv run pytest -q` exit 0 (1186 collected suite-wide) |
| SC2 | Two seeded verify runs over smoke-10m give identical events.hash | VERIFIED | Two runs exit 0; both print `events.hash=d6ce3e73dee25a74485666cfffcbb94e69f24e5ee1cd2ef10e0fb9a7a5ba0a0` and `verify=CONSISTENT seq=1 events=41` |
| SC3 | Killswitch replay run exits 0; OrderPlaced count is 0 | FAILED | Run exits **1** (`RuntimeError: seat bot-04-sniper cycle crashed`: OrderRequest mint 45 chars > 44 max). Reproduced from clean state (var/ wiped). Sqlite query prints 0 exit 0, but the run itself fails the criterion |
| SC4 | Live mode exits 3 sending nothing; daily/weekly reports exit 0; daily report is ASCII-only | VERIFIED | `run --mode live --once` exit 3, lists 8 unmet preconditions, "No transaction was attempted"; reports exit 0; non-ASCII grep prints `0` |
| SC5 | Vendor tree gone, license present, no scoped vendor references | VERIFIED | `test ! -e vendor/grokbot-pumpfun` exit 0; `test -f src/pumpgrok/engine/LICENSE-grokbot-pumpfun` exit 0; scoped rg prints nothing |
| CKP | `run --mode paper --once --replay tests/fixtures/replay/smoke` completes a full ten-seat cycle offline | VERIFIED | Exit 0, `engine decision=skip reason=data_unavailable`, `cycle_end` row; run_once_replay runs run_replay plus all ten seat cycles in roster order (src/pumpgrok/supervisor/scheduler.py) |

**Score:** 5/6 criterion-level truths hold (SC3 failed).

Note on SC1: transient inline tool output once rendered a single `Pytest: No tests collected` line for the `uv run pytest` form; every run redirected to a file (three repetitions, both `uv run` and direct `.venv` invocations) collected 244/244 consistently with exit 0. Treated as a display artifact, not a result.

Note on SC4 ASCII sub-check: the pipeline prints `0` as required; the trailing `grep -c` itself exits 1, which is grep's standard "no lines selected" status for a zero count, not a failure of the criterion (the criterion constrains only what is printed).

Note on SC3 hermeticity: `run_once_replay` constructs `RiskEngine(..., env={})` deliberately, so host killswitch env/file/alert state does not leak into the deterministic replay ledger; only ledger `KillSwitchSet` rows are honored (src/pumpgrok/supervisor/scheduler.py). Killswitch rejection itself is unit-covered (tests/risk/test_killswitch.py, suite green). Even after the mint fix, SC3 exercises the no-approval/no-trade path rather than the killswitch-rejection path; the OrderPlaced=0 assertion then holds trivially. Recorded here as context, not as a second gap.

### Required Artifacts (spot-checked per requirement)

All paths exist, are substantive (matched key symbols), and are wired (imported/used; full suite green). Full per-requirement table below; artifact notes here only where non-obvious:

- PAPER-001 curve fills: src/pumpgrok/execution/paper_adapter.py (liquidity floor, partials, slippage_exceeded, tx_dropped) + curve_math.py + fees.py + latency.py
- RISK-001/002/005: src/pumpgrok/risk/engine.py (check, order_hash, 19-step first-failure-wins, daily_loss/drawdown halts, FLOOR HALTED bytes, KILL verdict, seat_may_trade)
- RISK-003: src/pumpgrok/risk/breakers.py (DataStale, LossVelocity, ExecErrors, half-open probe, ledger rebuild)
- RISK-004: src/pumpgrok/risk/killswitch.py (env/file/alert poll, flatten, in-flight barrier, CLI-only clear)
- RISK-006: src/pumpgrok/supervisor/seat_task.py (observe-only latch, restart budget, heartbeat staleness)
- AUTO-001..004: src/pumpgrok/supervisor/scheduler.py + seat_task.py + health.py (roster-order ticks, clock.timeout crash, autonomy levels, SIGTERM drain, /healthz + /readyz + var/health.json)
- PAPER-002: src/pumpgrok/ledger/store.py (BEGIN IMMEDIATE, prev_hash chain, INCONSISTENT, idempotency refusal) + reducer.py + reconcile.py
- PAPER-003: src/pumpgrok/ledger/export.py (meta.export_seq resume, vendor-shape trades.jsonl, tmp+os.replace)
- PAPER-004: src/pumpgrok/replay/runner.py + fixtures.py + recorder.py + rng.py (FixtureClock, seeded RNG, canonical_request_hash, 180 s DataStale hole)
- PAPER-005: paper_adapter.py (graduated force-close, post_graduation_no_reserves, blind_flatten at last_good)
- PAPER-006: src/pumpgrok/reporting/ (daily.py, weekly.py, render.py with str.format, ASCII-only, fixture snapshots)
- PAPER-007: src/pumpgrok/core/approvals.py (SOL-YYYYMMDD-NNN sequencing, autonomous_paper, approval_mismatch) + ledger/autonomy.py
- SEC-004: src/pumpgrok/execution/live/live_gate.py (9 preconditions, exit 3) + live/live_adapter.py (LiveGateError, LiveWriteAttempted)
- GOLIVE-001/002: cli.py live confirm (HMAC record, ApprovalRecorded kind=live_gate, never changes mode) + live_gate.validate (paper-window metrics, replay exclusion, notional cap)
- STRUCT-004: 19 characterization files covering the ported vendor modules; daily-loss auto-clear explicitly not ported with marked test
- STRUCT-006: vendor/ absent, LICENSE-grokbot-pumpfun present, scoped census clean (SC5)
- TOOL-004: src/pumpgrok/tools/exec/place.py (decision_id, derived idempotency key, atomic approval consume)
- TOOL-011: cli.py verbs print JSON; `paper buy --help` lists --ticket/--mint/--size-sol/--slippage-bps/--approval-id (verified live)
- R62: src/pumpgrok/engine/reputation.py (degraded book refuses buys reputation_degraded, exits continue, rebuild from PositionOpened/Closed) + tests/safety/test_reputation_degraded.py
- R65: src/pumpgrok/tools/onchain/curve_layout.py LAYOUT_STATUS="ASSUMED"; paper adapter refuses RPC-curve entries with data_unavailable (fail closed); tests/fixtures/rpc/bonding_curve/layout.json layout_status ASSUMED with recorded probe_error (mainnet probe timed out). Reported as ASSUMED per the phase gate, not marked verified.

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| PaperAdapter.place | RiskEngine.check | in-adapter call per order incl. CONFIRMING re-check | WIRED (code) / E2E BLOCKED | Unit-wired; e2e over smoke-10m blocked by the mint gap |
| RiskEngine | ledger | only RiskEngine appends HaltSet/BreakerTripped | WIRED | suite green incl. halt/breaker tests |
| supervisor seats | engine/risk/adapter | run_once_replay ten cycles roster order | WIRED | smoke run exit 0; smoke-10m crashes in sniper (mint gap) |
| report verbs | ledger | read-only render from fixture ledger | WIRED | daily/weekly exit 0 |
| live gate | CLI exit 3 | LiveGate.evaluate, 9 preconditions | WIRED | exit 3 observed with all unmet lines |
| RPC curve reads | PaperAdapter | rpc_curve_price_allowed gate -> data_unavailable | WIRED (fail closed) | ASSUMED layout never prices a fill |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| verify events.hash | canonical event JSON | replay of smoke-10m fixture (41 ticks + 1 LLM record) | Yes, stable d6ce3e73 across runs | FLOWING |
| killswitch replay ledger | OrderPlaced rows | none placed (crash precedes placement) | N/A (run fails first) | BLOCKED by gap |
| daily/weekly report | ledger at var/ | renders 8.3 sections from real ledger read | Yes (empty-paper-ledger render observed) | FLOWING |
| health endpoints | ledger + seat state | scheduler/health wiring | Code present, suite green; not live-probed | WIRED (unprobed) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| characterization collection >= 164 | `uv run pytest --collect-only -q tests/characterization` | exit 0, 244 tests | PASS |
| full suite green | `uv run pytest -q` | exit 0 (1186 collected) | PASS |
| deterministic replay | `uv run pumpgrok verify --fixture smoke-10m` (twice) | exit 0 both; identical events.hash d6ce3e73 | PASS |
| killswitch replay | `PUMPGROK_KILLSWITCH=1 uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke-10m` | exit 1, sniper mint ValidationError | FAIL (gap) |
| OrderPlaced count | sqlite count query on var/replay/smoke-10m/ledger.sqlite | prints 0, exit 0 | PASS (trivially; run crashed first) |
| live refusal | `uv run pumpgrok run --mode live --once` | exit 3, 8 unmet lines, no transaction | PASS |
| reports | `report --daily` / `--weekly` | exit 0 / exit 0 | PASS |
| ASCII-only daily | `report --daily \| grep -c -P '[^\x00-\x7F]'` | prints 0 | PASS |
| vendor retired | `test ! -e vendor/...`; `test -f .../LICENSE-...`; scoped rg | exit 0; exit 0; prints nothing | PASS |
| checkpoint ten-seat | `run --mode paper --once --replay tests/fixtures/replay/smoke` | exit 0, cycle_end, engine skip | PASS |

Step 7b extras: no servers started; no state mutated except gitignored var/ regenerated ledgers. Full suite run once (backgrounded, exit 0); no per-truth suite re-runs.

### Probe Execution

No phase-declared probe scripts (no `probe-*.sh` referenced in 04 PLAN/SUMMARY files; conventional `scripts/*/tests/probe-*.sh` absent). Section not applicable.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| STRUCT-004 | 04-03 | 13 vendor modules ported, >=164 1:1 tests, no auto-clear port | SATISFIED | 244 characterization tests; `uv run pytest -q` exit 0 |
| STRUCT-006 | 04-09 | vendor tree deleted, license kept, census clean | SATISFIED | SC5 triple check all pass |
| PAPER-001 | 04-04 | curve-faithful fills, fees, latency, slippage, partials, tx_dropped | SATISFIED | execution/paper_adapter.py + curve_math.py/fees.py/latency.py; suite green |
| PAPER-002 | 04-01 | append-only WAL, hash chain, snapshots, reducer, tamper refusal | SATISFIED | ledger/store.py + reducer.py + reconcile.py; suite green |
| PAPER-003 | 04-01 | JSONL export resume, vendor-shape lines, atomic desk mirrors | SATISFIED | ledger/export.py; suite green |
| PAPER-004 | 04-02 | deterministic replay, missing-record fail, DataStale hole, record verb | SATISFIED | SC2 identical hash + gapped-dataset unit test green |
| PAPER-005 | 04-04 | graduation force-close, post-graduation reject, blind flatten | SATISFIED | paper_adapter.py graduated/blind_flatten/last_good; suite green |
| PAPER-006 | 04-09 | daily/weekly 8.3 sections, str.format, ASCII, snapshots | SATISFIED | SC4 reports exit 0, ASCII 0, render.py |
| PAPER-007 | 04-07 | SOL- tickets, approvals, manual vs autonomous semantics | SATISFIED | core/approvals.py SOL-/autonomous_paper/approval_mismatch; suite green |
| RISK-001 | 04-05 | 19-step check, order_hash, R20 budget from TOML | SATISFIED | risk/engine.py; suite green |
| RISK-002 | 04-05 | daily-loss/drawdown halts, human clear with approval | SATISFIED | risk/engine.py HaltSet/HaltCleared; suite green |
| RISK-003 | 04-05 | breakers, half-open probe, CONFIRMING re-check, ledger rebuild | SATISFIED | risk/breakers.py; suite green (e2e row in SC3 trivially 0) |
| RISK-004 | 04-05 | killswitch stops buys in one cycle, flatten, CLI-only clear | BLOCKED (e2e) | Unit tests green and OrderPlaced=0 observed, but SC3 run exits 1 on the mint crash before killswitch logic engages |
| RISK-005 | 04-05 | RISK KILL blocks mint session-wide; seat_may_trade side rules | SATISFIED | risk/engine.py KILL/seat_may_trade; suite green |
| RISK-006 | 04-08 | observe-only gating incl. sniper/risk and exit-manual halt | SATISFIED | supervisor/seat_task.py latch; suite green |
| AUTO-001 | 04-08 | ten asyncio seat tasks, roster order, 1 s tick, autonomy levels | SATISFIED | supervisor/scheduler.py; smoke run exit 0 |
| AUTO-002 | 04-08 | heartbeats, restart budget+backoff, latches, resume | SATISFIED | supervisor/seat_task.py; suite green |
| AUTO-003 | 04-08 | SIGTERM drain/snapshot/exit 0; second signal no force | SATISFIED | supervisor/scheduler.py signal handling; suite green |
| AUTO-004 | 04-08 | /healthz + /readyz + var/health.json semantics | SATISFIED | supervisor/health.py; suite green |
| AUTO-005 | 04-08 | degraded modes incl. replay fail-closed rows | SATISFIED | scheduler.py BLIND/DataStale/persistence_down/clock_skew; suite green |
| AUTO-006 | 04-08 | full ten-seat cycle over smoke, exit 0, offline | SATISFIED | checkpoint exit 0 |
| SEC-004 | 04-09 | live exit 3 with all unmet lines; stub raises, sends nothing | SATISFIED | SC4 live run exit 3; live_adapter.py LiveGateError |
| GOLIVE-001 | 04-09 | HMAC confirm record, no mode change | SATISFIED | cli.py live confirm; suite green |
| GOLIVE-002 | 04-09 | paper-window validation, replay exclusion, cap bound | SATISFIED | live_gate.py validate; weekly report prints gate table |
| TOOL-004 | 04-07 | exec.place decision_id, derived idempotency, atomic consume | SATISFIED | tools/exec/place.py; suite green |
| TOOL-011 | 04-07 | all section-12 verbs JSON, no exit-5 for served verbs | SATISFIED | paper buy --help flags verified live; verb coverage tests green |
| R62 | 04-06 | degraded reputation fail-closed + rebuild | SATISFIED | engine/reputation.py + tests/safety/test_reputation_degraded.py green |
| R65 | 04-04 | curve layout ASSUMED, RPC entries fail closed | ASSUMED (by design) | curve_layout.py LAYOUT_STATUS=ASSUMED; adapter data_unavailable gate; layout.json probe_error timeout; honestly reported, not marked verified |

Orphaned requirements: none — every Phase 4 requirement in REQUIREMENTS.md traceability is claimed by at least one 04 plan (04-01..04-09 cover STRUCT/PAPER/RISK/AUTO/SEC/GOLIVE plus TOOL-004/011 carry-overs; R62 in 04-06; R65 in 04-04).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (104 changed product files scanned) | - | TBD/FIXME/XXX | None | Zero debt markers |
| scripts/check.sh | 123-157 | PLACEHOLDER/placeholder | Info (false positive) | The checker implementation itself; it scans for the "your-org" placeholder, not debt |
| src/pumpgrok/cli.py | 174 | "not yet implemented" | Info (by design) | STRUCT-005 fallback for verbs whose subsystem is absent; full suite green |

No blockers, no warnings. Generated var/ ledgers are gitignored (`git check-ignore` confirms) and `git status` shows no tracked product modifications from verification (only untracked .planning/state.json and 01-REVIEW university file predate this run).

### Human Verification Required

None. All checkable behavior was exercised via CLI (no daemons started, no external services). Items a human could still eyeball but which do not block:

1. Weekly report row 1 reads `mode_live | OK | effective mode is live` under a default paper-mode invocation — the 9-row gate table otherwise evaluates correctly. Possible display-only quirk in the hypothetical-mode row; recorded as an observation, not a gap (criterion requires only exit 0, which holds).

### Gaps Summary

One blocking gap with a single root cause. The smoke-10m fixture mints (`Smoke10MintAAAA...`, `Smoke10MintBBBB...`, 45 chars each, in generator.py:29-30 and events.jsonl) violate the pre-existing `OrderRequest.mint` max-44 invariant, so any ten-seat replay run over smoke-10m that reaches a sniper signal crashes the seat and fails the run with exit 1. This fails SC3 as literally specified. Fix: shorten both mints to valid 32-44 char base58 strings, regenerate the manifest sha256 pins and the canonical verify hash (SC2's d6ce3e73 will change), then re-run all five criteria literally. No later milestone phase covers this (Phase 5 is soak/faults/metrics/runbooks), so it is not deferred.

---
_Verified: 2026-10-22T00:30:17Z_
_Verifier: Claude (gsd-verifier)_
