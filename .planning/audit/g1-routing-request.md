# G1 routing request to CHIEF (PR 16 path ownership)

Source: `python3 ci/gates/run_all.py --bot bot-00-chief --base origin/main` on branch `bot-00-chief/phase-6-integrity`, run 2026-11-12. G-1 reports 192 FOREIGN paths. The audit's earlier figure of 170 is stale and superseded by this count.

Per protocol (docs/cross-bot-protocol.md), CHIEF routes each group to its owning seat. No foreign path is edited by bot-00-chief. Each owner decides whether its paths are re-homed, reviewed, or left out of PR 16.

| Owner seat | Foreign paths |
|---|---|
| bot-02-risk | 150 |
| bot-04-sniper | 13 |
| bot-08-signal | 12 |
| bot-05-rug | 9 |
| bot-09-journal | 3 |
| bot-01-scout | 3 |
| bot-06-exit | 2 |

## bot-01-scout
- `src/pumpgrok/engine/monitor.py`
- `src/pumpgrok/tools/market/trades.py`
- `tests/characterization/test_monitor.py`

## bot-02-risk
- `.github/workflows/gates.yml`
- `.gitignore`
- `AGENTS.md`
- `ARCHITECTURE.md`
- `CLAUDE.md`
- `ci/tests/test_review_infra.py`
- `docs/CURVE_LAYOUT_PROBE.md`
- `docs/DISCOVERY.md`
- `docs/LIVE_READINESS.md`
- `docs/MIGRATION_MAP.md`
- `docs/RISK_POLICY.md`
- `docs/TOOL_CATALOG.md`
- `docs/VENDOR_PIN.md`
- `docs/design/interfaces.md`
- `docs/upgrade-plan-desk-v2.md`
- `prompts/_shared/core-directives.xml`
- `prompts/bot-02-risk.xml`
- `rules/pumpgrok-team.mdc`
- `src/pumpgrok/backtest/__init__.py`
- `src/pumpgrok/backtest/candidate.py`
- `src/pumpgrok/backtest/divergence.py`
- `src/pumpgrok/backtest/evaluate.py`
- `src/pumpgrok/backtest/harness.py`
- `src/pumpgrok/backtest/manifest.py`
- `src/pumpgrok/backtest/metrics.py`
- `src/pumpgrok/backtest/report.py`
- `src/pumpgrok/backtest/results.py`
- `src/pumpgrok/backtest/split.py`
- `src/pumpgrok/backtest/trials.py`
- `src/pumpgrok/cli/__init__.py`
- `src/pumpgrok/cli/backtest.py`
- `src/pumpgrok/cli/codes.py`
- `src/pumpgrok/cli/dispatch.py`
- `src/pumpgrok/cli/errors.py`
- `src/pumpgrok/cli/parsing.py`
- `src/pumpgrok/cli/promotion.py`
- `src/pumpgrok/cli/validators.py`
- `src/pumpgrok/cli/verbs_ops.py`
- `src/pumpgrok/cli/verbs_state.py`
- `src/pumpgrok/cli/wiring.py`
- `src/pumpgrok/config/settings.py`
- `src/pumpgrok/config/upgrade_bounds.toml`
- `src/pumpgrok/config/upgrade_space.toml`
- `src/pumpgrok/core/__init__.py`
- `src/pumpgrok/core/approvals.py`
- `src/pumpgrok/core/errors.py`
- `src/pumpgrok/core/ids.py`
- `src/pumpgrok/core/registry.py`
- `src/pumpgrok/core/risk_budget.py`
- `src/pumpgrok/core/units.py`
- `src/pumpgrok/execution/live/live_adapter.py`
- `src/pumpgrok/execution/live/live_gate.py`
- `src/pumpgrok/ledger/active_set.py`
- `src/pumpgrok/ledger/export.py`
- `src/pumpgrok/ledger/reducer.py`
- `src/pumpgrok/replay/runner.py`
- `src/pumpgrok/risk/__init__.py`
- `src/pumpgrok/risk/engine.py`
- `src/pumpgrok/risk/engine/__init__.py`
- `src/pumpgrok/risk/engine/constants.py`
- `src/pumpgrok/risk/engine/core.py`
- `src/pumpgrok/risk/engine/model.py`
- `src/pumpgrok/risk/engine/steps.py`
- `src/pumpgrok/risk/sizing.py`
- `src/pumpgrok/tools/__init__.py`
- `src/pumpgrok/tools/_common.py`
- `src/pumpgrok/upgrade/__init__.py`
- `src/pumpgrok/upgrade/bounds.py`
- `src/pumpgrok/upgrade/escalate.py`
- `src/pumpgrok/upgrade/evidence.py`
- `src/pumpgrok/upgrade/gate.py`
- `src/pumpgrok/upgrade/params.py`
- `src/pumpgrok/upgrade/rollback.py`
- `src/pumpgrok/upgrade/scheduled.py`
- `src/pumpgrok/upgrade/space.py`
- `tests/backtest/__init__.py`
- `tests/backtest/test_divergence.py`
- `tests/backtest/test_evaluator.py`
- `tests/backtest/test_holdout_split.py`
- `tests/backtest/test_metrics.py`
- `tests/backtest/test_replay_result_fields.py`
- `tests/backtest/test_report_render.py`
- `tests/backtest/test_review_round1_core.py`
- `tests/backtest/test_review_round1_settings.py`
- `tests/backtest/test_run_manifest.py`
- `tests/backtest/test_shared_result_schema.py`
- `tests/backtest/test_single_search_engine.py`
- `tests/backtest/test_trial_limits.py`
- `tests/characterization/test_vendor_log.py`
- `tests/cli/test_backtest_review_round1.py`
- `tests/cli/test_review_trade_prices.py`
- `tests/docs/test_doc_consistency.py`
- `tests/docs/test_historical_banners.py`
- `tests/docs/test_verify_doc_commands_offline.py`
- `tests/e2e/test_autonomous_paper_recorded.py`
- `tests/fixtures/rpc/bonding_curve/probe.json`
- `tests/integrity/__init__.py`
- `tests/integrity/test_analyzer_sol_conversion_shared.py`
- `tests/integrity/test_daily_loss_integer.py`
- `tests/integrity/test_fail_closed_state.py`
- `tests/integrity/test_function_length.py`
- `tests/integrity/test_ledger_mark_fee_partial_sell.py`
- `tests/integrity/test_live_gate_clock.py`
- `tests/integrity/test_money_types.py`
- `tests/integrity/test_paper_genesis_meta.py`
- `tests/integrity/test_peaks_survive_restart.py`
- `tests/integrity/test_rng_roots.py`
- `tests/integrity/test_serve_restart_keeps_peaks.py`
- `tests/integrity/test_single_sol_conversion.py`
- `tests/integrity/test_wr07_replay_ledger_removed.py`
- `tests/ledger/test_active_set_applied_at_startup.py`
- `tests/ledger/test_store_batch.py`
- `tests/risk/test_engine.py`
- `tests/safety/amendment_2026_10_25_frozen.txt`
- `tests/safety/test_blind_advisory.py`
- `tests/safety/test_constitution_amendment.py`
- `tests/safety/test_constitution_constants.py`
- `tests/safety/test_import_graph_no_live.py`
- `tests/safety/test_live_adapter_raises.py`
- `tests/safety/test_live_disabled_overlays.py`
- `tests/safety/test_live_gate_wallet_cap.py`
- `tests/safety/test_live_refusal_lists_nine.py`
- `tests/safety/test_manual_ticket_no_upgrade.py`
- `tests/safety/test_no_backtest_to_live_path.py`
- `tests/safety/test_no_live_adapter_registered.py`
- `tests/safety/test_provider_startup_env.py`
- `tests/safety/test_reputation_degraded.py`
- `tests/safety/test_static_guards.py`
- `tests/safety/test_wallet_allowlist_settings.py`
- `tests/soak/test_soak_multiday_replay.py`
- `tests/supervisor/test_latch_rebuild.py`
- `tests/supervisor/test_lifecycle.py`
- `tests/supervisor/test_restarts.py`
- `tests/supervisor/test_review_scheduler.py`
- `tests/supervisor/test_review_seat_task.py`
- `tests/supervisor/test_supervisor_bounded_restart.py`
- `tests/test_live_gate.py`
- `tests/test_tools_cli.py`
- `tests/tools/test_genesis_fail_closed.py`
- `tests/tools/test_verb_coverage.py`
- `tests/upgrade/__init__.py`
- `tests/upgrade/test_active_set_ledger.py`
- `tests/upgrade/test_escalation.py`
- `tests/upgrade/test_evidence_no_overwrite.py`
- `tests/upgrade/test_no_live_imports.py`
- `tests/upgrade/test_param_set_hash.py`
- `tests/upgrade/test_promotion_evidence.py`
- `tests/upgrade/test_promotion_gate.py`
- `tests/upgrade/test_rollback_exact.py`
- `tests/upgrade/test_scheduled_promotion.py`

