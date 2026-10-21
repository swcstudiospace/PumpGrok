---
phase: 01-foundation
plan: 03
subsystem: core
tags: [pydantic-v2, ulid, crockford, registry, least-privilege, idempotency, risk-budget]
requires:
  - phase: 01-foundation
    provides: design contracts in docs/design/interfaces.md (module map, invariants I1-I5, R19/R20/R28/R29/R33)
provides:
  - 15 core modules (side_effect, errors, ids, idempotency, correlation, tool, datasource, adapter, skill, bot, registry, approvals, atomic_write, interfaces facade, package re-export)
  - ToolRegistry with audited LIVE_WRITE refusal (I3/I4) and ToolSpec R19 multi-dot names
  - IdFactory Crockford ULIDs (spec-vector verified) plus AST uuid ban (R29)
  - canonical_json float rejection with Decimal-as-str (R28)
  - RiskBudget nine keys with 0.05 daily-loss cap; ApprovalRecord R33 kinds
affects: [phase-2-tools, phase-4-paper, ledger-hash-chain, replay-determinism]

actuals:
  tokens: 15920
  tasks: 3
  commits: 6

tech-stack:
  added: [pydantic-v2-models]
  patterns: [frozen-pydantic-models, protocol-plus-impl, clock-injection, registry-least-privilege, loud-atomic-write]

key-files:
  created:
    - src/pumpgrok/core/side_effect.py
    - src/pumpgrok/core/errors.py
    - src/pumpgrok/core/ids.py
    - src/pumpgrok/core/idempotency.py
    - src/pumpgrok/core/correlation.py
    - src/pumpgrok/core/tool.py
    - src/pumpgrok/core/datasource.py
    - src/pumpgrok/core/adapter.py
    - src/pumpgrok/core/skill.py
    - src/pumpgrok/core/bot.py
    - src/pumpgrok/core/registry.py
    - src/pumpgrok/core/approvals.py
    - src/pumpgrok/core/atomic_write.py
    - src/pumpgrok/core/interfaces.py
    - src/pumpgrok/core/__init__.py
    - tests/core/test_registry.py
    - tests/core/test_models.py
    - tests/core/test_ids.py
  modified: []

key-decisions:
  - "Clock protocol defined in ids.py until replay/clock.py (plan 01-05) exists and becomes the definition site"
  - "IdFactory enforces ULID monotonicity (bump on equal/backwards clock) so FixtureClock replays are strictly increasing"
  - "DataBlind added alongside DataStale for the blind-flatten path (R25)"
  - "registry._wrap defers the adapter import to the approval branch to keep core import graph acyclic"
  - "ToolSpec/ToolGrant/BotManifest live in tool.py/bot.py (not registry.py); task-1 commit carried them because the tracer tests need both"

patterns-established:
  - "TDD RED (failing-test commit) precedes every GREEN implementation commit"
  - "No float money: int lamports/units, Decimal ratios/prices, canonical_json rejects float and stringifies Decimal"
  - "Every refusal audited before the exception propagates (I4)"

requirements-completed: [FOUND-005]

coverage:
  - id: D1
    description: "Deterministic Crockford ULIDs plus audited ToolRegistry LIVE_WRITE refusal"
    requirement: "FOUND-005"
    verification:
      - kind: unit
        ref: "tests/core/test_registry.py (5 tests: spec vector, refusal x2 callers, resolve, roster refusal, name pattern)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Core models: RiskBudget nine keys with 0.05 cap, canonical_json, ApprovalRecord R33 kinds, BotManifest"
    requirement: "FOUND-005"
    verification:
      - kind: unit
        ref: "tests/core/test_models.py (5 tests: budget cap, canonical_json, idempotency key, approvals, manifest)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Loud atomic_write plus ULID edge tests and static uuid ban"
    requirement: "FOUND-005"
    verification:
      - kind: unit
        ref: "tests/core/test_ids.py (5 tests: monotonicity, 80-bit width, round-trip, loud failure, uuid AST walk)"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-10-21
status: complete
---

# Phase 01 Plan 03: Core Contract Summary

**15-module core contract: Crockford ULID identity, audited least-privilege tool registry with unconditional LIVE_WRITE refusal, R20 RiskBudget, R33 approvals, float-rejecting canonical_json, and loud atomic writes — all green under TDD.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-10-21
- **Tasks:** 3 (tracer + 2 auto, all TDD with RED commits)
- **Files modified:** 18 created, 0 modified

## Accomplishments

