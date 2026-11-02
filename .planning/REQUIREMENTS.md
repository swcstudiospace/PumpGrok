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

### Grok operator onboarding (ONB)

- [ ] ONB-01: The onboarding inventory lists every operator input in the table above with a required, optional, forbidden or not-read value for paper and for live, and a snapshot test pins the table. Check: `uv run pytest -q tests/onboarding/test_input_inventory.py`
- [ ] ONB-02: `doctor --json --mode <paper|live>` prints one record per input with name, required_for_mode, status and source (env, config, ledger, default or none), and exits non-zero when a required input is missing or a forbidden input is present for the requested mode. Check: `{ env -i PATH="$PATH" HOME="$HOME" uv run pumpgrok doctor --json --mode live >/dev/null; test $? -ne 0; } && uv run pytest -q tests/onboarding/test_doctor_json.py`
- [ ] ONB-03: `run --mode paper` refuses to start, exits non-zero and names each missing required input, until the required paper inputs are complete and every enabled seat has a recorded access decision. Check: `{ env -i PATH="$PATH" HOME="$HOME" uv run pumpgrok run --mode paper --once >/dev/null 2>&1; test $? -ne 0; } && uv run pytest -q tests/onboarding/test_paper_start_gate.py`
- [ ] ONB-04: Each seat's tool access is listed from its tool roster for operator approval, and a grant exists only as an operator-choice row in the ledger, so no seat has a grant by default. Check: `uv run pytest -q tests/onboarding/test_access_approval.py`
- [ ] ONB-05: No secret value is echoed, stored, logged or written to the ledger, and doctor, run and onboarding rows report only presence and source, as shown by a sentinel-value test over stdout, stderr, the log output and the ledger file. Check: `uv run pytest -q tests/onboarding/test_no_secret_echo.py`
- [ ] ONB-06: A wallet public address is accepted only when it base58-decodes to exactly 32 bytes and passes an Ed25519 curve-point check, and a refusal names the field without echoing the value. Check: `uv run pytest -q tests/onboarding/test_wallet_address.py`
- [ ] ONB-07: Paper needs no wallet, so the wallet field is never read on the paper path and a paper start with no address, or with a malformed one, is not blocked by it. Check: `uv run pytest -q tests/onboarding/test_paper_no_wallet.py`
- [ ] ONB-08: The RPC endpoint is recorded as an explicit operator choice by host only (scheme, host and port, never path, query, userinfo or key), and with no recorded choice doctor reports the public endpoint as status default and does not record it as a choice. Check: `uv run pytest -q tests/onboarding/test_rpc_choice.py`
- [ ] ONB-09: When any Grok seat is enabled the x.ai key is a required input for paper and live, an empty value counts as missing, and no request is ever sent with an empty bearer. Check: `uv run pytest -q tests/onboarding/test_grok_key_required.py`
- [ ] ONB-10: In a live desk environment the HMAC confirmation key is a forbidden input, so doctor reports it present or absent by name and source only, and a present key fails the live onboarding check. Check: `uv run pytest -q tests/onboarding/test_hmac_forbidden.py`

- Dedupe: requirement IDs ONB-01 to ONB-10 are not audit findings; finding IDs ONB-01 to ONB-06 are named explicitly below.
- Dedupe ONB-01 (finding): kept here in ONB-06 and ONB-07; HARD-18 is removed.
- Dedupe ONB-02 (finding, SEC-04): stays in HARD-19; ONB-10 is the HMAC presence check (LIV-11) and claims no finding ID.
- Dedupe ONB-03 (finding): kept here in ONB-09; HARD-20 is removed.
- Dedupe ONB-04 (finding): kept here in ONB-02; HARD-21 is removed.
- Dedupe ONB-05 (finding): kept here in ONB-08; HARD-22 is removed.
- Dedupe ONB-06 (finding): kept here in ONB-01, ONB-03 and ONB-04; HARD-23 is removed.
- ONB-01 refers to the input table in the ONB draft (archive/v4-families-drafts/ONB.md); that table is not copied into this file.

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

