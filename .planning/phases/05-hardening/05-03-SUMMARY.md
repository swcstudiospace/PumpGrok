---
phase: 05-hardening
plan: 03
subsystem: degradation-soak
tags: [fault-injection, soak, rollover, AUTO-007, AUTO-008]
status: complete
commits:
  - cc77c25
  - cd404c5
  - 766d9aa
plan_head_before: 095e2ec
dependency_graph:
  requires: [05-01]
  provides: [fault-harness, rollover-emitter, soak-3d, degradation-suites]
  affects: [05-matrix, container, nightly-soak]
tech_stack:
  added: []
  patterns: [protocol-fakes, day-keyed-idempotency, virtual-time-soak, manifest-first-load]
key_files:
  created:
    - tests/harness/test_faults.py
    - tests/degradation/test_llm_failure.py
    - tests/degradation/test_rpc_failure.py
    - tests/degradation/test_data_source_outage.py
    - tests/degradation/test_ledger_unwritable.py
    - tests/degradation/test_clock_skew.py
    - tests/degradation/test_partial_restart.py
    - scripts/build_soak_fixture.py
    - tests/fixtures/replay/soak-3d/events.jsonl
    - tests/fixtures/replay/soak-3d/llm.jsonl
    - tests/fixtures/replay/soak-3d/manifest.json
    - tests/soak/test_soak_multiday_replay.py
    - tests/fixtures/llm/timeout.json
    - tests/fixtures/http/adversarial/mixed.json
    - tests/fixtures/secrets/planted.txt
  modified:
    - tests/harness/faults.py
    - tests/harness/__init__.py
    - src/pumpgrok/replay/clock.py
    - src/pumpgrok/supervisor/scheduler.py
    - tests/supervisor/test_degraded.py
decisions:
  - "Backward skew rides advance_to only forward; FixtureClock.jump(delta_s) is the backward step (PATTERNS 0.8 option B), forward jumps fire timers like advance_to."
  - "Rollover emitted in Supervisor._end_of_tick outside seat cycles; run_once_replay read-only assert narrowed to allow exactly day-keyed DailyRollover rows (5.2 conflict), stated in a code comment."
  - "Soak fixture uses a half-open day range (Jan 1 00:00 inclusive to Jan 4 00:00 exclusive): 4320 ticks over exactly three UTC days, so three rollovers, not four."
  - "Cyrillic lookalikes are flagged by non-ASCII detection, not NFKC (NFKC does not fold U+043E); fixture note corrected."
metrics:
  duration: "1 session"
  tasks: 3
  commits_actual: 3
actuals:
  tokens: 62000
  tasks: 3
  commits: 3
---

# Phase 5 Plan 03: Fault and Soak Evidence Summary

One-liner: Extended fault harness with six protocol fakes, idempotent
DailyRollover emission per UTC day, six degradation suites proving every
AUTO-005 row with recovery, and a 3-day soak over a synthesised 813 KB
fixture with SC1 green in 140 s wall time.

## Tasks Completed

### Task 1: Harness fakes, clock backward move, DailyRollover emitter (cc77c25)

- `tests/harness/faults.py`: `FaultMode` gains `malformed` and `unknown`;
  `InjectedUnknown` marker added. Six protocol fakes in the FaultInjector
  style with fired-counters: `FaultyLLMClient`, `FaultyRpcClient`
  (ordered failover, product `RpcError`/`DataStale`), `FaultyDataSource`,
  `FaultyPriceSource`, `FaultyExecutionAdapter` (unknown, never retried),
  `FaultyLedgerStore` (EACCES wrapper delegating reads). `TIMEOUT` raises
  builtin `TimeoutError` everywhere, preserving the module rule.
- `src/pumpgrok/replay/clock.py`: `FixtureClock.jump(delta_s)` moves
  virtual time backward (forward jumps fire timers like `advance_to`).
- `src/pumpgrok/supervisor/scheduler.py`: `rollover_key(day_utc)` in the
  `halt_key` shape; `Supervisor._emit_rollover` appends one `DailyRollover`
  per UTC day including the first, in `_end_of_tick` outside the seat
  cycles; `run_once_replay` read-only assert narrowed to allow exactly
  rollover-keyed rows (conflict and location stated in comments).
- `tests/harness/test_faults.py` (new): every fake mode plus the
  acceptance proof — a three-virtual-day supervisor run yields exactly
  three DailyRollover events, idempotent within a day.
- `tests/supervisor/test_degraded.py`: two golden tests updated in the
  same commit (Pitfall 11) to expect the JournalNote plus the fixture-day
  rollover; CLI smoke count 1 -> 2.

Verify: `uv run pytest -q tests/supervisor/test_degraded.py tests/harness/
-k "not slow"` exit 0 (24 passed).

### Task 2: Six degradation tests over the harness (cd404c5)

- `test_llm_failure.py` (INV-R-34): timeout/503/429/malformed/unknown via
  `FaultyLLMClient` degrade to `rule_fallback`; `require_llm` gives
  `observe_only_buys`; rule scoring with no auditor has audit 0.0; the
  supervisor ticks twice with heartbeats advancing; `GrokOps.precheck`
  exhausts a 1-call budget; the `timeout.json` template replays with
  virtual latency; the planted x.ai key carries the pragma and never
  reaches the ledger.
