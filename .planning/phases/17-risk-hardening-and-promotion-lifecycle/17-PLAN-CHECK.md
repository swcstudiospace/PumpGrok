# 17-PLAN-CHECK: Risk hardening and promotion lifecycle

Verdict: PASS with warnings. No blockers. All 14 Phase 17 requirement ids are claimed and tasked, waves are acyclic and match CONTEXT, seats are pure, acceptance is honest, hashes stay pinned.

## Coverage: every requirement id delivered by a plan task with a real command

| Requirement | Plans | Proving command in plans | Status |
|---|---|---|---|
| RSK-01 slice | 17-01, 17-04 | test_strategy_slice.py, test_live_paper_risk_wiring.py | Covered |
| RSK-02 kill | 17-01 | test_strategy_kill.py, human-only clear asserted | Covered |
| RSK-03 feed health | 17-02, 17-04 | test_feed_health.py, idle test, never-ticked fails closed in live | Covered |
| RSK-04 exec failures | 17-02 | test_exec_failure_breaker.py, UNKNOWN to halt | Covered |
| RSK-05 entry checks | 17-02 | test_entry_checks.py, mint_lists.toml, fail closed | Covered |
| RSK-08 19 rows | 17-01, 17-02 | test_step_rows_stable.py plus characterization | Covered |
| PRM-01 stages | 17-03 | test_stages.py, PAPER ledger rows plus JournalNote in one append_batch | Covered |
| PRM-02 thresholds | 17-03 | test_thresholds.py, floors 14 days, 50 trades, 1.2 factor, 0.15 drawdown | Covered |
| PRM-03 gate reuse | 17-03 | test_gate_reuse.py plus tests/upgrade, paper param skips divergence only | Covered |
| PRM-04 demotion | 17-03 | test_demotion.py, demote verb help | Covered |
| PRM-05 event trigger | 17-03, 17-04 | test_no_timers.py, wiring test, grep for sleep and grok covered by AST test | Covered |
| PRM-06 writers | 17-03 | test_writer_discipline.py, gate:promotion or human only, content verified | Covered |
| RT-03 event desk | 17-04 | test_event_desk_e2e.py plus idle, no SKIPPED, LayeredBudget exhausted | Covered |
| RT-04 recovery | 17-05 | test_restart_recovery.py plus exit deadlines, 3 crash points, ledger equality | Covered |
| PRC-03, PRC-06 | 17-06, 17-07 | equal hash pairs, STATE, ROADMAP, VERIFICATION, check.sh | Covered |

## Checks against the focus list

1. 19 rows and risk_json pinned: 17-01 and 17-02 keep STEP_IDS at 19, map slice to max_token_fraction, kill and feed stale to breaker_open, unbound and entry fail to seat_may_trade, stage ineligible to live_gate, and rerun characterization plus both hash pins. RSK-06 choke proof stays in Phase 18 by design; 17-01, 17-02, 17-04 keep all enforcement inside check and record the signer repeat as a Phase 18 dependency.
2. Promotion rows: writers limited to gate:promotion and human, stored content verified, decision log in the same batch, hash change resets to BACKTEST, live mirror noted as Phase 18 work.
3. Thresholds refuse looser than LiveGate floors; OD-03 0.30, OD-15 empty blocklist and disabled allowlist, OD-16 20 orders 150 bps gap and demote under 1.0 over 20 closed, OD-08 progress caps 0.85 and 0.92 all appear in tests or TOML, REVIEW items carried as unverified receipt notes.
4. Demotion automatic on threshold, kill, halt, hash change with one-operation rollback verb. Effect timing relative to an in-flight decision is not pinned, see W3.
5. Entry missing or stale facts fail closed; feed health lazy, quiet when no exposure and no buy under check, owns no timer. Demotion next-decision timing unpinned, see W3.
6. Scope clean: live refusal exit 3 in every behavior sweep, no signing or key code, no exits or risk imports of the Grok gateway, no silent work outside the phase, deferred ideas absent.
7. Seat purity confirmed with resolve_owner: cli files to bot-02-risk, supervisor and tests/desk to bot-00-chief, CHANGELOG to bot-09-journal, STATE and ROADMAP to bot-00-chief close plan only. No plan writes approved_by, summaries go to /tmp/v4/summaries. Cited line numbers verified: STEP_IDS 19 entries and EXIT_SKIP_STEPS in constants.py, live_gate sell behavior in steps.py near line 239, cooldowns in breakers.py near line 65, evaluate_candidate in gate.py line 84. Cross-phase cites (live_paper.py, wake.py, EntryRefresh, BacktestEvidenceProvider, step rows pin, entry hook test) are absent in this worktree because phases 11 to 16 are unexecuted here; each is produced by a declared dependency or by this phase itself, so INFO only.

## WARNINGS

W1. 17-01 Task 2 says extend EXIT_SKIP_STEPS with the new step names, but D-06 adds no new steps. Adding seat_may_trade or live_gate to the skip set would change existing exit evaluation and fight 18-05. Exact fix: reword the action to pass exits inside the new reason branches with no change to EXIT_SKIP_STEPS membership; the hash pins in acceptance already police this.

W2. Exact ROADMAP commands with no covering plan line: paper replay run mode paper once replay smoke and make test from SC1, tests/execution/test_entry_gate_hook.py plus tomllib load of mint_lists.toml from SC4, contracts diff against v4-base from SC12, test_replay_hash_pin.py from SC13, and the clock sleep plus grok grep from SC8. Exact fix: append these six lines to the 17-07 close sweep or to the owning plan sweeps (hook and toml to 17-02, pins to 17-05, replay and make test to 17-04, grep to 17-03, contracts diff to 17-07).

W3. 17-03 demotion never states when a demotion or kill takes effect relative to an in-flight evaluation, and D-08 with D-14 form a kill to demotion to kill loop with no stated order or idempotency key across the pair. Exact fix: add one Task 3 test asserting a demotion written mid-batch excludes the strategy from the next on_edge decision and that repeated edges write one row per id per day.

W4. 17-04 claims EVT-12, which is not a Phase 17 ROADMAP requirement, and Task 2 says edit wake.py while keeping it byte identical. Exact fix: drop EVT-12 from requirements or map it explicitly, and reword to keep cadence mode byte identical while adding only the evaluator wakes.

## INFO

I1. 17-02 and 17-03 share wave 2 and branch PR-30 but touch disjoint file sets; no files_modified overlap, so no ordering hazard.
I2. RSK-06 parametrized adapters by perturbed ledgers with zero place frames is correctly absent here and owned by Phase 18 per CONTEXT and the plan index notes.
I3. 17-05 crash datasets named smoke and each strat dataset is sufficient; name the strat sets explicitly at execution time.

Plans verified. Ready to execute on planner revision of W1 to W4.
