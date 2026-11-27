---
phase: 06-integrity-closure
plan: 5
subsystem: execution
tags: [paper-adapter, scheduler, replay, refactoring, INT-08]

# Dependency graph
requires:
  - phase: 06-integrity-closure
    provides: 06-CONTEXT.md shared decisions (D-09: stage splits, no behavior change)
provides:
  - paper_adapter _place_order/_place_buy split into stage functions (52/54 lines)
  - scheduler _replay_cycles split into module-level seat stages (50 lines)
  - tests/integrity/test_function_length.py length guard (INT-08)
affects: [06-integrity-closure closing plan (before/after replay hash compare)]

# Actuals (#2632)
actuals:
  tokens: 7433
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns: ["stage-function split: orchestrator dispatches, stages own one ledger/fee step"]

key-files:
  created:
    - tests/integrity/test_function_length.py
  modified:
    - src/pumpgrok/execution/paper_adapter.py
    - src/pumpgrok/supervisor/scheduler.py

key-decisions:
  - "NamedTuple value objects (_BuyQuote/_BuyConfirmed) carry stage results; no new modules"
  - "Replay seat cycles are module-level functions wired with functools.partial, not closures"

patterns-established:
  - "Stage split: thin orchestrator (<=60 AST lines) over verbatim-moved stage helpers"

requirements-completed: [INT-08]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "paper_adapter _place_buy/_place_order split into stages, signatures and behavior unchanged"
    requirement: "INT-08"
    verification:
      - kind: other
        ref: "python3 AST span check on src/pumpgrok/execution/paper_adapter.py for _place_buy/_place_order (<=60 lines)"
        status: unknown
      - kind: unit
        ref: "tests/integrity/test_function_length.py::test_orchestrators_fit_length_budget"
        status: unknown
    human_judgment: false
  - id: D2
    description: "scheduler _replay_cycles split into seat stage functions, cycles and behavior unchanged"
    requirement: "INT-08"
    verification:
      - kind: other
        ref: "python3 AST span check on paper_adapter.py + supervisor/scheduler.py for all three orchestrators (<=60 lines)"
        status: unknown
      - kind: unit
        ref: "tests/integrity/test_function_length.py (full file)"
        status: unknown
    human_judgment: false

# Metrics
duration: single session (not tracked)
completed: 2026-10-25
status: complete
---

# Phase 06 Plan 05: Split Long Functions Summary

**paper_adapter `_place_buy`/`_place_order` and scheduler `_replay_cycles` split into verbatim-moved stage functions (52/54/50 AST lines), signatures and ledger behavior unchanged, plus an AST length-guard test.**

## Performance

- **Duration:** single session (start time not tracked in this sandbox)
- **Completed:** 2026-10-25T10:30:12Z
- **Tasks:** 2
- **Files modified:** 3 (2 modified, 1 created)

## Accomplishments

- `_place_order` (was ~95 lines, now 52) orchestrates `_order_risk_decision` + `_order_curve` + side dispatch.
- `_place_buy` (was ~224 lines, now 54) orchestrates `_buy_sizing` / `_buy_append_batch` / `_buy_confirm` / `_buy_fill_rows` / `_buy_settle` via `_BuyQuote` / `_BuyConfirmed` NamedTuples.
- `_replay_cycles` (was ~112 lines, now 50) wires ten module-level seat stages (`_replay_chief` … `_replay_journal` + `_replay_mark_open`) with `functools.partial`; nested closures removed.
- New `tests/integrity/test_function_length.py` pins all three orchestrators to ≤60 AST lines and asserts every stage function exists.

## Task Commits

Each task was committed atomically:

1. **Task 1: Split paper_adapter _place_buy and _place_order into stages** - `bbe16b8` (refactor)
2. **Task 2: Split scheduler _replay_cycles and add length guard** - `cdfd6f3` (refactor)

## Files Created/Modified

- `src/pumpgrok/execution/paper_adapter.py` - stage helpers + two thin orchestrators; no signature or math changes
- `src/pumpgrok/supervisor/scheduler.py` - module-level seat stages + partial wiring; no signature or logic changes
- `tests/integrity/test_function_length.py` - AST length guard (deterministic, no network)

## Decisions Made

- Used `typing.NamedTuple` value objects for buy-stage results instead of new dataclasses/modules: zero new imports beyond `NamedTuple`, immutable, typed. No new modules per plan constraint.
- Used `functools.partial` (already imported in scheduler) for seat wiring instead of thin inner wrappers: keeps `_replay_cycles` at 50 lines where ten 2-line wrappers plus dict would have landed near the 60-line ceiling and been brittle under formatting.
- `RiskDecision` added to the existing `pumpgrok.risk.engine` import for the `_order_risk_decision` annotation (same module already imported; no new dependency edge).

## Deviations from Plan

None - plan executed exactly as written. (Import line-wrap and NamedTuple-vs-dataclass are stylistic choices inside the task scope, not deviations.)

## Issues Encountered

None in-plan. One observation outside scope: the main checkout at `/root/src/repos/pumpgrok` shows `M tests/integrity/test_paper_genesis_meta.py` (mtime 2026-10-25 10:28). That file is not in this plan's `files_modified` and was not touched from this worktree (all edits used absolute worktree paths); likely a sibling executor's stray write. Left untouched.

## Event Order / Payload Analysis (for the closing-plan hash compare)

Every ledger write, fee/slippage computation, RNG draw, and clock read executes in the original order with the original arguments. Places where order or payload could in principle change, verified unchanged:

**paper_adapter**

1. `_order_risk_decision`: `order_hash_for` → `risk.check(stage="ACCEPTED", …)` → bound-check `RuntimeError` → `risk refused` `_reject`. Same call, same kwargs, same position after the `_repeat_outcome` early-return.
2. `_order_curve`: `_read_curve` → `no_reserves` / `data_unavailable` (BUY-only source gate, INV-R-16 comment kept) / `post_graduation_no_reserves` gates. Same order, same payloads.
3. `_buy_sizing`: floor check → `filled`/`fraction`/`venue_fee`/`x_net`/`slippage_bps`/`out0`/`threshold`. Arithmetic moved verbatim.
4. `_buy_append_batch`: `ulid()` × 2 (order_id, quote_id) drawn **before** the `append_batch` attempt, exactly as before — so the RNG sequence is identical on the success path, the `IntegrityError`→repeat path (two ulids already consumed, repeat Fill returned), and the `in_flight` raise path.
5. `_buy_confirm`: `_await_confirmation(forbid_complete=True, owner=owner, …)` → cap recompute (same comment, same math, `slippage_bps` reused from the quote) → `buy_out` at confirm reserves → `slippage_exceeded` gate with the same `_inflight.discard` before `_reject` and the same `quote_out`/`threshold`/`confirm_out`/`fees` payload.
6. `_buy_settle` + `_buy_fill_rows`: `network_cost` → `cash_debit` → `price_avg` → `slipped` → `venue_tx_ref` ulid (same position: after confirm math, before the fold) → single `_fold_state()` → `had_position` → rows with `_now_ts()` calls in the same order (FillRecorded `ts_utc`, PositionOpened `ts_utc`, then `opened_ts_utc`) → single `append_batch(rows)` → `inflight.discard` → `_last_price_ts`/`_last_reserves` → `Fill(FILLED if filled == size else PARTIAL, …)` with `quote.size` as the comparator. One `append_batch` per fill; `FillRecorded` always first, `PositionOpened` second and only when flat — unchanged.
7. In-principle (non-ledger) difference: exception tracebacks now include the stage frame. Ledger rows store only reason/detail strings, so no payload change; only human-readable log tracebacks differ textually.

**scheduler**

8. Seat dict key order unchanged (`bot-00-chief` … `bot-09-journal`); Supervisor/SeatTask consume via `await cycle(ctx)` positionally — verified no `__name__`/introspection use (grep over supervisor/).
9. `_replay_mark_open` keeps the exact `trading is not None and refresh_marks is not None` guard, awaited in risk/sniper/journal at the same points.
10. Sniper read-only path (no trading): same `dataset_events[0]` mint read, same `< 32` → `no_mint` gate, same `IdFactory(clock, rng)` draw order (`decision_id` ulid then `approval_id` ulid inside the f-string), same `risk.check(order, seat="bot-04-sniper", source="replay")`.
11. Signal seat: same `FixtureClock` vs scratch-timeline branch, same `llm_request_for(dataset_name, list(dataset_events))` copy semantics at call time.
12. In-principle differences: (a) cycle callables are now `functools.partial` objects / module functions rather than per-call closures — identity and `__name__` differ, but nothing reads them; (b) `trading`/`risk`/`store`/etc. are bound at `_replay_cycles` return time instead of closure-read at call time — the arguments are never rebound after construction, so call-time values are identical.

**Replay hash:** the before value `b69c29542954129b52a8c9ab1cad390441b7b356dd4828c8c7a4345bea55ad32` (captured on 87e664d) stands. No after value was recorded by this executor: worktree rule (3) forbids running pumpgrok/probes, so the orchestrator must run the smoke-10m replay after merge and compare.

## Acceptance Commands (for the orchestrator to run)

```bash
python3 -c "import ast,sys; t=ast.parse(open('src/pumpgrok/execution/paper_adapter.py').read()); f={n.name:(n.end_lineno-n.lineno) for n in ast.walk(t) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in ('_place_buy','_place_order')}; print(sorted(f.items())); sys.exit(0 if set(f)=={'_place_buy','_place_order'} and all(l<=60 for l in f.values()) else 1)"
```

```bash
python3 -c "import ast,sys; f={}; [f.update({n.name:(n.end_lineno-n.lineno)}) for p in ('src/pumpgrok/execution/paper_adapter.py','src/pumpgrok/supervisor/scheduler.py') for n in ast.walk(ast.parse(open(p).read())) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in ('_place_buy','_place_order','_replay_cycles')]; sys.exit(0 if set(f)=={'_place_buy','_place_order','_replay_cycles'} and all(l<=60 for l in f.values()) else 1)"
```

```bash
uv run pytest -q tests/integrity/test_function_length.py
```

Manual span counts (def line → last line): `_place_order` 539→591 = 52; `_place_buy` 1015→1069 = 54; `_replay_cycles` 723→773 = 50.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- INT-08 code split complete in this worktree; closing plan still needs: smoke-10m after-hash, `make lint` / `make typecheck` / `make test`, and `./scripts/check.sh` (all orchestrator-run).
- No blockers. No new ledger event types; R32 vocabulary untouched.

---
*Phase: 06-integrity-closure*
*Completed: 2026-10-25*

## Self-Check: PASSED

- All four files present (paper_adapter.py, scheduler.py, test_function_length.py, SUMMARY).
- Both task commits present in history (bbe16b8, cdfd6f3).