### Hardening (HARD)

- [ ] HARD-01: Settings loading refuses any non-default min_total_score or scoring weight in every overlay, including live.toml, with a ConfigError that names the key, until a decision-path reader consumes it. Check: `uv run pytest -q tests/hardening/test_scoring_knobs_refused.py`
- [ ] HARD-02: Every broad except in src/pumpgrok/supervisor/ is narrowed to typed exceptions and each remaining handler logs with exc_info, as an AST guard over that package asserts. Check: `uv run pytest -q tests/hardening/test_supervisor_excepts.py`
- [ ] HARD-03: Import-linter fails when risk imports engine or execution imports tools, and importing the tools package no longer loads the full tool registry. Check: `uv run pytest -q tests/hardening/test_layering_contracts.py`
- [ ] HARD-04 (owner confirmation pending): `pumpgrok upgrade rollback` restores the prior active set in one command, exits 0 and writes a ledger row, as a CLI test asserts. Check: `uv run pytest -q tests/hardening/test_rollback_verb.py`
- [ ] HARD-05: Each module listed in ARCH-05 is either wired to a production importer or deleted, and an AST test fails on any src/pumpgrok module with no non-test importer that is not on an explicit empty allowlist. Check: `uv run pytest -q tests/hardening/test_no_orphan_modules.py`
- [ ] HARD-06: The 60-line function-size guard covers every target directory under src/pumpgrok, and any function over 60 lines that is absent from a shrink-only allowlist (including _build_serve, 113 lines) fails the test. Check: `uv run pytest -q tests/hardening/test_function_size_all_dirs.py`
- [ ] HARD-07: A resumed serve after a crash between OrderPlaced and FillRecorded places no second sniper BUY and records no second simulated fill for the same (mint, candidate), as a resumed-serve test asserts. Check: `uv run pytest -q tests/hardening/test_resume_buy_idempotent.py`
- [ ] HARD-08: Opening-equity and snapshot rows are hash-chained, and ledger open refuses to start when the baseline row is missing instead of falling back to the budget default, as a test that deletes and edits the row asserts. Check: `uv run pytest -q tests/hardening/test_baseline_chain.py`
- [ ] HARD-09: An unreadable kill-latch file makes check() return a latch-unreadable verdict without raising, and exit and flatten sells remain permitted, as a test that makes the file unreadable asserts. Check: `uv run pytest -q tests/hardening/test_killswitch_unreadable.py`
- [ ] HARD-10: The live-promotion gate fails on any unparsable ledger row instead of skipping it and computes profit factor and drawdown with integer or Decimal ratios, as a test with a corrupt row asserts. Check: `uv run pytest -q tests/hardening/test_live_gate_rows.py`
- [ ] HARD-11: The float sizing API in risk/sizing.py is deleted and halt and export ratios use Decimal, as an AST scan of those modules asserts. Check: `uv run pytest -q tests/hardening/test_no_float_ratios.py`
- [ ] HARD-12: evaluate_halts raises InconsistentLedgerError on an inconsistent ledger instead of returning None, as a test of the replay-only caller asserts. Check: `uv run pytest -q tests/hardening/test_evaluate_halts_inconsistent.py`
- [ ] HARD-19: Live confirm stores the hash of the effective wallet allowlist and refuses to confirm when that allowlist is empty, as a test asserts the refusal's exit code. Check: `uv run pytest -q tests/hardening/test_live_confirm_binding.py`
- [ ] HARD-24: G-3 accepts only paths inside the repository or an allowlisted directory, runs its child process with a minimal environment and returns masked output only, as a test asserts that an outside path is refused and no gateway secret reaches the child. Check: `uv run pytest -q tests/hardening/test_receipt_check_containment.py`
- [ ] HARD-25: Startup refuses an RPC URL that carries a provider key in userinfo or path, httpx logging is capped at WARNING, and URL path segments that look like keys are redacted in logs, as a test asserts each. Check: `uv run pytest -q tests/hardening/test_rpc_key_redaction.py`
- [ ] HARD-26: Credentialed endpoints and webhook URLs must match a configured host allowlist and credentialed httpx clients are built with trust_env=False, as a test asserts that a non-allowlisted host is refused. Check: `uv run pytest -q tests/hardening/test_credentialed_endpoints.py`
- [ ] HARD-30: The G-2 bypass pattern refuses a receipt whose command contains --collect-only, as a test with that receipt asserts a non-zero exit. Check: `uv run pytest -q ci/tests/test_check_receipt_bypass.py`
- [ ] HARD-31: G-2 re-executes each receipt command in CI and fails when the re-run exit code differs from the recorded one, as a fixture test asserts a non-zero exit on mismatch. Check: `uv run pytest -q ci/tests/test_check_receipt_reexec.py`
- [ ] HARD-32: G-3 skips only the top-level paths in an anchored allowlist and no inline pragma skips a line, as a test asserts that a secret under build/ and a secret on a pragma line are both reported. Check: `uv run pytest -q ci/tests/test_check_secrets_skips.py`
- [ ] HARD-33: gates.yml fails on git errors in the receipt-lookup and change-detection steps with no or-true masking, and the G-2 bypass scan covers gates.yml, as a test asserts both. Check: `uv run pytest -q ci/tests/test_gates_yml_no_mask.py`

