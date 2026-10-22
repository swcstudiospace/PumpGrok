---
phase: 04-paper-trading-and-autonomy
reviewed: 2026-10-22T00:00:00Z
depth: standard
files_reviewed: 91
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
  - tests/test_skip_cycle.py
  - tests/test_tools_cli.py
  - tests/tools/exec/test_exec_family.py
  - tests/tools/test_approvals_tickets.py
  - tests/tools/test_verb_coverage.py
findings:
  critical: 4
  warning: 6
  info: 9
  total: 19
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-10-22T00:00:00Z
**Depth:** standard
**Files Reviewed:** 91
**Status:** issues_found

## Summary

Reviewed all 91 Phase 4 files at standard depth, with extra attention to
live-mode refusal, kill switch / halt authority, approval single-send,
integer money math, ledger hash-chain invariants, replay determinism, and
exception paths that could swallow halts.

The core design is sound: the live gate fails closed (preconditions 5-9
unmet by design), LiveAdapterStub refuses every write, canonical_json
rejects float leaves, the OrderPlaced+consumption row share one
append_batch transaction, and replay runs on FixtureClock plus a seeded
rng. No hardcoded secrets, no signing code outside the HMAC confirm path,
no wall clock in replay paths.

Four Critical findings block ship: operator risk configuration is silently
ignored (CR-01), retrying a risk-refused order crashes with a raw
sqlite3.IntegrityError (CR-02), and both human clear paths are broken in
opposite directions -- halt clear allows only one clear per UTC day and
then crashes (CR-03), kill clear can report success without writing the
clear row (CR-04). Six Warnings and nine Info items follow.

## Critical Issues

### CR-01: Operator risk configuration is silently ignored

**File:** `src/pumpgrok/tools/__init__.py:240-260`, `src/pumpgrok/execution/__init__.py:27-50`
**Issue:** `Settings` declares `risk: RiskBudget` (settings.py:266), so
`[risk]` TOML and `PUMPGROK_RISK__*` env are accepted startup config. But
`build_operator_registry` constructs the engine with fresh defaults:

```python
engine = RiskEngine(store=store, budget=RiskBudget(), ...)
budget = RiskBudget()
```

and `build_adapter` likewise hardcodes `budget=RiskBudget(),
limits=EngineLimits()` while `del settings` discards the passed settings.
An operator who lowers `paper_equity_sol`, `max_open_positions`,
`max_trades_per_day`, or `min_trade_lamports` gets no effect and no
warning; the desk trades under default ceilings. Same for any `[limits]`
tuning (`max_slippage_bps`, `mtm_interval_s`, `confirm_timeout_s`).
**Fix:** thread `settings.risk` and the limits section through both
factories, e.g. `budget=settings.risk` /
`limits=settings.limits` (adding a `limits` field to `Settings` if
intended to be configurable), and add a startup log line echoing the
effective budget so a silent-default regression is visible.

### CR-02: Retrying a risk-refused order crashes with raw sqlite3.IntegrityError

**File:** `src/pumpgrok/execution/paper_adapter.py:1003-1024` (`_repeat_outcome`), `:289-340` (`place`), `:1004-1024` (`_reject`)
**Issue:** `_repeat_outcome` only recognizes repeats via the
`exec_place_key(ticket, side, decision)` OrderPlaced row. An ACCEPTED-stage
refusal writes no OrderPlaced row, only an OrderRejected row keyed
`f"reject|{request.ticket_id}|{request.side.value}|{decision_id}|{stage}|{reason}"`.
A retry with the same decision_id therefore reaches `self._reject` again
with the identical key (the cached reject decision in `_decisions`
guarantees the same reason), and the second `store.append` raises
`sqlite3.IntegrityError`, which `place()` does not catch and `run_place`
does not translate (it catches only `OrderRejectedError` /
`OrderUnknownError`). The caller gets a raw sqlite traceback instead of
the documented clean refusal, violating the PLACE_SPEC "a repeated
decision returns the first" contract for the reject case. Contained by
`run_guarded` in the supervisor, but fatal to CLI/script retries.
**Fix:** in `place()`, before re-running risk, look up a prior
OrderRejected row for the same decision (by_key on the reject key prefix
or a decision scan) and re-raise the stored refusal; or wrap `_reject`'s
append in a duplicate-key guard that returns the existing refusal.

