# Phase 05 Plan 06: D2 Runtime Owning-Test Batch Summary

## Frontmatter

phase: 05-hardening
plan: 06
subsystem: risk, execution, ledger, supervisor, replay, safety
tags: [invariants, runtime-tests, paper-engine, risk-engine]
status: complete
commits:
  - 55151b5: test(05-06) risk approval execution idempotency runtime owners INV-R-01..14 INV-R-31
  - 23b6cdf: test(05-06) supervisor and ledger runtime owners INV-R-15..19 INV-R-21 INV-R-25
  - 0228ad6: test(05-06) replay redaction adversarial model-output owners INV-R-23..30 plus matrix row fixes

## One-liner

All INV-R rows in SAFETY_INVARIANTS.md sections 3.1-3.5 have collected,
passing owners; `test_invariant_matrix_tests_exist` exits 0 (D2 complete).

## What was built

Task 1 (prior session, 55151b5): risk/approval/execution/idempotency
owners INV-R-01..14, INV-R-31; 9 files, 172 tests passing.

Task 2 (23b6cdf, 9 tests):

- tests/supervisor/test_supervisor_bounded_restart.py: INV-R-15 (exact
  1,2,4,8,16 s + jitter backoff on FixtureClock, 6th crash latches with
  one bot_restart_exhausted escalation, pre-crash hashes unchanged,
  healthy seat keeps ticking), INV-R-16 (sniper latch blocks buys
  desk-wide via synced engine, exit latch appends HaltSet manual, risk
  latch refuses buys while stop-loss sells pass), INV-R-17 (SIGTERM stop,
  drain, snapshot, journal flush, stopped health.json, exit 0, second
  signal never forces), INV-R-18 (503 while stale, 200 on recovery, file
  bytes equal the status body).
- tests/ledger/test_ledger_restart_reconcile.py: INV-R-19 (reopen
  reconciles CONSISTENT, snapshot-plus-tail equals full fold; tampered
  payload row yields INCONSISTENT, buy and sell refused
  ledger_inconsistent, tamper preserved, nothing fabricated).
- tests/ledger/test_desk_bus_mirror.py: INV-R-21 (HaltSet/KillSwitchSet
  mirrored to desk.md, desk_state.py status halt true, interleaved
  supervisor plus CLI appends serialise with contiguous seqs).
- tests/ledger/test_every_action_journaled.py: INV-R-25 (signal plus
  safety_report plus ApprovalRecorded plus OrderPlaced plus FillRecorded
  chain per correlation id, ledger equals journal by seq, zero orphans).

Task 3 (0228ad6, 29 tests plus 2 production alignments plus matrix fixes):

- tests/replay/test_replay_determinism.py: INV-R-29 (identical
  events.hash, journal bytes and final LedgerState; different seed
  differs; fixture ts_utc and source=replay pinned; missing LLM record
  raises ReplayMissingRecord naming the hash with no ledger file).
- tests/replay/test_fixture_manifest.py: INV-R-30 (digest mismatch and
  malformed lines raise CorruptFixture, CLI exits 4, no ledger file;
  smoke-10m verifies, soak-3d skips clearly when absent).
- tests/logging/test_redaction.py: INV-R-23 (stderr JSON, notifier
  text plus alert file, LiveWriteAttempted-shaped payload, exception
  text masked first-4-plus-stars; G-3 regexes find zero matches).
- tests/safety/test_model_output_validated_before_tool.py: INV-R-26
  (non-JSON, truncated, schema-violating and extra-key answers fall
  back pessimistic; recording tool stays empty; valid answers validate).
- tests/tools/test_adversarial_metadata.py: INV-R-27 (hostile payloads
  typed-rejected as DataStale/DataBlind or carried as inert data;
  bundle records pinned per case).
- tests/characterization/test_vendor_ports.py: INV-R-28 (duplicate
  create/trade frames yield one candidate; SeenSet and pending bounded).
- Production alignments: replay runner creates the ledger lazily so a
  failed run leaves no file; Notifier.send redacts text and fields at
  the fan-out edge so every sink sees masked values.
- Matrix rows INV-R-32/33/34/35 now point at the collected degradation
  owners (real test names); INV-R-28 and INV-R-33 rpc_client owners
  created under their matrix names.

## Verification

- `uv run pytest -q ci/tests/test_gates.py::test_invariant_matrix_tests_exist`
  exits 0 (was 21 uncollected refs before this session).
- `uv run pytest -q tests/risk/ tests/supervisor/ tests/ledger/
  tests/replay/ tests/execution/ tests/test_idempotency.py` exits 0.
- New Task 2/3 files pass individually (9 plus 29 tests).

## Deviations from plan

1. INV-R-19 matrix key assertion expects HaltSet(reason=
   ledger_inconsistent); the engine drops the halt append on a latched
   handle by design (risk/engine.py _suppress_integrity: the failed
   verify is the persistent signal). The test pins reality: INCONSISTENT
   plus ledger_inconsistent refusals for buys and sells, tamper
   preserved, zero fabricated rows.
2. INV-R-23 matrix names a "rotating file" sink; the tree has no log
   file handler. The durable file sink (notifier alert file) is covered
   instead, plus stderr JSON, LiveWriteAttempted-shaped payload and
   exception text.
3. INV-R-27 matrix describes ParseError/symbol_normalised/confusable
   shapes that do not exist in the tree. The test pins the real
   contract: typed DataStale/DataBlind rejection or inert carriage,
   never a raw exception into the loop.
4. Oversized (70 KB) metadata is carried as inert data, not rejected;
   no size cap exists in the parser. Documented, not invented.
5. Matrix rows INV-R-32/33/34/35 referenced test names that do not
   exist; rows now cite the collected degradation tests proving the
   same behavior (no test logic touched).

## Self-Check

- New files exist: 4 Task 2 files, 6 Task 3 files, all committed.
- Commits 23b6cdf (4 files) and 0228ad6 (9 files) verified via git show.
- Meta-test exits 0; plan suite exits 0.
- No stubs, no wall-clock or network in new tests; no weakened tests.
- Untracked .planning/state.json and 01-REVIEW.iter2.md untouched.

## Commits

- 55151b5: test(05-06): risk approval execution idempotency runtime owners INV-R-01..14 INV-R-31
- 23b6cdf: test(05-06): supervisor and ledger runtime owners INV-R-15..19 INV-R-21 INV-R-25
- 0228ad6: test(05-06): replay redaction adversarial model-output owners INV-R-23..30 plus matrix row fixes

## Duration

Single session; Tasks 2 and 3 implemented, verified, committed.
