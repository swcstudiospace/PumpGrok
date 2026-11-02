# N6 section 8 changes applied to the plan set

Method: the sequencer's 111 units (`/tmp/v4/planning/units.json`) were loaded, every N6 section 8 item was applied as a unit change (new, split, moved, deleted, re-dependent), the units were bundled into plans (`plans_def.py`), and `build.py` re-verified seat purity (`resolve_owner` for every path), dependency order (no plan depends on a later phase), shared-file order and PR acyclicity. Scripts: `/tmp/v4/final/tools/{units_v4,plans_def,build,docs_gen}.py` (reproducible: `cd tools && python3 build.py && python3 docs_gen.py`). Plan ids are `PHASE-NN`.

Facts verified for this integration (not taken from the designs): repo HEAD `641927c` (PRs 17 to 20 not on main; only a private `_is_writer` exists at `ledger/active_set.py:51`); trading `smoke` replay in a clean cwd gives `events.hash=bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54`, `verify=CONSISTENT seq=11 events=5` (two runs, identical); smoke-10m gives `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` with `seq=2 events=41`; `VENUE_FEE_BPS = 100` in `execution/fees.py`; `Settings` section modules are not yet split (Q13s does it); `src/pumpgrok/supervisor/**` and `tests/desk/**` are chief-owned, `tests/**` otherwise risk, `execution/**` sniper, `cli/**` risk; EventSource literal spelled at nine sites (below).

## 1. N6 section 8 ranked list