### CR-03: Halt clear allows one clear per UTC day, then crashes; clear is non-atomic

**File:** `src/pumpgrok/risk/engine.py:951-986` (`request_halt_clear`)
**Issue:** Three defects in one function. (a) The HaltCleared idempotency
key is `f"halt-clear|{ts_utc[:10]}"` -- no reason, no approval id. A
second halt and clear on the same UTC day raises `sqlite3.IntegrityError`,
which the CLI (`cli.py:715-718`) does not catch (only `ValueError`), so
the operator gets a traceback during incident recovery. (b) The two writes
(HaltCleared, then consumed ApprovalRecorded) are separate `store.append`
calls, not one `append_batch`: a crash between them leaves the halt
cleared while the approval stays unconsumed and reusable, violating
single-send. (c) `_halt_clear`/`_killswitch_clear` build the engine with
default budget/limits (compounds CR-01), so the fold that gates "no
active halt" can disagree with the wired engine.
**Fix:** key the clear row per approval
(`f"halt-clear|{approval.id}"`), write both rows in one `append_batch`,
and have the CLI catch `sqlite3.IntegrityError`/`LedgerInconsistent` and
return `halt_clear_refused` instead of a traceback.

### CR-04: Kill-switch clear can report success without clearing

**File:** `src/pumpgrok/risk/killswitch.py:259-262` (`request_clear`)
**Issue:** Both appends sit inside `_SuppressIntegrity`, which swallows
`sqlite3.IntegrityError`:

```python
with _SuppressIntegrity():
    self._store.append(**cleared)  # key kill_switch_key("clear", reason, day)
    self._store.append(**consumed)
return cleared
```

The clear key is per (reason, day). If a row with that key already exists
(a prior clear for the same reason today, while the switch was since
re-engaged), the `KillSwitchCleared` write is silently dropped, the
consumed-approval row still lands, and the function returns the `cleared`
dict -- the CLI prints `{"ok": true, "killswitch": "cleared"}` while
`_latest_set()` still reports engaged and the engine keeps refusing.
Fail-closed, but a false success plus a burned approval during incident
response. Non-atomicity (two appends, crash window between them) matches
CR-03.
**Fix:** do not suppress around the clear row: attempt the clear append
first without suppression (treat duplicate key as an explicit
"already cleared today, re-poll" outcome, not success), then write both
rows in one `append_batch`.

## Warnings

### WR-01: RiskEngine decision cache never invalidates across halt/kill/breaker changes

**File:** `src/pumpgrok/risk/engine.py:543-557`
**Issue:** `check()` caches by `f"{stage}|{order_hash}|{order.approval_id or ''}"`
with no TTL, no generation counter, and no clearing on halt/kill/breaker
transitions. A cached PASS replays the old evaluated row set even after a
halt engages or a breaker trips; a cached REJECT survives a human halt
clear (liveness). The adapter masks most of this via `_repeat_outcome`,
but any second `check()` on the same key without an OrderPlaced row (e.g.
the CR-02 retry path, CONFIRMING re-checks sharing an engine across
adapters, supervisor replays) consults stale gate state. The dict also
grows without bound for a long-lived supervisor.
**Fix:** key the cache with a state generation (halt active + kill active
+ open breakers + ledger head seq), or drop the cache and rely on the
ledger-keyed `_repeat_outcome` for idempotence; at minimum bound the dict
size.

### WR-02: Status views disagree with the kill switch on what "env set" means

**File:** `src/pumpgrok/tools/risk/halt_status.py:75`, `src/pumpgrok/tools/risk/kill_switch.py:122`
**Issue:** Both views compute
`env_set = os.environ.get("PUMPGROK_KILLSWITCH", "").strip() == "1"`,
but `KillSwitch.poll()` and `live_sources()` treat any non-empty value
other than `"0"`/`"false"` as engaged. With
`PUMPGROK_KILLSWITCH=stop` (a documented truthy value), the engine refuses
every order while `risk.halt_status` and `risk.kill_switch` report the
switch inactive.
**Fix:** share one helper, e.g. `killswitch.env_engaged(environ)` used by
`poll`, `live_sources`, and both views.

### WR-03: CLI-minted approval ids use a deterministic default-seed RNG

