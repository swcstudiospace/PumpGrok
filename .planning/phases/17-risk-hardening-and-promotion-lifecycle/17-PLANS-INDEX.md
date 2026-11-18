# Phase 17 plans index: Risk hardening and promotion lifecycle

Status: plan set revised for the confirmed sweep fixes and the IRC decisions from Main. Owner decisions D17-1 to D17-7 (17-CONTEXT.md, 2026-11-18) remain binding. The ROADMAP is not edited here. This revision changed 17-01, 17-02 and this index. 17-03 to 17-07 are unchanged in this round.

Sources of truth:
- `17-CONTEXT.md` in this directory: decisions, verified evidence, seat map.
- `.planning/ROADMAP.md` Phase 17 block: goal, criteria 1 to 14, deliverables, plan ids 17-01 to 17-07.
- `.planning/REQUIREMENTS.md`: RSK rows (lines 99 to 106; traceability lines 337 to 344), PRM rows (lines 110 to 115), RT-03 and RT-04 (lines 243 and 244), PRC-03 (line 192).
- `ownership.yaml`, last matching rule wins. Owners resolved by hand: `src/pumpgrok/**` is bot-02-risk unless a later rule overrides it; `src/pumpgrok/supervisor/**` is bot-00-chief; `src/pumpgrok/execution/**` is bot-04-sniper; `tests/**` is bot-02-risk (line 336) except `tests/desk/**` (bot-00-chief) and `tests/execution/**` (bot-04-sniper); `CHANGELOG.md` is bot-09-journal. `tests/supervisor/**` falls under `tests/**`, bot-02-risk. `ci/gates/check_ownership.py` was not run.
- Base: branch `bot-00-chief/v4-phase-14`. Draft PRs target it. Contract baseline: tag `v4-base` (09f83be); `git diff --name-only v4-base -- contracts` is empty at planning time.

## Wave table

| Wave | Plan | Branches (one owning seat each) | depends_on | Criteria |
|---|---|---|---|---|
| 1 | 17-01 | bot-02-risk/phase-17-strategy-slice-kill (two commits); bot-00-chief/phase-17-router-strategy-id | none | 2, 5 |
| 1 | 17-03 | bot-02-risk/phase-17-entry-checks; bot-04-sniper/phase-17-entry-hook | none | 4 |
| 2 | 17-02 | bot-02-risk/phase-17-feed-health-breaker | 17-01 (shares risk/engine/steps.py) | 3 |
| 3 | 17-04 | bot-02-risk/phase-17-promotion | 17-01 (shares cli/verbs_state.py), 17-02 (ordering) | 6, 7, 9 |
| 4 | 17-05 | bot-02-risk/phase-17-promotion-evaluator; bot-00-chief/phase-17-event-desk | 17-02, 17-03, 17-04 | 8, 10 |
| 5 | 17-06 | bot-02-risk/phase-17-restart-state; bot-00-chief/phase-17-restart-recovery | 17-05 | 11 |
| 6 | 17-07 | bot-09-journal/phase-17-changelog | 17-01 to 17-06 | 1, 12, 13, 14 |

Six waves, seven plans. Wave 1 holds two plans; their file lists are disjoint (checked file by file). Every other wave holds one plan. 17-01 executes as two commits, verified in order (Main decision 3): commit 1 is S-K1 to S-K4 (killswitch), commit 2 is RSK-01, RSK-02, RSK-08 and then S-K5, S-K6.

## Criteria coverage (ROADMAP Phase 17, criteria 1 to 14)

| Criterion | Plan | Note |
|---|---|---|
| 1 | 17-07 | Orchestrator final gate. D17-2: paper smoke deferred to deployment. |
| 2 | 17-01 | Strategy slice and kill tests. |
| 3 | 17-02 | Feed health, loss-velocity reset and halt-verdict tests (criterion 3 amended by owner decision 2026-11-18; RSK-04 moved to Phase 18). |
| 4 | 17-03 | Entry checks and mint list. |
| 5 | 17-01 | STEP_IDS and risk_json stability. |
| 6 | 17-04 | Stages, thresholds, gate reuse, upgrade tests. |
| 7 | 17-04 | Demotion test and `promotion demote --help`. |
| 8 | 17-05 | No timers, no Grok, composition-root subscription. |
| 9 | 17-04 | Writer discipline. |
| 10 | 17-05 | Event desk e2e and idle tests. |
| 11 | 17-06 | Restart recovery and exit deadlines. |
| 12 | 17-07 | Contracts diff check: the amended criterion 12 (owner, 2026-11-18, extended to PromotionStageSet). Only the three event schemas (strategy_kill_set, strategy_kill_cleared, promotion_stage_set) and one change document under `contracts/changes/` may differ from `v4-base`. Criterion text names PRM-01; mapped as written. |
| 13 | 17-07 | Smoke-10m pin pair, with the D17-1 literal substitution (Finding 1). |
| 14 | 17-07 | Live refusal, orchestrator run. |