- Dedupe HARD-13: finding HR-01 is kept in HOST-04 (health and runtime scope).
- Dedupe HARD-14: finding HR-03 is kept in HOST-06 (shutdown and runtime scope).
- Dedupe HARD-15: finding HR-04 is kept in HOST-07 (ledger state scope; HOST-07 also verifies before replacing).
- Dedupe HARD-16: finding HR-05 is kept in HOST-03 and HOST-05 (probes and routes).
- Dedupe HARD-17: finding HR-06 is kept in HOST-01 and HOST-02 (state directory and volume).
- Dedupe HARD-18: finding ONB-01 is kept in ONB-06 and ONB-07 (wallet input scope).
- Dedupe HARD-20: finding ONB-03 is kept in ONB-09 (x.ai key is an input); the draft's .env.example comment fix has no line in this plan.
- Dedupe HARD-21: finding ONB-04 is kept in ONB-02 (doctor required inputs and non-zero exit).
- Dedupe HARD-22: finding ONB-05 is kept in ONB-08 (RPC endpoint choice).
- Dedupe HARD-23: finding ONB-06 is kept in ONB-01, ONB-03 and ONB-04; ONB-02 already gives doctor --json, so the machine-readable half is not repeated.
- Dedupe HARD-27: finding SEC-06 is kept in HOST-09 and HOST-10 (gateway exposure).
- Dedupe HARD-28: finding SEC-07 is kept in HOST-13 and HOST-14 (container and secrets).
- Dedupe HARD-29: finding SEC-08 is kept in HOST-05, HOST-11 and HOST-12 (health server).
- Constraint on HARD-19: the HMAC key minimum-length clause is removed because the desk holds no HMAC value (ONB-10, LIV-11); the 32-byte floor belongs to the signer under LIV-04 and LIV-08 (Phase 18) and is not added here.
- Finding ONB-02 (SEC-04) stays in HARD-19 for the allowlist hash and the empty-allowlist refusal; ONB-10 covers the HMAC presence check and claims no finding ID.

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

### Hosted runtime (HOST)

