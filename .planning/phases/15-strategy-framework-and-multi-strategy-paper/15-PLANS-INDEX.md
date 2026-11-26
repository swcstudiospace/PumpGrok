# Phase 15 plans index: Strategy framework and multi-strategy paper

Status: plan set drafted, not executed. No code, test, gate or pin has been changed by this index.

Sources of truth:
- `.planning/ROADMAP.md` Phase 15 section (goal, depends-on, requirements, success criteria 1 to 15, deliverables, plan ids 15-01 to 15-08).
- `.planning/REQUIREMENTS.md` (MKT-09, STR-01, STR-03, STR-04, STR-05, STR-06, FEE-01, RT-02; RT-04 is cited by criterion 8, library half only).
- `ownership.yaml` (last matching pattern wins), `docs/cross-bot-protocol.md`, `docs/quality-gates.md`.
- Base: branch `bot-00-chief/v4-phase-14`, head `0052468`, tag `v4-base`. Working tree was clean when this index was written.

## Corrections and findings the owner must see

1. **The roadmap has 15 success criteria, not 13.** The brief said 13. ROADMAP lines 188 to 202 are numbered 1 to 15. All 15 are covered below. Nothing was dropped.
2. **Fee model v2 does not exist in the repository.** `src/pumpgrok/execution/fees.py` has one `FeeModel` (venue 100 bps, base 5000, priority from `micro_lamports_per_cu`). The Phase 13 roadmap line is checked `[x]` and says v2 is selectable, but the Phase 13 sniper receipt (`.receipts/bot-04-sniper/13-03-sniper-receipt.md`, "Fee model v2: out of scope, untouched") says it was not built. FEE-01 therefore includes building v2 (plan 15-07). The v2 terms come from FEE-01 text: venue fee, PumpPortal fee when that builder is used, ATA rent on the first buy of a mint, signer priority-fee cap. Their numeric values are proposals (see Parameter and fee proposals), marked PENDING OWNER APPROVAL.
3. **`legacy_screening` exists only in planning docs.** No code, test or fixture uses the name. The legacy strategy is an adapter over the existing replay decision path (`src/pumpgrok/supervisor/scheduler/serve.py::run_once_replay` and `src/pumpgrok/replay/runner.py::run_replay`), not a new engine.
4. **Contract surface is a hard boundary.** `NoteKind` (`src/pumpgrok/ledger/events.py`) and the event models generate `contracts/events/*.schema.json`. Criterion 13 requires zero changes under `contracts/` against `v4-base`. This phase therefore adds no event type, no `NoteKind` value and no event field. New durable state goes to sidecar SQLite tables created in `src/pumpgrok/ledger/store.py`. If a plan appears to need a model change, it must STOP and report to the owner.
5. **Sizing exceeds the budget for five plans.** The planner budget is at most 3 tasks and at most 5 files per plan (receipts excluded). The roadmap fixes the plan list at 8 (ids 15-01 to 15-08, "the list of record"). Plans 15-01, 15-02, 15-03, 15-04 and 15-07 each touch more than 5 files. Plan 15-05 is exactly at the limit. Each plan still has 3 tasks. The owner must either accept this or approve splitting the over-budget plans into sub-plans. Splitting changes the list of record, so it is not done here.
6. **Trading-smoke re-pin happens once.** Only plan 15-07 moves `tests/fixtures/replay/pins/trading_smoke.json`. Criterion 14 requires the smoke-10m hash to stay `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`. If any plan moves smoke-10m, that is a STOP, not a re-pin.
7. **`estimate` frontmatter is not emitted.** The estimate-calibration step was not run, so no calibrated token figure exists. Plans carry no `estimate` key.

## Owner decisions applied (binding)