**File:** `src/pumpgrok/cli.py:558-560`
**Issue:** `_mint_approval_id()` builds a fresh
`IdFactory(WallClock(), make_rng())` per call; `make_rng()` defaults to
`DEFAULT_SEED = 20260101` (replay/rng.py:12-15), so the 80 random bits are
identical across calls and ULID uniqueness rests solely on the wall-clock
millisecond. Two mints in the same millisecond -- easy in
halt-clear/killswitch-clear scripts, or across two processes -- produce
the same `apr-` id, colliding the `consumed|{id}` / `halt-clear|{day}` /
`kill_switch_key("clear", ...)` keys and surfacing as IntegrityError
crashes or, worse, cross-type consumed-key aliasing between a halt_clear
and a killswitch_clear approval.
**Fix:** use `random.Random()` (OS-seeded) or a process-shared factory
with monotonic state for CLI-minted ids; keep the seeded stream for
replay paths only.

### WR-04: `_sol_to_lamports` accepts Infinity and breaks the ValueError contract

**File:** `src/pumpgrok/core/approvals.py:139-147`
**Issue:** `parse_human_phrase` documents "any deviation raises
ValueError", but `_sol_to_lamports` only checks `if size <= 0`. For
`Decimal("Infinity")` the comparison is False, so it proceeds to
`int(...to_integral_value())`, which raises `OverflowError` -- not
`ValueError` -- escaping every caller that maps `ValueError` to
`approval_mismatch` (and any future approve verb). `NaN` happens to raise
`ValueError` via `int()`, but only by accident. (The CLI path is safe:
`cli.py:135-136` checks `is_finite()`; this gap is specific to the phrase
boundary.)
**Fix:** add `if not size.is_finite(): raise ValueError(...)` before the
sign check.

### WR-05: `risk.halt_status` folds the ledger without verifying the hash chain

**File:** `src/pumpgrok/tools/risk/halt_status.py:70-100` (`run_halt_status`)
**Issue:** The operator-facing halt view calls `store.read(limit=None)`
directly and never calls `store.verify()`. A tampered or corrupt ledger
(bad row hash, broken prev_hash link) still renders a confident
`halted: false` view. The trading path is protected
(`_step_ledger_inconsistent`, `evaluate_halts`), but the exact screen an
operator consults during an incident is not.
**Fix:** call `store.verify()` first and surface `halted: true,
reasons: ["ledger_inconsistent"]` (or an explicit `unverified` flag) on
`LedgerInconsistent`.

### WR-06: Cap math routes money through float, violating R28

**File:** `src/pumpgrok/risk/engine.py:816`, `:826`
**Issue:** `cap = int(float(self._budget.max_trade_fraction) * ctx.equity)`
(and the `max_token_fraction` equivalent) converts the Decimal fraction
to binary float before multiplying lamports. `float(Decimal("0.02"))` is
inexact, so caps can differ by a lamport from the Decimal computation the
rest of the money path uses (`fees.py`, `curve_math.py`, `_sol_to_lamports`
all stay integer/Decimal). Financially negligible, but it breaks the
"money is int, ratios are Decimal" invariant at a decision boundary.
**Fix:** `cap = int(self._budget.max_trade_fraction * ctx.equity)` (Decimal
* int stays Decimal).

## Info

### IN-01: Bare `except Exception` in MTM peak update keeps a stale peak silently

**File:** `src/pumpgrok/ledger/reducer.py:289-290`
**Issue:** `except Exception: peak = pos.price_peak` swallows Decimal and
shape errors from ledger `MarkToMarket` rows with no log, no counter, no
`unknown_events` entry. Fail-safe direction (stale peak triggers trailing
stops earlier), but a malformed feed is invisible.
**Fix:** narrow to `(InvalidOperation, ValueError, TypeError, KeyError)`
and count the event in `unknown_events` or a counter.

### IN-02: `position_size_lamports` uses banker's rounding, unlike the HALF_UP boundary

**File:** `src/pumpgrok/risk/sizing.py:56-60`
**Issue:** `round(min(by_score, by_budget))` on a float uses round-half-even
on an already-inexact float product, while the phrase and config
boundaries (`approvals._sol_to_lamports`, `cli.size_sol_to_lamports`)
use `ROUND_HALF_UP` on Decimals. One-lamport disagreements at exact halves.
**Fix:** compute in Decimal and quantize with `ROUND_HALF_UP`.

### IN-03: Duplicate `model_config` assignment in CreatorRecord