- [ ] HOST-01: PUMPGROK_STATE_DIR must be an absolute path; a relative or empty value is refused at startup, and the ledger, desk, replay and reputation paths all resolve under that one directory with none left cwd-relative. Check: `uv run pytest -q tests/hosted/test_state_dir.py`
- [ ] HOST-02: The compose desk service mounts one named volume at the state directory and no host bind mount for state. Precondition: the named volume is not enabled until the F1 resume defect is closed (HARD-07 passes). Check: `uv run pytest -q tests/hosted/test_compose_volume.py`
- [ ] HOST-03: /livez returns 200 while the process loop runs, whatever the halted or kill-switch state, and /readyz returns 503 when the last per-tick ledger verification failed or the tick is stale; a halted desk is 200 on both, with the halt shown in the body. Check: `uv run pytest -q tests/hosted/test_health_probes.py`
- [ ] HOST-04: The ledger_status in every health body comes from that tick's ledger verification and is never a constant, so a corrupted ledger reports a non-CONSISTENT status on the next tick. Check: `uv run pytest -q tests/hosted/test_health_ledger_status.py`
- [ ] HOST-05: The health server serves only /livez, /readyz and /metrics, /healthz is removed with every caller migrated, and any other path returns 404 with an empty body. Check: `uv run pytest -q tests/hosted/test_health_routes.py`
- [ ] HOST-06: A final snapshot, export or health write that fails during shutdown makes the process exit non-zero and records the failure in the final health output. Check: `uv run pytest -q tests/hosted/test_shutdown_exit.py`
- [ ] HOST-07: `pumpgrok ledger backup` writes a ledger copy, and `pumpgrok ledger restore` verifies the candidate's hash chain before atomically replacing the active file; a failed verification leaves the active file byte-identical and exits non-zero. Check: `uv run pytest -q tests/hosted/test_ledger_backup_restore.py`
- [ ] HOST-08: PUMPGROK_LOG_LEVEL accepts only DEBUG, INFO, WARNING or ERROR, any other value is refused at startup, and log output is JSON in every profile. Check: `uv run pytest -q tests/hosted/test_log_config.py`
- [ ] HOST-09: The gateway refuses a non-loopback bind unless a TLS or reverse-proxy flag is set, and the refusal exits non-zero before the gateway serves any request. Check: `uv run pytest -q tests/hosted/test_gateway_bind.py`
- [ ] HOST-10: The gateway refuses a bearer token shorter than 32 bytes and refuses startup when two configured tokens are equal. Check: `uv run pytest -q tests/hosted/test_gateway_tokens.py`
- [ ] HOST-11: The health server binds 127.0.0.1 by default in the container, and /metrics returns 401 without a configured token whenever the server binds beyond loopback. Check: `uv run pytest -q tests/hosted/test_health_bind.py`
- [ ] HOST-12: The health server closes any connection that has not sent a complete request within the configured read timeout (default 5 s). Check: `uv run pytest -q tests/hosted/test_health_read_timeout.py`
- [ ] HOST-13: Hosted secrets reach the desk container only as Docker secrets mounted under /run/secrets; the compose file has no env_file entry and no secret-valued environment entry. Check: `uv run pytest -q ci/tests/test_compose_docker_secrets.py`
- [ ] HOST-14: Every FROM image in the Dockerfile and every image in docker-compose.yml is pinned by sha256 digest. Check: `uv run pytest -q ci/tests/test_image_digest_pins.py`
- [ ] HOST-15: Every health body and metric family from a hosted replay run (/livez, /readyz, /metrics) carries a replay-demo label (replay_demo true, ledger_source replay) until live-data paper lands, and the label cannot be false before then. Check: `uv run pytest -q tests/hosted/test_replay_demo_label.py`