| # | Sev | How the plan changed | Plans |
|---|-----|----------------------|-------|
| 1 | BLOCKER | LiveGate split into `check_entry` (all rows) and `check_exit` (rows 1, 2, 5, 6, 8 only); the engine calls `check_exit` for sells and mints `autonomous_live` for exit-rule and flatten sells while any live position is open, even with a halt, kill, breaker or expired arm; demotion never strands a position; amendment clause 2 last sentence rewritten to suspend entries only (errata E1). New acceptance: exit sells pass with halt set, kill file present, breaker open and arm expired; entries refused in the same states. | 18-02, 18-05, 18-07 |
| 2 | BLOCKER | Arm record lists (strategy id, param hash) pairs; `live confirm --strategy id:hash`; any param hash change needs a new arm; maximum expiry `live.arm_max_expiry_hours` default 72, hard ceiling 168 (OD-07); config hash plus ledger-held param hashes bound; place frame carries `param_set_hash`; signer re-derives the current hash from stage rows. Errata E1/E2 add the pair and the maximum to the amendment text. | 12-01, 18-01, 18-02, 18-03, 18-07 |
| 3 | BLOCKER | C-09 split into C-09a (IPC, persistence, reconcile) and C-09b (TxBuilder, policy). C-09b implements the instruction-level allowlist (System Transfer to pinned recipient only; Token and Token-2022 deny list with CloseAccount only to wallet; ATA create only for wallet and intent mint; pump program discriminator allowlist with PDA equality; v0 ALT resolved or refused), signer-owned blockhash, and verification of the final signed bytes after compute-limit edits. | 18-03, 18-04 |
| 4 | BLOCKER | New unit R0 generalizes `ParamSet`, `CandidateParams`, `load_bounds` and harness trial identity to `[strategy.ID.PARAM]`; legacy `content_hash` pinned byte-identical by a golden test; runs before B10, B12 and C-05 (all depend on it). | 15-01 |
| 5 | BLOCKER | New chief units: RT1a and RT1b (event-mode seat cycle bodies, Phase 14), RT2 (Intent to `exec.place` router with ticket and approval allocation, Phase 15), RT3 (full composition root: bus, sources, strategy runtime, gateway, router, promotion edges, Timer; Phase 17, dependencies A1, A3, A4, A5, A6, B07, B08, B10, C-05 plus RT1, RT2, B17), RT4 (restart recovery wiring) and risk-owned REC (strategy restore). WIRE-17 is bundled with RT3. | 14-05, 14-06, 15-03, 15-06, 17-04, 17-05 |
| 6 | BLOCKER | C-13 and C-14 become one owner-applied plan/PR (human applies and merges), list every missed copy (`prompts/bot-04-sniper.xml:6,27`, `prompts/bot-00-chief.xml:65`, `agents/chief.md:72`, `AGENTS.md:91`, `ARCHITECTURE.md:170`, `SETUP.md:120,203,241`, `docs/ROSTER.md:116`, `docs/runbooks/setup.md:27`, RISK_POLICY 3.3 R17 line 128, plus the finds `skills/key-custody/SKILL.md:24` and ROSTER key-custody rows), add `test_amendment_copies_complete.py`, record the waiver PR number N and the approver in the receipt and the pinned set; PRC-19 removes the waiver. | 18-07, 19-04 |
| 7 | BLOCKER | C-07 now lists all nine literal sites: three risk-owned sites changed (`ledger/events.py:31`, `ledger/store.py:31`, `risk/engine/steps.py:222`) with 18 schemas, the six sniper and journal sites deliberately stay narrow and are pinned by an AST test; declared `breaking: false`, `semantic_changes: []`, every regenerated schema listed individually, `generate-event-schemas.py --check`. Contingent companion plans (not counted) cover the case where mypy forces a narrow site to widen. This chooses the first N6 alternative (list all literal files) without folding code into the waived PR. | 18-01 |
| 8 | BLOCKER | `strategies/allocation.py` and `strategy_of` live in C-01 (plan 15-01); B10 and C-02 both depend on C-01 and no longer on each other for these; replay `REPLAY_TICKET` gap closed by RT2's real ticket allocation. | 15-01, 15-02, 17-01 |
| 9 | MAJOR | New TSMOKE unit pins the trading `smoke` ledger hash and full row dump in plan 11-01, before any engine unit (all splits depend on 11-01); A2 parity runs on `smoke`; A4 text corrected (it touches `serve.py`, hosts `run_once_replay`; claim is 'unchanged by test'); trading-smoke acceptance is added to every code plan. | 11-01, 12-03, 14-03 |
| 10 | MAJOR | T4 deleted. Wake, metrics and Hermes tests are chief-owned under `tests/desk` inside A4, A7, A8; the risk-owned idle and hang tests move into A10 after the code exists; EVT-08 is in A4's acceptance; no `importorskip`. O2t likewise deleted (item 24 of N6 section 4). | 14-03, 14-04, 14-07, 19-03 |
| 11 | MAJOR | One catalog in `events/models.py` (A1) with every Design A, B and C kind and a single `EventPublisher`; B06, B07, B09 depend on A1; B07 depends on A3 and only decodes; X1 shrinks to the bridge with an explicit CurveTick-to-PositionTick mapping constant; backtest uses DeterministicBus ordering. | 12-02, 12-03, 13-01, 13-02 |
| 12 | MAJOR | A3 owns staleness (SourceStateBook, SourceStatus); `DegradedState.ws_data_stale` is written by the A4 bridge from it, FeedHealth (C-04) and LivePriceSource (B08) read it; no `note_tick` call sites elsewhere. Allowed timers gain the 45 s MTM refresh (only while positions are open) and reconcile-on-start. | 12-03, 13-02, 14-03, 17-02 |
| 13 | MAJOR | Hermes daily rollup is disabled in event mode (`superseded_by: events`) and replaced by an event-triggered journal cycle on `Timer(daily_rollover)`; `require_activity` dropped; rug-watch disabled; idle desk starts zero sessions. | 14-04, 14-06 |
| 14 | MAJOR | Explicit gateway cache-key payload of ints and strings, Decimals stringified, `canonical_request_hash` not fed raw requests; tests for Decimal stability and for renamed age-like fields. | 14-01 |
| 15 | MAJOR | New GRKFX evidence-50 fixture with at least 50 admitted candidates; A9's ratio gate runs on it and asserts the candidate count. | 14-01, 14-04 |
| 16 | MAJOR | Desk caps: owner decision OD-02 (default paper-event overlay 6 open positions, 40 trades per day; live stays 3 and 20), applied as a NEW overlay so no hash moves. Ticket width: OD-06 default keep three digits; C-01 refuses allocation at 999 with a typed error (no contract change, no silent wrap). | 15-01, 15-02 |
| 17 | MAJOR | Recorder manifest values are strings and every jsonl is listed; `DatasetCurveSource` uses a per-mint bisect index with a perf-shaped test. | 13-01, 16-02 |
| 18 | MAJOR | PF1 (sniper) adds a paper factory so B17's paper root never imports `build_adapter`; C-12 adds a separate live factory that imports the registered class by dotted path only when the gate is open; C-10 updates the import-graph test text (supervisor and CLI may reach the registry module, never the client). | 13-03, 15-06, 18-05, 18-08 |
| 19 | MAJOR | Socket mode 0660 plus group; attestation and identity served over the authenticated socket, never files in shared `var/`; persisted nonce window and signer-clock timestamps; time-sync check in doctor; the doc states that SO_PEERCRED across containers authenticates nothing beyond signer policy. | 14-07, 18-01, 18-02, 18-03 |
| 20 | MAJOR | Stated: stage, kill and halt rows live in the paper ledger, the signer folds the live ledger; C-17 mirrors them idempotently at promotion, kill and halt edges and at arm time; C-01b reads both paths and reports provenance; the docs say this is consistency, not independence. | 17-03, 18-01, 18-06 |
| 21 | MAJOR | SET0 is the one settings skeleton plan (first in Phase 12); A0, B06, B09, B10, B16, C-02, C-06 lost their settings files; later units add no field. Unowned keys (watch_max, mtm_refresh_s, gap_haircut_bps, signer keys) are in SET0. | 12-01 |
| 22 | MAJOR | Live-eligible strategies exit before completion: bounds `max_progress at most 0.85`, `exit_progress at most 0.92`, promotion threshold requires them (OD-08; PumpSwap sells out of scope); new human-gated unit B05e for `EVENT_DECODE_STATUS` beside the LAYOUT_STATUS flip. | 13-05, 15-04, 15-05, 17-03 |
| 23 | MAJOR | Restart recovery: REC (risk library) plus RT4 (chief wiring and crash tests on `smoke` and strat-*), bus `recover()` in A1. Paper fee model: FEE1 (sniper, selectable v2, default v1, no hash move) and FEE2 (risk, default flip, trading-smoke re-pin, before and after lines in the Phase 15 CHANGELOG). | 13-03, 15-01, 15-03, 15-07, 17-05 |
| 24 | MAJOR | Q06 makes lint, typecheck and audit cover `services/` (path-conditional); A10 wires the idle-Grok gate into `run_all.py`, a pytest wrapper, `ci.yml` and the Makefile together; C-09a adds the signer's own lint, mypy and pip-audit over its own lock; O5 adds the nightly soak. | 11-03, 14-07, 18-03, 19-04 |
| 25 | MINOR | Claim errors corrected in unit notes: 5 (ladder modes: A5), 12 (`serve.py` hosts `run_once_replay`: A4), 22 (three seats import CURVE_ACCOUNT_SIZE: B03 keeps the name and value), 26 (manifest sources are `dict[str, str]`: B09, GRKFX), 40 (portal fee documented, only recipient unpinned: FEE1, C-09b). | 13-01, 13-03, 13-04, 14-01, 14-03, 18-04 |
| 26 | MINOR | No setting name contains `seed`, `span` or an `_at` suffix (the cache-key regex drops them); `seed` renamed `rng_stream`. | 12-01, 16-03 |
| 27 | MINOR | P (performance) and L (live path) metric families added to the event-mode metrics extension and the health sections. | 14-04, 19-03 |
| 28 | MINOR | USD cap versus 1.0 SOL documented in the runbook and the errata (cap_sol = min(1.0, 200 USD / SOL price minus fees) at arm time, OD-12). | 18-09 |
| 29 | MINOR | `stop_loss_poll_seconds` stays in bounds (cadence default) with a test that it has no effect in event mode; removal deferred (OD-20). | 15-04 |

