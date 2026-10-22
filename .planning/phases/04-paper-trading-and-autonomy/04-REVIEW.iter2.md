---
phase: 04-paper-trading-and-autonomy
reviewed: 2026-10-22T00:00:00Z
depth: standard
files_reviewed: 92
files_reviewed_list:
  - ci/tests/test_gates.py
  - src/pumpgrok/cli.py
  - src/pumpgrok/config/settings.py
  - src/pumpgrok/core/__init__.py
  - src/pumpgrok/core/adapter.py
  - src/pumpgrok/core/approvals.py
  - src/pumpgrok/core/errors.py
  - src/pumpgrok/engine/__init__.py
  - src/pumpgrok/engine/agents/__init__.py
  - src/pumpgrok/engine/agents/auditor.py
  - src/pumpgrok/engine/agents/base.py
  - src/pumpgrok/engine/agents/checker.py
  - src/pumpgrok/engine/agents/narrative.py
  - src/pumpgrok/engine/agents/timing.py
  - src/pumpgrok/engine/alerts.py
  - src/pumpgrok/engine/analyzer.py
  - src/pumpgrok/engine/exits.py
  - src/pumpgrok/engine/models.py
  - src/pumpgrok/engine/monitor.py
  - src/pumpgrok/engine/reputation.py
  - src/pumpgrok/engine/scoring.py
  - src/pumpgrok/engine/tune.py
  - src/pumpgrok/engine/watcher.py
  - src/pumpgrok/execution/__init__.py
  - src/pumpgrok/execution/curve_math.py
  - src/pumpgrok/execution/fees.py
  - src/pumpgrok/execution/latency.py
  - src/pumpgrok/execution/live/live_adapter.py
  - src/pumpgrok/execution/live/live_gate.py
  - src/pumpgrok/execution/not_yet_implemented.py
  - src/pumpgrok/execution/paper_adapter.py
  - src/pumpgrok/ledger/__init__.py
  - src/pumpgrok/ledger/autonomy.py
  - src/pumpgrok/ledger/desk_bus.py
  - src/pumpgrok/ledger/events.py
  - src/pumpgrok/ledger/export.py
  - src/pumpgrok/ledger/reconcile.py
  - src/pumpgrok/ledger/reducer.py
  - src/pumpgrok/ledger/store.py
  - src/pumpgrok/ledger/tickets.py
  - src/pumpgrok/ledger/views.py
  - src/pumpgrok/replay/__init__.py
  - src/pumpgrok/replay/clock.py
  - src/pumpgrok/replay/recorder.py
  - src/pumpgrok/replay/runner.py
  - src/pumpgrok/replay/sources.py
  - src/pumpgrok/reporting/__init__.py
  - src/pumpgrok/reporting/daily.py
  - src/pumpgrok/reporting/render.py
  - src/pumpgrok/reporting/weekly.py
  - src/pumpgrok/risk/__init__.py
  - src/pumpgrok/risk/breakers.py
  - src/pumpgrok/risk/engine.py
  - src/pumpgrok/risk/killswitch.py
  - src/pumpgrok/risk/limits.py
  - src/pumpgrok/risk/sizing.py
  - src/pumpgrok/tools/__init__.py
  - src/pumpgrok/tools/exec/cancel.py
  - src/pumpgrok/tools/exec/place.py
  - src/pumpgrok/tools/exec/positions.py
  - src/pumpgrok/tools/exec/quote.py
  - src/pumpgrok/tools/exec/simulate.py
  - src/pumpgrok/tools/onchain/curve_layout.py
  - src/pumpgrok/tools/risk/halt_status.py
  - src/pumpgrok/tools/risk/kill_switch.py
  - tests/characterization/test_vendor_alerts.py
  - tests/characterization/test_vendor_config.py
  - tests/characterization/test_vendor_log.py
  - tests/characterization/test_vendor_ops.py
  - tests/characterization/test_vendor_risk.py
  - tests/characterization/test_vendor_state.py
  - tests/execution/__init__.py
  - tests/execution/test_curve_math.py
  - tests/execution/test_graduation_blind.py
  - tests/execution/test_live_gate_fails_fast.py
  - tests/execution/test_paper_adapter.py
  - tests/fixtures/replay/smoke-10m/generator.py
  - tests/ledger/test_store_batch.py
  - tests/registry_harness.py
  - tests/replay/test_runner_determinism.py
  - tests/reporting/__init__.py
  - tests/reporting/test_reporting_render.py
  - tests/risk/test_breakers.py
  - tests/risk/test_engine.py
  - tests/risk/test_killswitch.py
  - tests/safety/test_reputation_degraded.py
  - tests/test_operator_budget_wiring.py
  - tests/test_skip_cycle.py
  - tests/test_tools_cli.py
  - tests/tools/exec/test_exec_family.py
  - tests/tools/test_approvals_tickets.py
  - tests/tools/test_verb_coverage.py
