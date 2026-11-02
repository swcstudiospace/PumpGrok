# Phase 17 CONTEXT: Risk hardening and promotion lifecycle

Milestone v4, Phase 17. Goal per ROADMAP: the risk engine enforces per-strategy slices and strategy kills on EXISTING R34 rows (19 rows and the risk_json shape unchanged), entry checks and feed health fail closed, live failure classes feed the exec-error breaker, strategies move BACKTEST to PAPER to LIVE_ELIGIBLE and back on recorded evidence under version-controlled thresholds with no timers and no Grok, and the chief composition root (event desk) wires all of it plus restart recovery. After this phase the whole paper desk runs end to end on recorded data (checkpoint 17).

Depends on: Phase 15 (C-01 readers, strategy core, router), Phase 16 (BacktestEvidenceProvider 16-03, CLI 16-04), Phase 12 (SourceStateBook), Phase 13 (EntryRefresh Protocol 13-03, datafeed), Phase 14 (wake, gateway, cycles). Reuses without re-implementing: upgrade/gate.evaluate_candidate checks 1 to 4, divergence.check, upgrade/{escalate,evidence}.py, ledger/active_set.py reader pattern (ledger order, last valid row, is_writer prefix check), risk/breakers.py, autonomy read.

## Locked decisions (NON-NEGOTIABLE)

- D-01: Money integer lamports; Decimal only for fractions.
- D-02: Clock-only time; NO timers and no Clock.sleep anywhere in promotion/ (AST test).
- D-03: Live stays refused (exit 3); the engine never mints autonomous_live in this phase.
- D-04: hashes are identity only; the (strategy id, param_set_hash) pair identifies a stage, a hash is never a score.
- D-05: mypy --strict, ruff, no dead code, no swallowed errors, no placeholders, ASCII-only docs.
- D-06: STEP_IDS stays 19 and the risk_json row shape stays pinned (11-02 test). A 20th row would change every order row and the replay hash. New reasons map onto existing rows: strategy_slice_exceeded -> max_token_fraction; strategy_killed and feed_stale -> breaker_open; strategy_unbound and entry_check_failed -> seat_may_trade; strategy_stage_ineligible -> live_gate. New steps never apply to sells (EXIT_SKIP_STEPS, constants.py:32-47).
- D-07: Slice: inside the max_token_fraction step, remaining slice = slice_lamports(equity, weight) minus open cost basis of that strategy's positions; a buy above is capped, or rejected if below min_trade_lamports. Weights arrive as Mapping[str, Decimal] at engine construction. Desk D6 limits (2 percent per trade, 5 percent per token, 5 percent daily floor, 15 percent drawdown) stay on desk equity; slices only tighten.
- D-08: Strategy kill state is a ledger row `ConfigChanged(keys_changed=["strategy_kill:ID"], new_hash="killed", by="gate:risk")`, read with is_writer semantics; triggers: strategy day loss >= risk.strategy.daily_loss_fraction_of_slice (REVIEW 0.25), N consecutive losses (REVIEW 4), an exec_errors trip attributed to it, or a demotion; idempotent per (id, day); clear is human-only. Exits always pass.
- D-09: Feed health: only feeds declared critical count; staleness is evaluated lazily at check() and on the RiskEdge from a transport disconnect, never by timer; it applies only when exposure exists or a buy is under check (idle is quiet); in live mode a required feed that never ticked fails closed. FeedHealth READS the SourceStateBook and SourceStatus events and owns no timer. Strategies declare required_feeds.
- D-10: EXEC_ERROR_REASONS gains sim_failed, send_failed, tx_failed_onchain (tx_dropped exists); same 3-in-10-minutes trip rebuilt from the ledger. Any UNKNOWN sets HaltSet(reason="live_unknown") immediately, human-clear only.
- D-11: Entry checks (risk/entry_checks.py): async EntryGate.refresh(mint) implements the 13-03 EntryRefresh Protocol, fills a Clock-TTL cache (risk.entry.facts_ttl_s 30); the sync engine reads it through an injected entry_facts(mint); missing or stale facts fail closed. Rules: mint and freeze authority null; mint owner Token or Token-2022; Token-2022 extensions limited to metadataPointer and tokenMetadata; holder concentration (REVIEW 0.30, OD-03); the wallet's own ATA extensions checked (ImmutableOwner fine, CpiGuard and default-frozen reject); block and allow lists from config/mint_lists.toml (human-required; default empty blocklist, allowlist disabled, OD-15).
- D-12: Stage machine BACKTEST to PAPER to LIVE_ELIGIBLE; LIVE is derived, never stored. Stage row `ConfigChanged(keys_changed=["strategy_stage:ID:HASH"], old_hash=prior, new_hash=stage, by="gate:promotion" or "human:NAME")` plus a decision-log JournalNote in the same append_batch with refs strategy:ID, param_set:HASH, run:ID. Any hash change resets that pair to BACKTEST. Stage rows live in the PAPER ledger and are mirrored into the live ledger by C-17 in Phase 18.
- D-13: Thresholds in config/promotion_thresholds.toml (human-required) load fail-closed; the loader enforces LiveGate floors (14 days, 50 closed trades, profit factor 1.2, drawdown 0.15) and refuses looser values. OD-16 defaults: min_shadow_orders 20, max_shadow_slippage_gap_bps 150, demotion when profit factor < 1.0 over the last 20 closed. LIVE_ELIGIBLE additionally requires strategy max_progress <= 0.85 and exit_progress <= 0.92 (OD-08).
- D-14: Gate reuse: BACKTEST to PAPER runs evaluate_candidate checks 1 to 4 (bounds, trials, autonomy, holdout); `evaluate_candidate` gains `paper: MetricsReport | None` and None skips only the divergence check; PAPER to LIVE_ELIGIBLE runs all five. Paper metrics use only source=paper rows attributed by strategy_of, valued through backtest/equity.py; replay and backtest rows never count. Automatic demotion LIVE_ELIGIBLE to PAPER on a demote threshold, strategy kill, a halt with ledger_inconsistent, or a hash change. Humans demote and arm; they cannot promote past a failed threshold. One-operation rollback: `pumpgrok promotion demote ID --by human:NAME`.
- D-15: PromotionEvaluator.on_edge(edge) is a pure function subscribed to PositionChange(closed), RiskEdge (breaker, halt, kill), Timer(daily_rollover) and BacktestCompleted; no Grok. The composition root (17-04, RT3 plus WIRE-17) subscribes it, constructs the engine with slice weights and FeedHealth, wires the EntryGate and still refuses to build unless the effective mode is paper. E2E: recorded smoke and strat-* datasets to asserted fills; idle 24 virtual hours with zero Grok calls and zero Timers beyond the allowed set.
- D-16 (RT4): on start EventBus.recover() runs once, tapes and the held-mint watch set are restored through StrategyRuntime.restore, every open position's ExitDeadline is re-armed from PositionOpened ts plus max_hold_s, exit peaks come from the ledger fold, and a one-time reconcile runs as the allowed reconcile-on-start. Crash tests at three points on smoke and strat-*: ledger rows equal the uninterrupted run and no position loses its exit.

