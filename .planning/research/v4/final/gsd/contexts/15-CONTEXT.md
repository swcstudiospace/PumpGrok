# Phase 15 CONTEXT: Strategy framework and multi-strategy paper

Milestone v4, Phase 15. Goal per ROADMAP: a frozen Strategy protocol, a static registry, a runtime with read-only contexts and per-strategy capital slices exist; legacy_screening runs through the runtime with fills identical to run_once_replay; three baseline strategies (momentum_breakout, new_launch_sniper, mean_reversion) have bounded, version-controlled parameters and fixture datasets; a live-data paper composition root provably cannot send; strategy Intents reach exec.place only through a router with ticket and approval allocation. This is the ONLY phase with a deliberate hash move: the paper fee model v2 default flip (FEE2) re-pins the trading smoke.

Depends on: Phase 13 (datafeed, fee model v2 option 13-03, recorder), Phase 14 (wake core 14-03), Phase 12 (settings, catalog). Reuses without re-implementing: upgrade/{params,bounds,gate}.py, backtest/{candidate,harness,evaluate}.py, ledger/tickets.py allocate_ticket, execution curve_math (impact_buy), supervisor/exit_rules.py, upgrade_bounds.toml.

## Locked decisions (NON-NEGOTIABLE)

- D-01: Money integer lamports; slices are integer floors; Decimal only for weights and ratios.
- D-02: Clock-only time; strategy hooks have no clock, sleep, ledger, registry or network.
- D-03: Live stays refused (exit 3); the paper root never imports build_adapter or execution/live.
- D-04: hashes are identity only; strategy_version_id and param hashes identify, never score.
- D-05: mypy --strict, ruff, no dead code, no swallowed errors, no placeholders, ASCII-only docs.
- D-06 (R0): ParamSet gains an optional `strategy: {id, params}` member (default None, extra=forbid kept), validated through the registered StrategyParams model; `load_bounds` also parses `[strategy.ID.PARAM]` sections with the same KeyBound and OutOfBoundsError semantics (never clamped); the harness TrialLedger identity includes strategy id and params hash. content_hash for every existing (strategy=None) ParamSet stays BYTE-IDENTICAL: tests/upgrade/test_paramset_hash_stable.py pins golden hashes of the legacy shapes. Reason: PR 17/19 evidence must stay valid and B/C bounds and arm pairs need one identity.
- D-07 (C-01): `strategy_of(store, ticket_id)` lives in ledger/strategy_state.py and `slice_lamports(desk_equity_lamports: int, weight: Decimal) -> int` (floor, leaf module, no risk imports) in strategies/allocation.py, both here, so B10 and C-02 do not depend on each other. Attribution carrier: `allocate_ticket(..., strategy_id=None, param_set_hash=None)` appends refs `strategy:ID` and `param_set:HASH` AFTER refs[0]; legacy_screening writes no refs; an unbound ticket is legacy_screening.
- D-08 (OD-06): ticket format stays `SOL-YYYYMMDD-NNN` (3 digits); allocation refuses at 999 with a typed error (no 4-digit contract change, no silent wrap); tickets are allocated for APPROVED intents only.
- D-09 (FEE2): the ONLY deliberate hash move in v4. Flips the paper fee default to model v2 and makes the backtest CLI build FeeModel from settings (cli/backtest.py hard-codes VENUE_FEE_BPS near line 628). smoke-10m is unchanged; the trading-smoke pin files are re-generated deliberately and plan 15-07 records `Phase 15: trading-smoke events.hash before: OLD_PIN` and `after: NEW_PIN`. Needs OD-09 review of v2 constants before merge; without it v1 stays default.
- D-10 (OD-02, OD-17): new overlay config/overlays/paper-event.toml (new file; existing overlays and every replay hash untouched): max_open_positions 6, max_trades_per_day 40, runtime_enabled true, wake_mode event, live.enabled false; strategy slice weights 0.20 each for legacy_screening, momentum_breakout, new_launch_sniper, mean_reversion (0.20 unallocated). Live stays inside current rules (3 positions, 20 trades, notional cap at most 1.0 SOL, D6 fractions). test_live_disabled_overlays iterates the new overlay.
- D-11: Strategy protocol is synchronous and pure: `Strategy` has id, version, params_model, needs and hooks on_start, on_new_token, on_tick, on_fill, on_deadline, on_stop; `Intent(kind enter|exit, strategy_id, mint, size_lamports|None, reason, rule, max_slippage_bps, ttl_s, score, features of ints and strings)`. A raising hook is caught and counted; after 5 faults the strategy is disabled. Strategies without `needs` make zero LLM calls (test_no_llm).
- D-12: `strategy_version_id = sha256(canonical_json({id, version, params_hash, code_sha256}))`. Strategy ids match `[a-z][a-z0-9_]{2,31}`. Registry is a static dict, no plugins. Declared BOUNDS equal the `[strategy.ID.PARAM]` sections of upgrade_bounds.toml EXACTLY (test).
- D-13 (OD-08): live-eligible strategies exit before completion: bounds `max_progress <= 0.85` and `exit_progress <= 0.92` (mean_reversion already caps 0.80). PumpSwap sells are out of scope. `stop_loss_poll_seconds` stays in bounds (cadence default) with a test that it has NO effect under wake_mode event.
- D-14 (REC): `StrategyRuntime.restore(snapshot)` rebuilds MintTape rings from the recorder tail, exit peaks and entry prices from the ledger fold, probation and cooldown from rows, watch-set seeds from open positions; ExitDeadline = PositionOpened ts + max_hold_s. A kill-and-restore test equals the uninterrupted run. The chief wiring half is RT4 (17-05).
- D-15 (RT2): the router is the missing hop between a strategy Intent and sniper exec.place: allocate ticket (D-08 guard), size via the allocator, mint only the approval the CURRENT autonomy level allows (below autonomous-paper it does NOT mint; the intent is journaled as refused, never silently approved, OD-10), then call exec.place through the same entry as replay (supervisor/scheduler/orders.py) with one ledger transaction per intent and key exec_place_key(ticket, side, decision_id). The router has no Grok or live handle.
- D-16 (B17): per-strategy ExitRules with an optional `ticket_filter` on ExitRules/LedgerExitBook (default None) so the global book never double-sells a strategy position; the paper root builds its adapter with execution.paper_factory.build_paper_adapter and refuses to build unless the effective mode is paper; an AST scan finds no signing or send symbol outside the allowlist.