## 2. Other N6 findings applied (outside the ranked list)

| N6 location | Disposition | Plans |
|-------------|-------------|-------|
| Verdict: PRs 17 to 20 not on main; `backtest/equity.py`, `is_writer`, `verify_stored_content` UNVERIFIED | Preflight commands in plan 11-01 acceptance (fail until the PRs merged); B15, C-01b, C-05 rely on them. | 11-01 |
| Section 1 contention: cli lane, tests/conftest.py, registry and bounds serialization, doctor chain, errors.py | Shared-file chain computed in pr-plan.md section 8; B07 only owner of conftest.py; doctor chain Q20r, A12, C-06, O1. | 13-02, 14-07, 18-02 |
| Section 1 timers and ordering contradictions (EVT-10, A2 vs A4, C-05 Timer, C-04 transports) | EVT-10 set extended (item 12); A2 proves determinism half, EVT-08 completes in A4; Timer kinds live in A1's catalog so C-05 needs no A4 dependency; C-04 depends on A3. | 12-03, 14-03, 17-02, 17-03 |
| Section 2 row 7, 9 (budget message, cache key hazard) | A5 changes the precheck denial text to `budget.denial_reason()` and fixes the key. | 14-01 |
| Section 2 row 25 (`run --record` is an exit-5 stub) | B18 implements it on the B09 recorder. | 16-04 |
| Section 3 items 4 and 5 (scan per call, FIFO continuation order) | Bisect index (B16a); drain-until-quiescent (A2). | 12-03, 16-02 |
| Section 3 item 7 (before and after lines per phase) | Every journal plan records smoke-10m and trading-smoke before and after lines, including equal pairs. | 11-10, 15-07, 19-06 |
| Section 3 item 8 (GRK-11 vacuous on soak-3d) | See item 15. | 14-01 |
| Section 4 importorskip, collect-only (T4), C-07 and G-4, tests owned by risk, import graph, dependencies | T4 and O2t deleted; collect-only acceptance replaced (Q01, Q02); C-07 non-breaking with explicit surfaces; chief and sniper plans never edit `tests/live` or `tests/safety` (only risk plans do); signer tests only under `services/desk-signer/tests`. | 11-03, 18-01, 18-03 |
| Section 5.5 single send (fsync directory, finalized check for DROPPED, second RPC) | C-09a. | 18-03 |
| Section 5.6 UNKNOWN and drift (token balances, ATA rent, creator-fee vault) | C-10 reconcile compares SOL and token balances inside `live.drift_tolerance_lamports` (OD-03). | 18-05 |
| Section 5.7 strand risk | OD-08; ceilings in B12 to B14 and C-05. | 15-04, 15-05, 17-03 |
| Section 5.8 Token-2022 (wallet ATA extensions, re-check before send) | C-03 (entry check) and C-09b (re-check immediately before send). | 17-02, 18-04 |
| Section 5.9 amendment: failed on-chain result drops human wait; breaker auto-resets after 900 s | C-10 latches `tx_failed_onchain` as a human-clear halt; errata E2 amends clause 3. | 18-05, 18-07 |
| Section 5.9 closing paragraph versus runbook step 4 (committed overlay with enabled=true) | Runbook uses an operator-local `PUMPGROK_CONFIG` outside git; errata E3. | 18-07, 18-09 |
| Section 6 (a) no GSD phases, CONTEXT, PLAN, SUMMARY units | plans.json is the plan layer; PLN-00 installs roadmap and requirements; per-phase CONTEXT and per-plan PLAN and SUMMARY files are produced by the GSD workflow from plans.json (not repo units). | 11-09 |
| Section 6 (b) no ci.yml, signer typecheck, soak split units | Q02, Q06, C-09a, O5. | 11-03, 18-03, 19-04 |
| Section 6 (c) vacuous fixtures, Hermes idle session, seat cycles | Items 5, 13, 15. | 14-01, 14-04, 14-05 |
| Section 6 (d) verify fallback with real budget exhaustion in e2e | RT3 e2e and A5 tests exhaust a real LayeredBudget. | 14-01, 17-04 |
| Section 6 (e) autonomous-paper set by a human, EVENT_DECODE_STATUS review, restart recovery | OD-10 (RT2 refuses and journals below the level), B05e, REC and RT4. | 13-05, 15-03, 15-06, 17-05 |
| Section 6 (f) annualization under 7 days | B15 returns annualization_valid=false and None. | 16-01 |
| Section 6 (g) desk caps starve four strategies | OD-02. | 15-02 |
| Section 7 bus capacity on public RPC, paid-RPC decision | OD-05; B06 and B07 default watch-set caps; no code assumes a paid provider. | 13-01, 13-02 |
| Section 7 pump.fun REST availability and Cloudflare | B07 fallback degrades to SourceStatus(blind) and refuses buys. | 13-02 |
| Section 7 time sync and `assert_no_skew` | A12 doctor probe; C-08 hello skew check. | 14-07, 18-01 |

