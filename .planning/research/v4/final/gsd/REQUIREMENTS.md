# Requirements: PumpGrok Desk v4

**Defined:** 2026-10-28
**Core Value:** The desk reacts to events instead of polling, runs several bounded strategies in paper against live-recorded data, promotes and demotes them on recorded evidence, and carries a fully built but DORMANT live path that only a human can arm; no agent and no desk process can move real funds.

Source: owner decisions of 2026-10-28 (live is armed once by a human and then autonomous inside caps; live limits stay inside the current rules, notional cap at most 1.0 SOL and the D6 fractions; custody is a segregated signer process; constitution amendments are drafted for the owner and applied only by a human-approved pull request; draft PRs 17 to 20 merge first, in the order 18, 19, 20, 17; receipts are approved as human:SomeRandmGuyy in batches at the ship checkpoints after phases 12, 14, 17 and 19), the three v4 designs (A events and Grok gateway, B strategies backtest and data, C risk promotion and live), the N6 critique as applied in `changes-applied.md`, and `plans.json` (74 plans, nine phases). Requirement ids continue the v3 numbering where a family already exists (BT-08 onward, LIV-03 onward, PRC-03 onward). Command forms use `uv run` and exit 0 unless stated.

## v4 Requirements

### Event runtime (EVT)

- [ ] EVT-01: Typed frozen event models with derived event ids, priority by kind table, integer money only. Check: `uv run pytest -q tests/events/test_models.py`
- [ ] EVT-02: The P0 lane never drops, P1 overflow goes to the persisted DLQ, P2 coalesces. Check: `uv run pytest -q tests/events/test_bus_backpressure.py`
- [ ] EVT-03: Per-entity FIFO and P0 isolation from slow P1 handlers. Check: `uv run pytest -q tests/events/test_bus_lanes.py`
- [ ] EVT-04: Dedup with TTL (persisted for P0 and P1) and debounce or latest-wins coalescing on the injected Clock. Check: `uv run pytest -q tests/events/test_bus_dedup_coalesce.py`
- [ ] EVT-05: Handler retry for transient errors only with seeded jitter, poison to the DLQ, and `pumpgrok events dlq replay` works. Check: `uv run pytest -q tests/events/test_bus_retry_dlq.py tests/cli/test_events_cli.py`
- [ ] EVT-06: Every handler is idempotent under double delivery (ledger rows unchanged). Check: `uv run pytest -q tests/events/test_handler_idempotency.py`
- [ ] EVT-07: Graceful shutdown persists pending events and recover() resumes each exactly once. Check: `uv run pytest -q tests/events/test_bus_shutdown.py`
- [ ] EVT-08: Deterministic drain gives a byte-identical ledger across two runs, holds a trading-smoke parity, and equals the legacy smoke-10m hash under fixture_compat with zero skipped tests. Check: `uv run pytest -q tests/replay/test_event_drain_parity.py && ! uv run pytest tests/replay/test_event_drain_parity.py -rs | grep -q SKIPPED`
- [ ] EVT-09: SourceSupervisor backoff resets only after stable_s, staleness reaches DegradedState, resync seeds held mints, cursor survives corruption. Check: `uv run pytest -q tests/events/test_sources.py tests/degradation/test_event_source_faults.py`
- [ ] EVT-10: Event-mode supervisor wakes seats per SEAT_WAKES, cadence mode is unchanged, and the remaining timers are exactly the allowed set. Check: `uv run pytest -q tests/desk/test_event_wake.py tests/supervisor/test_scheduler.py`
- [ ] EVT-12: Idle desk: 24 virtual hours with zero source events makes zero Grok calls. Check: `uv run pytest -q tests/events/test_idle_zero_grok.py && uv run python ci/gates/check_idle_grok.py`
- [ ] EVT-13: Superseded Hermes jobs are disabled and desk doctor refuses event mode while one is still enabled. Check: `uv run pytest -q tests/desk/test_hermes_jobs_superseded.py tests/test_doctor_event_mode.py tests/cli/test_wake_mode.py`
- [ ] EVT-14: One event catalog and one source and staleness owner. Check: `uv run pytest -q tests/events/test_models_v4_kinds.py tests/events/test_sources.py`

### Grok gateway (GRK)