## Requirement coverage

| Requirement | Plan | Note |
|---|---|---|
| RSK-01 | 17-01 | |
| RSK-02 | 17-01 | |
| RSK-03 | 17-02 | |
| RSK-04 | Phase 18 (live parts; moved by owner decision 2026-11-18) | live failure producers and the live-path UNKNOWN halt; the paper-path UNKNOWN is unchanged |
| RSK-05 | 17-03 | |
| RSK-06 | 17-03 | Partial; traceability row says Phase 18 (Finding 3). |
| RSK-07 | 17-07 | No requirement row. Named as a design id that PRC-03 enforces. |
| RSK-08 | 17-01 | |
| RSK-09 | not in Phase 17 | Traceability row (line 344) assigns Phase 18. |
| PRM-01 | 17-04 | |
| PRM-02 | 17-04 | Includes the non-finite bounds fix (S-B4). |
| PRM-03 | 17-04 | |
| PRM-04 | 17-04 | |
| PRM-05 | 17-05 | Includes the explicit human-only mode for `run_promotion_check` (S-P1). |
| PRM-06 | 17-04 | Includes the candidate-hash binding (S-P2). |
| RT-03 | 17-05 | |
| RT-04 | 17-06 | Includes the exit-sell guard (S-X1). |
| PRC-01 | 17-07 | Criterion 1. |
| PRC-03 | 17-07 | Criterion 13. |
| LIV-07 | 17-07 | Criterion 14. |

## Sweep fixes folded in (IRC revision)

Each confirmed fix is its own task with a regression test that fails on the unfixed code.

| Id | Fix | Plan / task | Regression test | Seat |
|---|---|---|---|---|
| S-K1 | Reject a kill reason whose first token is FLATTEN (bare `KILL FLATTEN`) | 17-01 T1 (commit 1) | tests/risk/test_killswitch_flatten_reason.py | bot-02 |
| S-K2 | `kill_file_text` refuses a FLATTEN-led reason | 17-01 T2 (commit 1) | tests/risk/test_killswitch_flatten_reason.py | bot-02 |
| S-K3 | Clear idempotency key includes the clear epoch | 17-01 T3 (commit 1) | tests/risk/test_clear_idempotency_epoch.py | bot-02 |
| S-K4 | One fsynced atomic writer for latch and escalation; clear removes latch through it | 17-01 T4 (commit 1) | tests/risk/test_killswitch_durable.py | bot-02 |
| S-K5 | Desk brief receives the real kill file path | 17-01 T8 (commit 2) | tests/risk/test_desk_brief_killswitch.py | bot-02 |
| S-K6 | Decision cache keyed on seat, creator, exit_reason, observe-only | 17-01 T9 (commit 2) | tests/risk/test_decision_cache_keys.py | bot-02 |
| S-B1 | Loss-velocity breaker: `state` reads half_open; BreakerReset persists | 17-02 T4 | tests/risk/test_loss_velocity_reset.py | bot-02 |
| S-B2 | `evaluate_halts`: corrupt ledger raises; already-active halt returns `HALT_ALREADY_ACTIVE` | 17-02 T5 | tests/risk/test_evaluate_halts_verdict.py; tests/supervisor/test_review_scheduler.py (new case) | bot-02 |
| S-E1 | Entry check rejects missing authority fields, missing REQUIRED_IDS, BLIND | 17-03 T4 | tests/risk/test_entry_checks.py (new cases) | bot-02 |
| S-B4 | Upgrade bounds reject non-finite values and bounds (PRM-02) | 17-04 T4 | tests/upgrade/test_bounds_finite.py | bot-02 |
| S-P2 | Promotion verdict, candidate hash and evidence bound in one value; candidate_hash == params_hash before any write (PRM-06) | 17-04 T5 | tests/promotion/test_evidence_binding.py | bot-02 |
| S-P1 | `run_promotion_check` has no default mode; the human path is explicit | 17-05 T2 | tests/upgrade/test_promotion_mode_required.py | bot-02 |
| S-X1 | One failing exit sell does not abort later positions; state persisted in finally | 17-06 T4 | tests/desk/test_exit_sell_guard.py | bot-00 |