## 3. Unit-level delta against the sequencer (111 units)

- **Deleted:** T4, O2t. **Split:** B16 into B16a and B16b; C-09 into C-09a and C-09b. **Re-scoped:** X1 (bridge only), A0 and every settings-touching unit (settings moved to SET0), C-03s (Protocol hook, Phase 13), C-07 (explicit literal list), C-13 and C-14 (one owner-applied PR with the missed copies).
- **New units (16):** TSMOKE, Q06, SET0, B05e, FEE1, PF1, GRKFX, RT1a, RT1b, R0, FEE2, REC, RT2, RT3, RT4, C-17 (plus the split halves C-09a, C-09b, B16a, B16b).
- **Moved between phases or PRs:** B01 and B02 pulled forward into the Phase 11 rug and chief PRs; B04c to Phase 14; C-03s to Phase 13; B04 and B04s no longer depend on B03 (agnostic tests first); B05 and B05e follow B04, B04s and the human review.
- **Dependencies added:** B10 on R0, SET0, A1; B12 to B14 on R0 and FEE2; B07 on A1, A3; B08 on A3; B09 and B06 on A1 and SET0; A4 and A2 on TSMOKE; A10 on RT1b, A9, Q06; C-05 on R0, A3, B16b; C-02 on SET0, B16b; C-03 on C-03s; C-06 and C-10 on SET0; C-09a on Q06, SET0; C-11 on C-17; WIRE-18 on C-17.
- Result: 74 plans over 127 units (111 minus 2 deleted minus 2 split parents plus 4 split halves plus 16 new), 45 PRs.