- [ ] GRK-01: The deterministic prefilter skips before any budget is spent. Check: `uv run pytest -q tests/grok/test_prefilter.py`
- [ ] GRK-02: The cache key comes from canonical_request_hash with per-agent TTLs and fallbacks are never cached. Check: `uv run pytest -q tests/grok/test_cache.py`
- [ ] GRK-03: In-flight coalescing: N identical requests make one call. Check: `uv run pytest -q tests/grok/test_coalesce.py`
- [ ] GRK-04: The layered persisted budget is atomic, honors the reserve share and survives a restart. Check: `uv run pytest -q tests/grok/test_budget.py`
- [ ] GRK-05: The sanitizer and strict JSON parse defeat the injection corpus. Check: `uv run pytest -q tests/grok/test_sanitize_injection.py tests/engine/test_gateway_agents.py`
- [ ] GRK-06: The fallback ladder follows signal_scoring_mode with breaker and half-open probe. Check: `uv run pytest -q tests/grok/test_fallback_ladder.py`
- [ ] GRK-07: Exits and risk never import or wait on the gateway; a hung transport cannot delay an exit. Check: `uv run pytest -q tests/safety/test_no_grok_in_exit_risk.py tests/degradation/test_grok_hang_exit.py`
- [ ] GRK-08: The replay backend honors recorded request hashes and a miss raises, never the network. Check: `uv run pytest -q tests/grok/test_replay_backend.py tests/replay/test_replay_determinism.py`
- [ ] GRK-09: The four agents run behind the gateway and the signal seat never calls GrokAgent.run directly. Check: `uv run pytest -q tests/engine/test_gateway_agents.py`
- [ ] GRK-10: Event and Grok metric families are exposed in event mode while the nine existing families are unchanged. Check: `uv run pytest -q tests/supervisor/test_metrics.py tests/desk/test_metrics_events.py`
- [ ] GRK-11: The measurement script reports before and after JSON on a fixture with at least 50 admitted candidates, and calls_after is at most 20 percent of calls_before on evidence-50 and soak-3d. Check: `uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/evidence-50 --min-candidates 50 --max-ratio 0.2 && uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/soak-3d --max-ratio 0.2`

### Curve truth and live market data (MKT)

- [ ] MKT-01: The bonding-curve layout matches the official token-first account (49 and 166 byte accounts) and a bad discriminator is rejected. Check: `uv run pytest -q tests/tools/onchain/test_curve_layout.py`
- [ ] MKT-02: The decoder round-trips all five pump event types, ignores trailing bytes and raises EventDecodeError on truncation. Check: `uv run pytest -q tests/tools/onchain/test_pump_events.py`
- [ ] MKT-03: The mainnet probe record is decoded_pending_review, and VERIFIED is written only after a human reviewed_by; otherwise ASSUMED with the exact probe error. Check: `uv run pytest -q tests/tools/onchain/test_probe_record.py tests/desk/test_probe_pump_accounts.py`
- [ ] MKT-04: The price gate is an allowlist: unknown and unverified sources are refused, replay sources allowed. Check: `uv run pytest -q tests/tools/onchain/test_price_gate.py`
- [ ] MKT-05: The watch set never exceeds its cap, pins held mints and counts overflow. Check: `uv run pytest -q tests/datafeed/test_watchset.py tests/datafeed/test_bridge.py`
- [ ] MKT-06: A FaultInjector TIMEOUT reconnect produces no duplicate signature, emits gap events and honors the rate limiter. Check: `uv run pytest -q tests/datafeed/test_feed.py`
- [ ] MKT-07: LivePriceSource returns None when disconnected, completion refuses entry, a gap holds the position, a timeout marks zero. Check: `uv run pytest -q tests/datafeed/test_price_source.py tests/datafeed/test_graduation.py`
- [ ] MKT-08: Every held mint is marked within 60 seconds on a fake Clock and no timer exists while flat. Check: `uv run pytest -q tests/datafeed/test_marks.py`
- [ ] MKT-09: No-send proof for live-data paper: read-only RPC allowlist, AST scan, frame capture, environment refusal. Check: `uv run pytest -q tests/datafeed/test_readonly.py tests/desk/test_live_paper_root.py`
- [ ] MKT-10: EVENT_DECODE_STATUS is VERIFIED only through a human-set reviewed_by; otherwise it stays ASSUMED. Check: `uv run pytest -q tests/tools/onchain/test_event_decode_status.py`

### Recorder (REC)

- [ ] REC-01: A sealed dataset passes load_dataset, holds ticks only and has non-decreasing timestamps. Check: `uv run pytest -q tests/replay/test_live_recorder.py`
- [ ] REC-02: Gaps are written to gaps.jsonl and a torn last line is recovered on startup. Check: `uv run pytest -q tests/replay/test_live_recorder.py -k 'gap or torn'`
- [ ] REC-03: `run --record`, `replay trim`, `replay rebuild-ticks` and `replay import` work and rerun byte-identically. Check: `uv run pytest -q tests/cli/test_record.py`