findings:
  critical: 0
  warning: 0
  info: 12
  total: 12
status: issues_found
---

# Phase 04: Code Review Report (iteration 2, fix-pass re-review)

**Reviewed:** 2026-10-22T00:00:00Z
**Depth:** standard
**Files Reviewed:** 92
**Status:** issues_found (info only; zero Critical, zero Warning)

## Summary

Re-reviewed the 91 iter-1 files plus `tests/test_operator_budget_wiring.py`
(new in fix commit 54d2a94) against the 10 fix commits (54d2a94..5f73511).
Method: read the full `git diff 54d2a94^..HEAD -- src/`, then re-read every
hunk site in current source to confirm each prior Critical/Warning is
actually fixed (not merely test-pinned), and hunted the fix hunks for
regressions (shared-mutable budget, cache-key side effects, TOCTOU on the
new pre-checks, import/removal breakage, transaction safety of the new
IntegrityError handler).

Result: all 4 prior Criticals and all 6 prior Warnings are FIXED in
source. The fixes are narrow, correctly scoped, and introduce no new
Critical or Warning. Three new minor Info items were found (all in fix
hunks). The 9 prior Info items are untouched by the fix diff and carry
over (line numbers re-pinned below).

No tests were run (out of scope for this review); test names cited are
the fixer's claims, not independent verification. No source files were
modified.

## Prior Criticals: verification

### CR-01 (fixed): Operator risk configuration is threaded through

**File:** `src/pumpgrok/tools/__init__.py:272-278`, `src/pumpgrok/execution/__init__.py:39-46`, `src/pumpgrok/config/settings.py:268`, `src/pumpgrok/cli.py:708-711`
**Verified:** `build_operator_registry` now uses `budget = settings.risk`
and `limits=settings.limits` (no more `RiskBudget()` / `EngineLimits()`
fresh defaults), plus a startup `log.info` echoing the effective budget
and limits. `build_adapter` resolves `budget`/`limits` from `settings`
with `getattr` fallback to defaults for attribute-less stubs. `Settings`
gains `limits: EngineLimits = Field(default_factory=EngineLimits)`.
`_halt_clear` takes `settings` and builds its gate engine with
`settings.risk` / `settings.limits`. `cli.py` no longer imports
`RiskBudget`/`EngineLimits` and has no remaining uses (grep clean).
Shared-object risk checked: `budget` is only read (`lambda: budget`
closures, `self._budget.<field>` reads in engine/adapter) -- no
`self._budget.<field> =` writes exist in engine or adapter, so sharing
one object across engine/adapter/tools is safe.
**Status:** fixed, no regression.

### CR-02 (fixed): Repeated risk refusal replays the stored refusal

**File:** `src/pumpgrok/execution/paper_adapter.py:82-106`, `:1037-1059`
**Verified:** `_reject` now wraps `store.append` in
`try/except sqlite3.IntegrityError`; on duplicate key it loads the stored
row via `by_key(key)` (which JSON-decodes `payload`, store.py:415-441)
and returns `_rejection_from_row(stored, fallback=err)`, mapping
`confirmation_timeout` rows to `OrderUnknownError` and all else to
`OrderRejectedError`, with `int(fees)` guarded by try/except. Store
safety confirmed: `append` rolls back on any exception (store.py
`except Exception: ROLLBACK`), so the handle is usable for the follow-up
`by_key`. The `stored is None` branch re-raises, which is correct (no
delete path exists, so None means a deeper fault, not a dup).
**Status:** fixed, no regression.