## R. Requirement additions (for PLN-00 to install in `.planning/REQUIREMENTS.md`)

| ID | Requirement | Carried by |
|----|-------------|-----------|
| PRC-09 | The trading `smoke` ledger hash and full row dump are pinned and checked in a clean cwd by every code plan. | 11-01 |
| PRC-10 | CI lint, typecheck and audit cover services/ when present; the idle-Grok gate runs in CI. | 11-03, 14-07 |
| PRC-11 | Every v4 settings section exists once in the settings skeleton, config-gated off. | 12-01 |
| EVT-14 | One event catalog and one source and staleness owner. | 12-02, 12-03 |
| STR-06 | Param identity covers strategy parameters; legacy content hashes unchanged. | 15-01 |
| FEE-01 | Paper fee model v2 is selectable and the default flip records a before and after pair. | 13-03, 15-01 |
| MKT-10 | EVENT_DECODE_STATUS is VERIFIED only through a human-set reviewed_by. | 13-05 |
| RT-01 | Event-mode seat cycle bodies exist for all ten seats and run on wakes. | 14-05, 14-06 |
| RT-02 | Strategy Intents reach exec.place only through the router with ticket and approval allocation. | 15-06 |
| RT-03 | The event desk composition root wires bus, sources, runtime, gateway, router and promotion edges and refuses to build unless paper. | 17-04 |
| RT-04 | Restart recovery re-arms deadlines and restores tapes, peaks, probation and the watch set. | 15-03, 17-05 |
| RSK-09 | Exit sells check only the live gate rows that make sense and are minted autonomous_live while any live position is open. | 18-02, 18-05 |
| LIV-17 | The arm record binds (strategy id, param hash) pairs with a stated maximum expiry. | 18-02 |
| LIV-18 | The signer enforces an instruction-level transaction allowlist with a signer-owned blockhash. | 18-04 |
| LIV-19 | Stage, kill and halt are mirrored into the live ledger; signer persistence and drift checks cover tokens. | 18-03, 18-05, 18-06 |
| LIV-20 | The literal sites of the event source are explicit, three widened, six pinned narrow. | 18-01 |

