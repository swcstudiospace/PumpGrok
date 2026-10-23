---
phase: 01-foundation
plan: 05
subsystem: testing
tags: [replay, clock, rng, fixtures, sha256, network-block, static-analysis, pytest]

# Dependency graph
requires:
  - phase: 01-foundation (plan 01-01)
    provides: pinned toolchain (pyproject, uv.lock, Makefile, pytest-asyncio auto mode)
  - phase: 01-foundation (plan 01-03)
    provides: core/ids.py IdFactory and the Clock protocol that this plan relocates
provides:
  - Clock protocol with WallClock (sole time-primitive importer) and FixtureClock (virtual time, heap-ordered sleep/timeout)
  - make_rng(seed=20260101), the only random.Random constructor in src/pumpgrok
  - sha256-manifest fixture gate (verify_manifest, load_dataset, CorruptFixture) and strict JSONL reader
  - Hand-authored smoke dataset at tests/fixtures/replay/smoke
  - Autouse offline guard (httpx transports + websockets connect) in tests/conftest.py
  - FaultInjector with stale, timeout, rate_limit, raise, unwritable modes
  - AST static guard for virtual time, seeded RNG and uuid/secrets
provides_for_later:
  - replay CLI path (plan 01-08) maps CorruptFixture to exit 4 before any ledger is opened
affects: [01-08 CLI replay path, 01-09 Dockerfile COPY of tests/fixtures/replay/smoke, phase 2 fixture-recorded HTTP tests, phase 4 determinism claims]

# Actuals (#2632)
actuals:
  tokens: 10657   # chars/4 over the 14 files changed in this plan (42629 chars)
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Clock injected everywhere; WallClock is the only module touching time/asyncio timers"
    - "Manifest-gated fixture load: verify sha256 and layout before any ledger path is touched"
    - "Strict JSONL readers: a corrupt line raises with its line number; nothing is skipped"
    - "Offline by default: autouse fixture patches class-specific transports so MockTransport still works"
    - "AST guard with resolved import aliases; comments and docstrings never count"

key-files:
  created:
    - src/pumpgrok/replay/clock.py
    - src/pumpgrok/replay/rng.py
    - src/pumpgrok/replay/fixtures.py
    - src/pumpgrok/replay/__init__.py
    - tests/conftest.py
    - tests/harness/__init__.py
    - tests/harness/faults.py
    - tests/fixtures/replay/smoke/manifest.json
    - tests/fixtures/replay/smoke/events.jsonl
    - tests/replay/test_clock.py
    - tests/replay/test_fixtures.py
    - tests/test_network_block.py
    - tests/safety/test_static_guards.py
  modified:
    - src/pumpgrok/core/ids.py

key-decisions:
  - "Clock protocol moved from core/ids.py to replay/clock.py as the 01-03 SUMMARY specified; ids.py re-exports it. Import order verified both ways (pumpgrok.replay first, pumpgrok.core first)."
  - "FixtureClock implements sleep and timeout on a single (when, seq) heap, as paper-engine 4.2 specifies, so the Clock protocol is honest in replay; timeout cancels the current task at the virtual deadline and raises TimeoutError."
  - "Fixture timestamps are ISO-8601 ts_utc strings (ledger form), not the float `ts` shown in the design sketch; the loader parses them and rejects backwards time."
  - "Static guard has two allowlists: time primitives only in replay/clock.py (the plan's exact allowlist), and random.Random constructor only in replay/rng.py (the plan's make_rng-only prohibition). Unseeded random.Random() is banned everywhere."
  - "FaultInjector stale mode rewinds ts_utc by one hour and marks the event fault=stale. Unwritable mode is enforced by open_sink(path), because a reader-level unwritable fault has no meaning."
  - "Smoke dataset: four hand-authored ticks over two mints, sha256 listed for events.jsonl only."

patterns-established:
  - "Pattern: time enters only through Clock; wall clock imported in one module, enforced by tests/safety/test_static_guards.py"
  - "Pattern: fixture bytes are untrusted until verify_manifest passes; error fields carry file, line, loc and type, never input values"
  - "Pattern: network blocked in conftest; degraded upstream behaviour injected explicitly through harness.faults.FaultInjector"