## Grey-area defaults

- G-01: Sizing: size = clamp(floor(slice_equity * risk_per_trade / stop_fraction), MIN_TRADE_LAMPORTS, floor(slice_equity * max_position_fraction)), then desk fractions cap it (slices only tighten). Reason: D6 stays authoritative.
- G-02: Bounds sections alphabetical by strategy id; plans 15-04 then 15-05 serialize registry.py and upgrade_bounds.toml. Reason: shared-file merge order.
- G-03: Replay buys use constant REPLAY_TICKET (supervisor/scheduler/orders.py:50) so attribution does not exist on the replay path; allocate_ticket is the only carrier.

## Phase boundary

In scope: ledger/{tickets,strategy_state}.py, strategies/ package, upgrade/{params,bounds,gate}.py and backtest candidate/harness/evaluate identity changes, config/overlays/paper-event.toml, upgrade_bounds.toml strategy sections, fixtures strat-breakout, strat-launch, strat-reversion, supervisor/{live_paper.py,exit_rules.py} and the router (chief, 15-06), paper_fees defaults. Out of scope: promotion, risk slice enforcement (17-01), live path, mainnet runs.

## Canonical references

src/pumpgrok/upgrade/{params,bounds,gate}.py, src/pumpgrok/backtest/{candidate,harness,evaluate}.py, src/pumpgrok/config/upgrade_bounds.toml, src/pumpgrok/ledger/tickets.py, src/pumpgrok/supervisor/exit_rules.py, supervisor/scheduler/orders.py, tests/upgrade/, research/B-strategies-backtest-data.md sections 4 and 5, research/changes-applied.md items 4, 5, 8, 16, 22, 23, 29.