| # | Decision | Where it lands |
|---|---|---|
| 1 | Paper fee model v2 becomes the paper default (FEE-01). One recorded trading-smoke re-pin. Before and after values recorded in CHANGELOG.md. | 15-07 (code, pin), 15-08 (CHANGELOG entry, journal-owned) |
| 2 | Strategy parameters: propose starting values with a reason each, keep them inside bounds, mark PENDING OWNER APPROVAL, do not pin as final. | 15-01 (bounds sections), 15-04 (strategy defaults), 15-08 (owner checkpoint) |
| 3 | Intent router below autonomous-paper: refuse and journal; approve nothing. | 15-06 |
| 4 | Live-data paper root RPC endpoint is chosen by the owner at deployment. Phase uses a read-only test double. No bundled endpoint is consent. | 15-05 (required endpoint argument, no default, double in tests) |

## Waves and dependencies

| Wave | Plan | Title | Seats (files) | Depends on | autonomous | Criteria closed | Requirements |
|---|---|---|---|---|---|---|---|
| 1 | 15-01 | Parameter identity and strategy bounds | RISK | none | true | 2 | STR-06 |
| 2 | 15-02 | Strategy protocol, static registry, paper-event overlay | RISK | 15-01 | true | 3, 4 | STR-01 |
| 3 | 15-03 | Runtime, capital slices, attribution, legacy through runtime | RISK | 15-02 | true | 5 | STR-03 |
| 4 | 15-04 | Three baseline strategies, fixtures, no-LLM, recovery | RISK | 15-03 | true | 6, 7, 8 | STR-04, STR-05, RT-04 (library half) |
| 4 | 15-05 | Live-data paper root and exit-rule ticket filter | CHIEF + RISK | 15-03 | true | 10, 12 | MKT-09 |
| 5 | 15-06 | Intent router to exec.place | CHIEF | 15-04, 15-05 | true | 11 | RT-02 |
| 6 | 15-07 | Fee model v2 default and the one trading-smoke re-pin | SNIPER + RISK | 15-04, 15-05, 15-06 | false | 9, 14 (pin half) | FEE-01 |
| 7 | 15-08 | Phase close: gates, contract surface, CHANGELOG, live refusal | CHIEF + JOURNAL | 15-07 | false | 1, 13, 14 (CHANGELOG half), 15 | PRC-01, PRC-03, LIV-07 |

Waves: 7 (matches the roadmap). Same-wave plans share no files: wave 4 has 15-04 (strategies, fixtures, tests/strategies) and 15-05 (supervisor, tests/desk, one test double), with no overlap.

Seat keys: RISK = bot-02-risk, CHIEF = bot-00-chief, SNIPER = bot-04-sniper, JOURNAL = bot-09-journal. Each file below lists the seat and the `ownership.yaml` rule that resolves it.

## Plan files

### 15-01 Parameter identity and strategy bounds (wave 1, RISK)