requirements-completed: ["FOUND-012"]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "Clock protocol; WallClock is the sole time importer; FixtureClock replays fixture timestamps in order with heap-ordered sleep and timeout"
    requirement: "FOUND-012"
    verification:
      - kind: unit
        ref: "tests/replay/test_clock.py#test_fixture_clock_replays_fixture_timestamps_in_order"
        status: pass
      - kind: unit
        ref: "tests/replay/test_clock.py#test_fixture_timeout_cancels_body_at_virtual_deadline"
        status: pass
    human_judgment: false
  - id: D2
    description: "make_rng(seed=20260101) is the seeded RNG; same seed and fixture reproduce byte-identical ULIDs"
    requirement: "FOUND-012"
    verification:
      - kind: unit
        ref: "tests/replay/test_clock.py#test_replayed_ids_are_byte_identical_for_same_fixture_and_seed"
        status: pass
      - kind: unit
        ref: "tests/replay/test_clock.py#test_same_seed_replays_identical_sequence"
        status: pass
    human_judgment: false
  - id: D3
    description: "sha256 manifest gate: tampered fixture raises CorruptFixture with no ledger file created; strict JSONL readers"
    requirement: "FOUND-012"
    verification:
      - kind: unit
        ref: "tests/replay/test_fixtures.py#test_tampered_byte_raises_corrupt_fixture_and_creates_no_ledger"
        status: pass
      - kind: unit
        ref: "tests/replay/test_fixtures.py#test_strict_reader_raises_on_corrupt_line"
        status: pass
    human_judgment: false
  - id: D4
    description: "Offline by default: un-mocked httpx and websockets calls raise NetworkBlocked; MockTransport still serves"
    requirement: "FOUND-012"
    verification:
      - kind: unit
        ref: "tests/test_network_block.py#test_unmocked_async_httpx_request_is_blocked"
        status: pass
      - kind: unit
        ref: "tests/test_network_block.py#test_mock_transport_still_serves_recorded_responses"
        status: pass
      - kind: unit
        ref: "tests/test_network_block.py#test_websocket_connect_is_blocked_on_modern_path"
        status: pass
    human_judgment: false
  - id: D5
    description: "FaultInjector drives stale, timeout, rate_limit, raise and unwritable modes through the fixture reader"
    requirement: "FOUND-012"
    verification:
      - kind: unit
        ref: "tests/test_network_block.py#test_stale_mode_rewinds_the_event_and_marks_it"
        status: pass
      - kind: unit
        ref: "tests/test_network_block.py#test_unwritable_mode_leaves_events_and_fails_the_sink"
        status: pass
    human_judgment: false
  - id: D6
    description: "Static guard rejects asyncio.sleep/timeout/wait_for, time.*, datetime.now, uuid, secrets, random.random and unseeded Random outside the allowlists; passes on the current tree"
    requirement: "FOUND-012"
    verification:
      - kind: unit
        ref: "tests/safety/test_static_guards.py#test_src_pumpgrok_has_no_forbidden_primitives"
        status: pass
      - kind: unit
        ref: "tests/safety/test_static_guards.py#test_smuggled_wall_clock_in_scratch_copy_is_caught"
        status: pass
    human_judgment: false

# Metrics
duration: ~15min (estimate; no timer)
completed: 2026-10-21
status: complete
---

# Phase 01 Plan 05: Replay Primitives, Offline Guard, Static Virtual-Time Guards Summary

**Clock, seeded RNG and a sha256-gated smoke fixture ship with an offline-by-default test harness, FaultInjector degraded modes, and an AST guard that bars wall-clock, uuid and ambient randomness from src/pumpgrok**

## Performance

- **Duration:** ~15 min (estimate; no timer was running)
- **Started:** not recorded; first task commit 2026-10-21T04:50:04Z
- **Completed:** 2026-10-21T04:52:12Z (last task commit)
- **Tasks:** 3 of 3
- **Files modified:** 14 (13 created, 1 modified)