### CR-03 (fixed): Halt clear is per-approval and atomic

**File:** `src/pumpgrok/risk/engine.py:960-1020`, `src/pumpgrok/cli.py:700-723`
**Verified:** `request_halt_clear` pre-checks
`by_key(f"consumed|{approval.id}")` (reuse raises `ValueError`), keys the
clear row `f"halt-clear|{approval.id}"` (engine.py:989), and writes both
rows in one `append_batch` (atomic; duplicate key refuses the whole
batch per store.py). CLI `_halt_clear(by, reason, settings)` catches
`(ValueError, sqlite3.IntegrityError, LedgerInconsistent)` and returns
`halt_clear_refused`; sole caller updated (`:774`). Required imports
(`sqlite3`, `LedgerInconsistent`) are present in cli.py (`:39`, `:66`).
**Status:** fixed. Residual concurrent-duplicate race noted as IN-12
(single-process scoped, CLI-mapped).

### CR-04 (fixed): Kill-switch clear is atomic with explicit refusal

**File:** `src/pumpgrok/risk/killswitch.py:220-275`, `src/pumpgrok/cli.py:808`
**Verified:** `_SuppressIntegrity` no longer wraps the clear path. Both
rows are pre-checked by key (`duplicate clear key` and `already consumed`
raise `ClearRefused`) and written in one `append_batch([cleared,
consumed])` (`:275`). The old false-success shape (suppressed clear
append + landed consumed row + returned `cleared`) is gone. CLI catches
`(ClearRefused, ValueError, sqlite3.IntegrityError, LedgerInconsistent)`.
**Status:** fixed. Same residual-race note as CR-03 applies (IN-12).

## Prior Warnings: verification

### WR-01 (fixed): Decision cache is generation-keyed and bounded

**File:** `src/pumpgrok/risk/engine.py:195`, `:548-595`
**Verified:** `_cache_key` composes
`stage|order_hash|approval_id|store.count()|kill(active,source,reason)|open|half-open`
sets; any ledger append, kill flip, or breaker membership change misses
the cache. `_cache_key` calls `KillSwitch.poll()`, which is read-only
(`observe()` is the writer; poll has no append path), so key computation
has no ledger side effects. `is_open`'s lazy cooldown transition
(IN-07) makes time-based open-to-half-open expiry visible in the key
(`open_breakers()` is read inside `_cache_key`), so no cache livelock:
the first check after cooldown computes a different key and re-evaluates.
Eviction (`:563-564`) pops oldest-inserted past 1024; one insert per
check, so bounded. Coupling with IN-07 noted as IN-11.
**Status:** fixed, no regression.

### WR-02 (fixed): Kill-switch env truthiness is shared

**File:** `src/pumpgrok/risk/killswitch.py:105-117`, `:144`, `:199`, `src/pumpgrok/tools/risk/halt_status.py:100`, `src/pumpgrok/tools/risk/kill_switch.py:122`
**Verified:** `env_engaged` (non-empty other than `"0"`/`"false"`) is used
by `poll`, `live_sources`, `run_halt_status`, and `_status` alike.
Semantics identical to the old inline checks, so no behavior change
beyond unifying the views.
**Status:** fixed, no regression.

### WR-03 (fixed): CLI approval ids draw OS entropy

**File:** `src/pumpgrok/cli.py:557-565`
**Verified:** `_mint_approval_id` seeds `make_rng` with
`int.from_bytes(os.urandom(16), "big")`; `os` is imported (`:37`),
`make_rng(seed: int)` accepts it (rng.py:15), and `random.Random`
accepts 128-bit seeds. Replay paths still use the seeded stream.
**Status:** fixed, no regression.

### WR-04 (fixed): Non-finite SOL sizes rejected as ValueError