### Strategy framework (STR)

- [ ] STR-01: The strategy version id tracks code and parameters and the bounds TOML matches the declared BOUNDS exactly. Check: `uv run pytest -q tests/strategies/test_base.py tests/strategies/test_registry.py tests/config/test_paper_event_overlay.py`
- [ ] STR-03: legacy_screening writes no attribution refs and the per-strategy fold equals the desk total. Check: `uv run pytest -q tests/strategies/test_attribution.py tests/ledger/test_strategy_state.py tests/ledger/test_ticket_refs.py`
- [ ] STR-04: Each strategy rule flips exactly at its bound, fixture datasets produce the asserted fills, and the look-ahead canary holds. Check: `uv run pytest -q tests/strategies`
- [ ] STR-05: No strategy hook reaches an LLM client and an idle runtime makes zero calls. Check: `uv run pytest -q tests/strategies/test_no_llm.py`
- [ ] STR-06: Parameter identity covers strategy parameters (ParamSet, CandidateParams, load_bounds and harness trial identity use `[strategy.ID.PARAM]`); legacy content hashes are unchanged and pinned by a golden test. Check: `uv run pytest -q tests/upgrade/test_paramset_hash_stable.py tests/upgrade/test_paramset_strategy.py`

### Backtest v2 (BT)

- [ ] BT-08: Metrics v2 formulas hold and undefined values are None, never zero or infinity. Check: `uv run pytest -q tests/backtest/test_metrics_v2.py`
- [ ] BT-09: Round trips and the per-strategy breakdown sum to the desk view. Check: `uv run pytest -q tests/backtest/test_roundtrip.py`
- [ ] BT-10: The look-ahead canary passes and evidence grading refuses non-promotion data. Check: `uv run pytest -q tests/backtest/test_lookahead.py tests/backtest/test_grading.py`
- [ ] BT-11: Gap segmentation and the flatten haircut behave as specified. Check: `uv run pytest -q tests/backtest/test_gaps.py`
- [ ] BT-12: Strategy-aware replay of legacy_screening on smoke matches the v1 fills and net lamports. Check: `uv run pytest -q tests/backtest/test_strategy_replay.py`
- [ ] BT-13: Autonomous backtest runs are idempotent, deterministic and gated on autonomous-paper. Check: `uv run pytest -q tests/backtest/test_scheduler.py`

### Risk hardening (RSK)

- [ ] RSK-01: The strategy exposure slice is enforced in the engine with its reason on an existing row. Check: `uv run pytest -q tests/risk/test_strategy_slice.py`
- [ ] RSK-02: A strategy kill is written to and read from the ledger and cleared only by a human. Check: `uv run pytest -q tests/risk/test_strategy_kill.py`
- [ ] RSK-03: Feed staleness is lazy and idle-quiet and a never-ticked required feed fails closed in live mode. Check: `uv run pytest -q tests/risk/test_feed_health.py`
- [ ] RSK-04: Live failure classes feed exec_errors and any UNKNOWN sets a halt. Check: `uv run pytest -q tests/risk/test_exec_failure_breaker.py`
- [ ] RSK-05: Entry checks reject authority, extension, holder, list and BLIND cases. Check: `uv run pytest -q tests/risk/test_entry_checks.py tests/execution/test_entry_gate_hook.py`
- [ ] RSK-06: No order reaches a signer past a failed check, including frames sent straight to the signer. Check: `uv run pytest -q tests/safety/test_risk_choke_point.py tests/safety/test_signer_only_bypass.py`
- [ ] RSK-08: The 19 STEP_IDS and the risk_json row shape are unchanged (pinned in Phase 11, re-run in Phase 17). Check: `uv run pytest -q tests/risk/test_step_rows_stable.py`
- [ ] RSK-09: Exit sells check only the live gate rows that make sense (rows 1, 2, 5, 6, 8) and are minted autonomous_live while any live position is open, even with a halt, kill, breaker or expired arm. Check: `uv run pytest -q tests/live/test_gate_exit_rows.py tests/live/test_exit_sells_autonomous_live.py`

### Promotion lifecycle (PRM)

