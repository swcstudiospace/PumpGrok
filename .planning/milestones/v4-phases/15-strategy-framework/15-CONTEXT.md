# Phase 15: Strategy framework and multi-strategy paper - Context

**Gathered:** 2026-11-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a frozen Strategy protocol, a static registry, a runtime with read-only contexts and per-strategy capital slices, three baseline strategies (momentum_breakout, new_launch_sniper, mean_reversion) with bounded version-controlled parameters and fixture datasets, strategy-aware parameter identity with legacy content hashes unchanged, paper fee model v2 as the default with one recorded trading-smoke re-pin, a live-data paper composition root, and an Intent-to-exec.place router that provably cannot send. The runtime is off in every default configuration. Smoke-10m events.hash stays `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`; the trading-smoke ledger hash moves exactly once, in this phase, with the fee default flip.

This phase covers MKT-09, STR-01, STR-03, STR-04, STR-05, STR-06, FEE-01, RT-02 (ROADMAP Phase 15 Requirements line). RT-04 restart-recovery is included at library level only (recovery state restores tapes, peaks, probation); the desk composition-root wiring is Phase 17. Risk slices and kills enforcement (RSK-01, RSK-02) is Phase 17; this phase builds allocation and attribution only. Promotion stages (PRM-*) is Phase 17. Backtest v2 metrics and scheduler (BT-*) is Phase 16; the strategy-replay parity here is the paper-side proof (legacy_screening through the runtime equals run_once_replay fills and net lamports). Grok gateway behavior is Phase 14; strategies here never reach an LLM client (STR-05).

## Locked Decisions

- D-01: Four strategies only — legacy_screening plus momentum_breakout, new_launch_sniper, mean_reversion. No fifth strategy is added.
- D-02: The Strategy protocol is frozen for this phase: version id derives from code and parameters, declared BOUNDS equal the `[strategy.<ID>.<PARAM>]` sections of upgrade_bounds.toml exactly. Changing BOUNDS without changing the TOML is a refusal, not a warning.
- D-03: Parameter identity covers strategy parameters (ParamSet, CandidateParams, load_bounds, harness trial identity). Legacy filter/exits sections and their content hashes are byte-identical, pinned by a golden test (STR-06).
- D-04: paper-event.toml is a new overlay with max_open_positions 6 and max_trades_per_day 40. live.toml is unchanged at 3 and 20.
- D-05: Paper fee model v2 (venue 100 bps plus the PumpPortal fee when that builder is used, ATA rent on the first buy of a mint, signer priority-fee cap per FEE-01) becomes the paper default. v1 stays selectable. The trading-smoke re-pin happens once, in this phase, and is recorded as a before/after pair in CHANGELOG.md (journal seat).
- D-06: The live-data paper root (supervisor/live_paper.py) refuses to build unless the mode is paper. The Intent router reaches exec.place only with ticket and approval allocation; below the autonomous-paper level it journals refusals and approves nothing. No signing or send symbol exists outside the allowlist.
- D-07: Paper only throughout. No live adapter, no key material, no signTransaction/sendTransaction anywhere in strategies/ or datafeed/. `uv run pumpgrok run --mode live --once` still exits 3.
- D-08: contracts/ is untouched in this phase (`git diff --name-only v4-base -- contracts` is empty).

## NOT Doing

- Enforcing strategy slices or kills in the risk engine (Phase 17).
- Promotion stages, thresholds, demotion (Phase 17).
- Metrics v2, round trips, autonomous backtest scheduler (Phase 16).
- Flipping wake_mode to event, enabling live, funding a wallet, devnet or mainnet execution (Phase 18, dormant).
- Any edit outside the delivered file sets of plans 15-01 to 15-07. plans are file-disjoint within this phase; in particular 15-04 and 15-06 share no file.

## Success Criteria (ROADMAP Phase 15, all 15 items)

