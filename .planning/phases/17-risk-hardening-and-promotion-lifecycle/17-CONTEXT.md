# Phase 17 Context: Risk hardening and promotion lifecycle

Status: discussed 2026-11-18. The owner accepted every grey-area default (HTIL, 2026-11-18). No code yet.
Requirements: RSK-01, RSK-02, RSK-03, RSK-04, RSK-05, RSK-08, PRM-01 to PRM-06, RT-03, RT-04 (ROADMAP.md Phase 17; REQUIREMENTS.md).
Plans: 17-01 to 17-07 in six waves. The plan list of record is in ROADMAP.md; plan contents come from the planning step.

## Decisions

D17-1 Criterion 13 pin literal. The before and after lines use smoke-10m events.hash 1dffa784... (the repo pin, tests/replay/pin_support.py:37; CHANGELOG Phase 16 hash lines). The b69c29... literal named in the Phase 17 criterion 13 is absent from code, tests, Makefile and scripts. The trading-smoke pin a4461e80... is unchanged.

D17-2 Criterion 1 (paper smoke checkpoint, `run --mode paper --once --replay tests/fixtures/replay/smoke`). Recorded deferral to deployment, as for Phases 14 to 16. The operator authority is absent in this checkout, so the smoke exits 1 here.

D17-3 Promotion evidence (PRM-01 to PRM-03).
- A zero-loss paper record is unmet. execution/live/live_gate.py:212 yields profit factor inf for gains with no losses, and inf passes MIN_PROFIT_FACTOR. Promotion must not inherit that pass. LiveGate stays unchanged in this phase; the live gate rows belong to Phase 18.
- Promotion thresholds load from config/promotion_thresholds.toml and equal the LiveGate floors: MIN_PAPER_DAYS 14, MIN_CLOSED_TRADES 50, MIN_PROFIT_FACTOR 1.2, MAX_DRAWDOWN_FRACTION 0.15 (live_gate.py:33-36). A looser value refuses to load.
- The paper window starts at each strategy's first paper fill. LiveGate uses the desk's first paper row (live_gate.py, _paper_days).

D17-4 Strategy exposure slice (RSK-01). Enforced on the existing R34 row max_token_fraction (default 0.05; core/risk_budget.py:24-31), applied per strategy. STEP_IDS stays at 19 entries (risk/engine/constants.py:9-29). risk_json shape unchanged (RSK-08).

D17-5 Strategy kill and kill clear (RSK-02).
- A kill is written to and read from the ledger.
- Clear is human-only: cleared_by starts with `human:` and is not a seat id (killswitch.py, request_clear).
- Today request_clear refuses while the latch file exists (killswitch.py:372-373, 399-401), and nothing deletes that file. The clear verb removes the latch after the KillSwitchCleared row is written, and it uses the existing human approval phrase path (core/approvals.py:157-197).

D17-6 Entry checks (RSK-05, RSK-06).
- Reject: mint or freeze authority present; Token-2022 PermanentDelegate, TransferHook or NonTransferable extension; top-10 holder concentration at or above the fail threshold of 25% (warn 20%; config/sections/engine.py:69-70); BLIND status.
- Warn only: other Token-2022 extensions. tools/safety/checks/readers.py:99-112 warns on any extension today.
- config/mint_lists.toml (new) starts empty and fails closed when missing.
- The safety checks gate nothing today; the entry-gate hook must consume them.

D17-7 Restart state (RT-04). Rebuild exit deadlines, tapes, probation and the watch set from the ledger on restart. Add ledger rows only where a rebuild is impossible. No change under contracts/: criterion 12 requires `git diff --name-only v4-base -- contracts` to stay empty (v4-base tag 09f83beb).

## Verified evidence (direct checks, 2026-11-18)
- Absent: supervisor/event_desk.py, supervisor/recovery.py, risk/strategy_slice.py, risk/entry_checks.py, risk/feed_health.py, config/mint_lists.toml, the promotion/ package, tests/promotion/, tests/desk/test_event_desk_e2e.py, tests/desk/test_event_desk_idle.py, tests/desk/test_restart_recovery.py, tests/desk/test_restart_exit_deadlines.py, tests/desk/test_live_paper_risk_wiring.py, and the risk and safety test files named in the criteria.
- Present: EventBus events/bus.py:54; GrokGateway grok/gateway.py:212; StrategyRuntime strategies/runtime.py:44; IntentRouter supervisor/intent_router.py:70; ReplayRuntime supervisor/scheduler/replay_runtime.py:171; tests/execution/test_entry_gate_hook.py; tests/strategies/test_recovery.py; tests/desk holds 21 test files.
- Breakers: DATA_STALE_S 120, DATA_STALE_MISSES 3, DATA_STALE_COOLDOWN_S 60 (risk/breakers.py:48-50); EXEC_ERRORS_REJECTS 3, window 600 s, cooldown 900 s (risk/breakers.py:63-65); blind_max_s 300 and mtm_interval_s 60 (risk/limits.py:29-30).
- Gaps: a never-ticked required feed does not fail closed (DataStaleBreaker); two of four exec_errors reason producers are missing; the UNKNOWN outcome (core/adapter.py:103; core/errors.py:97) feeds no halt; no refusal to build a non-paper desk (supervisor/scheduler/supervisor.py:172 only forces manual-ticket in live); exit deadlines, tapes, probation and the watch set are absent (peaks restore through supervisor/exit_rules.py:99-127).
- Name collision: cli/promotion.py already exists (the upgrade check, wired by cli/verbs_state.py:30 and :120). The new `promotion demote` verb and the new package must not reuse its names.
- Scout correction: DeskMap's negative claims about tests/desk, tests/strategies, the gateway and the intent router were wrong. They were rechecked directly and are not relied on.

## Seat ownership (ownership.yaml; last match wins)
- bot-02-risk: src/pumpgrok/risk/**, src/pumpgrok/ledger/**, src/pumpgrok/upgrade/**, src/pumpgrok/config/**, src/pumpgrok/promotion/** (general src/pumpgrok/** rule), tests/risk/**, tests/promotion/**, tests/upgrade/**, tests/safety/**.
- bot-00-chief: src/pumpgrok/supervisor/** (event_desk.py, recovery.py, live_paper.py), src/pumpgrok/cli.py, tests/desk/**, .planning/**.
- bot-04-sniper: src/pumpgrok/execution/** (ownership.yaml:310), tests/execution/**. execution/live/** has its own rule at ownership.yaml:312-315; the planning step reads it before assigning a branch.
- bot-09-journal: CHANGELOG.md.
The planning step verifies each path against ownership.yaml before it assigns a branch.

## Branch plan
- Units run on `bot-0N-<seat>/phase-17-<unit>` branches cut from `bot-00-chief/v4-phase-14`, one owning seat per branch (G-1).
- PRs are drafts against `bot-00-chief/v4-phase-14`. Agents do not merge. Phase 18 waits for all of Phase 17 to merge (owner answer q2).

## Open for the planning step
- Plan contents for 17-01 to 17-07 and their six waves.
- Linear sub-issues and Notion rows per plan, once plan titles exist.
- Sweep overlap: sweep fix units wait for Phase 17 merges on overlapping files (decided at sweep triage).