- [ ] PRM-01: The stage machine BACKTEST to PAPER to LIVE_ELIGIBLE records ledger rows and a decision log. Check: `uv run pytest -q tests/promotion/test_stages.py`
- [ ] PRM-02: Promotion thresholds load fail-closed and floors equal or exceed the LiveGate constants. Check: `uv run pytest -q tests/promotion/test_thresholds.py`
- [ ] PRM-03: Promotion reuses the upgrade gate checks; there is no second search. Check: `uv run pytest -q tests/promotion/test_gate_reuse.py tests/upgrade`
- [ ] PRM-04: Automatic demotion and the hash-change reset work. Check: `uv run pytest -q tests/promotion/test_demotion.py`
- [ ] PRM-05: Promotion is event-triggered with no timers and no Grok, and is subscribed by the composition root. Check: `uv run pytest -q tests/promotion/test_no_timers.py tests/desk/test_live_paper_risk_wiring.py`
- [ ] PRM-06: Writer discipline: is_writer, verify_stored_content and one parameter hash. Check: `uv run pytest -q tests/promotion/test_writer_discipline.py`

### Dormant live path (LIV)

- [ ] LIV-03: Gate rows 5 and 6 are real settings and a notional cap above 1.0 SOL refuses to load. Check: `uv run pytest -q tests/live/test_gate_rows56.py`
- [ ] LIV-04: The arm record is verified and bound to the configuration hash and an expiry; its settings fields exist in the config skeleton. Check: `uv run pytest -q tests/live/test_arm_record.py tests/config/test_live_settings_caps.py`
- [ ] LIV-05: The no_active_stop reader folds halt, kill, breakers and strategy kills read-only. Check: `uv run pytest -q tests/ledger/test_stop_state.py`
- [ ] LIV-06: Gate row 8 is met only through an explicit registry containing exactly the signer entry. Check: `uv run pytest -q tests/live/test_registry.py tests/execution/test_build_adapter_registry.py`
- [ ] LIV-07: A default live start still exits 3 listing the nine preconditions. Check: `{ uv run pumpgrok run --mode live --once; test $? -eq 3; } && uv run pytest -q tests/safety/test_live_refusal_lists_nine.py`
- [ ] LIV-08: The signer applies its policy refusals independently of the desk. Check: `cd services/desk-signer && uv run pytest -q && cd ../.. && uv run pytest -q tests/safety/test_signer_isolation.py`
- [ ] LIV-09: Single send: the SIGNED row is persisted before the RPC call and UNKNOWN is never retried. Check: `uv run pytest -q tests/live/test_single_send.py tests/core/test_signer_protocol.py`
- [ ] LIV-10: Fills are reconciled from chain and restart recovery resolves non-terminal orders. Check: `uv run pytest -q tests/live/test_reconcile.py tests/desk/test_live_wiring_dormant.py`
- [ ] LIV-11: The desk holds no key or signer import and doctor flags the HMAC key in a live desk environment. Check: `uv run pytest -q tests/safety/test_no_signing_outside_live_stub.py tests/test_doctor_probes.py`
- [ ] LIV-12: Shadow-live never sends and records the expected-versus-simulated gap. Check: `uv run pytest -q tests/live/test_shadow.py`
- [ ] LIV-13: The guard tests are tightened, rewritten with the registry and green. Check: `uv run pytest -q tests/safety`
- [ ] LIV-14: The additive live event source passes G-4 as a change document. Check: `python3 ci/gates/check_contracts.py --base origin/main --change contracts/changes/v4-live-source.yaml`
- [ ] LIV-15: autonomous_live approvals are minted only when armed, verified and the strategy is listed. Check: `uv run pytest -q tests/live/test_autonomous_live.py`
- [ ] LIV-16: The amendment oracle matches the owner-approved draft text exactly and generate-templates --check passes. Check: `uv run pytest -q tests/safety/test_constitution_amendment_2026_10_28.py && python3 scripts/generate-templates.py --check`
- [ ] LIV-17: The arm record binds (strategy id, parameter-set hash) pairs with a stated maximum expiry (default 72 hours, hard ceiling 168); any hash change needs a new arm record. Check: `uv run pytest -q tests/live/test_arm_scope.py tests/live/test_arm_expiry_ceiling.py`
- [ ] LIV-18: The signer enforces an instruction-level transaction allowlist with a signer-owned blockhash and verifies the final signed bytes. Check: `cd services/desk-signer && uv run pytest -q tests/test_txpolicy_allowlist.py tests/test_blockhash_signer_owned.py tests/test_final_bytes_verify.py`
- [ ] LIV-19: Stage, kill and halt are mirrored idempotently into the live ledger; signer persistence and drift checks cover SOL and token balances; a failed on-chain send latches a human-clear halt. Check: `uv run pytest -q tests/live/test_stage_mirror.py tests/live/test_reconcile.py tests/live/test_tx_failed_onchain_latch.py`
- [ ] LIV-20: The literal sites of the event source are explicit: nine sites, three risk-owned widened, six sniper and journal sites pinned narrow by an AST test. Check: `uv run pytest -q tests/ledger/test_event_source_literal_sites.py`