1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
2. `uv run pytest -q tests/upgrade tests/backtest/test_harness_strategy_identity.py` exits 0, `uv run pytest -q tests/upgrade/test_paramset_hash_stable.py tests/upgrade/test_paramset_strategy.py` exits 0 and `uv run python -c "import tomllib;tomllib.load(open('src/pumpgrok/config/upgrade_bounds.toml','rb'))"` exits 0; ParamSet, bounds and the harness trial identity cover `[strategy.ID.PARAM]` and legacy content hashes are byte-identical (STR-06)
3. `uv run pytest -q tests/strategies/test_base.py tests/strategies/test_registry.py` exits 0; the strategy version id changes with code or parameters and the declared BOUNDS equal the `[strategy.ID.PARAM]` sections of upgrade_bounds.toml exactly (STR-01)
4. `uv run pytest -q tests/config/test_paper_event_overlay.py` exits 0; the paper-event overlay (6 open positions, 40 trades per day) exists as a new overlay and the live overlay is unchanged at 3 and 20 (STR-01)
5. `uv run pytest -q tests/strategies/test_attribution.py tests/strategies/test_allocation.py tests/strategies/test_legacy_parity.py tests/ledger/test_strategy_state.py tests/ledger/test_ticket_refs.py` exits 0; legacy_screening writes no refs, per-strategy P&L folds to the desk total, legacy through the runtime equals run_once_replay fills and net lamports (STR-03)
6. `uv run pytest -q tests/strategies tests/upgrade` exits 0; every rule flips exactly at its bound and each fixture dataset (`strat-breakout`, `strat-launch`, `strat-reversion`) produces its asserted fills (STR-04)
7. `uv run pytest -q tests/strategies/test_no_llm.py` exits 0; no hook can reach an LLM client and an idle runtime makes zero calls (STR-05)
8. `uv run pytest -q tests/strategies/test_recovery.py` exits 0; strategy restart-recovery state restores tapes, peaks and probation (RT-04, library half; the desk wiring is proven in Phase 17)
9. `uv run pytest -q tests/config/test_paper_fees_default.py tests/backtest/test_fee_parity.py tests/execution/test_fee_model_v2.py` exits 0; fee model v2 is the paper default and backtest and paper fees agree (FEE-01)
10. `uv run pytest -q tests/desk/test_live_paper_root.py tests/desk/test_exit_rules_filter.py tests/datafeed/test_readonly.py` exits 0; the root refuses to build unless the mode is paper, an AST scan finds no signing or send symbol outside the allowlist, and the global exit book never double-sells a strategy position (MKT-09)
11. `uv run pytest -q tests/desk/test_intent_router.py tests/desk/test_ticket_approval_allocation.py` exits 0 and `! uv run pytest tests/desk/test_intent_router.py -rs | grep -q SKIPPED` exits 0; strategy Intents reach exec.place only through the router with ticket and approval allocation, and below the autonomous-paper level the router journals refusals and approves nothing (RT-02)
12. `uv run pytest -q tests/safety/test_import_graph_no_live.py tests/safety/test_no_signing_outside_live_stub.py` exits 0 with `strategies/` and `datafeed/` present (MKT-09)
13. `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0` exits 0; no contract surface changed in this phase (`v4-base` is the tag on the commit where draft PRs 16 to 20 are merged) (STR-01)
14. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" && grep -qF "Phase 15: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md && grep -qF "Phase 15: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0 and `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qE 'Phase 15: trading-smoke events.hash before: [0-9a-f]{64}' CHANGELOG.md && grep -qF "Phase 15: trading-smoke events.hash after: $p" CHANGELOG.md` exits 0 (PRC-03)
15. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0; live stays refused (LIV-07)

## Code Context

- `src/pumpgrok/upgrade/params.py`: ParamSet validates filter/exits overrides through CandidateParams; content_hash is sha256 over canonical_json of normalized overrides. Frozen pydantic, extra forbid.
- `src/pumpgrok/upgrade/bounds.py`: OutOfBoundsError; load_bounds reads config/upgrade_bounds.toml (filter/exits tables). Strategy generalization adds `[strategy.<ID>.<PARAM>]` sections without editing legacy sections.
- `src/pumpgrok/execution/fees.py`: FeeModel with venue_fee_bps 100, BASE_FEE_LAMPORTS 5000, COMPUTE_UNITS 200000, micro_lamports_per_cu 20000; buy_net, buy_debit, sell_proceeds. Phase 13 made v2 selectable; this phase only flips the paper default (do not re-implement v2 arithmetic).
- `src/pumpgrok/supervisor/scheduler/serve.py`: run_once_replay(dataset_dir, filter_cfg, seed=..., ledger_path=...) — the behavior legacy_screening must equal through the runtime.
- `src/pumpgrok/config/overlays/paper.toml` and `live.toml`: both max_open_positions 3, max_trades_per_day 20. The new paper-event.toml changes only those two keys (plus execution mode paper).
- Integer money everywhere; Decimal only for ratios. Time only through the injected Clock. ULIDs from core/ids.py.

