---
phase: 04-paper-trading-and-autonomy
plan: 01
subsystem: ledger
tags: [sqlite, hash-chain, ledger, paper-trading, jsonl, tickets]
requires:
  - phase: 03-tools-and-skills
    provides: ledger store skeleton with append, verify, snapshots, and event models
provides:
  - Atomic LedgerStore.append_batch transaction primitive for risk, execution, and tickets
  - Pure reducer fold, positions and equity views, and snapshot-plus-tail restart reconcile
  - JSONL and vendor-shape trades export resumed from meta.export_seq
  - Atomic desk.md mirrors and SOL-YYYYMMDD-NNN ticket allocation
affects: [04-02, 04-03, 04-04, 04-05, 04-06, 04-07]
actuals:
  tokens: 17800
  tasks: 3
  commits: 3
tech-stack:
  added: []
  patterns: [single-write-lock transactions, pure reduce-state-fold, derived-export cursors]
key-files:
  created:
    - src/pumpgrok/ledger/reducer.py
    - src/pumpgrok/ledger/views.py
    - src/pumpgrok/ledger/reconcile.py
    - src/pumpgrok/ledger/export.py
    - src/pumpgrok/ledger/desk_bus.py
    - src/pumpgrok/ledger/tickets.py
    - tests/ledger/test_store_batch.py
  modified:
    - src/pumpgrok/ledger/store.py
    - src/pumpgrok/ledger/__init__.py
key-decisions:
  - "append_batch holds one threading lock for the repeat-check plus all rows; cross-handle contention still resolves in sqlite BEGIN IMMEDIATE with busy_timeout 5000"
  - "verify latches an in-handle INCONSISTENT flag so a tamper refuses further appends; reconcile reports, RiskEngine halts in plan 04-05"
  - "Snapshot meta carries chain_hash for the 6e check; the 6d full-replay comparison ignores meta"
  - "One export_seq cursor serves both journal and trades exports in a single export_ledger pass"
  - "Tickets allocate optimistically through append_batch with recount on UNIQUE conflict instead of adding a second transaction path"
requirements-completed: [PAPER-002, PAPER-003]
coverage:
  - id: D1
    description: "Atomic append_batch batch primitive with rollback on any error"
    requirement: "PAPER-002"
    verification:
      - kind: unit
        ref: "tests/ledger/test_store_batch.py::test_batch_approval_consume_plus_order_commits_atomically"
        status: pass
      - kind: unit
        ref: "tests/ledger/test_store_batch.py::test_concurrent_writers_never_interleave_rows"
        status: pass
    human_judgment: false
  - id: D2
    description: "Pure reducer fold with positions and equity views"
    requirement: "PAPER-002"
    verification:
      - kind: unit
        ref: "tests/ledger/test_store_batch.py::test_reducer_views_fold_over_paper_fill"
        status: pass
    human_judgment: false
  - id: D3
    description: "Restart reconcile replays snapshot-plus-tail and reports CONSISTENT or INCONSISTENT"
    requirement: "PAPER-002"
    verification:
      - kind: unit
        ref: "tests/ledger/test_store_batch.py::test_restart_replays_snapshot_plus_tail"
        status: pass
      - kind: unit
        ref: "tests/ledger/test_store_batch.py::test_tamper_verifies_inconsistent_and_refuses_appends"
        status: pass
    human_judgment: false
  - id: D4
    description: "JSONL and vendor-shape trades export resumed from meta.export_seq"
    requirement: "PAPER-003"
    verification:
      - kind: unit
        ref: "tests/ledger/test_store_batch.py::test_export_resumes_without_duplicate_rows"
        status: pass
    human_judgment: false
  - id: D5
    description: "Atomic desk.md halt and kill-switch mirrors"
    requirement: "PAPER-003"
    verification:
      - kind: unit
        ref: "tests/ledger/test_store_batch.py::test_desk_mirrors_swap_atomically"
        status: pass
    human_judgment: false
  - id: D6
    description: "SOL-YYYYMMDD-NNN ticket allocation with per-day sequencing"
    requirement: "PAPER-003"
    verification:
      - kind: unit
        ref: "tests/ledger/test_store_batch.py::test_tickets_allocate_per_day_sequences"
        status: pass
    human_judgment: false
duration: 35min
completed: 2026-10-21
status: complete
---

# Phase 04 Plan 01: Ledger of Record Summary

**Hash-chained WAL ledger with atomic batch appends, pure reducer fold, restart reconcile, resumed JSONL export, atomic desk mirrors, and per-day ticket allocation**

## Performance