### Engineering quality (QLT)

- [ ] QLT-01: The default test path excludes the 49 minute soak test; soak runs through make test-soak and nightly CI. Check: `uv run pytest -q tests/quality/test_fast_split.py && make -n test | grep -q 'not slow' && make -n test-soak | grep -q 'm slow'`
- [ ] QLT-02: Branch coverage is measured by make cov with a floor ratcheted to the measured baseline. Check: `make cov && grep -n 'fail_under' pyproject.toml`
- [ ] QLT-03: Ruff complexity rules C901, PLR0912 and PLR0915 are enforced on all new code and the legacy baseline can only shrink. Check: `uv run ruff check . && uv run pytest -q ci/tests/test_complexity_ratchet.py`
- [ ] QLT-04: The six hotspots are split: no function over 60 lines in paper_adapter sell, batch and confirm, RiskEngine evaluate, cli backtest, config settings and seat_task. Check: `uv run pytest -q tests/quality/test_function_size.py`
- [ ] QLT-05: Characterization tests pin each hotspot before it is refactored and the replay hash stays unchanged. Check: `uv run pytest -q tests/characterization tests/config/test_settings_surface_characterization.py tests/cli/test_backtest_verb_characterization.py tests/supervisor/test_seat_task_characterization.py`
- [ ] QLT-06: The six plain-swallow broad excepts are narrowed to typed error tuples and a guard rejects new ones. Check: `uv run pytest -q tests/quality/test_no_plain_swallow.py tests/core/test_manifests_errors.py tests/test_doctor_errors.py tests/tools/onchain/test_onchain_errors.py tests/tools/market/test_jupiter_errors.py`
- [ ] QLT-07: Hypothesis property tests cover integer money math, ledger reducer ordering and replay determinism. Check: `uv run pytest -q tests/property`
- [ ] QLT-08: A mutation-testing smoke target scoped to risk and execution runs on demand. Check: `make mutation-smoke && test -f docs/mutation-testing.md`
- [ ] QLT-09: An SBOM (CycloneDX) is produced as a CI artifact. Check: `uv run pytest -q ci/tests/test_sbom_step.py`
- [ ] QLT-10: Compose services run read-only with tmpfs, all capabilities dropped and no-new-privileges. Check: `uv run pytest -q tests/safety/test_compose_hardening.py`

### Process (PRC)

- [ ] PRC-03: smoke-10m events.hash stays b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d at every phase close, and the trading smoke ledger hash is pinned and checked in a clean cwd; each phase records a CHANGELOG before and after pair for both (equal pairs are recorded, not skipped; the trading-smoke pair moves once, in Phase 15, with the paper fee model v2 default flip). The ids EVT-11, STR-02 and RSK-07 of the three designs state this same invariant and are enforced here. Check: `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py && uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`
- [ ] PRC-04: No PR-number waiver remains in gates.yml and a test pins the waiver set. Check: `! grep -nE 'pull_request\.number' .github/workflows/gates.yml && uv run pytest -q ci/tests/test_no_pr_waivers.py`
- [ ] PRC-05: Every seat can track its v4 receipt without editing a foreign path (glob allowlist). Check: `grep -qF '!.receipts/bot-0*/v4-p*.json' .gitignore && uv run pytest -q ci/tests/test_security_workflows.py`
- [ ] PRC-06: Each phase closes with exactly one journal-owned CHANGELOG pull request and one chief-owned .planning update. Check: `for p in 11 12 13 14 15 16 17 18 19; do grep -qF "Phase $p: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md || exit 1; grep -qE "Phase $p: trading-smoke events.hash after: [0-9a-f]{64}" CHANGELOG.md || exit 1; done`
- [ ] PRC-07: The constitution amendment is applied only by a human-approved pull request (the owner applies and merges) with one step-scoped G-1 waiver and the exact approved text. Check: `uv run pytest -q tests/safety/test_constitution_amendment_2026_10_28.py`
- [ ] PRC-08: The amendment-PR waiver is removed after merge and the waiver set is empty again. Check: `! grep -nE 'pull_request\.number' .github/workflows/gates.yml`
- [ ] PRC-09: The trading `smoke` ledger hash and full row dump are pinned and checked in a clean cwd by every code plan. Check: `uv run pytest -q tests/replay/test_trading_smoke_pin.py`
- [ ] PRC-10: CI lint, typecheck and audit cover services/ when present; the idle-Grok gate runs in CI. Check: `uv run pytest -q ci/tests/test_ci_covers_services.py ci/tests/test_idle_grok_gate.py`
- [ ] PRC-11: Every v4 settings section exists once in the settings skeleton, config-gated off. Check: `uv run pytest -q tests/config/test_v4_settings_skeleton.py`

