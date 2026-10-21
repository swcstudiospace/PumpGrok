---
phase: 01-foundation
reviewed: 2026-10-21T03:21:27Z
depth: deep
files_reviewed: 33
files_reviewed_list:
  - .env.example
  - docs/design/paper-engine.md
  - src/pumpgrok/config/overlays/dev.toml
  - src/pumpgrok/config/overlays/live.toml
  - src/pumpgrok/config/overlays/paper.toml
  - src/pumpgrok/config/settings.py
  - src/pumpgrok/core/__init__.py
  - src/pumpgrok/core/adapter.py
  - src/pumpgrok/core/approvals.py
  - src/pumpgrok/core/atomic_write.py
  - src/pumpgrok/core/bot.py
  - src/pumpgrok/core/correlation.py
  - src/pumpgrok/core/datasource.py
  - src/pumpgrok/core/errors.py
  - src/pumpgrok/core/idempotency.py
  - src/pumpgrok/core/ids.py
  - src/pumpgrok/core/interfaces.py
  - src/pumpgrok/core/registry.py
  - src/pumpgrok/core/risk_budget.py
  - src/pumpgrok/core/side_effect.py
  - src/pumpgrok/core/skill.py
  - src/pumpgrok/core/tool.py
  - src/pumpgrok/ledger/__init__.py
  - src/pumpgrok/ledger/events.py
  - src/pumpgrok/ledger/store.py
  - tests/config/test_forbidden_keys.py
  - tests/config/test_secret_refusal.py
  - tests/config/test_settings.py
  - tests/core/test_ids.py
  - tests/core/test_models.py
  - tests/core/test_registry.py
  - tests/ledger/test_events.py
  - tests/ledger/test_store.py
findings:
  critical: 0
  warning: 0
  info: 14
  total: 14
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-10-21T03:21:27Z
**Depth:** deep
**Files Reviewed:** 33
**Status:** issues_found
**Iteration:** 2 (re-review after fixes for CR-01 and WR-01 to WR-09)

## Summary

Iteration 2 re-reviewed the fix commits `3b4e1ea..a7a76eb` inline (diff inspection and a parse
check of every changed module; the test suite was not run in this pass). All Critical and Warning
findings from iteration 1 are resolved. No new Critical or Warning findings were introduced.
Fourteen Info findings remain open. They are outside the default `critical_warning` fix scope
and were not addressed.

## Resolved in this pass

| Finding | Severity | Commit | Resolution |
|---------|----------|--------|------------|
| CR-01 | Critical | 3b4e1ea | `.env.example` trimmed to keys `Settings` declares; drift test added. |
| WR-01 | Warning | 8101b38 | Single `RiskBudget` in `core/risk_budget.py`, imported by settings and bot. |
| WR-02 | Warning | 6d054e0 | `mask()` returns length only. |
| WR-03 | Warning | 57994bf | `atomic_write_json` removes its temp file on any failure. |
| WR-04 | Warning | e55ec46 | Snapshots are append-only (triggers, plain INSERT). |
| WR-05 | Warning | 5c0afd0 | `LedgerStore.append` validates type and payload against `EVENT_MODELS`. |
| WR-06 | Warning | 0b51828 | Unwired retry refused at spec construction; docs no longer claim retry, rate limit or alerts. |
| WR-07 | Warning | 3e90d15 | Span numbering restarts per root; nested child spans stay unique. |
| WR-08 | Warning | 3df5aae | Sell approvals bind `token_units`; `matches()` checks kind and side. |
| WR-09 | Warning | a7a76eb | `load_settings()` refuses effective mode `live` until the live gate exists. |

## Critical Issues

None open.

## Warnings

None open.

## Info

Open, not in the default fix scope. Unchanged from iteration 1.

### IN-01: Unreachable float branch in `_normalize`
**File:** `src/pumpgrok/core/idempotency.py:18-20`
**Fix:** Delete the two dead lines.

### IN-02: Duplicated correlation helpers and inconsistent validation
**File:** `src/pumpgrok/core/correlation.py:12-27`, `src/pumpgrok/core/ids.py:83-88`
**Fix:** Have `correlation.py` delegate to `CorrelationId`, and validate `n` in `child()`.

### IN-03: `derive_idempotency_key` docstring overstates the exclusion
**File:** `src/pumpgrok/core/idempotency.py:49-65`
**Fix:** Say "top-level `correlation_id`", or filter recursively.

### IN-04: No directory fsync after `os.replace`
**File:** `src/pumpgrok/core/atomic_write.py:23-27`
**Fix:** fsync the parent directory after `os.replace`.

### IN-05: Duplicate pragmas and duplicate source enumeration
**File:** `src/pumpgrok/ledger/store.py` (pragmas in `__init__` and `_SCHEMA`), `src/pumpgrok/ledger/events.py:31`
**Fix:** Keep the pragmas in one place; derive `SOURCES` from `EventSource`.

### IN-06: Naming rule and money conventions are inconsistent in event models
**File:** `src/pumpgrok/ledger/events.py`
**Fix:** Add `Seconds`, `Bps` and `Score` aliases, or document the exceptions.

### IN-07: Hash chain is unkeyed; tail truncation is not detected
**File:** `src/pumpgrok/ledger/store.py`
**Fix:** Record the limit in the design doc; plan an external head anchor if tamper evidence is required.

### IN-08: Misplaced protocol comment and stale docstring in adapter
**File:** `src/pumpgrok/core/adapter.py:158,163-164`
**Fix:** Move the `cancel` comment; correct the `LiveAdapterStub` docstring.

### IN-09: Star re-export shim
**File:** `src/pumpgrok/core/interfaces.py:1-6`
**Fix:** Delete the file if nothing imports it; update the design-doc reference.

### IN-10: Test hygiene
**File:** `tests/core/test_models.py`, `tests/core/test_registry.py` (`_call` unused), `tests/ledger/test_store.py`, `tests/config/test_forbidden_keys.py`, `tests/config/test_settings.py`
**Fix:** Narrow `pytest.raises(Exception)`; delete `_call`; use a declared field in the URL test; assert on parsed TOML.

### IN-11: Template and overlay comments
**File:** `.env.example`, `src/pumpgrok/config/overlays/dev.toml:3-4`
**Fix:** Use full-line comments in `.env.example`; reword the `dev.toml` note.

### IN-12: Skill manifest validation is weaker than the bot manifest
**File:** `src/pumpgrok/core/skill.py:37-52`
**Fix:** Reuse the bot id pattern for `bots`; default `network` to `False`.

### IN-13: Forbidden-name scan covers the whole host environment
**File:** `src/pumpgrok/config/settings.py` (`refuse_forbidden_env`)
**Fix:** Document the behaviour; no code change required.

### IN-14: Design document drift from the code
**File:** `docs/design/paper-engine.md`
**Fix:** Update references when the owning modules land; record deferred keys.

---

_Reviewed: 2026-10-21T03:21:27Z_
_Reviewer: Claude (gsd-code-reviewer, inline re-review)_
_Depth: deep_