## Plan Decomposition (7 plans, 5 waves)

- 15-01 Wave 1 (no deps): parameter identity generalization (upgrade params/bounds/gate, backtest candidate, harness identity), legacy-hash golden pins, paper-event overlay, upgrade_bounds strategy sections.
- 15-02 Wave 2 (dep 15-01): Strategy protocol, static registry, tape, memefilters, ledger strategy_state, ticket attribution refs, allocation.
- 15-03 Wave 3 (dep 15-02): runtime with read-only contexts, legacy_screening adapter + parity, recovery, no-LLM proof.
- 15-04 Wave 4 (dep 15-03): three baseline strategies + three fixture datasets + bound-flip fills.
- 15-05 Wave 2 (dep 15-01): fee model v2 default flip, backtest/paper fee parity, one trading-smoke re-pin (code side; CHANGELOG by journal seat).
- 15-06 Wave 4 (dep 15-03): live-data paper composition root, exit-rules ticket filter, Intent router with ticket/approval allocation (parallel with 15-04, no shared files).
- 15-07 Wave 5 (dep 15-01 to 15-06): phase closure — full gates, import-graph guards, both hash pairs present in CHANGELOG, live refusal, contracts-untouched proof.

Roadmap lists 8 plans (15-01 to 15-08); this decomposition uses 7. Coverage is by requirement, not by count: every Phase 15 requirement, every success criterion, and every deliverable maps to a plan below. The last closure plan absorbs the original 15-08 verification role; no source item is dropped.

## Goal Coverage Matrix

| Req | Plan(s) | Verification command (plan-owned) |
|---|---|---|
| STR-06 | 15-01 | SC 2 (plan 15-01) |
| STR-01 | 15-01 (overlay + bounds TOML), 15-02 (protocol + registry) | SC 3, 4 (plan 15-02 owns SC 3; 15-01 owns SC 4) |
| STR-03 | 15-02 (attribution, allocation, state, refs), 15-03 (legacy parity) | SC 5 (15-02: attribution/allocation/state/refs; 15-03: legacy parity) |
| STR-04 | 15-04 | SC 6 (plan 15-04) |
| STR-05 | 15-03 | SC 7 (plan 15-03) |
| RT-04 (lib half) | 15-03 | SC 8 (plan 15-03) |
| FEE-01 | 15-05 | SC 9 (plan 15-05) |
| MKT-09 | 15-06 (root, exit filter, readonly), 15-07 (import-graph guards) | SC 10 (15-06), SC 12 (15-07) |
| RT-02 | 15-06 | SC 11 (plan 15-06) |
| PRC-01, PRC-03, LIV-07, contracts-untouched | 15-07 | SC 1, 14, 15, 13; per-plan SC re-run after each plan |

Deliverables coverage: ledger/strategy_state + ticket refs + allocation -> 15-02; upgrade params/bounds/gate + backtest candidate -> 15-01; strategies base/registry/runtime/tape/attribution/memefilters/recovery/legacy + 3 baselines -> 15-02, 15-03, 15-04; upgrade_bounds strategy sections + paper-event overlay + 3 fixtures -> 15-01, 15-04; fees default flip + re-pin -> 15-05; live_paper + exit_rules filter + intent_router -> 15-06; CHANGELOG Phase 15 entry -> journal seat, verified by 15-07.

## Specifics

- The trading-smoke re-pin is the single sanctioned ledger-hash move of this phase. Smoke-10m events.hash is equal (before == after == b69c...). No plan under 15-05 re-pins again; 15-05 records before/after on its commit.
- Cash-debit semantics from execution/fees.py (buy_debit = filled + network_cost; sell_proceeds = gross - fee - network) and the slippage_exceeded/tx_dropped distinction are unchanged by the default flip; only the selected model changes.