### Observability and documentation (OBS)

- [ ] OBS-01: Desk doctor reports event bus, source states, Grok budget windows, strategy stages, kills and signer attestation read-only. Check: `uv run pytest -q tests/test_doctor_v4.py`
- [ ] OBS-02: health.json and the metric families carry the event, strategy and promotion sections. Check: `uv run pytest -q tests/supervisor/test_metrics.py tests/desk/test_health_event_sections.py tests/desk/test_metrics_strategy.py`
- [ ] OBS-03: Alert rules cover dead letters, stale sources, Grok budget exhaustion, strategy kills and signer UNKNOWN, and name only metrics that exist. Check: `uv run pytest -q tests/docs/test_alert_rules.py`
- [ ] OBS-04: README, SETUP, CLAUDE, ARCHITECTURE, the affected skills and the new runbooks describe v4 and every documented command runs. Check: `./scripts/verify_doc_commands.sh && ./scripts/check.sh`
- [ ] OBS-05: A milestone audit traces every v4 requirement to evidence and records that live is still refused. Check: `test -f .planning/milestones/v4-MILESTONE-AUDIT.md && { uv run pumpgrok run --mode live --once; test $? -eq 3; }`
- [ ] OBS-06: The nightly event-mode soak passes with zero idle Grok calls and its golden hash. Check: `PUMPGROK_REQUIRE_SOAK=1 uv run pytest -q -m slow tests/soak/test_soak_event_mode.py`
- [ ] OBS-07: Daily and weekly reports carry a per-strategy section whose parts sum to the desk view. Check: `uv run pytest -q tests/reporting/test_strategy_section.py`

### Paper fee model (FEE)

- [ ] FEE-01: Paper fee model v2 (venue 100 bps plus the PumpPortal fee when that builder is used, ATA rent on the first buy of a mint, signer priority-fee cap) is selectable, and the default flip records a before and after trading-smoke pair. Check: `uv run pytest -q tests/execution/test_fee_model_v2.py tests/config/test_paper_fees_default.py`

### Event desk runtime (RT)

- [ ] RT-01: Event-mode seat cycle bodies exist for all ten seats and run on wakes. Check: `uv run pytest -q tests/desk/test_event_cycles.py tests/desk/test_event_cycles_aux.py`
- [ ] RT-02: Strategy Intents reach exec.place only through the router with ticket and approval allocation. Check: `uv run pytest -q tests/desk/test_intent_router.py tests/desk/test_ticket_approval_allocation.py`
- [ ] RT-03: The event desk composition root wires bus, sources, runtime, gateway, router and promotion edges and refuses to build unless paper. Check: `uv run pytest -q tests/desk/test_event_desk_e2e.py tests/desk/test_event_desk_idle.py`
- [ ] RT-04: Restart recovery re-arms deadlines and restores tapes, peaks, probation and the watch set. Check: `uv run pytest -q tests/strategies/test_recovery.py tests/desk/test_restart_recovery.py tests/desk/test_restart_exit_deadlines.py`

## Standing process rules from v3

PRC-01 (each phase closes with `make lint`, `make typecheck`, `make test`, `./scripts/check.sh`, the replay smoke command and a `.receipts/<seat>/<task>.json` receipt per completion claim) and PRC-02 (branch naming `bot-0N-<seat>/v4-pPHASE-slug`; merge through ultrathink-ship after green CI and the Greptile bar, per PROJECT V3-5) are closed v3 requirements that continue to apply to every v4 phase. They are cited in success criteria as (PRC-01) and are not recounted here.

## Merged requirement ids