## Accomplishments

- `WallClock` is the only src module importing `time`, `asyncio.sleep` or `asyncio.timeout`; `FixtureClock` advances only through `advance_to(ts)` and fires sleep and timeout deadlines in `(when, seq)` order.
- `make_rng(seed=20260101)` is the single seeded `random.Random` constructor; the same seed reproduces identical IDs through `IdFactory`.
- `verify_manifest` and `load_dataset` check sha256 digests, reject unlisted `*.jsonl` files, reject traversal-style names and out-of-order timestamps, and raise `CorruptFixture` before any ledger path is touched (INV-R-30).
- Autouse network block: un-mocked `httpx` and `websockets` calls raise `NetworkBlocked`; `httpx.MockTransport` continues to work.
- `FaultInjector` exercises stale, timeout, rate_limit, raise and unwritable modes through the smoke fixture reader.
- AST guard (`tests/safety/test_static_guards.py`) passes on the current tree and catches 18 probe cases plus a smuggled `time.time()` in a scratch copy of `core/ids.py`.

## Task Commits

Each task was committed atomically:

1. **Task 1 (tracer): clock, seeded RNG, manifest-gated fixture load** - `139c5e2` (feat)
2. **Task 2: network-blocking conftest and FaultInjector** - `d26dcce` (test)
3. **Task 3: static virtual-time and uuid guards** - `04a1e21` (test)

**Plan metadata:** recorded in the SUMMARY commit that follows this file (docs(01-05)).

_Note: task 1 was TDD; RED was confirmed (`ModuleNotFoundError: pumpgrok.replay`) before implementation._

## Files Created/Modified

- `src/pumpgrok/replay/clock.py` - Clock protocol, format/parse of `ts_utc`, WallClock, FixtureClock (virtual sleep and timeout)
- `src/pumpgrok/replay/rng.py` - `DEFAULT_SEED`, `make_rng`
- `src/pumpgrok/replay/fixtures.py` - `CorruptFixture`, `FixtureManifest`, `verify_manifest`, `read_jsonl`, `load_dataset`, `event_epoch`
- `src/pumpgrok/replay/__init__.py` - package facade
- `src/pumpgrok/core/ids.py` - `Clock` now re-exported from `replay.clock` (definition moved)
- `tests/conftest.py` - autouse network block (httpx transports, websockets connect at both paths)
- `tests/harness/__init__.py` - `NetworkBlocked`
- `tests/harness/faults.py` - `FaultMode`, `FaultInjector`, `InjectedFault`, `InjectedRateLimit`
- `tests/fixtures/replay/smoke/manifest.json`, `events.jsonl` - hand-authored smoke dataset (sha256 listed)
- `tests/replay/test_clock.py` (10 tests), `tests/replay/test_fixtures.py` (10 tests)
- `tests/test_network_block.py` (13 tests), `tests/safety/test_static_guards.py` (21 tests)

## Decisions Made

- Clock lives in `replay/clock.py`; `core/ids.py` re-exports it, closing the watch item from 01-03.
- `FixtureClock` implements sleep and timeout on one heap so the protocol is real in replay. No stubs.
- Fixture timestamps use the ledger's ISO-8601 `ts_utc` form. The design sketch's float `ts` was not used.
- Static guard has the plan's time allowlist (`replay/clock.py`) plus an RNG-constructor allowlist (`replay/rng.py`) that enforces "make_rng is the only random.Random constructor". Unseeded `Random()` is banned everywhere.
- `secrets` and `random.SystemRandom` are banned in addition to the plan's list, per paper-engine 4.2.
- FaultInjector `stale` rewinds `ts_utc` by 3600 s and sets `fault: stale`. `unwritable` is enforced by `open_sink(path)`, which raises `PermissionError(EACCES)`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Clock relocation from `core/ids.py` was not in `files_modified`**
- **Found during:** Task 1 (Clock protocol)
- **Issue:** The 01-03 SUMMARY recorded that plan 01-05 would move the `Clock` definition to `replay/clock.py` and have `ids.py` re-export it. The plan's `files_modified` omitted `core/ids.py`.
- **Fix:** Moved the protocol; `ids.py` now imports and re-exports `Clock`. Verified `pumpgrok.core.Clock is pumpgrok.replay.Clock` and import order in fresh processes.
- **Files modified:** `src/pumpgrok/core/ids.py`
- **Verification:** full suite passes; `tests/core/test_ids.py` and `tests/core/test_registry.py` unchanged and green.
- **Committed in:** `139c5e2` (task 1)