## Grey-area defaults

- G-01: Blocked promotion attempts write one note per changed reason (key promo-blocked|id|hash|reason) and reuse upgrade/escalate.py for the human-facing Escalation. Reason: no spam, one channel.
- G-02: Evidence manifest via upgrade/evidence.record_promotion at var/upgrade/promotions/HASH.json. Reason: v3 precedent.
- G-03: Re-promotion after a demotion needs a fresh window starting at the demotion row. Reason: no flapping.

## Phase boundary

In scope: risk/{engine/{core,steps,constants},breakers,feed_health,entry_checks,strategy_slice}.py, config/{mint_lists,promotion_thresholds}.toml, promotion/ package, upgrade/gate.py paper parameter, promotion demote verb, supervisor/{event_desk,live_paper,scheduler/wake}.py, restart recovery tests. Out of scope: live gate rows, signer, arm record (Phase 18), amendment text, mainnet runs, human arming.

## Canonical references

src/pumpgrok/risk/engine/{core,steps,constants}.py, src/pumpgrok/risk/breakers.py (EXEC_ERRORS_COOLDOWN_S 900.0 at line 65), src/pumpgrok/ledger/{active_set,autonomy}.py, src/pumpgrok/upgrade/{gate,escalate,evidence}.py, src/pumpgrok/execution/live/live_gate.py, research/C-risk-promotion-live.md sections 1 and 2, research/changes-applied.md items 5, 12, 20, 22, 23.

## Existing code insights

