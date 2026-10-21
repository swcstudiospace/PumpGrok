---
phase: 01-foundation
plan: 04
subsystem: ledger
tags: [sqlite, hash-chain, pydantic, r32, ledger]
dependency_graph:
  requires: [01-02, 01-03]
  provides: [ledger-store, ledger-events, hash-rule]
  affects: [01-07, 01-08]
tech-stack:
  added: []
  patterns: [begin-immediate-single-writer, hash-chain-over-canonical-json, strict-forbid-models]
key-files:
  created:
    - src/pumpgrok/ledger/store.py
    - src/pumpgrok/ledger/__init__.py
    - src/pumpgrok/ledger/events.py
    - tests/ledger/test_store.py
    - tests/ledger/test_events.py
  modified:
    - docs/design/paper-engine.md
decisions:
  - Freeze the ledger schema and hash rule with idempotency_key in the hash input (locked Q3); genesis prev_hash 64 zeros; replay ledgers recreated each run.
  - JournalNote.note_kind follows paper-engine.md 3.3 with no halt value (locked Q4); skip rows use seat desk, kind note.
metrics:
  duration: 2026-10-21
  completed: 2026-10-21
status: complete
actuals:
  tasks: 3
  commits: 6
---

# Phase 01 Plan 04: Hash-Chained Ledger and 18 Event Models Summary

Hash-chained SQLite ledger with in-transaction BEGIN IMMEDIATE appends and 18 strict R32 pydantic event models; the one-way-door hash rule (idempotency_key included) is frozen in paper-engine.md 3.2.

## One-liner

SQLite WAL ledger with chained, trigger-guarded appends plus 18 strict R32 event models and a snake_case schema export.

## Changes

- `docs/design/paper-engine.md` 3.2: hash input now `prev_hash, seq, ts_utc, source, correlation_id, idempotency_key, type, payload_json` (locked Q3).
- `src/pumpgrok/ledger/store.py`: `LedgerStore` (sqlite3 stdlib, `isolation_level=None`, `BEGIN IMMEDIATE` appends, hash computed inside the transaction over `canonical_json`, `ROLLBACK` on error), append-only `RAISE(ABORT)` triggers on UPDATE/DELETE, snapshots table plus `atomic_write`-based snapshot file path, `recreate_ledger_db` replay helper, `verify()` chain walk raising `LedgerInconsistent`.
- `src/pumpgrok/ledger/events.py`: `EventType` StrEnum, 18 CamelCase models (`extra=forbid`, `source: Literal[paper, replay, manual]`, int money / Decimal-string prices, float rejected), `NoteKind` without halt, snake mapping, `event_json_schemas()` / `model_json_schema()` export for plan 01-07.
- `src/pumpgrok/ledger/__init__.py`: re-exports.
- `tests/ledger/test_store.py`, `tests/ledger/test_events.py`: tracer and model suites.

## Decisions

- Checkpoint decision (gate="decision", non-blocking, taken by executor per contract): hash input includes `idempotency_key` per locked Q3; `note_kind` per paper-engine.md 3.3 with no halt per locked Q4 (ROSTER divergence noted in the module docstring); genesis `prev_hash` 64 zeros; replay ledgers recreated each run. Recorded here and committed.
- Per-field strictness over model-level `strict=True`: model-level strict rejected Decimal-from-string prices, so models are lax with `Field(strict=True)` int/bool fields and a float-rejecting `BeforeValidator` on Decimals.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Model-level strict rejected valid Decimal strings**
- **Found during:** Task: 18 event models, first `test_events.py` verify run
- **Issue:** `ConfigDict(strict=True)` made `price_avg="1.25"` fail validation (strict Decimal rejects str input)
- **Fix:** Lax model config with `extra="forbid"`; `MoneyInt`/`StrictBool` via `Field(strict=True)`, `PriceDecimal` via `BeforeValidator(_reject_float)`
- **Files modified:** src/pumpgrok/ledger/events.py
- **Commit:** ddc3b39

## Verification

- `uv run pytest -q tests/ledger/test_store.py`: PASS (4 passed), run once, green on first run.
- `uv run pytest -q tests/ledger/test_events.py`: first run FAILED (`test_money_int_and_decimal_string_price`, strict Decimal rejected `"0.5"`); after the Rule 1 fix above, re-run PASS (4 passed).
- `grep -n idempotency_key docs/design/paper-engine.md`: hash-rule line in section 3.2 present (line 313).

## Known Stubs

None.

## Self-Check: PASSED

- `src/pumpgrok/ledger/store.py`, `events.py`, `__init__.py`, `tests/ledger/test_store.py`, `tests/ledger/test_events.py` all FOUND on disk.
- Commits bf811e6, 55e3d25, 70a3371, 61cfb32, 4763ca0, ddc3b39 all FOUND in `git log`.
