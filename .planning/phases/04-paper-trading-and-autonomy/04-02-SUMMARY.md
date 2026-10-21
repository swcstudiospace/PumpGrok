---
phase: 04-paper-trading-and-autonomy
plan: 02
subsystem: replay
tags: [replay, determinism, fixtures, ledger, paper-trading, verify, killswitch]
requires:
  - phase: 04-01
    provides: LedgerStore.append_batch atomic transaction primitive and hash-chained verify
provides:
  - Seeded deterministic replay runner folding fixture ticks into one engine verdict
  - Recorded-LLM lookup keyed by canonical request hash with fail-closed ReplayMissingRecord
  - Hand-authored smoke-10m fixture with sha256-pinned manifest
  - Working pumpgrok verify --fixture verb printing a stable events.hash
  - PUMPGROK_KILLSWITCH accepted by settings validation and canonical var/ledger.sqlite path
affects: [04-03, 04-04, 04-05, 04-06, 04-07]
actuals:
  tokens: 12000
  tasks: 3
  commits: 5
tech-stack:
  added: []
  patterns: [fixture-clock-driven replay, canonical-request-hash fixture lookup, manifest-pinned fixtures]
key-files:
  created:
    - src/pumpgrok/replay/sources.py
    - src/pumpgrok/replay/runner.py
    - src/pumpgrok/replay/recorder.py
    - tests/replay/test_runner_determinism.py
    - tests/fixtures/replay/smoke-10m/generator.py
    - tests/fixtures/replay/smoke-10m/manifest.json
  modified:
    - src/pumpgrok/replay/clock.py
    - src/pumpgrok/replay/__init__.py
    - src/pumpgrok/core/errors.py
    - src/pumpgrok/config/settings.py
    - src/pumpgrok/cli.py
    - src/pumpgrok/tools/__init__.py
    - tests/test_skip_cycle.py
    - tests/test_tools_cli.py
key-decisions:
  - "Runner stays out of replay/__init__: it folds engine decisions and settings, which cycle back through pumpgrok.core while it initializes"
  - "smoke-10m ships no 180 s hole so verify passes; the DataStale gap is covered by a synthetic gapped dataset in the determinism test"
  - "Datasets without llm.jsonl (legacy smoke) skip the model-resolution step; datasets with it require a hash hit"
  - "PAPER_LEDGER_PATH var/ledger.sqlite is canonical; var/desk/ledger.sqlite is retired; replay keeps var/replay/<dataset>/ledger.sqlite per R21"
requirements-completed: [PAPER-004]
coverage:
  - id: D1
    description: "Two seeded runs over smoke-10m produce identical events.hash with CONSISTENT verify"
    requirement: "PAPER-004"
    verification:
      - kind: unit
        ref: "tests/replay/test_runner_determinism.py::test_two_seeded_runs_produce_identical_hashes"
        status: pass
      - kind: integration
        ref: "uv run pumpgrok verify --fixture smoke-10m (twice, identical events.hash d6ce3e73)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Missing LLM record fails the run with ReplayMissingRecord"
    requirement: "PAPER-004"
    verification:
      - kind: unit
        ref: "tests/replay/test_runner_determinism.py::test_missing_llm_record_fails_the_run"
        status: pass
    human_judgment: false
  - id: D3
    description: "A 180 s silence hole trips DataStale before any ledger write"
    requirement: "PAPER-004"
    verification:
      - kind: unit
        ref: "tests/replay/test_runner_determinism.py::test_180s_silence_fails_the_run_with_data_stale"
        status: pass
    human_judgment: false
  - id: D4
    description: "PUMPGROK_KILLSWITCH=1 passes settings validation; canonical ledger path unified"
    requirement: "PAPER-004"
    verification:
      - kind: integration
        ref: "tests/test_skip_cycle.py::test_killswitch_env_passes_settings_validation"
        status: pass
      - kind: integration
        ref: "tests/test_tools_cli.py::TestOperatorVerbs::test_killswitch_set_prints_json_and_persists"
        status: pass
    human_judgment: false
  - id: D5
    description: "Skip-cycle test asserts runner engine semantics, not skip-only output"
    requirement: "PAPER-004"
    verification:
      - kind: integration
        ref: "tests/test_skip_cycle.py::test_runner_folds_fixture_events_into_one_fail_closed_verdict"
        status: pass
    human_judgment: false