Path notes: the desk brief tool is `src/pumpgrok/tools/__init__.py` (not the repo-root `tools/`). `backtest/evidence.py` and `upgrade/bounds.py` have no ownership rule of their own and fall to `src/pumpgrok/**`, bot-02-risk.

## Sweep items moved out of Phase 17

These are not in any Phase 17 plan. Each is a post-Phase-17 sweep unit with its own owner:
- `supervisor/seat_relay.py:137-155` seat relay cursor (bot-00-chief).
- `replay/maintenance.py:423-476` replay maintenance (bot-02-risk).
- `tools/onchain` large_transfers (bot-03-whale for transfers.py; bot-05-rug for holders.py).
- `tools/safety/score_report.py:430-446` and `tools/onchain/authorities.py` parsing (bot-05-rug; authorities lines to be re-checked by bot-05). `tools/safety/authorities.py` does not exist. 17-03 reads `REQUIRED_IDS` but edits none of these files.
- Observation bus and the daily report: both wait for owner decisions.

## Gate policy

- Subagents never run make, pytest, lint, typecheck, `scripts/check.sh` or the ci gates. The orchestrator runs each plan's acceptance commands after its branches merge to the integration base in wave order.
- Acceptance commands are copied verbatim from the ROADMAP criteria. Criterion 13 is the one exception, handled by D17-1 (Finding 1).
- Planner made no commits. Implementing agents commit only on their own branch.
- Each sweep task's regression test must fail on the unfixed code. The implementing agent records that failure before the fix; the orchestrator confirms it at merge.
- 17-01 commits are verified in order: commit 1 (S-K1 to S-K4) before commit 2 (RSK-01, RSK-02, RSK-08, S-K5, S-K6).
- HARD STOP (Main decision 2): the replay pins must hold before any merge and after each 17-01 commit. Pins: smoke-10m `events.hash` `1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700`; trading-smoke `a4461e80f926e46f9d5b85b0305c41fb44c72b63a875369e2b825ea8b7cd9404`; criterion 13 and 14 outputs. Any movement: stop and report to Main. Do not re-pin.

## Findings for the owner

1. **Criterion 13 pin literal.** The ROADMAP Phase 17 block still names `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`. D17-1 (binding) and the owner-amended criterion 13 use the repo pin `1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700` (tests/replay/pin_support.py:37) in the equality test and in both grep lines. 17-07 T2 uses the amended command and requires the ROADMAP amendment to be recorded before criterion 13 is reported passed. Not edited here.
2. **Criterion 1 smoke.** D17-2 records a deferral to deployment, as for Phases 14 to 16. The orchestrator reports criterion 1 as deferred, not passed.
3. **RSK-06 traceability.** REQUIREMENTS.md line 342 assigns RSK-06 to Phase 18. The ROADMAP Phase 17 requirement list excludes it. 17-03 carries it partially: the entry hook refuses a BUY on a failed check. The named RSK-06 tests (`tests/safety/test_risk_choke_point.py`, `tests/safety/test_signer_only_bypass.py`) do not exist, and no Phase 17 criterion names them. They are not built in this phase. Owner to confirm.
4. **Mint list path.** D17-6 writes `config/mint_lists.toml`. Criterion 4 uses `src/pumpgrok/config/mint_lists.toml`. The plans follow the criterion. The repo has no root `config/` directory.
5. **Promotion thresholds path.** D17-3 and the ROADMAP deliverable say `config/promotion_thresholds.toml`. The plans use `src/pumpgrok/config/promotion_thresholds.toml`, the existing package-config convention.
6. **Strategy kill events are new.** `KillSwitchCleared` clears the whole desk (`ledger/reducer.py:402`), so a strategy clear cannot reuse it. 17-01 adds `StrategyKillSet` and `StrategyKillCleared`. Planner decision; owner may reject.
7. **Not decided by any D17 entry (TODO, owner).**
   - Required-feed list (17-02).
   - Kill-clear and kill-set design (17-01 T6): decided by the owner. `killswitch clear --strategy <id>` and `killswitch set --strategy <id> --reason <text>`, both with `--by human:<name>`, using the existing approval path. No phrase grammar. Both verbs are wired in 17-01 T6.
   - Whether the per-strategy cap divides `max_token_fraction` across strategies (17-01). The plan uses the full fraction per strategy, matching the D17-4 wording "applied per strategy".
   - Demotion triggers beyond the hash-change reset (17-04).
   - Evaluator trigger event kinds (17-05). Planner suggests `FillRecorded` and `PositionClosed` (`ledger/events.py:57-59`).
   - Config key that gates new behavior off (17-05).
   - Watch-set definition (17-06).
   - Halt verdict for an already-active halt: decided by Main as `HALT_ALREADY_ACTIVE = "already_active"` (17-02 T5). Bot-00 callers forward it unchanged; their output changes only when a halt is already active.