File: `15-01-PLAN.md`. Sizing: 3 tasks, 9 files (over budget, see finding 5).

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/upgrade/params.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/upgrade/bounds.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/upgrade/gate.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/backtest/candidate.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/backtest/harness.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/config/upgrade_bounds.toml | bot-02-risk | src/pumpgrok/config/** |
| tests/upgrade/test_paramset_hash_stable.py | bot-02-risk | tests/** |
| tests/upgrade/test_paramset_strategy.py | bot-02-risk | tests/** |
| tests/backtest/test_harness_strategy_identity.py | bot-02-risk | tests/** |
| .receipts/bot-02-risk/15-01-params.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 2. Requirement: STR-06. Owner decision 2 (bounds part).

### 15-02 Strategy protocol, static registry, paper-event overlay (wave 2, RISK)

File: `15-02-PLAN.md`. Sizing: 3 tasks, 8 files (over budget).

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/strategies/__init__.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/strategies/base.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/strategies/registry.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/config/overlays/paper-event.toml | bot-02-risk | src/pumpgrok/config/** |
| src/pumpgrok/config/settings.py | bot-02-risk | src/pumpgrok/** |
| tests/strategies/test_base.py | bot-02-risk | tests/** |
| tests/strategies/test_registry.py | bot-02-risk | tests/** |
| tests/config/test_paper_event_overlay.py | bot-02-risk | tests/** |
| .receipts/bot-02-risk/15-02-protocol.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 3, 4. Requirement: STR-01.

### 15-03 Runtime, capital slices, attribution, legacy through runtime (wave 3, RISK)

File: `15-03-PLAN.md`. Sizing: 3 tasks, 13 files (over budget; the first task is the tracer and could be split out if the owner splits).

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/strategies/runtime.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/strategies/tape.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/strategies/attribution.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/strategies/allocation.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/strategies/legacy.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/ledger/strategy_state.py | bot-02-risk | src/pumpgrok/ledger/** |
| src/pumpgrok/ledger/ticket_refs.py | bot-02-risk | src/pumpgrok/ledger/** |
| src/pumpgrok/ledger/store.py | bot-02-risk | src/pumpgrok/ledger/** |
| tests/strategies/test_legacy_parity.py | bot-02-risk | tests/** |
| tests/strategies/test_attribution.py | bot-02-risk | tests/** |
| tests/strategies/test_allocation.py | bot-02-risk | tests/** |
| tests/ledger/test_strategy_state.py | bot-02-risk | tests/ledger/** |
| tests/ledger/test_ticket_refs.py | bot-02-risk | tests/ledger/** |
| .receipts/bot-02-risk/15-03-runtime.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 5. Requirement: STR-03. Read-only use of `src/pumpgrok/supervisor/scheduler/serve.py` (CHIEF) by the parity test; no edit.

### 15-04 Three baseline strategies, fixtures, no-LLM, recovery (wave 4, RISK)

File: `15-04-PLAN.md`. Sizing: 3 tasks, 16 files plus a receipt (over budget, the most over; see finding 5).

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/strategies/momentum_breakout.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/strategies/new_launch_sniper.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/strategies/mean_reversion.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/strategies/recovery.py | bot-02-risk | src/pumpgrok/** |
| tests/fixtures/replay/strat-breakout/manifest.json | bot-02-risk | tests/fixtures/replay/** |
| tests/fixtures/replay/strat-breakout/events.jsonl | bot-02-risk | tests/fixtures/replay/** |
| tests/fixtures/replay/strat-launch/manifest.json | bot-02-risk | tests/fixtures/replay/** |
| tests/fixtures/replay/strat-launch/events.jsonl | bot-02-risk | tests/fixtures/replay/** |
| tests/fixtures/replay/strat-reversion/manifest.json | bot-02-risk | tests/fixtures/replay/** |
| tests/fixtures/replay/strat-reversion/events.jsonl | bot-02-risk | tests/fixtures/replay/** |
| tests/strategies/test_rules_breakout.py | bot-02-risk | tests/** |
| tests/strategies/test_rules_launch.py | bot-02-risk | tests/** |
| tests/strategies/test_rules_reversion.py | bot-02-risk | tests/** |
| tests/strategies/test_lookahead_canary.py | bot-02-risk | tests/** |
| tests/strategies/test_no_llm.py | bot-02-risk | tests/** |
| tests/strategies/test_recovery.py | bot-02-risk | tests/** |
| .receipts/bot-02-risk/15-04-strategies.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 6, 7, 8. Requirements: STR-04, STR-05, RT-04 (library half; desk wiring is Phase 17 per the traceability table).

### 15-05 Live-data paper root and exit-rule ticket filter (wave 4, CHIEF + RISK)

File: `15-05-PLAN.md`. Sizing: 3 tasks, 5 files plus 2 receipts (at budget).

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/supervisor/live_paper.py | bot-00-chief | src/pumpgrok/supervisor/** |
| src/pumpgrok/supervisor/exit_rules.py | bot-00-chief | src/pumpgrok/supervisor/** |
| tests/desk/test_live_paper_root.py | bot-00-chief | tests/desk/** |
| tests/desk/test_exit_rules_filter.py | bot-00-chief | tests/desk/** |
| tests/datafeed/readonly_double.py | bot-02-risk | tests/** |
| .receipts/bot-00-chief/15-05-live-root.json | bot-00-chief | .receipts/bot-00-chief/** |
| .receipts/bot-02-risk/15-05-double.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 10, 12. Requirement: MKT-09. Read-only use of `src/pumpgrok/datafeed/readonly.py` (RISK) and `tests/datafeed/test_readonly.py` (RISK, existing); no edit to either. Read-only use of the existing guard tests `tests/safety/test_import_graph_no_live.py` and `tests/safety/test_no_signing_outside_live_stub.py` (RISK).

### 15-06 Intent router to exec.place (wave 5, CHIEF)

File: `15-06-PLAN.md`. Sizing: 3 tasks, 3 files (within budget).

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/supervisor/intent_router.py | bot-00-chief | src/pumpgrok/supervisor/** |
| tests/desk/test_intent_router.py | bot-00-chief | tests/desk/** |
| tests/desk/test_ticket_approval_allocation.py | bot-00-chief | tests/desk/** |
| .receipts/bot-00-chief/15-06-router.json | bot-00-chief | .receipts/bot-00-chief/** |

Criteria: 11. Requirement: RT-02. Owner decision 3.

### 15-07 Fee model v2 default and the one trading-smoke re-pin (wave 6, SNIPER + RISK)

File: `15-07-PLAN.md`. Sizing: 3 tasks, 10 files plus 2 receipts (over budget). Autonomous: false (human reviews the one hash move before it is committed).

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/execution/fees.py | bot-04-sniper | src/pumpgrok/execution/** |
| src/pumpgrok/execution/paper_factory.py | bot-04-sniper | src/pumpgrok/execution/** |
| src/pumpgrok/execution/paper_adapter/adapter.py | bot-04-sniper | src/pumpgrok/execution/** |
| tests/execution/test_fee_model_v2.py | bot-04-sniper | tests/execution/** |
| src/pumpgrok/config/settings.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/cli/backtest.py | bot-02-risk | src/pumpgrok/** |
| tests/config/test_paper_fees_default.py | bot-02-risk | tests/** |
| tests/backtest/test_fee_parity.py | bot-02-risk | tests/** |
| tests/fixtures/replay/pins/trading_smoke.json | bot-02-risk | tests/fixtures/replay/** |
| tests/fixtures/replay/pins/trading_smoke_rows.json | bot-02-risk | tests/fixtures/replay/** |
| .receipts/bot-04-sniper/15-07-fees.json | bot-04-sniper | .receipts/bot-04-sniper/** |
| .receipts/bot-02-risk/15-07-default.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 9, and the pin half of 14. Requirement: FEE-01. Owner decision 1.

### 15-08 Phase close: gates, contract surface, CHANGELOG, live refusal (wave 7, CHIEF + JOURNAL)

File: `15-08-PLAN.md`. Sizing: 3 tasks, 3 files plus 2 receipts (within budget). Autonomous: false (owner review of PENDING parameters and the ship checkpoint).

| File | Seat | Rule |
|---|---|---|
| CHANGELOG.md | bot-09-journal | CHANGELOG.md |
| docs/runbooks/strategies.md | bot-00-chief | docs/runbooks/** |
| .planning/ROADMAP.md | bot-00-chief | .planning/** |
| .receipts/bot-00-chief/15-08-phase-close.json | bot-00-chief | .receipts/bot-00-chief/** |
| .receipts/bot-09-journal/15-08-changelog.json | bot-09-journal | .receipts/bot-09-journal/** |

Criteria: 1, 13, 14 (CHANGELOG half), 15. Requirements: PRC-01, PRC-03 (phase-close invariant), LIV-07 (live stays refused). STR-01 contract check is criterion 13.

The plan file itself (`15-PLANS-INDEX.md` and `15-0N-PLAN.md`) is `.planning/**`, owned by bot-00-chief.

## Coverage

### Success criteria (all 15)

| # | Criterion (short) | Plan(s) | Check |
|---|---|---|---|
| 1 | make lint, typecheck, test, check.sh and paper smoke replay exit 0 | 15-08 | ROADMAP line 188 |
| 2 | ParamSet, bounds and trial identity cover `[strategy.ID.PARAM]`; legacy hashes byte-identical | 15-01 | ROADMAP line 189 |
| 3 | strategy version id tracks code and params; BOUNDS equal the TOML sections exactly | 15-02 | ROADMAP line 190 |
| 4 | paper-event overlay (6 open positions, 40 trades/day); live overlay unchanged at 3 and 20 | 15-02 | ROADMAP line 191 |
| 5 | legacy writes no refs; per-strategy P&L folds to desk total; legacy through runtime equals run_once_replay | 15-03 | ROADMAP line 192 |
| 6 | every rule flips exactly at its bound; each strat-* fixture produces asserted fills | 15-04 | ROADMAP line 193 |
| 7 | no hook reaches an LLM client; idle runtime makes zero calls | 15-04 | ROADMAP line 194 |
| 8 | restart recovery restores tapes, peaks, probation (library half of RT-04) | 15-04 | ROADMAP line 195 |
| 9 | fee model v2 is paper default; backtest and paper fees agree | 15-07 | ROADMAP line 196 |
| 10 | root refuses unless paper; AST scan finds no send or sign symbol; exit book never double-sells | 15-05 | ROADMAP line 197 |
| 11 | Intents reach exec.place only through the router; below autonomous-paper it journals and approves nothing | 15-06 | ROADMAP line 198 |
| 12 | import graph and signing guards pass with strategies/ and datafeed/ present | 15-05 | ROADMAP line 199 |
| 13 | zero changes under contracts/ against v4-base | 15-08 (and every plan keeps contracts/ untouched) | ROADMAP line 200 |
| 14 | smoke-10m pair equal and unchanged; trading-smoke pair moves exactly once; CHANGELOG records both pairs | 15-07 (pin), 15-08 (CHANGELOG) | ROADMAP lines 201 to 202 (full text) |
| 15 | live stays refused (`run --mode live --once` exits 3) | 15-08 | ROADMAP line 202 |

Criterion 14 has two halves: the re-pin is 15-07, and the CHANGELOG pairs are written by journal-owned 15-08 from values recorded in 15-07 receipts.

### Requirements (all 8, plus RT-04)

| Requirement | Plan(s) | Criteria |
|---|---|---|
| MKT-09 | 15-05 | 10, 12 |
| STR-01 | 15-02 (and 15-01 bounds TOML), 15-08 contract check | 3, 4, 13 |
| STR-03 | 15-03 | 5 |
| STR-04 | 15-04 | 6 |
| STR-05 | 15-04 | 7 |
| STR-06 | 15-01 | 2 |
| FEE-01 | 15-07 | 9 |
| RT-02 | 15-06 | 11 |
| RT-04 (cited by criterion 8; library half; desk wiring is Phase 17) | 15-04 | 8 |

Uncovered: none. Requirements and criteria cover every item listed in the roadmap for this phase.

## Parameter and fee proposals (PENDING OWNER APPROVAL)

None of the values below are final. Each is a proposal with a reason, inside a bound. They are recorded in `[strategy.ID.PARAM]` sections of `src/pumpgrok/config/upgrade_bounds.toml` (15-01) and in strategy `DEFAULTS` (15-04). They are not pinned as the phase's final values.

| Strategy | Parameter | Start | Bound [min, max] | Reason |
|---|---|---|---|---|
| momentum_breakout | lookback_seconds | 300 | [60, 1800] | Five minutes catches a launch's first breakout without holding a stale high. |
| momentum_breakout | breakout_pct | 20.0 | [1.0, 200.0] | A 20% move above the window high is a clear breakout on a thin curve. |
| momentum_breakout | max_hold_seconds | 900 | [60, 3600] | Breakouts decay; a 15-minute cap bounds exposure. |
| momentum_breakout | stop_loss_pct | 25.0 | [1.0, 100.0] | Sits inside the existing 100% exit ceiling and above typical breakout noise. |
| new_launch_sniper | max_age_seconds | 300 | [10, 900] | Five-minute launch window. The sniper uses its own age rule, not filter.min_age_seconds (120). Owner to confirm the interaction. |
| new_launch_sniper | min_unique_buyers | 5 | [1, 1000] | Matches the desk filter floor (filter.min_unique_buyers = 5), so the sniper never buys thinner than the filter allows. |
| new_launch_sniper | max_curve_progress | 0.10 | [0.0, 1.0] | Buys before most of the curve fills; the desk filter ceiling is 0.40. |
| new_launch_sniper | take_profit_pct | 80.0 | [1.0, 1000.0] | Launch spikes; 1000 matches the existing exits.take_profit_pct ceiling. |
| mean_reversion | window_seconds | 600 | [60, 7200] | Ten minutes defines a mean on a thin curve. |
| mean_reversion | z_threshold | 2.0 | [0.5, 5.0] | Two standard deviations is the conventional entry threshold. |
| mean_reversion | max_hold_seconds | 900 | [60, 3600] | Reversions that work resolve quickly; a failing one must not be held. |
| mean_reversion | stop_loss_pct | 15.0 | [1.0, 100.0] | A failed reversion should exit fast. |

Fee v2 proposals (15-07), all PENDING OWNER APPROVAL:

| Term | Proposed | Reason |
|---|---|---|
| ata_rent_lamports (charged on first buy of each mint) | RPC read at runtime (getMinimumBalanceForRentExemption(165)); offline replay pin recorded with epoch and source; SUPERSEDED 2039280 (owner decision 2026-11-15) | Standard rent-exempt minimum for a 165-byte SPL token account. Verify against chain docs before pinning. |
| pumpportal_fee_bps | 0 | Applies only when the PumpPortal builder is selected. No builder is used in v4 paper, and the rate is not in the repository. |
| priority_cap_micro_lamports_per_cu | 20000 | Equal to the current `micro_lamports_per_cu` default, so the cap does not move the priority cost by itself. |

The only trading-smoke movement expected from v2 is the ATA rent on first buy. Plan 15-07 requires the human checkpoint to confirm that the diff of trading-smoke rows contains only that term. Any other movement is a STOP.

## Stop conditions (apply to every plan)

- Any change under `contracts/` (criterion 13 fails).
- Any change to `smoke-10m` `events.hash` (criterion 14 fails; the pin must not move).
- Any change to the trading-smoke pin outside plan 15-07.
- Any `src/pumpgrok/execution/live/` edit (RISK owned; out of scope).
- Any router-minted approval (approvals are issued only by `RiskEngine.check`).
- Any default endpoint in the live-data paper root (owner decision 4).
- Any `SKIPPED` mark in a test named by a criterion.
- Any new event type, `NoteKind` value or event field.

## Execution order

1. 15-01 (RISK) records legacy hashes at `0052468` before any edit (golden test).
2. 15-02, then 15-03 (RISK).
3. 15-04 and 15-05 in parallel (RISK, and CHIEF + RISK).
4. 15-06 (CHIEF).
5. 15-07 (SNIPER + RISK), with the human checkpoint before the re-pin commit.
6. 15-08 (CHIEF + JOURNAL): gates, contract check, CHANGELOG, live refusal, owner checkpoint.

Each seat submits its own receipt for its completion claims (G-2). Journal owns the one CHANGELOG pull request. CHIEF owns the one `.planning` update. No push in this phase's planning.