**File:** `src/pumpgrok/engine/reputation.py:57-73`
**Issue:** `model_config = ConfigDict(extra="forbid")` is assigned twice in
`CreatorRecord`; the second silently overrides the first (identical, so no
behavior change, but a reviewer-cleanup item).
**Fix:** delete one.

### IN-04: Stale Phase-3 docstrings on the refusing adapter

**File:** `src/pumpgrok/execution/not_yet_implemented.py:1-11`, `:19-26`
**Issue:** Module and class docstrings still say "Phase 3 execution
backend" and "The atomic consume-and-order ledger transaction ...
are Phase 4 work", although Phase 4 shipped exactly that in
`PaperAdapter`. The behavior (raise, never fake) is correct; the prose
misdescribes the release.
**Fix:** update to "retired Phase 3 backend; Phase 4 wires PaperAdapter".

### IN-05: `assert` used for load-bearing invariants in risk steps

**File:** `src/pumpgrok/risk/engine.py:813`, `:820`, `:861`, `:868`, `:876`
**Issue:** `assert ctx.final_size is not None` guards real trading logic;
under `python -O` these vanish and the subsequent arithmetic fails with a
confusing `TypeError`. (Also `settings.py:285` uses `assert self.mode is
not None` in `effective_mode`.)
**Fix:** replace with explicit `if ...: raise _Fail(...)` / `ConfigError`.

### IN-06: `KILL FLATTEN` with no reason records reason `"FLATTEN"`

**File:** `src/pumpgrok/risk/killswitch.py:55-66` (`parse_kill_line`)
**Issue:** For the bare line `KILL FLATTEN`, the optional group
backtracks, `reason` captures `"FLATTEN"`, and the returned
`(True, "FLATTEN")` stores the literal word as the operator's reason.
Harmless for gating (still engages + flatten), noisy for audit.
**Fix:** special-case `rest in ("", "FLATTEN")` to require/flag a reason.

### IN-07: `Breaker.is_open` mutates state inside a property getter

**File:** `src/pumpgrok/risk/breakers.py:104-115`
**Issue:** Reading `is_open` performs the cooldown-expiry transition
(clears `opened_at`, sets `half_open`). `half_open_breakers()` depends on
calling `open_breakers()` purely for this side effect (`:427-433`). Works,
but a read that writes is a maintenance trap (e.g. a future `any(...)`
short-circuit changes transition timing).
**Fix:** split into `poll(now)` (mutating) + pure `is_open` snapshot; call
`poll` explicitly in `refresh`/`open_breakers`.

### IN-08: Unhandled arithmetic on degenerate zero-size fills (verification gap noted)

**File:** `src/pumpgrok/execution/paper_adapter.py:522`, `:574`, `:725`
**Issue:** `fraction = Decimal(filled) / Decimal(size)`,
`price_avg = Decimal(x_net) / Decimal(out1)`, and the sell-side
`Decimal(filled_units) / Decimal(units)` raise `decimal.DivisionByZero`
when the divisor is 0. Buys are guarded by the `size_too_small` step, but
no `OrderRejectedError` wraps these sites, so a degenerate curve (dust
`out1 == 0`) or zero-unit sell target would escape as an arithmetic
exception after OrderPlaced is written, leak the `_inflight` entry, and
leave the repeat path returning `in_flight`. Sell-side zero-unit
reachability was not fully verified (gap: `_sell_targets` zero handling).
**Fix:** validate divisors before dividing and route to `_reject`
(`below_liquidity_floor` / `no_reserves`); always discard the inflight key
in a `finally`.

### IN-09: `exit_rule` approval kind has no minter in scope

**File:** `src/pumpgrok/core/approvals.py:48-82`, `src/pumpgrok/risk/engine.py:599`
**Issue:** `ORDER_SIDES` and `wanted={"human_buy"}` /
`{"human_sell", "exit_rule"}` admit `exit_rule`, and the docstring says
exit_rule approvals "always carry token_units from the rule engine", but
no code in scope mints `kind="exit_rule"` (verified by grep: only
`_mint_autonomous` for `autonomous_paper` and CLI mints for
human/halt/killswitch kinds exist). Exit sells therefore only flow on
`human_sell` approvals. Probably a Phase-5 seam, but the contract implies
a producer that does not exist.
**Fix:** either add the rule-engine minter or document that `exit_rule` is
reserved and remove it from `wanted` until the producer ships.