## Existing code insights

- Today ParamSet holds only `filter` and `exits` (upgrade/params.py:31-33), load_bounds reads only those (upgrade/bounds.py:86) and evaluate_candidate takes a ParamSet (upgrade/gate.py:84), so strategy bounds would be silently ignored without R0.
- Hand-authored fixtures are unaffected by the virtual-versus-real progress overstatement; live progress = rS / 85 SOL.
- Memefilters (integer math): curve open, SOL quote, mayhem excluded, ub observed (None fails closed), creator not sold, topb_ppm cap, rS floor, modeled impact bound, creator block from engine/reputation.

## Specifics

- Parameter bounds (min..max): momentum_breakout lookback_s 30..600, breakout_pct 2..50, stop_loss_pct 5..40, exit_progress 0.5..0.92 (capped), max_hold_s 60..7200; new_launch_sniper max_age_s 5..120, confirm_window_s 2..30, take_profit_pct 10..200; mean_reversion lookback_s 120..3600, dd_min_pct 10..50, target_frac 0.2..1.0; full tables in research/B-strategies-backtest-data.md section 5.
- Look-ahead canary: extreme values after time T never change a decision at or before T. Each rule flips exactly at its bound.
- Hash rule this phase: smoke-10m pair EQUAL; trading-smoke pair `before: OLD_PIN`, `after: NEW_PIN` (plans 15-01 and 15-07).

## Deferred ideas

Dynamic strategy plugins; per-strategy LLM enrichment; a fourth-digit ticket number; stop_loss_poll_seconds removal (OD-20); slice rebalancing by performance.

## Ownership, receipt and hash rules (every plan of this phase)