- `test_rpc_failure.py` (INV-R-33): rate-limit then raise fails over in
  order to product `RpcError`; blind trips and recovers on a healthy
  probe; `ExecErrorsBreaker` trips at the third `rpc_error` and closes
  after a cooldown probe.
- `test_data_source_outage.py` (INV-R-32): WS silence trips DataStale at
  120 s on `DegradedState` and the product breaker, recovers on fresh
  ticks; REST outage serves last-good or typed `DataStale`; the blind
  window marks last-good and emits one `blind_flatten` escalation;
  `mixed.json` payloads raise typed `DataStale` (never raw) or are
  caller-flagged (non-ASCII confusable, negative reserves).
- `test_ledger_unwritable.py` (INV-R-20): `FaultyLedgerStore` refuses
  with EACCES, zero rows land during the fault, 1000 buffer then
  `LedgerUnavailable`, one `persistence_down` escalation, drain restores
  1000 rows and verifies.
- `test_clock_skew.py` (INV-R-22): `jump(-30)` refuses appends with
  `ClockSkew` plus a `clock_skew` escalation; `jump(+35)` resumes.
- `test_partial_restart.py` (INV-R-35): a crashing seat latches
  observe-only after budget exhaustion with one escalation while a peer
  ticks; idempotency keys stay unique; a breaker tripped through ledger
  rows reconstructs with its remaining cooldown after restart; a rebuilt
  supervisor resumes with one rollover for the shared day.
- Fixtures: `llm/timeout.json`, `http/adversarial/mixed.json`,
  `secrets/planted.txt` (every secret line carries
  `pragma: allowlist secret`; G-3 passes on all nine new files).

Verify: `uv run pytest -q tests/degradation/` exit 0 (31 passed).

### Task 3: Soak-3d fixture builder and multiday soak test (766d9aa)

- `scripts/build_soak_fixture.py`: synthesises soak-3d (seed 20260101,
  4320 sixty-second ticks, two mints, one mid-day-2 graduation, one
  creator with two launches, one recorded LLM outcome) with smoke-10m
  manifest keys including sha256 digests; 813,181 bytes, under 5 MB.
- `tests/soak/test_soak_multiday_replay.py`:
  `test_soak_replay_bounded_memory` (slow) replays all 4320 ticks through
  the real ten-seat replay cycles with tracemalloc marks per virtual
  hour, sys.excepthook plus loop-handler capture, per-day
  `DailyRollover` counts, ledger verify, and a rendered daily report per
  day; `test_soak_short_pr` runs the same hooks over smoke-10m;
  manifest test asserts the digest keys. Absent fixture fails under
  `PUMPGROK_REQUIRE_SOAK=1`, skips otherwise (both branches proven).

Verify: `uv run pytest -q tests/soak/test_soak_multiday_replay.py
tests/degradation/` exit 0 (34 passed, wall 140 s; soak-only 129 s,
against the 30-minute PR budget).

Checkpoint smoke: `uv run pumpgrok run --mode paper --once --replay
tests/fixtures/replay/smoke` exit 0.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stored-row shape is payload_json, not payload.**
Found during: Task 2 verify (blind-flatten test KeyError).
Fix: assert on `store.read()` rows (payload dicts) instead of the
`append_escalation` return value.
Files: tests/degradation/test_data_source_outage.py.

**2. [Rule 1 - Bug] NFKC does not fold Cyrillic lookalikes.**
Found during: Task 2 verify (confusable assertion failed).
Fix: caller flags non-ASCII mints for the confusable map; test asserts
non-ASCII presence plus NFKC stability; fixture note corrected.
Files: tests/degradation/test_data_source_outage.py,
tests/fixtures/http/adversarial/mixed.json.

**3. [Rule 1 - Bug] Cooldown advance missed the trip offset.**
Found during: Task 2 verify (breaker still open after cooldown).
Fix: advance to trip time plus cooldown plus one second.
Files: tests/degradation/test_rpc_failure.py.

**4. [Rule 1 - Bug] Inclusive endpoint spans four calendar days.**
Found during: Task 3 verify (4 rollovers, last on Jan 4).
Fix: builder uses a half-open range (4320 ticks); driver ticks every
stamp including the first. Three days, three rollovers.
Files: scripts/build_soak_fixture.py,
tests/soak/test_soak_multiday_replay.py.

**5. [Rule 2 - Correctness] Golden tests pinned the pre-rollover ledger.**
Found during: Task 1 implementation (Pitfall 11).
Fix: updated the two count assertions in the same commit; read-only
assert narrowed to rollover-keyed rows with the 5.2 rationale in code.
Files: tests/supervisor/test_degraded.py,
src/pumpgrok/supervisor/scheduler.py.

Or: "None - plan executed exactly as written" does not apply; the five
fixes above are the complete list.

## Known Stubs

None.

## Threat Flags

None. New surface review: the planted secret is fake, pragma-marked, and
G-3 green; the rollover emitter is day-keyed idempotent and appends
outside seat cycles; soak loads the manifest before opening any ledger
(T-05-06), fixtures carry digests, memory is tracemalloc-bounded with a
PR-time short variant (T-05-08).

## Self-Check

- tests/harness/test_faults.py, all six degradation files, builder,
  soak fixture (3 files), soak test, llm/adversarial/secret fixtures:
  FOUND on disk.
- cc77c25, cd404c5, 766d9aa: FOUND in `git log`.
- SC1 literal exit 0; checkpoint smoke exit 0.

## Self-Check: PASSED