- IdFactory emits spec-vector ULIDs (`1469918176385` -> prefix `01ARYZ6S41`) with a monotonicity guard; `uuid` is AST-banned under `src/pumpgrok` (R29).
- `ToolRegistry.find` raises `LiveGateError` for any LIVE_WRITE spec regardless of caller and audits every refusal as a `GrantAudit` row (I3/I4); invariants I1/I2/I5 enforced per the listing.
- `canonical_json` sorts keys with compact separators, rejects float leaves, stringifies Decimal (R28); `derive_idempotency_key` excludes `correlation_id` and returns 32 hex chars.
- `RiskBudget` carries the nine R20 keys with `daily_loss_halt_fraction` capped at 0.05 (INV-C-06); `ApprovalRecord` validates all seven R33 kinds; `ToolSpec` enforces the R19 multi-dot name pattern.
- `atomic_write_json` ports `StateStore.save` ordering exactly and re-raises OSError loudly.

## Task Commits

1. **Tracer RED** - `c0b4b84` (test: failing registry tests)
2. **Tracer GREEN** - `a065123` (feat: ids/errors/side_effect/tool/bot/registry/__init__)
3. **Task 2 RED** - `d06e358` (test: failing model tests)
4. **Task 2 GREEN** - `0de6062` (feat: interfaces/datasource/adapter/skill/approvals/idempotency/correlation, __init__ extended)
5. **Task 3 RED** - `7b4d37a` (test: failing ids/atomic-write tests)
6. **Task 3 GREEN** - `8c31bb0` (feat: atomic_write, __init__ export)

## Files Created/Modified

- `src/pumpgrok/core/{__init__,interfaces,side_effect,errors,correlation,idempotency,tool,datasource,adapter,skill,bot,registry,ids,approvals,atomic_write}.py` - full core contract per interfaces.md 2.1-2.5 and 923-.
- `tests/core/{test_registry,test_models,test_ids}.py` - 15 tests total, all passing.

## Decisions Made

- `Clock` protocol lives in `ids.py` for now; plan 01-05 (`replay/clock.py`) becomes the definition site and `ids.py` will re-export it. Documented in the module docstring.
- `IdFactory` bumps on equal/backwards clock values (standard ULID monotonicity) so fixed-clock replays stay strictly increasing and byte-reproducible.
- `DataBlind` error added next to `DataStale` for the R25 blind-flatten path; no other error classes invented.
- `registry._wrap` imports `OrderRequest` inside the approval branch only, keeping the core import graph acyclic (`registry -> adapter -> ids/errors`, no back edge).
- `Bot.cycle`/`heartbeat` use `Mapping[str, Any]` signatures exactly as the design listing (earlier draft used `dict[str, object]`; corrected before commit).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Sniper test seat failed manifest validation**
- **Found during:** Task 1 (tracer GREEN run)
- **Issue:** Test granted `bot-04-sniper` a PAPER_WRITE exec tool without `writes_to_exchange=True`, tripping the `_exec_writes_only_for_writers` validator.
- **Fix:** Test helper accepts `writes_to_exchange` and the sniper seat sets it `True`.
- **Files modified:** tests/core/test_registry.py
- **Verification:** `tests/core/test_registry.py` 5 passed.
- **Committed in:** a065123 (part of task commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test scaffolding, not plan scope)
**Impact on plan:** None - implementation matches the plan; only the test seat needed the manifest's own required flag.

## Issues Encountered

- `uv run pytest` worked without a project file (system-provided pydantic/pytest resolved); all three verify commands passed as written, so no workaround was needed.
- Two `edit`-tool range mistakes damaged `bot.py` and `__init__.py` mid-session (stale line ranges); both were re-read, repaired, and parse-verified before committing. No trace remains in the committed files.

## Verification (one run each, per contract)

- `uv run pytest -q tests/core/test_registry.py` -> **5 passed**
- `uv run pytest -q tests/core/test_models.py` -> **5 passed**
- `uv run pytest -q tests/core/test_ids.py` -> **5 passed**

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Core contract is importable via `pumpgrok.core` and via the `pumpgrok.core.interfaces` facade; downstream plans (ledger hash chain, replay determinism, tool catalog) can build on `IdFactory`, `canonical_json`, `ToolRegistry`, and `ApprovalRecord`.
- Watch item: when plan 01-05 creates `replay/clock.py`, move the `Clock` definition there and re-export from `ids.py` (noted in the module docstring).

---
*Phase: 01-foundation*
*Completed: 2026-10-21*