Design A (EVT-11), design B (STR-02) and design C (RSK-07) each stated the same invariant, the unchanged smoke-10m `events.hash`. No plan carries them separately, so they are not requirements of this milestone; the invariant is enforced once, by PRC-03, at every phase close. The pin test lands in Phase 11 so the Phase 11 refactors have the safety net before they start. The gaps in the EVT, STR and RSK numbering are intentional.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Arming live trading, moving real funds, or any agent-run live action | Live stays DORMANT in v4. The path is built and tested but only a human arms it once, by the runbook, after the amendment is merged; no agent arms, extends or widens an arm record. Which strategy and parameter hash to arm first, and when, is a human decision outside v4. |
| Key material or signing code inside the desk package | The key lives only in the separate desk-signer process on a host the human provisions; the desk package keeps zero signing symbols (INV-S-01 tightened). |
| Applying the constitution amendment by an agent | Drafted for owner approval with errata E1 to E5 (OD-01); applied only by a human-approved pull request that the owner applies and merges (PRC-07). |
| External historical data or new data vendors | Data policy: self-recorded only (D8, AF-10). The recorder and importer never fabricate or back-fill evidence. |
| Paid RPC procurement or spend by an agent | A human may choose and record a provider (OD-05); no v4 code assumes one. Defaults use the public endpoint with a reduced watch set. |
| PumpPortal paid trade-stream key, subscribeTokenTrade, subscribeAccountTrade | Default no (R45); the live feed uses the one free keyless connection plus logsSubscribe on RPC. |
| New chains, new venues, or non-pump.fun markets; PumpSwap sells after curve completion | Solana pump.fun only. Live-eligible strategies exit before the curve completes (OD-08); the venue and fee builder is an interface (TxBuilder), not a second venue; direct pump instruction building is a later option behind that interface. |
| New LLM vendors or a second model provider | Grok through the single gateway only; no hosted evaluation service. |
| Strategies beyond legacy_screening, momentum_breakout, new_launch_sniper and mean_reversion | The four baseline strategies and bounded parameter promotion are in scope; further alpha research is a later milestone. |
| Flipping the default wake mode to event | wake_mode stays cadence through v4; the flip is decided in the next milestone after a week of live-paper evidence (OD-20). |
| Jito bundles or tips enabled by default | Signer fee policy is priority fee only; tips are an opt-in off by default. |
| Telegram live verification, G-4 consumer acknowledgements beyond the one additive contract, bot-06 exit roster change | Human actions outside the code. |
| Manual-ticket exit approval path (PAPER-007) | Deferred by owner decision 2026-10-23. |
| Web UI, multi-tenant, billing | Spec non-goals. |

## Traceability

Which phases cover which requirements. Populated from `plans.json`; each requirement maps to exactly one phase, the phase that proves it, although a plan of an earlier phase may land part of it (for example the RSK-08 pin lands in Phase 11 and is re-run in Phase 17).