- Dedupe: findings HR-01, HR-03 to HR-06, SEC-06, SEC-07 and SEC-08 are held here; their HARD duplicates (HARD-13 to HARD-17, HARD-27 to HARD-29) are removed, see Hardening (HARD).
- Dedupe: HOST-15 (replay-demo label, finding HR-02) is kept because the audit's HR-02 row is only partially covered by MKT-09 and REC-03, and REC-03 does not scope the image.
- Scope: this family does not build, push or deploy an image without owner approval.

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
| ONB-01 | Phase 14 Event-driven desk and Grok gateway | Pending |
| ONB-02 | Phase 14 Event-driven desk and Grok gateway | Pending |
| ONB-03 | Phase 14 Event-driven desk and Grok gateway | Pending |
| ONB-04 | Phase 14 Event-driven desk and Grok gateway | Pending |
| ONB-05 | Phase 14 Event-driven desk and Grok gateway | Pending |
| ONB-06 | Phase 14 Event-driven desk and Grok gateway | Pending |
| ONB-07 | Phase 14 Event-driven desk and Grok gateway | Pending |
| ONB-08 | Phase 14 Event-driven desk and Grok gateway | Pending |
| ONB-09 | Phase 14 Event-driven desk and Grok gateway | Pending |
| ONB-10 | Phase 14 Event-driven desk and Grok gateway | Pending |
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
| HARD-01 | Phase 11 Engineering foundation and quality | Pending |
| HARD-02 | Phase 11 Engineering foundation and quality | Pending |
| HARD-03 | Phase 11 Engineering foundation and quality | Pending |
| HARD-04 | Phase 11 Engineering foundation and quality | Pending |
| HARD-05 | Phase 11 Engineering foundation and quality | Pending |
| HARD-06 | Phase 11 Engineering foundation and quality | Pending |
| HARD-07 | Phase 11 Engineering foundation and quality | Pending |
| HARD-08 | Phase 11 Engineering foundation and quality | Pending |
| HARD-09 | Phase 11 Engineering foundation and quality | Pending |
| HARD-10 | Phase 11 Engineering foundation and quality | Pending |
| HARD-11 | Phase 11 Engineering foundation and quality | Pending |
| HARD-12 | Phase 11 Engineering foundation and quality | Pending |
| HARD-19 | Phase 11 Engineering foundation and quality | Pending |
| HARD-24 | Phase 11 Engineering foundation and quality | Pending |
| HARD-25 | Phase 11 Engineering foundation and quality | Pending |
| HARD-26 | Phase 11 Engineering foundation and quality | Pending |
| HARD-30 | Phase 11 Engineering foundation and quality | Pending |
| HARD-31 | Phase 11 Engineering foundation and quality | Pending |
| HARD-32 | Phase 11 Engineering foundation and quality | Pending |
| HARD-33 | Phase 11 Engineering foundation and quality | Pending |
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
| HOST-01 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-02 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-03 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-04 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-05 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-06 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-07 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-08 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-09 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-10 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-11 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-12 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-13 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-14 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| HOST-15 | Phase 19 Observability, docs, hardening and milestone audit | Pending |
| FEE-01 | Phase 15 Strategy framework and multi-strategy paper | Pending |
| RT-01 | Phase 14 Event-driven desk and Grok gateway | Pending |
| RT-02 | Phase 15 Strategy framework and multi-strategy paper | Pending |
| RT-03 | Phase 17 Risk hardening and promotion lifecycle | Pending |
| RT-04 | Phase 17 Risk hardening and promotion lifecycle | Pending |

**Coverage: v4 requirements: 156 total, 156 mapped, 0 unmapped**

| Phase | Requirements |
|-------|--------------|
| 11 Engineering foundation and quality | 35 |
| 12 Event runtime core | 10 |
| 13 Curve truth, live market data and recorder | 11 |
| 14 Event-driven desk and Grok gateway | 26 |
| 15 Strategy framework and multi-strategy paper | 8 |
| 16 Backtest v2 and autonomous evaluation | 8 |
| 17 Risk hardening and promotion lifecycle | 14 |
| 18 Dormant live path, amendment-gated | 21 |
| 19 Observability, docs, hardening and milestone audit | 23 |