**File:** `src/pumpgrok/core/approvals.py:145-146`
**Verified:** `if not size.is_finite(): raise ValueError(...)` precedes
the sign check, covering Infinity, -Infinity, and NaN (NaN also fails
`<= 0` but previously escaped via `int()` path only by accident; now
explicit). `size` is always `Decimal` here, so `is_finite` exists.
**Status:** fixed, no regression.

### WR-05 (fixed): Halt status verifies the chain first

**File:** `src/pumpgrok/tools/risk/halt_status.py:80-99`
**Verified:** `run_halt_status` calls `store.verify()` first and returns
`halted: True, reasons: ["ledger_inconsistent"]` on `LedgerInconsistent`.
Poisoning analysis: `verify()` latches `_inconsistent` on the shared
handle, but `_step_ledger_inconsistent` (engine.py:699-715) verifies on
every check anyway, so the engine poisons itself identically; the view
only surfaces it earlier. No new failure mode. Minor view inaccuracy in
the inconsistent branch noted as IN-10.
**Status:** fixed, no regression.

### WR-06 (fixed): Fraction caps use Decimal math

**File:** `src/pumpgrok/risk/engine.py:846`, `:859`
**Verified:** both caps are `int(fraction * ctx.equity)` with no `float()`
round-trip (`Decimal * int` is exact; `int()` truncates toward zero for
the positive domain, same direction as before).
**Status:** fixed, no regression.

## Info

### IN-01: Bare `except Exception` in MTM peak update keeps a stale peak silently (carried over)

**File:** `src/pumpgrok/ledger/reducer.py:289`
**Issue:** Unchanged by the fix diff; still swallows Decimal/shape errors
from ledger `MarkToMarket` rows with no log, counter, or
`unknown_events` entry. Fail-safe direction, still invisible.
**Fix:** narrow to `(InvalidOperation, ValueError, TypeError, KeyError)`
and count the event.

### IN-02: `position_size_lamports` uses banker's rounding, unlike the HALF_UP boundary (carried over)

**File:** `src/pumpgrok/risk/sizing.py:77` (`round(min(by_score, by_budget))`)
**Issue:** Unchanged; float round-half-even vs the Decimal ROUND_HALF_UP
used at the phrase/config boundaries. One-lamport disagreements at exact
halves.
**Fix:** compute in Decimal and quantize with ROUND_HALF_UP.

### IN-03: Duplicate `model_config` assignment in CreatorRecord (carried over)

**File:** `src/pumpgrok/engine/reputation.py:55`, `:70`
**Issue:** `model_config = ConfigDict(extra="forbid")` assigned twice;
identical, so no behavior change.
**Fix:** delete one.

### IN-04: Stale Phase-3 docstrings on the refusing adapter (carried over)

**File:** `src/pumpgrok/execution/not_yet_implemented.py:1`, `:30`
**Issue:** Still says "Phase 3 execution backend" although Phase 4 wired
PaperAdapter; behavior (refuse, never fake) is correct.
**Fix:** update to "retired Phase 3 backend; Phase 4 wires PaperAdapter".

### IN-05: `assert` used for load-bearing invariants in risk steps (carried over)

**File:** `src/pumpgrok/risk/engine.py:845`, `:856`, `:909`, `:917` (lines shifted by fix insertions; same asserts)
**Issue:** `assert ctx.final_size is not None` guards live trading logic;
vanishes under `python -O`.
**Fix:** replace with explicit `if ...: raise _Fail(...)`.

### IN-06: `KILL FLATTEN` with no reason records reason `"FLATTEN"` (carried over)

**File:** `src/pumpgrok/risk/killswitch.py:42`, `:69` (`parse_kill_line`)
**Issue:** Unchanged; bare `KILL FLATTEN` stores the literal word as the
operator reason. Gating unaffected, audit noisy.
**Fix:** special-case the bare form to require/flag a reason.

### IN-07: `Breaker.is_open` mutates state inside a property getter (carried over)

**File:** `src/pumpgrok/risk/breakers.py:106-113`
**Issue:** Unchanged; cooldown-expiry transition runs on read. Now also
load-bearing for WR-01 (see IN-11).
**Fix:** split into mutating `poll(now)` plus pure snapshot; see IN-11
before touching.