---

_Positive notes (verified, no finding):_ `canonical_json` rejects float
and non-finite Decimal leaves; `LedgerStore.append/append_batch` chain
hashes under `BEGIN IMMEDIATE` with rollback; `verify()` latches
`_inconsistent` and refuses writes; live preconditions 5-9 are unmet by
design with no signing path reachable; `ApprovalRecord.matches` binds
ticket+mint+slippage+size and refuses clear/live-gate kinds for orders;
`matches` consumption is atomic with OrderPlaced in `_append_order_batch`;
replay uses `FixtureClock` + `make_rng(seed)` with no `time.time` /
unseeded `random` in replay paths; secrets travel via env with
`SecretStr`, CLI secret flags refused, key-bearing values never logged.

_Reviewed: 2026-10-22T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

---

## Fix pass (2026-10-22)

Scope: all 4 Critical and 6 Warning findings. Info findings are untouched.
Every finding below was reproduced in the cited source before the fix.
No finding was not-applicable. Regression tests were added for each fix;
no tests were weakened or deleted. No `noqa`, no `type: ignore`, no float
for lamports, no signing code.

| finding | status | commit | evidence |
|---|---|---|---|
| CR-01 | fixed | 54d2a94 | `Settings` gains `[limits]` (`settings.py`); `build_operator_registry` and `build_adapter` thread `settings.risk`/`settings.limits` into the engine, adapter and trading/risk tools with a startup log line; CLI halt clear uses settings. Tests: `tests/test_operator_budget_wiring.py` (4 tests). |
| CR-02 | fixed | 6fcad30 | `PaperAdapter._reject` catches duplicate-key `IntegrityError` and returns the stored refusal (`_rejection_from_row`, confirmation_timeout maps to `OrderUnknownError`). Test: `test_repeated_risk_refusal_replays_first_refusal` asserts one `OrderRejected` row and no traceback on retry. |
| CR-03 | fixed | 52d593f | `request_halt_clear` keys the clear row per approval (`halt-clear\|{approval.id}`), refuses reused approvals with `ValueError`, writes both rows in one `append_batch`; CLI maps `ValueError`/`IntegrityError`/`LedgerInconsistent` to `halt_clear_refused`. Test: `test_halt_clear_twice_same_day_with_distinct_approvals`. |
| CR-04 | fixed | 500643f | `request_clear` pre-checks the clear and consumed keys (duplicate clear key raises `ClearRefused`, never a false success) and writes both rows in one `append_batch`. Test: `test_kill_clear_same_reason_after_reengage_refuses`. |
| WR-01 | fixed | 4fd4633 | `RiskEngine.check` cache key adds ledger head seq, kill poll state, and open/half-open breaker sets; entries evicted past `_DECISION_CACHE_MAX` (1024). Tests: `test_cached_pass_does_not_survive_halt`, `test_decision_cache_is_bounded`. |
| WR-02 | fixed | 08ca88c | New `killswitch.env_engaged` helper shared by `poll`, `live_sources`, `run_halt_status`, and the kill-switch status view. Tests: truthy/falsy parametrizations plus `test_status_views_agree_with_engine_on_truthy_env`. |
| WR-03 | fixed | 7c1f748 | `_mint_approval_id` seeds `make_rng` from `os.urandom(16)` instead of the fixed replay seed; replay paths still use the seeded stream (static-guard suite stays green). Test: `test_minted_approval_ids_are_unique_in_a_burst`. |
| WR-04 | fixed | fff8c19 | `_sol_to_lamports` raises `ValueError` for non-finite sizes (`is_finite` check covers Infinity and NaN). Test: `test_phrase_rejects_non_finite_sizes` (6 spellings). |
| WR-05 | fixed | a508130 | `run_halt_status` calls `store.verify()` first; on `LedgerInconsistent` returns halted with reason `ledger_inconsistent`. Test: `test_halt_status_reports_inconsistent_on_tampered_ledger`. |
| WR-06 | fixed | 5f73511 | Cap math uses `int(fraction * equity)` in Decimal (no `float()` round-trip) in both fraction steps. Test: `test_fraction_caps_use_decimal_math` pins the exact Decimal cap (501360546187) where float math lands one lamport higher. |

_Fix pass completed: 2026-10-22_
_Fixer: Claude (gsd-code-fixer)_