duration: 60min
completed: 2026-10-21
status: complete
---

# Phase 04 Plan 02: Deterministic Replay Skeleton Summary

**Seeded FixtureClock runner with hash-chained replay ledger, recorded-LLM lookup by canonical request hash, hand-authored smoke-10m fixture, working verify verb, killswitch env fix, and canonical paper ledger path**

## Performance

- **Duration:** 60 min
- **Started:** 2026-10-21T18:00:00Z
- **Completed:** 2026-10-21T19:00:00Z
- **Tasks:** 3
- **Files modified:** 14

## Accomplishments

- One fixture event flows clock-to-ledger: runner advances FixtureClock per event ts, folds ticks into one engine verdict, appends one JournalNote (source=replay) via LedgerStore.append_batch, verifies CONSISTENT
- Two seeded runs over smoke-10m print identical events.hash d6ce3e73dee25a74485666cfffcbb94e69f24e5ee1cd2ef10e968c7000e0eb6a; a different seed differs
- Recorded LLM outcomes served by canonical request hash with virtual latency_s on the clock; a hash miss raises ReplayMissingRecord; datasets without llm.jsonl skip the step
- smoke-10m generator authors 41 ticks over ten minutes plus one recorded LLM ok outcome; manifest pins every listed file with sha256; re-running regenerates byte-identical files
- pumpgrok verify --fixture is a real verb: resolves bundled datasets, replays into var/replay/<dataset>/ledger.sqlite, prints events.hash, exits 0 on CONSISTENT
- PUMPGROK_KILLSWITCH=1 passes settings validation; the killswitch run exits 0
- Every wired CLI verb opens the canonical paper ledger var/ledger.sqlite via a ledger_path override; var/desk/ledger.sqlite is retired; replay keeps var/replay/<dataset>/ledger.sqlite
- tests/test_skip_cycle.py asserts runner engine semantics: fail-closed skip/data_unavailable, event count, virtual stamp equals last fixture ts, genesis prev_hash, CONSISTENT chain

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer: fixture event through FixtureClock into hash-chained ledger with verify** - `902bf07` (feat)
2. **Task 2: Recorder, canonical request hash, smoke-10m fixture** - `d8d879c` (feat)
3. **Task 3: Killswitch env fix, canonical ledger path, skip-cycle rewrite** - `8f57c1a` (fix)
4. **Contract test migration (verify exit-5 to real verb, canonical paths)** - `87f9f04` (test)

**Plan metadata:** pending (docs: complete plan commit below)

## Files Created/Modified

- `src/pumpgrok/replay/sources.py` - ordered FixtureEventSource view over a verified FixtureDataset
- `src/pumpgrok/replay/runner.py` - run_replay: manifest verify, 120 s gap gate, clock advance, engine fold, LLM lookup, append_batch, verify, events.hash
- `src/pumpgrok/replay/recorder.py` - canonical_request_hash, ReplayLlm lookup with virtual latency, load_llm_records
- `src/pumpgrok/replay/clock.py` - sanctioned yield_to_loop primitive for peer seat tasks
- `src/pumpgrok/core/errors.py` - ReplayMissingRecord (fail, never invent)
- `src/pumpgrok/config/settings.py` - PUMPGROK_KILLSWITCH in NON_SETTING_ENV_NAMES
- `src/pumpgrok/cli.py` - PAPER_LEDGER_PATH, verify verb handler, _skip_cycle delegates to run_replay
- `src/pumpgrok/tools/__init__.py` - ledger_path override on build_operator_registry
- `tests/replay/test_runner_determinism.py` - identical hashes, different seed differs, gap trips DataStale, miss raises ReplayMissingRecord
- `tests/fixtures/replay/smoke-10m/` - generator.py, events.jsonl, llm.jsonl, manifest.json
- `tests/test_skip_cycle.py` - engine-semantics assertions over the runner
- `tests/test_tools_cli.py` - verify promoted out of exit-5 tables, canonical ledger assertions

## Decisions Made