| Requirement | Phase | Status |
|-------------|-------|--------|
| EVT-01 | Phase 12 Event runtime core | Pending |
| EVT-02 | Phase 12 Event runtime core | Pending |
| EVT-03 | Phase 12 Event runtime core | Pending |
| EVT-04 | Phase 12 Event runtime core | Pending |
| EVT-05 | Phase 12 Event runtime core | Pending |
| EVT-06 | Phase 12 Event runtime core | Pending |
| EVT-07 | Phase 12 Event runtime core | Pending |
| EVT-08 | Phase 14 Event-driven desk and Grok gateway | Pending |
| EVT-09 | Phase 12 Event runtime core | Pending |
| EVT-10 | Phase 14 Event-driven desk and Grok gateway | Pending |
| EVT-12 | Phase 14 Event-driven desk and Grok gateway | Pending |
| EVT-13 | Phase 14 Event-driven desk and Grok gateway | Pending |
| EVT-14 | Phase 12 Event runtime core | Pending |
| GRK-01 | Phase 14 Event-driven desk and Grok gateway | Pending |
| GRK-02 | Phase 14 Event-driven desk and Grok gateway | Pending |
| GRK-03 | Phase 14 Event-driven desk and Grok gateway | Pending |
| GRK-04 | Phase 14 Event-driven desk and Grok gateway | Pending |
| GRK-05 | Phase 14 Event-driven desk and Grok gateway | Pending |
| GRK-06 | Phase 14 Event-driven desk and Grok gateway | Pending |
| GRK-07 | Phase 14 Event-driven desk and Grok gateway | Pending |
| GRK-08 | Phase 14 Event-driven desk and Grok gateway | Pending |
| GRK-09 | Phase 14 Event-driven desk and Grok gateway | Pending |
| GRK-10 | Phase 14 Event-driven desk and Grok gateway | Pending |
| GRK-11 | Phase 14 Event-driven desk and Grok gateway | Pending |
| MKT-01 | Phase 13 Curve truth, live market data and recorder | Pending |
| MKT-02 | Phase 13 Curve truth, live market data and recorder | Pending |
| MKT-03 | Phase 13 Curve truth, live market data and recorder | Pending |
| MKT-04 | Phase 13 Curve truth, live market data and recorder | Pending |
| MKT-05 | Phase 13 Curve truth, live market data and recorder | Pending |
| MKT-06 | Phase 13 Curve truth, live market data and recorder | Pending |
| MKT-07 | Phase 13 Curve truth, live market data and recorder | Pending |
| MKT-08 | Phase 13 Curve truth, live market data and recorder | Pending |
| MKT-09 | Phase 15 Strategy framework and multi-strategy paper | Pending |
| MKT-10 | Phase 13 Curve truth, live market data and recorder | Pending |
| REC-01 | Phase 13 Curve truth, live market data and recorder | Pending |
| REC-02 | Phase 13 Curve truth, live market data and recorder | Pending |
| REC-03 | Phase 16 Backtest v2 and autonomous evaluation | Pending |
| STR-01 | Phase 15 Strategy framework and multi-strategy paper | Pending |
| STR-03 | Phase 15 Strategy framework and multi-strategy paper | Pending |
| STR-04 | Phase 15 Strategy framework and multi-strategy paper | Pending |
| STR-05 | Phase 15 Strategy framework and multi-strategy paper | Pending |
| STR-06 | Phase 15 Strategy framework and multi-strategy paper | Pending |
| BT-08 | Phase 16 Backtest v2 and autonomous evaluation | Pending |
| BT-09 | Phase 16 Backtest v2 and autonomous evaluation | Pending |
| BT-10 | Phase 16 Backtest v2 and autonomous evaluation | Pending |
| BT-11 | Phase 16 Backtest v2 and autonomous evaluation | Pending |
| BT-12 | Phase 16 Backtest v2 and autonomous evaluation | Pending |
| BT-13 | Phase 16 Backtest v2 and autonomous evaluation | Pending |
| RSK-01 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| RSK-02 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| RSK-03 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| RSK-04 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| RSK-05 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| RSK-06 | Phase 18 Dormant live path, amendment-gated | Pending |
| RSK-08 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| RSK-09 | Phase 18 Dormant live path, amendment-gated | Pending |
| PRM-01 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| PRM-02 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| PRM-03 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| PRM-04 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| PRM-05 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| PRM-06 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| LIV-03 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-04 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-05 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-06 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-07 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-08 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-09 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-10 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-11 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-12 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-13 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-14 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-15 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-16 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-17 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-18 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-19 | Phase 18 Dormant live path, amendment-gated | Pending |
| LIV-20 | Phase 18 Dormant live path, amendment-gated | Pending |
| QLT-01 | Phase 11 Engineering foundation and quality | Pending |
| QLT-02 | Phase 11 Engineering foundation and quality | Pending |
| QLT-03 | Phase 11 Engineering foundation and quality | Pending |
| QLT-04 | Phase 11 Engineering foundation and quality | Pending |
| QLT-05 | Phase 11 Engineering foundation and quality | Pending |
| QLT-06 | Phase 11 Engineering foundation and quality | Pending |
| QLT-07 | Phase 11 Engineering foundation and quality | Pending |
| QLT-08 | Phase 11 Engineering foundation and quality | Pending |
| QLT-09 | Phase 11 Engineering foundation and quality | Pending |
| QLT-10 | Phase 11 Engineering foundation and quality | Pending |
| PRC-03 | Phase 11 Engineering foundation and quality | Pending |
| PRC-04 | Phase 11 Engineering foundation and quality | Pending |
| PRC-05 | Phase 11 Engineering foundation and quality | Pending |
| PRC-06 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| PRC-07 | Phase 18 Dormant live path, amendment-gated | Pending |
| PRC-08 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| PRC-09 | Phase 11 Engineering foundation and quality | Pending |
| PRC-10 | Phase 11 Engineering foundation and quality | Pending |
| PRC-11 | Phase 12 Event runtime core | Pending |
| OBS-01 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| OBS-02 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| OBS-03 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| OBS-04 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| OBS-05 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| OBS-06 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| OBS-07 | Phase 16 Backtest v2 and autonomous evaluation | Pending |
| FEE-01 | Phase 15 Strategy framework and multi-strategy paper | Pending |
| RT-01 | Phase 14 Event-driven desk and Grok gateway | Pending |
| RT-02 | Phase 15 Strategy framework and multi-strategy paper | Pending |
| RT-03 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| RT-04 | Phase 17 Risk hardening and promotion lifecycle | Pending |

**Coverage: v4 requirements: 111 total, 111 mapped, 0 unmapped**

| Phase | Requirements |
|-------|--------------|
| 11 Engineering foundation and quality | 15 |
| 12 Event runtime core | 10 |
| 13 Curve truth, live market data and recorder | 11 |
| 14 Event-driven desk and Grok gateway | 16 |
| 15 Strategy framework and multi-strategy paper | 8 |
| 16 Backtest v2 and autonomous evaluation | 8 |
| 17 Risk hardening and promotion lifecycle | 14 |
| 18 Dormant live path, amendment-gated | 21 |
| 19 Observability, docs, hardening and milestone audit | 8 |