- **Duration:** 35 min
- **Started:** 2026-10-21T17:15:00Z
- **Completed:** 2026-10-21T17:50:15Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- LedgerStore.append_batch commits approval consumption plus order rows in one transaction; any error rolls back with no partial rows
- Concurrent writers serialize with contiguous seqs and a chain that verifies CONSISTENT
- A tampered payload verifies INCONSISTENT and the handle refuses further appends
- Restart reconcile replays snapshot-plus-tail through the reducer fold with cash, snapshot, source, and position integrity checks
- JSONL and vendor trades.jsonl exports resume from meta.export_seq; buy lines carry tx_hash dry_run; reruns write nothing
- Desk halt and kill-switch mirrors swap atomically via tmp plus fsync plus os.replace
- Tickets allocate SOL-YYYYMMDD-NNN with NNN at one plus the day count

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer: one JournalNote through append_batch into views and export with verify** - `0839e22` (feat)
2. **Task 2: Batch edge cases, read-by-idempotency-key, reducer, views, reconcile** - `bcc9e1a` (feat)
3. **Task 3: Export, desk mirrors, ticket allocation** - `8c4e004` (feat)

**Plan metadata:** pending (docs: complete plan commit below)

## Files Created/Modified

- `src/pumpgrok/ledger/store.py` - append_batch, write lock, inconsistency latch, meta get/set, read-by-key (existing by_key kept)
- `src/pumpgrok/ledger/reducer.py` - pure LedgerState fold over the 18 event types
- `src/pumpgrok/ledger/views.py` - cash, positions, unrealized, equity, drawdown, pnl, fees, equity curve, win rate, profit factor
- `src/pumpgrok/ledger/reconcile.py` - snapshot-plus-tail replay, chain verify, 6a-6f integrity checks, HaltSet row shape for RiskEngine
- `src/pumpgrok/ledger/export.py` - canonical journal plus vendor trades.jsonl under one export_seq cursor
- `src/pumpgrok/ledger/desk_bus.py` - atomic desk.md halt, halt-clear, and kill-switch mirrors
- `src/pumpgrok/ledger/tickets.py` - SOL-YYYYMMDD-NNN allocation over JournalNote rows
- `src/pumpgrok/ledger/__init__.py` - package exports for all new modules
- `tests/ledger/test_store_batch.py` - 13 batch, fold, reconcile, export, mirror, and ticket tests

## Decisions Made

- append_batch holds one threading lock for the repeat-check plus all rows; cross-handle contention still resolves in sqlite BEGIN IMMEDIATE with busy_timeout 5000
- verify latches an in-handle INCONSISTENT flag so a tamper refuses further appends; reconcile reports, RiskEngine halts in plan 04-05
- Snapshot meta carries chain_hash for the 6e check; the 6d full-replay comparison ignores meta
- One export_seq cursor serves both journal and trades exports in a single export_ledger pass
- Tickets allocate optimistically through append_batch with recount on UNIQUE conflict instead of adding a second transaction path

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Snapshot 6d comparison excluded writer meta**
- **Found during:** Task 2 (restart reconcile)
- **Issue:** Tail replay state carries snapshot meta chain_hash while the genesis full replay does not, so field-for-field comparison always failed on ledgers with a snapshot
- **Fix:** 6d compares state dumps with meta excluded; the chain_hash itself is still checked by 6e
- **Files modified:** src/pumpgrok/ledger/reconcile.py
- **Verification:** test_restart_replays_snapshot_plus_tail passes
- **Committed in:** bcc9e1a (Task 2 commit)

**2. [Rule 1 - Bug] export_journal consumed the shared cursor before export_trades**
- **Found during:** Task 3 (export)
- **Issue:** First draft had each exporter read past meta.export_seq and advance it, so the second exporter always saw zero rows
- **Fix:** export_ledger reads once past the cursor and writes both targets, then advances the cursor
- **Files modified:** src/pumpgrok/ledger/export.py
- **Verification:** test_export_resumes_without_duplicate_rows passes with trade_lines 3
- **Committed in:** 8c4e004 (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (2 correctness bugs)
**Impact on plan:** Both fixes required for the acceptance criteria (snapshot restart, shared export cursor). No scope creep.

## Issues Encountered

- The bash tool renders live piped pytest output as "No tests collected"; redirecting to a file shows the real results (13/13 pass, full suite 924 pass). Recorded here so future plans redirect first.
- Two edit-tool patch operations consumed adjacent def lines during store.py surgery; restored immediately with re-reads. No residue: ruff, format, and mypy are green.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ledger of record complete: plan 04-02 (PaperAdapter) can place orders through append_batch
- HaltSet ledger_inconsistent row shape defined in reconcile.ledger_inconsistent_halt for RiskEngine in plan 04-05
- Replay sources (plan 04-03) and reporting (plan 04-06) can fold and read views from this base
- No blockers

## Self-Check: PASSED

- All 9 files exist on disk, verified via test and lint runs against the working tree
- All 3 task commits exist: 0839e22, bcc9e1a, 8c4e004
- Full gate: pytest 924 passed exit 0, ruff check exit 0, ruff format check exit 0, mypy 129 files exit 0

---
*Phase: 04-paper-trading-and-autonomy*
*Completed: 2026-10-21*