- Three breakers exist (data_stale, loss_velocity, exec_errors), restart-safe via ledger rows; v4 extends them. The exec_errors breaker auto-resets after 900 s, which is why live tx_failed_onchain latches a human-clear halt in 18-05.
- RiskEngine._step_live_gate runs for sells today (steps.py:239-245) and live_gate is not in EXIT_SKIP_STEPS; plan 18-05 changes that. `source = ctx.source if ... in ("paper","replay","manual") else "paper"` at steps.py:222.
- v3 closed with promotion library-only because nothing subscribed it; 17-04 exists to prevent a repeat.

## Specifics

- Plan 17-01 and 17-02 merge steps.py edits in order (shared-file chain 17-01, 17-02, 18-01, 18-05); constants.py 17-01 then 17-02; breakers.py 17-02 then 18-05; gate.py 15-01 then 17-03.
- Hash rule this phase: both pairs EQUAL against the post-Phase-15 pins (17-06); every new behavior is config-gated off in replay configs.

## Deferred ideas

Per-strategy volatility-scaled slices; automatic arm proposals; promotion on live-recorded sets only; PumpSwap exits.

## Ownership, receipt and hash rules (every plan of this phase)

- Branch `bot-0N-seat/v4-pPHASE-slug`, one PR per (phase, seat) (PR table below). Receipt `.receipts/bot-0N-seat/v4-pPHASE-slug.json` (task_id = slug, branch = the branch), tracked through the glob `!.receipts/bot-0*/v4-p*.json` from plan 11-01; no other seat edits .gitignore.
- `approved_by` is NEVER self-written and a seat never approves its own work. An agent reviewer (chief for risk-authored work, risk for other seats) reads the diff; human-gated receipts are committed WITHOUT approved_by and the owner adds `human:SomeRandmGuyy` in a batch at the ship checkpoint (after phases 12, 14, 17, 19).
- Seat purity: every path resolves to the plan seat via `resolve_owner(path, load_manifest(DEFAULT_MANIFEST))`; tests/** is risk except tests/desk/** (chief) and tests/engine/** (signal); execution/** sniper; cli/** risk; supervisor/** chief. A foreign-test failure gets a one-file companion plan by the owning seat, merged first.
- Replay hashes: smoke-10m `events.hash` is `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` (seq=2 events=41, verdict and rollover rows only). Trading `smoke` (5 events, seq 11) gave `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54` at HEAD 641927c; plan 11-01 pins it at v4-base; it moves only in plan 15-01. Run receipts in a fresh worktree without var/ledger.sqlite.
- Live stays refused: `uv run pumpgrok run --mode live --once; test $? -eq 3`; nothing arms it.
- Acceptance lines are real commands; exit 0 means success. The G-2 bypass family (collect-only, `--co`, `|| true`, stderr to /dev/null, `--force`, `--dry-run`, inline PUMPGROK_LIVE_ENABLE) never appears; `! cmd -rs | grep -q SKIPPED` proves no skips. Plans touching src also run make lint and make typecheck.


## Plans (7 planned; research/plans.json is the source)

Pull requests in merge order (numbers from research/pr-plan.md):

| PR | Branch | Plans | Approver | Checkpoint |
|----|--------|-------|----------|------------|
| PR-30 | `bot-02-risk/v4-p17-risk-promotion` | 17-01, 17-02, 17-03 | human:SomeRandmGuyy (batch); agent review first | CP17 |
| PR-31 | `bot-00-chief/v4-p17-event-desk-recovery` | 17-04, 17-05 | bot-02-risk (agent) | CP17 |
| PR-32 | `bot-09-journal/v4-p17-changelog` | 17-06 | bot-02-risk (agent) | CP17 |
| PR-33 | `bot-00-chief/v4-p17-close` | 17-07 | bot-02-risk (agent) | CP17 |

### 17-01: Strategy slice and strategy kill in RiskEngine on existing rows

- seat bot-02-risk; wave 1; PR-30; depends_on: 11-04, 12-01, 15-01, 15-02, 16-03; order_after 16-02; requirements: RSK-01, RSK-02, RSK-08; owner decisions: OD-03.
- files: src/pumpgrok/risk/strategy_slice.py, src/pumpgrok/risk/engine/constants.py, src/pumpgrok/risk/engine/core.py, src/pumpgrok/risk/engine/steps.py, tests/risk/test_strategy_slice.py, tests/risk/test_strategy_kill.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/risk tests/characterization/risk
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 17-02: Entry checks and mint lists; feed health and live failure classes

- seat bot-02-risk; wave 2; PR-30; depends_on: 12-03, 13-03, 17-01; requirements: RSK-05, RSK-03, RSK-04; owner decisions: OD-03, OD-15.
- files: src/pumpgrok/risk/entry_checks.py, src/pumpgrok/config/mint_lists.toml, src/pumpgrok/risk/engine/constants.py, src/pumpgrok/risk/engine/steps.py, tests/risk/test_entry_checks.py, src/pumpgrok/risk/feed_health.py, src/pumpgrok/risk/breakers.py, tests/risk/test_feed_health.py, tests/risk/test_exec_failure_breaker.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/risk/test_entry_checks.py tests/risk/test_step_rows_stable.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/risk tests/degradation
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 17-03: Promotion package, thresholds, gate paper parameter, promotion demote verb

- seat bot-02-risk; wave 2; PR-30; depends_on: 12-02, 12-03, 15-01, 16-03, 16-04, 17-01; requirements: PRM-01, PRM-02, PRM-03, PRM-04, PRM-05, PRM-06; owner decisions: OD-08, OD-16.
- files: src/pumpgrok/promotion/__init__.py, src/pumpgrok/promotion/stages.py, src/pumpgrok/promotion/thresholds.py, src/pumpgrok/promotion/evaluator.py, src/pumpgrok/promotion/demotion.py, src/pumpgrok/config/promotion_thresholds.toml, src/pumpgrok/upgrade/gate.py, src/pumpgrok/cli/parsing.py, src/pumpgrok/cli/dispatch.py, src/pumpgrok/cli/verbs_ops.py, tests/promotion/test_stages.py, tests/promotion/test_thresholds.py, tests/promotion/test_gate_reuse.py, tests/promotion/test_demotion.py, tests/promotion/test_no_timers.py, tests/promotion/test_writer_discipline.py, tests/upgrade/test_gate_paper_param.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/promotion tests/upgrade
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 17-04: Event desk composition root and the risk, promotion and entry-gate wiring

- seat bot-00-chief; wave 3; PR-31; depends_on: 11-01, 12-02, 12-03, 13-02, 13-03, 14-01, 14-02, 14-03, 14-06, 15-02, 15-06, 17-01, 17-02, 17-03; requirements: PRM-05, RSK-01, RSK-03, RT-03, EVT-12; owner decisions: OD-05.
- files: src/pumpgrok/supervisor/live_paper.py, src/pumpgrok/supervisor/scheduler/wake.py, tests/desk/test_live_paper_risk_wiring.py, src/pumpgrok/supervisor/event_desk.py, tests/desk/test_event_desk_e2e.py, tests/desk/test_event_desk_idle.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/desk tests/supervisor
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/desk/test_event_desk_e2e.py tests/desk/test_event_desk_idle.py
! uv run pytest tests/desk/test_event_desk_e2e.py -rs | grep -q SKIPPED
uv run pytest -q tests/replay/test_trading_smoke_pin.py
make lint
make typecheck
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 17-05: Restart recovery wiring with crash tests

- seat bot-00-chief; wave 4; PR-31; depends_on: 11-01, 12-02, 15-03, 17-04; requirements: RT-04.
- files: src/pumpgrok/supervisor/recovery.py, tests/desk/test_restart_recovery.py, tests/desk/test_restart_exit_deadlines.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/desk/test_restart_recovery.py tests/desk/test_restart_exit_deadlines.py
! uv run pytest tests/desk/test_restart_recovery.py -rs | grep -q SKIPPED
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/replay/test_trading_smoke_pin.py
make lint
make typecheck
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 17-06: CHANGELOG entry for Phase 17 with both hash pairs

- seat bot-09-journal; wave 5; PR-32; depends_on: 17-01, 17-02, 17-03, 17-04, 17-05; order_after 16-06; requirements: PRC-03, PRC-06.
- files: CHANGELOG.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -qF 'Phase 17: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
grep -qF 'Phase 17: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 17: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 17: trading-smoke events.hash after: $p" CHANGELOG.md
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 17-07: Phase 17 close: STATE, verification record, progress table

- seat bot-00-chief; wave 6; PR-33; depends_on: 17-01, 17-02, 17-03, 17-04, 17-05, 17-06; order_after 16-07; requirements: PRC-06.
- files: .planning/STATE.md, .planning/ROADMAP.md, .planning/phases/17-risk-hardening-and-promotion-lifecycle/17-VERIFICATION.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -q 'Phase 17' .planning/STATE.md
./scripts/check.sh
test -f .planning/phases/17-risk-hardening-and-promotion-lifecycle/17-VERIFICATION.md
python3 ci/gates/check_ownership.py --validate-manifest
```