## bot-04-sniper
- `docs/design/paper-engine.md`
- `src/pumpgrok/execution/paper_adapter.py`
- `src/pumpgrok/execution/paper_adapter/__init__.py`
- `src/pumpgrok/execution/paper_adapter/adapter.py`
- `src/pumpgrok/execution/paper_adapter/batch.py`
- `src/pumpgrok/execution/paper_adapter/buy.py`
- `src/pumpgrok/execution/paper_adapter/confirm.py`
- `src/pumpgrok/execution/paper_adapter/marks.py`
- `src/pumpgrok/execution/paper_adapter/models.py`
- `src/pumpgrok/execution/paper_adapter/quote.py`
- `src/pumpgrok/execution/paper_adapter/sell.py`
- `tests/execution/test_live_gate_fails_fast.py`
- `tests/execution/test_live_gate_ledger_path.py`

## bot-05-rug
- `src/pumpgrok/engine/watcher.py`
- `src/pumpgrok/tools/onchain/curve_layout.py`
- `src/pumpgrok/tools/onchain/deployer_history.py`
- `src/pumpgrok/tools/onchain/rpc.py`
- `src/pumpgrok/tools/safety/checks/__init__.py`
- `src/pumpgrok/tools/safety/provider.py`
- `src/pumpgrok/tools/safety/score_report.py`
- `tests/characterization/test_watcher.py`
- `tests/tools/safety/test_score_report.py`

## bot-06-exit
- `src/pumpgrok/engine/exits.py`
- `tests/characterization/test_exits.py`

## bot-08-signal
- `skills/replay-and-backtest/SKILL.md`
- `src/pumpgrok/engine/__init__.py`
- `src/pumpgrok/engine/agents/auditor.py`
- `src/pumpgrok/engine/analyzer.py`
- `src/pumpgrok/engine/models.py`
- `src/pumpgrok/engine/pipeline.py`
- `src/pumpgrok/engine/reputation.py`
- `src/pumpgrok/engine/tune.py`
- `tests/characterization/test_analyzer.py`
- `tests/characterization/test_pipeline.py`
- `tests/characterization/test_reputation.py`
- `tests/characterization/test_tune.py`

## bot-09-journal
- `CHANGELOG.md`
- `src/pumpgrok/reporting/render.py`
- `src/pumpgrok/reporting/weekly.py`

## Ask

1. Each owner confirms whether its listed paths belong in PR 16. 2. Paths confirmed as out of scope are removed from PR 16 by CHIEF. 3. Paths confirmed as in scope are re-homed through the owner's own seat branch, not committed from bot-00-chief. This request does not waive G-1.