**2. [Rule 2 - Missing Critical] Manifest gate stricter than the plan text**
- **Found during:** Task 1
- **Issue:** Plan requires sha256 verification. Without also rejecting unlisted `*.jsonl` files, bytes could enter replay beside the verified set. Without name checks, a manifest could point outside its directory.
- **Fix:** Unlisted `*.jsonl` files raise `CorruptFixture`. Names must be plain and digests lowercase hex. Event timestamps must be parseable and non-decreasing. Non-finite JSON numbers are rejected.
- **Files modified:** `src/pumpgrok/replay/fixtures.py`
- **Verification:** `test_unlisted_jsonl_file_is_rejected`, `test_manifest_with_path_traversal_name_is_rejected`, `test_out_of_order_timestamps_are_rejected`, `test_strict_reader_rejects_non_finite_numbers_and_non_objects`
- **Committed in:** `139c5e2` (task 1)

**3. [Rule 2 - Missing Critical] Error reports must not echo input values**
- **Found during:** Task 1
- **Issue:** pydantic `ValidationError` embeds offending input. Fixture errors can surface to CLI output, and the plan's settings rule forbids echoing values.
- **Fix:** Manifest validation errors are reduced to `loc: type` pairs with `include_input=False`, and the raise uses `from None`.
- **Verification:** `test_manifest_error_report_carries_no_input_values`
- **Committed in:** `139c5e2` (task 1)

**Total deviations:** 3 auto-fixed (3 Rule 2). **Impact:** all three strengthen the stated guarantees (INV-R-30, T-01-51, the no-echo rule). No scope creep beyond the plan's artifacts, and no changed behaviour for the existing tests.

## Issues Encountered

- One hashline edit in `tests/replay/test_fixtures.py` targeted the wrong line and corrupted a file. I rewrote that file whole before committing; the broken state was never committed.
- `gsd_run check evaluation-scope` does not exist in this environment (`Unknown check subcommand`). The self-check below uses a `git log` on the branch instead.
- `config-get workflow.human_verify_mode` was not queried; I applied the documented default (`end-of-phase`). Under that default the tracer's `<verify>` carries only `<automated>`, so the tracer gate took row 3 (re-run verify, continue) and no checkpoint was raised.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Replay primitives, the manifest gate and the smoke dataset are in place for plan 01-08 (CLI replay path: map `CorruptFixture` to exit 4 before any ledger write) and plan 01-09 (Dockerfile COPY of `tests/fixtures/replay/smoke`).
- Offline guard is active for the whole suite. Later plans that need HTTP must use `httpx.MockTransport`.
- **For the orchestrator's formatter pass (not run here per the wave rule):** `src/pumpgrok/replay/fixtures.py` has 2 lines over 100 characters and `tests/safety/test_static_guards.py` has 1. `ruff format` and `ruff check` have not been run on this plan.
- Lint and typecheck (`make lint typecheck`) have not been run; the plan's verify commands are the pytest commands only.

## Self-Check: PASSED

- Key files exist on disk (`[ -f ]` on all 13 created files and `ids.py`).
- Commits on this branch for plan 01-05 (`git log`): `139c5e2`, `d26dcce`, `04a1e21`.
- Task acceptance criteria re-run after each task; the plan-level verification passes (exit 0).
- Plan verification command `uv run pytest -q tests/replay/ tests/test_network_block.py tests/safety/test_static_guards.py`: exit 0.
- Full suite `uv run pytest -q`: passes.

---
*Phase: 01-foundation*
*Completed: 2026-10-21*