- Branch `bot-0N-seat/v4-pPHASE-slug`, one PR per (phase, seat) (PR table below). Receipt `.receipts/bot-0N-seat/v4-pPHASE-slug.json` (task_id = slug, branch = the branch), tracked through the glob `!.receipts/bot-0*/v4-p*.json` from plan 11-01; no other seat edits .gitignore.
- `approved_by` is NEVER self-written and a seat never approves its own work. An agent reviewer (chief for risk-authored work, risk for other seats) reads the diff; human-gated receipts are committed WITHOUT approved_by and the owner adds `human:SomeRandmGuyy` in a batch at the ship checkpoint (after phases 12, 14, 17, 19).
- Seat purity: every path resolves to the plan seat via `resolve_owner(path, load_manifest(DEFAULT_MANIFEST))`; tests/** is risk except tests/desk/** (chief) and tests/engine/** (signal); execution/** sniper; cli/** risk; supervisor/** chief. A foreign-test failure gets a one-file companion plan by the owning seat, merged first.
- Replay hashes: smoke-10m `events.hash` is `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` (seq=2 events=41, verdict and rollover rows only). Trading `smoke` (5 events, seq 11) gave `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54` at HEAD 641927c; plan 11-01 pins it at v4-base; it moves only in plan 15-01. Run receipts in a fresh worktree without var/ledger.sqlite.
- Live stays refused: `uv run pumpgrok run --mode live --once; test $? -eq 3`; nothing arms it.
- Acceptance lines are real commands; exit 0 means success. The G-2 bypass family (collect-only, `--co`, `|| true`, stderr to /dev/null, `--force`, `--dry-run`, inline PUMPGROK_LIVE_ENABLE) never appears; `! cmd -rs | grep -q SKIPPED` proves no skips. Plans touching src also run make lint and make typecheck.


## Plans (8 planned; research/plans.json is the source)

Pull requests in merge order (numbers from research/pr-plan.md):

| PR | Branch | Plans | Approver | Checkpoint |
|----|--------|-------|----------|------------|
| PR-23 | `bot-02-risk/v4-p15-strategy-framework` | 15-01, 15-02, 15-03, 15-04, 15-05 | human:SomeRandmGuyy (batch); agent review first | CP17 |
| PR-24 | `bot-00-chief/v4-p15-paper-root-router` | 15-06 | bot-02-risk (agent) | CP17 |
| PR-25 | `bot-09-journal/v4-p15-changelog` | 15-07 | bot-02-risk (agent) | CP17 |
| PR-26 | `bot-00-chief/v4-p15-close` | 15-08 | bot-02-risk (agent) | CP17 |

### 15-01: Ledger readers and allocation, ParamSet generalization, paper fee model v2 flip with the trading smoke re-pin

- seat bot-02-risk; wave 1; PR-23; depends_on: 11-01, 12-01, 13-03; requirements: STR-03, STR-06, STR-01, FEE-01, PRC-03; owner decisions: OD-06, OD-09, OD-02.
- files: src/pumpgrok/ledger/tickets.py, src/pumpgrok/ledger/strategy_state.py, tests/ledger/test_strategy_state.py, tests/ledger/test_ticket_refs.py, src/pumpgrok/strategies/allocation.py, tests/strategies/test_allocation.py, src/pumpgrok/upgrade/params.py, src/pumpgrok/upgrade/bounds.py, src/pumpgrok/upgrade/gate.py, src/pumpgrok/backtest/candidate.py, src/pumpgrok/backtest/harness.py, src/pumpgrok/backtest/evaluate.py, tests/upgrade/test_paramset_strategy.py, tests/upgrade/test_paramset_hash_stable.py, tests/upgrade/test_bounds_strategy_sections.py, tests/backtest/test_harness_strategy_identity.py, tests/upgrade/fixtures/bounds_strategy_sample.toml, src/pumpgrok/config/sections/paper_fees.py, src/pumpgrok/cli/backtest*.py, tests/fixtures/replay/pins/trading_smoke.json, tests/fixtures/replay/pins/trading_smoke_rows.json, tests/config/test_paper_fees_default.py, tests/backtest/test_fee_parity.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/ledger
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/upgrade tests/backtest/test_harness_strategy_identity.py
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pytest -q tests/config/test_paper_fees_default.py tests/backtest/test_fee_parity.py
make lint
make typecheck
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 15-02: Strategy core: protocol, registry, runtime, tape, attribution, paper-event overlay

- seat bot-02-risk; wave 2; PR-23; depends_on: 11-04, 12-01, 12-02, 13-01, 15-01; requirements: STR-01, STR-03, STR-05; owner decisions: OD-02, OD-17.
- files: src/pumpgrok/strategies/__init__.py, src/pumpgrok/strategies/base.py, src/pumpgrok/strategies/registry.py, src/pumpgrok/strategies/runtime.py, src/pumpgrok/strategies/tape.py, src/pumpgrok/strategies/attribution.py, tests/strategies/test_base.py, tests/strategies/test_registry.py, tests/strategies/test_attribution.py, tests/strategies/test_no_llm.py, src/pumpgrok/config/overlays/paper-event.toml, tests/config/test_paper_event_overlay.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/strategies/test_base.py tests/strategies/test_registry.py tests/strategies/test_attribution.py tests/strategies/test_no_llm.py tests/config
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 15-03: memefilters, legacy_screening wrapper with parity, strategy restart-recovery state

- seat bot-02-risk; wave 3; PR-23; depends_on: 12-02, 15-01, 15-02; requirements: STR-03, STR-04, RT-04.
- files: src/pumpgrok/strategies/memefilters.py, src/pumpgrok/strategies/legacy.py, src/pumpgrok/strategies/registry.py, tests/strategies/test_memefilters.py, tests/strategies/test_legacy_parity.py, src/pumpgrok/strategies/recovery.py, src/pumpgrok/strategies/tape.py, src/pumpgrok/strategies/runtime.py, tests/strategies/test_recovery.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/strategies/test_memefilters.py tests/strategies/test_legacy_parity.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/strategies/test_recovery.py tests/strategies
uv run pytest -q tests/replay/test_trading_smoke_pin.py
make lint
make typecheck
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 15-04: Strategies momentum_breakout and new_launch_sniper with bounds and fixtures

- seat bot-02-risk; wave 4; PR-23; depends_on: 15-01, 15-02, 15-03; requirements: STR-04; owner decisions: OD-08.
- files: src/pumpgrok/strategies/momentum.py, src/pumpgrok/strategies/registry.py, src/pumpgrok/config/upgrade_bounds.toml, tests/strategies/test_momentum.py, tests/fixtures/replay/strat-breakout/events.jsonl, tests/fixtures/replay/strat-breakout/manifest.json, src/pumpgrok/strategies/sniper.py, tests/strategies/test_sniper.py, tests/fixtures/replay/strat-launch/events.jsonl, tests/fixtures/replay/strat-launch/manifest.json.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/strategies/test_momentum.py tests/strategies/test_registry.py tests/upgrade
uv run pytest -q tests/strategies/test_sniper.py tests/strategies/test_registry.py tests/upgrade
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 15-05: Strategy mean_reversion with bounds and fixture

- seat bot-02-risk; wave 5; PR-23; depends_on: 15-01, 15-02, 15-03; order_after 15-04; requirements: STR-04.
- files: src/pumpgrok/strategies/reversion.py, src/pumpgrok/strategies/registry.py, src/pumpgrok/config/upgrade_bounds.toml, tests/strategies/test_reversion.py, tests/fixtures/replay/strat-reversion/events.jsonl, tests/fixtures/replay/strat-reversion/manifest.json.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/strategies/test_reversion.py tests/strategies/test_registry.py tests/upgrade
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 15-06: ExitRules ticket filter and live-data paper composition root; Intent to exec.place router with ticket and approval allocation

- seat bot-00-chief; wave 3; PR-24; depends_on: 11-01, 13-01, 13-02, 13-03, 14-03, 15-01, 15-02; requirements: MKT-09, RT-02, STR-03; owner decisions: OD-10.
- files: src/pumpgrok/supervisor/exit_rules.py, src/pumpgrok/supervisor/live_paper.py, tests/desk/test_live_paper_root.py, tests/desk/test_exit_rules_filter.py, src/pumpgrok/supervisor/intent_router.py, tests/desk/test_intent_router.py, tests/desk/test_ticket_approval_allocation.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/desk/test_live_paper_root.py tests/desk/test_exit_rules_filter.py tests/datafeed/test_readonly.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/desk/test_intent_router.py tests/desk/test_ticket_approval_allocation.py
! uv run pytest tests/desk/test_intent_router.py -rs | grep -q SKIPPED
uv run pytest -q tests/replay/test_trading_smoke_pin.py
make lint
make typecheck
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 15-07: CHANGELOG entry for Phase 15: smoke-10m pair unchanged, trading-smoke pair moves (fee model v2)

- seat bot-09-journal; wave 6; PR-25; depends_on: 15-01, 15-02, 15-03, 15-04, 15-05, 15-06; order_after 14-08; requirements: PRC-03, PRC-06.
- files: CHANGELOG.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -qF 'Phase 15: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
grep -qF 'Phase 15: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
grep -qE 'Phase 15: trading-smoke events.hash before: [0-9a-f]{64}' CHANGELOG.md
p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 15: trading-smoke events.hash after: $p" CHANGELOG.md
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 15-08: Phase 15 close: STATE, verification record, progress table

- seat bot-00-chief; wave 7; PR-26; depends_on: 15-01, 15-02, 15-03, 15-04, 15-05, 15-06, 15-07; order_after 14-09; requirements: PRC-06.
- files: .planning/STATE.md, .planning/ROADMAP.md, .planning/phases/15-strategy-framework-and-multi-strategy-paper/15-VERIFICATION.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -q 'Phase 15' .planning/STATE.md
./scripts/check.sh
test -f .planning/phases/15-strategy-framework-and-multi-strategy-paper/15-VERIFICATION.md
python3 ci/gates/check_ownership.py --validate-manifest
```