### IN-08: Unhandled arithmetic on degenerate zero-size fills (carried over)

**File:** `src/pumpgrok/execution/paper_adapter.py:547`, `:607`, `:750`
**Issue:** Unchanged; `Decimal(x) / Decimal(y)` with `y == 0` raises
`decimal.DivisionByZero` outside any `OrderRejectedError` mapping, after
OrderPlaced is written.
**Fix:** validate divisors and route to `_reject`; discard the inflight
key in a `finally`.

### IN-09: `exit_rule` approval kind has no minter in scope (carried over)

**File:** `src/pumpgrok/core/approvals.py:49`, `:70`, `:81`, `:99-101`
**Issue:** Unchanged; `exit_rule` is admitted and validated but nothing in
scope mints it.
**Fix:** add the rule-engine minter or document as reserved (Phase-5 seam).

### IN-10 (new): Inconsistent-ledger view hard-codes `kill_switch_active: False`

**File:** `src/pumpgrok/tools/risk/halt_status.py:83-99`
**Issue:** The WR-05 fix's early return reports `halted: True` with
`kill_switch_active: False` without consulting env/file sources, so on a
tampered ledger with `PUMPGROK_KILLSWITCH` set (or the KILLSWITCH file
present) the incident view understates the kill-switch cause. Fail-safe
(`halted` dominates and gates the same refusals), but the exact screen
an operator reads during an incident can show `kill_switch_active:
false` while the switch is engaged.
**Fix:** compute `env_set`/`file_set` before the verify branch (cheap,
no ledger read) and include them in the inconsistent return.

### IN-11 (new): Decision-cache correctness now depends on IN-07's mutating read

**File:** `src/pumpgrok/risk/engine.py:585-593`, `src/pumpgrok/risk/breakers.py:106-113`
**Issue:** `_cache_key` observes breaker cooldown expiry only because
`open_breakers()` triggers `is_open`'s lazy open-to-half-open transition
as a read side effect. A future cleanup of IN-07 into a pure getter
(without an explicit poll in the key path) would silently reintroduce
WR-01 staleness for time-based breaker transitions, with no test to catch
the coupling.
**Fix:** when splitting IN-07, keep an explicit mutating poll call inside
`_cache_key` (or compare `remaining_cooldown()`/clock in the key), and
pin a test where a cached PASS expires across a breaker cooldown with no
ledger append.

### IN-12 (new): Concurrent same-approval clear still escapes as raw IntegrityError (residual, single-process scoped)

**File:** `src/pumpgrok/risk/engine.py:980-1020`, `src/pumpgrok/risk/killswitch.py:268-275`
**Issue:** The consumed/clear pre-checks (`by_key`) plus `append_batch`
close the sequential-reuse hole (verified: second sequential reuse hits
the pre-check and raises `ValueError`/`ClearRefused`), but two processes
racing the same approval id past the pre-check still collide in
`append_batch` with a raw `sqlite3.IntegrityError` at the engine API
layer. The only production callers are the CLI paths, which catch it and
return `<verb>_refused`, so no operator-visible regression; direct API
concurrency would see the raw error instead of a refusal type.
**Fix:** optionally catch `sqlite3.IntegrityError` inside
`request_halt_clear`/`request_clear` and re-raise as
`ValueError`/`ClearRefused` so the API contract holds under
multi-process use.

---

_Positive notes (re-verified, no finding):_ `poll()` is read-only so
`_cache_key` has no ledger side effects; `append`/`append_batch` roll
back on error (store.py) making the CR-02 `by_key` fallback and the
CR-03/CR-04 batches safe; `by_key` JSON-decodes payload so
`_rejection_from_row` operates on dicts; `OrderUnknownError` import
present for the confirmation_timeout mapping; shared `budget` object is
read-only across engine/adapter/tools; `build_adapter` getattr fallback
keeps attribute-less stub settings working; `env_engaged` preserves the
prior fail-closed truth table exactly.

_Reviewed: 2026-10-22T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard (iter2 re-review of fix commits 54d2a94..5f73511)_