- Runner and sources stay out of `pumpgrok.replay.__init__`: the runner folds engine decisions and settings, which import back through `pumpgrok.core` while it is still initializing (ImportError on first collection). The package init keeps primitives only (clock, rng, fixtures); composition imports come from their modules.
- smoke-10m carries no silence hole so `verify` passes clean; the 180 s DataStale gate is proven by a synthetic two-event gapped dataset in the determinism test, keeping the committed fixture green.
- Datasets without llm.jsonl (legacy smoke) skip model resolution; datasets with it must contain the run's request hash. Non-ok recorded outcomes are recorded in the verdict note text; degradation paths land in later plans.
- Yield-to-loop lives in clock.py as `yield_to_loop` (asyncio.sleep(0) inside the one allowlisted module); the synchronous runner advances virtual latency directly via advance_to.
- Tool-call timeout/error outcomes from the recorder surface as LlmResult for the runner to record; only a missing record raises.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Package-init import cycle through replay.runner**
- **Found during:** Task 1 (tracer collection)
- **Issue:** Exporting run_replay from `pumpgrok.replay.__init__` cycled: settings -> core/__init__ -> ids -> replay.clock -> replay/__init__ -> runner -> settings (partially initialized ImportError)
- **Fix:** Runner and sources import from their modules; package init keeps clock/rng/fixtures primitives with a comment recording why
- **Files modified:** src/pumpgrok/replay/__init__.py, src/pumpgrok/cli.py, tests/replay/test_runner_determinism.py
- **Verification:** test collection passes; full suite exit 0
- **Committed in:** 902bf07 (Task 1 commit)

**2. [Rule 1 - Bug] Clock edit split async def sleep from its body**
- **Found during:** Task 2 (yield primitive)
- **Issue:** An insert anchored on the sleep def line left the def without its docstring/body, breaking the module
- **Fix:** Restored the `async def sleep` line with its docstring; clock tests pass
- **Files modified:** src/pumpgrok/replay/clock.py
- **Verification:** tests/replay/test_clock.py 10/10 pass
- **Committed in:** d8d879c (Task 2 commit)

**3. [Rule 3 - Blocking] verify exit-5 contract tests broke on the real verb**
- **Found during:** Closing gate (full suite)
- **Issue:** Two test_tools_cli.py tables asserted `verify --fixture smoke` exits 5 with a not-yet-implemented JSON envelope; the plan promotes verify to a real verb (exit 0, text output), so the suite failed
- **Fix:** Removed verify from both exit-5 tables; added test_verify_fixture_replays_and_prints_stable_hash (exit 0, CONSISTENT, byte-identical output across two runs). Updated three var/desk/ledger.sqlite assertions to the canonical var/ledger.sqlite
- **Files modified:** tests/test_tools_cli.py
- **Verification:** tests/test_tools_cli.py 67/67 pass; full suite exit 0
- **Committed in:** 87f9f04 (test commit)

---

**Total deviations:** 3 auto-fixed (2 correctness bugs, 1 blocking contract migration)
**Impact on plan:** All required by the plan's own behavior changes (real verify verb, canonical ledger path). No scope creep: killswitch file path unification and timeout/error degradation paths stay deferred.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: tampering-surface | src/pumpgrok/replay/recorder.py | New llm.jsonl fixture input crosses into the ledger note text; mitigated by manifest sha256 verification before any line is trusted (T-04-04 holds) |

No new network, auth, or schema-at-trust-boundary surface: the runner is file-to-sqlite only, the recorder never calls a model, and no new packages were added (T-04-SC holds).

## Issues Encountered

- The shared-shell pytest runner prints "No tests collected" on piped output; redirecting to a file shows real results (same as 04-01). Recorded here so future plans redirect first.
- Timestamp string formats differ between fixture millis (`.000Z`) and ledger micros (`.000000Z`); the skip-cycle assertion compares parsed epochs via parse_ts_utc instead of raw strings.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Replay skeleton ready: later plans replay against run_replay and assert on events.hash
- ROADMAP criterion 2 shape (`verify --fixture smoke-10m`) runs green with a stable hash
- ROADMAP criterion 3 unblocked: PUMPGROK_KILLSWITCH=1 no longer exits 1 from settings validation
- NotYetImplementedAdapter still refuses paper fills; PaperAdapter plus RiskEngine land in 04-03/04-05
- No blockers

## Self-Check: PASSED

- All 14 files exist on disk, verified via lint and test runs against the working tree
- All 4 task commits exist: 902bf07, d8d879c, 8f57c1a, 87f9f04
- Closing gate: pytest exit 0, ruff check exit 0, ruff format check exit 0, mypy exit 0 (132 files), verify twice exit 0 with identical events.hash

---
*Phase: 04-paper-trading-and-autonomy*
*Completed: 2026-10-21*