## C. Amended phase success criteria (apply when PLN-00 installs the roadmap)

- Phase 11 criterion 2: replace `uv run pytest tests/soak --collect-only -q stderr merged | grep -qi deselected` by `uv run pytest -q tests/quality/test_fast_split.py` and the two `make -n` checks; add `uv run pytest -q tests/replay/test_trading_smoke_pin.py` and the three preflight commands (equity.py, is_writer, verify_stored_content); add Q06 checks (`make -n typecheck | grep -q services`).
- Phase 12: add `uv run pytest -q tests/config/test_v4_settings_skeleton.py`; criterion 6 runs the parity on `smoke_trading` and the quiescence test; criterion 9 stays (no contract change).
- Phase 13: replace `tests/desk/test_probe_pump_accounts.py` ownership note (B02 delivered in Phase 11); criterion 5 (probe script removal) moves to Phase 14; add `tests/tools/onchain/test_event_decode_status.py` and `tests/execution/test_fee_model_v2.py tests/execution/test_paper_factory.py tests/execution/test_entry_gate_hook.py`.
- Phase 14: criteria 5, 8, 9 use `tests/desk/test_event_wake.py`, `tests/desk/test_hermes_jobs_superseded.py`, `tests/desk/test_metrics_events.py` (not `tests/supervisor` or `tests/` root); criterion 6 adds `-k smoke_trading`; criterion 7 adds `uv run pytest -q ci/tests/test_idle_grok_gate.py` and `grep -q check_idle_grok ci/gates/run_all.py`; criterion 10 runs on `tests/fixtures/replay/evidence-50` with `--min-candidates 50`; add `tests/desk/test_event_cycles.py tests/desk/test_event_cycles_aux.py tests/desk/test_event_golden_hashes.py`.
- Phase 15: add `tests/upgrade/test_paramset_hash_stable.py tests/upgrade/test_paramset_strategy.py`, `tests/desk/test_intent_router.py tests/desk/test_ticket_approval_allocation.py`, `tests/strategies/test_recovery.py`, `tests/config/test_paper_fees_default.py`; criterion 10 changes: the smoke-10m pair is equal and the trading-smoke pair is `before: OLD_PIN`, `after: NEW_PIN`.
- Phase 16: criterion 3 and 4 add `tests/backtest/test_dataset_curve_source_perf.py`.
- Phase 17: criterion 8 adds `tests/desk/test_event_desk_e2e.py tests/desk/test_event_desk_idle.py tests/desk/test_restart_recovery.py tests/desk/test_restart_exit_deadlines.py`; criterion 4 hook test now ships in Phase 13.
- Phase 18: criterion 5 becomes `cd services/desk-signer && uv run pytest -q` plus `uv run pytest -q tests/safety/test_signer_isolation.py` (no `tests/services/desk_signer`); add `tests/live/test_gate_exit_rows.py tests/live/test_arm_scope.py tests/live/test_arm_expiry_ceiling.py tests/live/test_exit_sells_autonomous_live.py tests/live/test_tx_failed_onchain_latch.py tests/live/test_stage_mirror.py tests/ledger/test_event_source_literal_sites.py tests/safety/test_amendment_copies_complete.py`; criterion 12 is the amendment oracle plus copies test.
- Phase 19: criteria 3 uses `tests/desk/test_health_event_sections.py` and `tests/desk/test_metrics_strategy.py`; criterion 8 and 9 unchanged; O2t removed.

## Verification performed

- `resolve_owner` over every path of every plan: seat-pure for all plans except 18-07 (owners risk, chief, sniper, by design).
- No plan depends on a plan of a later phase; shared explicit files are only shared within one seat (plus the amendment PR); PR graph acyclic with merge order consistent with the table in pr-plan.md.
- No acceptance command matches the G-2 bypass family (`--co`, `--collect-only`, `|| true`, `stderr discard to /dev/null`, `--force`, `--dry-run`, inline `PUMPGROK_LIVE_ENABLE`).
- Not exercised: any new unit's code, tests or hashes (designs only); the C-AMENDMENT-DRAFT wording; the claim that the PRs 17 to 20 symbols exist (plan 11-01 preflight proves it at v4-base).