8. **Blind status resolved.** The BLIND status is the literal `"blind"` (`tools/safety/checks/__init__.py:4`).
9. **File and task budget.** The planner budget is 5 files and 3 tasks per plan. The sweep fixes push these plans further over it: 17-01 has 9 tasks, 19 files and two commits (18 files on bot-02, 1 on bot-00); 17-04 has 5 tasks and 17 files; 17-02 has 5 tasks and 9 files; 17-05 has 4 tasks and 10 files on two seats; 17-06 has 4 tasks and 7 files on two seats. The ROADMAP fixes seven plans, so none is split. Each task is independently verifiable.
10. **Corrections to the context file.** The kill switch is `src/pumpgrok/risk/killswitch.py` (bot-02), not `execution/live/killswitch.py`. The "no refusal to build a non-paper desk" claim is true only for the scheduler, which forces manual-ticket in live (`supervisor/scheduler/supervisor.py:209-214`). The live-data root refuses non-paper at `supervisor/live_paper.py:114`. No event desk exists.
11. **Threat models.** No `<threat_model>` section is written. The planner did not read a `security_enforcement` setting. Owner to confirm whether one is required.

## Decision record (IRC, Main)

- Item 1, S-B2 proceeds. `evaluate_halts` returns `HALT_ALREADY_ACTIVE`. Deviation to confirm: `tests/supervisor/test_review_scheduler.py:152` asserts `None` in a no-breach case, which stays `None`. This revision adds a new already-active test beside it instead of re-asserting line 152.
- Item 1, bot-00 callers: forward the verdict unchanged. No bot-00 branch was added. Deviation to confirm.
- Item 2, replay pins are a hard stop. Written into 17-01 and 17-02 execution rules, their verification sections, and the gate policy above.
- Item 3, 17-01 stays one plan with two commits: S-K1 to S-K4 first, then RSK-01, RSK-02, RSK-08, S-K5 and S-K6. Deviation to confirm: the RSK tasks were not named in Main's split, so they are placed in commit 2 with S-K5 and S-K6.
- Item 4, 17-01 T6 unblocked by the owner: the strategy-kill clear extends the existing `killswitch clear` verb with `--strategy <id>` and `--by human:<name>`; same human-only check and existing approval path; no new phrase grammar. T6 stays in commit 2. Recorded in 17-01 T6 and Finding 7.
- Item 5, Main (IRC): 17-01 T4 clear contract refuses only for env and alert sources, removes the latch by compare-and-delete, and makes a retry idempotent; the three existing clear tests move to the new contract; commit 1 includes tools/risk/kill_switch.py. 17-03: authority sources are tools/onchain/authorities.py, authorities_tool.py and checks/authority.py; readers.py holds extensions only; list keys are deny and warn; a BLIND top-10 holder row warns when no paid RPC provider is recorded, and an absent required row rejects. 17-05 T5 passes the holder-pair flag from the composition root.
- Item 6, owner: criterion 12 amended for Phase 17 to allow exactly `contracts/events/strategy_kill_set.schema.json`, `contracts/events/strategy_kill_cleared.schema.json` and one change document under `contracts/changes/`. Recorded in ROADMAP Phase 17 criterion 12, 17-07, and 17-01 T6 (bot-02 files; generator run, not edited).
- Item 7, owner (2026-11-18): RSK-04 moves to Phase 18 (live failure producers and the live-path UNKNOWN halt). Criterion 3 is amended to `tests/risk/test_feed_health.py`, `tests/risk/test_loss_velocity_reset.py`, `tests/risk/test_evaluate_halts_verdict.py` and `tests/supervisor/test_review_scheduler.py`. 17-02 T2 and T3 are deferred: the live adapter is the refusing stub `LiveAdapterStub`, and UNKNOWN is produced on the paper path only.
- Item 8, owner (2026-11-18): criterion 12 extended to allow `contracts/events/promotion_stage_set.schema.json` (PromotionStageSet). Criterion 12 is now exactly three event schemas and one change document under `contracts/changes/`. The change document is `contracts/changes/phase-17-strategy-kill-events.yaml`, extended to cover the promotion surface at version 1.2.0 by 17-04 T1. Recorded in ROADMAP criterion 12, 17-07, 17-04 and 17-01.
