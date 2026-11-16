# Phase 16 plans index: Backtest v2 and autonomous evaluation

Status: plan set drafted, not executed. Owner decisions of 2026-11-15 and owner confirmations of 2026-11-16 are recorded below and in each affected plan. The gap and grading thresholds and the cooldown are approved, and open question 1 (synthetic definition) is answered 2026-11-16 (16-GAP-THRESHOLDS-PROPOSAL.md). The Metrics v2 set is seven metrics, confirmed 2026-11-16. The 2026-11-16 amendment narrows 16-04 and adds 16-08 (plan count 8). No code, test, fixture, pin, gate or CHANGELOG entry has been changed by this index.

Sources of truth:
- `.planning/ROADMAP.md` Phase 16 section (goal, depends-on, requirements, success criteria 1 to 13, deliverables, plan ids 16-01 to 16-07, six waves). This index adds 16-08 (amendment 2026-11-16); the ROADMAP is not edited here.
- `.planning/REQUIREMENTS.md`: REC-03 (line 78), BT-08 to BT-13 (lines 90 to 95), OBS-07 (line 210).
- `ownership.yaml` (last matching rule wins). Every file below was resolved with `resolve_owner` from `ci/gates/check_ownership.py`.
- Phase 15 record: `.planning/phases/15-strategy-framework-and-multi-strategy-paper/15-PLANS-INDEX.md` (owner decisions, stop conditions, parameter and fee proposals).
- `docs/strategies-replay-exception.md` (legacy replay-only exception), `docs/design/paper-engine.md` (CLI verbs at lines 494, 516, 886 to 893), `docs/upgrade-plan-desk-v2.md` (R12, STRUCT-005).
- Base: branch `bot-00-chief/v4-phase-14`, head `6281a39` (CHIEF commit: Phase 15 closed with criterion 1 deferred; Phase 16 criterion 12 amended to 1dffa784). Tag `v4-base` is the contract baseline.
- Hash baselines: smoke-10m `1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700` (owner amendment 2026-11-15; CHANGELOG records it since Phase 14). Trading-smoke `a4461e80f926e46f9d5b85b0305c41fb44c72b63a875369e2b825ea8b7cd9404` (Phase 15, refund era).

## Findings the owner must see

1. **Spec gaps, decided where marked.** The repo docs define none of the following: `replay import`, `live serve`, the Metrics v2 formula set, the gap and grading thresholds (long dataset, gap-light, cooldown), the semantics of `replay rebuild-ticks` beyond its one-line description, and the channel by which a backtest result is published to the promotion gate. The owner decided `replay import`, `live serve`, `replay rebuild-ticks`, the Metrics v2 set and the publication channel on 2026-11-15 (section "Owner decisions 2026-11-15"). The gap and grading thresholds and the cooldown were approved on 2026-11-16 (16-GAP-THRESHOLDS-PROPOSAL.md, approval record). Open question 1 (synthetic definition) was answered on 2026-11-16: synthetic and hand-authored data, including tmp_path datasets, is never promotion evidence, so approved values may enter code (16-03).
2. **Existing promotion path.** `src/pumpgrok/cli/promotion.py` and `src/pumpgrok/upgrade/scheduled.py` (UPG-05: autonomous-paper only, human-invoked) already run a promotion check. BT-13 must feed the existing gate (`upgrade/gate.py`) through `BacktestEvidenceProvider`. It must not add a second promotion or search path (criterion 10).
3. **Publication event.** The Phase 16 checkpoint says results are "published to the promotion gate as an event". Owner decision 6 (2026-11-15) selects option A: each result is written as an existing ledger JournalNote with NoteKind `verdict`. JournalNote is an existing event type. No new `EventKind`, no new `NoteKind` value and no contract change. The ROADMAP wording and criterion 11 are not edited here. Plan 16-05 carries the decision.
4. **Stale smoke-10m baseline in other phases.** Phase 15 criterion 14, and Phase 17, 18 and 19 criteria with their CHANGELOG greps, still name `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`. The CHANGELOG has recorded `1dffa...` since Phase 14, so those criteria will not pass as written. Owner amendment needed for those phases. Not edited here. Commit 6281a39 records the Phase 15 item as an open owner item.
5. **Stale fee doc comment.** `src/pumpgrok/execution/fees.py:22` still says ATA rent is 2039280. The owner decision of 2026-11-15 makes rent RPC-read at runtime with a pinned offline fallback. The fix belongs to Phase 15 (SNIPER seat). Phase 16 does not edit that file.
6. **Phase 15 criterion 1 deferral.** Phase 16 criterion 1 runs `pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke`. Commit 6281a39 records the deferral for Phase 15 only. Plan 16-07 assumes it does not carry forward to Phase 16. Owner to confirm.
7. **Budget.** The planner budget is at most 3 tasks and at most 5 files per plan (receipts excluded). Plan 16-06 has 8 files and is over budget. The roadmap fixes the plan list at seven, so it is not split here.
8. **Amendment conflicts (2026-11-16).** (a) The stop condition on network clients in `backtest/` and `replay/` is narrowed to exclude the socket factory in `datafeed/transport.py` (16-08). (b) The recorder writes feed.jsonl only when `record_frame` is called, so the existing Phase 13 assertions on the manifest key set in `tests/replay/test_live_recorder.py` stay unchanged and new cases are added (16-04). (c) `live serve --mode live` must exit 3 before the wallet-confirm step, which otherwise can exit 1 under a configured live wallet (16-08, dispatch.py).

## Owner decisions 2026-11-15 (binding for Phase 16)

| # | Decision | Where it binds |
|---|---|---|
| 1 | Replay import accepts only ledgers this desk recorded, verified by hash chain. Anything else is rejected. | 16-04 |
| 2 | `live serve` runs only the paper root and refuses any live mode. Live stays disabled. | 16-08; 16-07 criterion 13 |
| 3 | `replay rebuild-ticks` rebuilds only from the recorded raw feed, never from derived data. | 16-04 |
| 4 | Metrics v2 is the standard set of seven metrics: total return, max drawdown, Sharpe and Sortino annualized (counted separately), hit rate, profit factor, expectancy. Undefined values are None. Annualization under 7 days is flagged annualization_valid=false, a flag and not a metric. Count confirmed 2026-11-16 (row I). | 16-01; 16-06 |
| 5 | Gap and grading thresholds and the cooldown: APPROVED 2026-11-16 as proposed in 16-GAP-THRESHOLDS-PROPOSAL.md. Values enter code once, as APPROVED_THRESHOLDS. Open question 1 answered 2026-11-16 (row H). | 16-03; 16-05, 16-06, 16-07 (unblocked by these approvals) |
| 6 | Promotion-gate publication: option A, the existing journal note path. No new bus event kind. Criterion 11 stays unchanged. | 16-05; 16-07 |

## Owner confirmations 2026-11-16 (binding for Phase 16)

| # | Confirmation | Where it binds |
|---|---|---|
| A | Gap and grading thresholds approved as in 16-GAP-THRESHOLDS-PROPOSAL.md: long dataset 7 days; gap-light maximum single gap 300 s; total gap time at most 5 percent of the window; cooldown 300 s from gap end. The 500 bps haircut stays fixed by criterion 4. | 16-03; 16-05; 16-06; 16-07 |
| B | `run --record` may wrap transports through replay/live_recorder.py without a CHIEF supervisor edit. | 16-08 (transport wrap); 16-04 (recorder) |
| C | Metrics v2 readings: total_return is a ratio; total_return_lamports, annualized_return and average_hold_seconds are dropped; expectancy_lamports is a Decimal lamports mean; annualization_valid is included. Count: seven metrics (row I). | 16-01; 16-06 |
| D | "Recorded by this desk" means source `paper`. | 16-04 |
| E | live serve is paper-only: no --mode selector; --mode live exits 3; any other --mode value is a usage error. | 16-08; 16-07 |
| F | An imported ledger is placed and verified, not converted. Replayability of imports is undefined and not decided. | 16-04 |
| G | Option A publication: JournalNote with NoteKind verdict, whose ledger source must be an existing SOURCES value. 16-05 STOPS if the existing writer cannot record a backtest result under an existing source. | 16-05; 16-07 |
| H | Open question 1 (synthetic definition) answered: synthetic and hand-authored data, including datasets built in `tmp_path`, is never promotion evidence; it is graded as such. Approved threshold values may enter code. | 16-03; 16-05; 16-06; 16-07 |
| I | Metrics v2 count: seven metrics (total_return, max_drawdown, sharpe_ratio, sortino_ratio, hit_rate, profit_factor, expectancy_lamports), Sharpe and Sortino counted separately, plus annualization_valid as a flag. Corrects the six-metric wording. | 16-01; 16-06 |

## Amendment 2026-11-16: recorder, record and serve split (binding)

Owner decisions of 2026-11-16 on the Phase 16 plan set. Plan 16-04 is narrowed, plan 16-08 is added, and the plan count is now 8.

| # | Decision | Where it binds |
|---|---|---|
| 1 | 16-04 files gain `src/pumpgrok/cli/dispatch.py` and `src/pumpgrok/cli/verbs_ops.py` (routing). Owner default applied; the form answer did not register. Owner to confirm. | 16-04 |
| 2 | rebuild-ticks: the recorder persists raw feed frames to `feed.jsonl`. This changes the sealed-dataset contract and is flagged for owner review. `contracts/` is not touched (criterion 11 still holds). `live_recorder.py` and the seal allow-list are in 16-04. | 16-04 |
| 3 | `run --record` and `live serve` move to plan 16-08 (wave 2, depends on 16-04). 16-08 maps to criterion 7 (run --record part), criterion 13 (live serve refusal) and REC-03. The `--mode live` exit 3 check stays in 16-08. | 16-08; 16-04 narrowed |
| 4 | `trim --max-events N` keeps the last N events after the keep-fills rule. No 180 s gap insertion. | 16-04 |
| 5 | `import` copies the ledger to `var/replay/<name>/` and records its sha256 in a sidecar file there. | 16-04 |

Planner-chosen details, flagged for owner confirmation (the owner did not decide them):
- Dataset paths: `var/datasets/<name>/` for recorded datasets, `var/datasets/<name>-trimmed/` and `var/datasets/<name>-rebuilt/` for outputs.
- Import file name `imported-ledger.sqlite` (with its `.sha256` sidecar), so the `ledger.sqlite` that `verify --fixture` recreates is never overwritten.
- Trim's "mints with an order" is read from a full offline replay, because events.jsonl holds no orders.
- The derived tick file is `events.jsonl` (`EVENTS_NAME`) in the code; paper-engine.md section 4.3 calls it `ticks.jsonl`. The code name is used.
- Budget: 16-04 and 16-08 each touch 7 files (over the planner budget of 5, finding 7).

Follow-up, not in this commit: `16-07-PLAN.md` frontmatter `depends_on` must add `16-08`. Its criterion 13 gate stays in 16-07 as the close re-run.

## Owner decisions in force (Phase 15, binding)

| # | Decision | Where it binds in Phase 16 |
|---|---|---|
| 1 | Fee model v2 is the paper default (FEE-01). | 16-02 and 16-06 use `PAPER_DEFAULT_FEE_MODEL`. Backtest and paper fees agree. |
| 2 | Refund at close. The ATA deposit is held as an asset until the position closes in full, then refunded to cash and kept out of realized P&L. | 16-01 round trips and metrics exclude the refund from realized P&L. 16-03 flatten applies the same asset rule. |
| 3 | RPC-read rent with pinned offline fallback. Runtime reads rent from RPC. Offline replay uses the pinned value with its recorded epoch and source. | Backtest and replay never call RPC. 16-02 and 16-05 use the pinned offline value from the 15-07 receipt. |
| 4 | Legacy replay-only exception (`docs/strategies-replay-exception.md`). | 16-02 `strategy_run` adds no placement name, no import of legacy placement, and no allowlist entry. `tests/strategies/test_legacy_exception.py` stays green. |
| 5 | PENDING strategy values approved as recorded. | Phase 16 uses the Phase 15 `upgrade_bounds.toml` and strategy DEFAULTS values exactly. No retuning. |
| 6 | Live stays refused. The live-data root takes an RPC endpoint with no default (Phase 15 decision 4). | 16-08 `live serve` refuses `--mode live` (exit 3) and requires an explicit endpoint. 16-07 criterion 13. |

## Waves and dependencies

| Wave | Plan | Title | Seats | Depends on | autonomous | Criteria closed | Requirements |
|---|---|---|---|---|---|---|---|
| 1 | 16-01 | Metrics v2 and round trips | RISK | Phase 15 (15-03, 15-07) | true | 2 | BT-08, BT-09 |
| 1 | 16-04 | Replay verbs and recorder amendment | RISK | Phase 13-01, Phase 14-07 | false | 7 (replay half) | REC-03 |
| 2 | 16-02 | Event source and strategy-aware replay | RISK | 16-01; Phase 15 (15-03, 15-04, 15-06) | true | 5 | BT-12 |
| 2 | 16-08 | run --record, transports and live serve | RISK | 16-04; Phase 13-01, Phase 14-07, Phase 15 live-data root | false | 7 (record half), 13 (live serve refusal) | REC-03, LIV-07 |
| 3 | 16-03 | Gap segmentation and evidence grading | RISK | 16-02 | true | 3, 4 | BT-10, BT-11 |
| 4 | 16-05 | Autonomous scheduler, store, evidence provider | RISK | 16-03 (with 16-01, 16-02) | true | 6 | BT-13 |
| 5 | 16-06 | Strategy backtest verb and per-strategy report | RISK + JOURNAL | 16-01, 16-02, 16-05 | true | 7 (strategy half), 8, 9 | REC-03, OBS-07 |
| 6 | 16-07 | Phase close | CHIEF + JOURNAL + RISK | 16-01 to 16-06, 16-08 | false | 1, 10, 11, 12, 13 | PRC-01, PRC-03, LIV-07 |

Waves: 6, matching the roadmap. Wave 1 has two plans with no shared files: 16-01 touches `backtest/` and `tests/backtest/`; 16-04 touches `cli/`, `replay/` and `tests/`. Wave 2 has 16-02 and 16-08, also with disjoint files. Plan count: 8 (16-01 to 16-08). ROADMAP line 249 still says seven plans; CHIEF updates it at close.

Seat keys: RISK = bot-02-risk, CHIEF = bot-00-chief, JOURNAL = bot-09-journal. Each plan file lists its seat and the `ownership.yaml` rule that resolves each path.

## Blocking status (2026-11-16)

| Plan | Status | Blocked by |
|---|---|---|
| 16-01 | Ready. Metric set decided (decision 4). | none |
| 16-02 | Ready. Not affected by the decisions. | 16-01 |
| 16-03 | Ready. Thresholds approved 2026-11-16 (decision 5); open question 1 answered 2026-11-16 (row H). | none |
| 16-04 | Ready. Scope narrowed by the 2026-11-16 amendment: replay verbs and recorder amendment. Record and live serve moved to 16-08. | none |
| 16-08 | Ready after 16-04 lands. Record wrap and live serve approved 2026-11-16 (decisions B and E). | 16-04 (order) |
| 16-05 | Unblocked by the 2026-11-16 approvals. Publication confirmed (option A). Runs after 16-03 lands (plan order). | 16-03 implementation (order only) |
| 16-06 | Unblocked by the 2026-11-16 approvals. Runs after 16-05 lands. | 16-05 (order only) |
| 16-07 | Threshold approval received 2026-11-16. Runs after 16-01 to 16-06 land; owner close review remains. | 16-01 to 16-06 (order); owner close review |

## Plan files

### 16-01 Metrics v2 and round trips (wave 1, RISK)

File: `16-01-PLAN.md`. Sizing: 3 tasks, 4 files (within budget).

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/backtest/metrics_v2.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/backtest/roundtrip.py | bot-02-risk | src/pumpgrok/** |
| tests/backtest/test_metrics_v2.py | bot-02-risk | tests/** |
| tests/backtest/test_roundtrip.py | bot-02-risk | tests/** |
| .receipts/bot-02-risk/16-01-metrics.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 2. Requirements: BT-08, BT-09. Metric set: decided 2026-11-15 (owner decision 4; see "Decided definitions and pending items").

### 16-02 Event source and strategy-aware replay (wave 2, RISK)

File: `16-02-PLAN.md`. Sizing: 3 tasks, 4 files (within budget).

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/backtest/event_source.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/backtest/strategy_run.py | bot-02-risk | src/pumpgrok/** |
| tests/backtest/test_strategy_replay.py | bot-02-risk | tests/** |
| tests/backtest/test_dataset_curve_source_perf.py | bot-02-risk | tests/** |
| .receipts/bot-02-risk/16-02-replay.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 5. Requirement: BT-12. Read-only use of `supervisor/intent_router.py` and `supervisor/scheduler/serve.py` (CHIEF); no edit.

### 16-03 Gap segmentation and evidence grading (wave 3, RISK)

File: `16-03-PLAN.md`. Sizing: 3 tasks, 5 files (within budget). Autonomous: true (owner approvals of 2026-11-16 recorded; no open question remains).

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/backtest/gaps.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/backtest/grading.py | bot-02-risk | src/pumpgrok/** |
| tests/backtest/test_lookahead.py | bot-02-risk | tests/** |
| tests/backtest/test_grading.py | bot-02-risk | tests/** |
| tests/backtest/test_gaps.py | bot-02-risk | tests/** |
| .receipts/bot-02-risk/16-03-grading.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 3, 4. Requirements: BT-10, BT-11. Thresholds: APPROVED 2026-11-16 (16-GAP-THRESHOLDS-PROPOSAL.md; owner decision 5); defined once as APPROVED_THRESHOLDS in grading.py. Synthetic and hand-authored data, including datasets built in tmp_path, is never promotion evidence (owner answer 2026-11-16). No new fixture directory: gapped and traded-only datasets are built in `tmp_path` and graded as synthetic.

### 16-04 Replay verbs and recorder amendment (wave 1, RISK)

File: `16-04-PLAN.md`. Sizing: 3 tasks, 7 files (over budget, finding 7; owner default for routing, and the 2026-11-16 recorder amendment). Autonomous: false (owner reviews the sealed-dataset contract change in Task 3).

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/cli/parsing.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/cli/dispatch.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/cli/verbs_ops.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/replay/maintenance.py | bot-02-risk | src/pumpgrok/replay/** |
| src/pumpgrok/replay/live_recorder.py | bot-02-risk | src/pumpgrok/replay/** |
| tests/replay/test_live_recorder.py | bot-02-risk | tests/replay/** |
| tests/cli/test_record.py | bot-02-risk | tests/** |
| .receipts/bot-02-risk/16-04-record.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 7 (replay half). Requirement: REC-03. Decisions: owner 1 to 3 (2026-11-15); amendment 2026-11-16, decisions 2, 4 and 5. Read-only: datafeed frame handling (portal.py, logs.py, bridge.py); supervisor/live_paper.py (CHIEF; must not change). The sealed-dataset contract change (feed.jsonl in the seal allow-list) is flagged for owner review. `run --record` and `live serve` moved to 16-08.

### 16-05 Autonomous scheduler, store and evidence provider (wave 4, RISK)

File: `16-05-PLAN.md`. Sizing: 3 tasks, 5 files (within budget). Autonomous: true (publication channel option A, owner decision 6, confirmed 2026-11-16). Unblocked by the threshold approval; runs after 16-03 lands.

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/backtest/scheduler.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/backtest/store.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/backtest/evidence.py | bot-02-risk | src/pumpgrok/** |
| tests/backtest/test_scheduler.py | bot-02-risk | tests/** |
| tests/backtest/test_evidence_provider.py | bot-02-risk | tests/** |
| .receipts/bot-02-risk/16-05-scheduler.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 6. Requirement: BT-13. Read-only use of `ledger/autonomy.py` (`read_autonomy`), `upgrade/gate.py` and `upgrade/scheduled.py`. No edit to those.

### 16-06 Strategy backtest verb and per-strategy report (wave 5, RISK + JOURNAL)

File: `16-06-PLAN.md`. Sizing: 3 tasks, 8 files (OVER budget, finding 7). Autonomous: true. Prints the decided Metrics v2 table (decision 4). Unblocked by the 2026-11-16 approvals; runs after 16-05 lands.

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/cli/backtest.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/cli/strategy_backtest.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/cli/parsing.py | bot-02-risk | src/pumpgrok/** |
| tests/cli/test_strategy_backtest.py | bot-02-risk | tests/** |
| src/pumpgrok/reporting/strategy_section.py | bot-09-journal | src/pumpgrok/reporting/** |
| src/pumpgrok/reporting/daily.py | bot-09-journal | src/pumpgrok/reporting/** |
| src/pumpgrok/reporting/weekly.py | bot-09-journal | src/pumpgrok/reporting/** |
| tests/reporting/test_strategy_section.py | bot-09-journal | tests/reporting/** |
| .receipts/bot-02-risk/16-06-cli.json | bot-02-risk | .receipts/bot-02-risk/** |
| .receipts/bot-09-journal/16-06-report.json | bot-09-journal | .receipts/bot-09-journal/** |

Criteria: 7 (strategy half), 8, 9. Requirements: REC-03 (backtest --strategy), OBS-07.

### 16-07 Phase close (wave 6, CHIEF + JOURNAL + RISK)

File: `16-07-PLAN.md`. Sizing: 3 tasks, 4 files plus 3 receipts (within budget). Autonomous: false (owner reviews the hash record and approves the close). Threshold approval received 2026-11-16 (decision 5); runs after 16-01 to 16-06 land.

| File | Seat | Rule |
|---|---|---|
| CHANGELOG.md | bot-09-journal | CHANGELOG.md |
| CLAUDE.md | bot-02-risk | **/*.md |
| docs/runbooks/strategies.md | bot-00-chief | docs/runbooks/** |
| .planning/ROADMAP.md | bot-00-chief | .planning/** |
| .receipts/bot-00-chief/16-07-close.json | bot-00-chief | .receipts/bot-00-chief/** |
| .receipts/bot-02-risk/16-07-gates.json | bot-02-risk | .receipts/bot-02-risk/** |
| .receipts/bot-09-journal/16-07-changelog.json | bot-09-journal | .receipts/bot-09-journal/** |

Criteria: 1, 10, 11, 12, 13. Requirements: PRC-01, PRC-03, LIV-07.

### 16-08 run --record, transports and live serve (wave 2, RISK)

File: `16-08-PLAN.md`. Sizing: 3 tasks, 7 files (over budget, finding 7). Autonomous: false (owner reviews one recorded dataset and one live serve --once run). Depends on 16-04.

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/datafeed/transport.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/datafeed/feed_loop.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/cli/parsing.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/cli/dispatch.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/cli/verbs_state.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/cli/verbs_ops.py | bot-02-risk | src/pumpgrok/** |
| tests/cli/test_record.py | bot-02-risk | tests/** |
| .receipts/bot-02-risk/16-08-record.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 7 (record half), 13 (live serve refusal; the criterion 13 gate is re-run by 16-07 at close). Requirements: REC-03, LIV-07. Read-only: datafeed/readonly.py; supervisor/live_paper.py (CHIEF; not edited). Owner decisions: 2 and 3 (2026-11-15), B and E (2026-11-16).

## Coverage

### Success criteria (all 13)

| # | Criterion (short) | Plan(s) | ROADMAP line |
|---|---|---|---|
| 1 | make lint, typecheck, test, check.sh and paper smoke replay exit 0 | 16-07 | 225 |
| 2 | Metrics v2 formulas, None for undefined, annualization_valid under 7 days; negative phrase grep | 16-01 | 226 |
| 3 | Look-ahead canary; grading refuses traded_only, fixture, hand-authored data | 16-03 | 227 |
| 4 | Gap flatten with 500 bps haircut or exclusion and flag; no entries during cooldown | 16-03 | 228 |
| 5 | legacy_screening replay matches v1 fills and net lamports; per-mint bisect perf test | 16-02 | 229 |
| 6 | Repeated edge does no work; read_autonomy gate; no LLM client; deterministic persist; evidence provider | 16-05 | 230 |
| 7 | tests/cli/test_record.py and tests/cli/test_strategy_backtest.py; verbs rerun byte-identically | 16-04 (replay), 16-08 (run --record), 16-06 (strategy) | 231 |
| 8 | `backtest --fixture smoke-10m` output byte-identical across two runs | 16-06 | 232 |
| 9 | Daily and weekly reports carry per-strategy section; parts sum to desk view | 16-06 | 233 |
| 10 | No grid or itertools.product in engine or backtest; single search engine test | 16-07 (guard; no plan adds the tokens) | 234 |
| 11 | Zero diff under `contracts/` against `v4-base` | 16-07 (guard; every plan keeps contracts untouched) | 235 |
| 12 | smoke-10m and trading-smoke pairs equal and unchanged; CHANGELOG records both pairs | 16-07 | 236 |
| 13 | `run --mode live --once` exits 3 | 16-07 (gate re-run), 16-08 (live serve refusal) | 237 |

Criterion 12 is amended per owner: the smoke-10m baseline is `1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700` (ROADMAP line 236 carries the amendment, commit 6281a39; the old value appears only inside the amendment note). The trading-smoke baseline is `a4461e80...`. Both hashes must be unchanged in Phase 16.

### Requirements (all 8, plus OBS-07 and PRC-03 close)

| Requirement | Plan(s) | Criteria |
|---|---|---|
| REC-03 | 16-04, 16-06, 16-08 | 7 |
| BT-08 | 16-01 | 2 |
| BT-09 | 16-01 (breakdown sums), 16-06 (report sums) | 2, 9 |
| BT-10 | 16-03 | 3 |
| BT-11 | 16-03 | 4 |
| BT-12 | 16-02 | 5 (and 11 contract guard) |
| BT-13 | 16-05 | 6 |
| OBS-07 | 16-06 | 9 |

Uncovered: none in the sense of unassigned work. Nothing is open after the 2026-11-16 owner answers (rows H and I of the confirmations table): open question 1 of 16-GAP-THRESHOLDS-PROPOSAL.md is answered, and the Metrics v2 count is seven. Every item is decided; see "Decided definitions and pending items".

## Decided definitions and pending items

Decided on 2026-11-15 (decisions 1 to 4 and 6) and confirmed or approved on 2026-11-16 as noted in each section. Each affected plan states its decision inline. Open items are marked.

### Metrics v2 set (16-01): decided, decision 4

| Metric | Definition | None when |
|---|---|---|
| total_return | (closing equity minus opening equity) divided by opening equity, as a Decimal fraction. Not annualized. | opening equity <= 0 |
| max_drawdown | largest peak-to-trough decline of equity, as a Decimal fraction of the peak | peak <= 0 |
| sharpe_ratio | annualized: mean per-step return divided by its sample standard deviation, scaled by sqrt(365 / step_days) | annualization_valid is false; fewer than 2 returns; zero sample standard deviation |
| sortino_ratio | annualized: mean per-step return divided by downside deviation, scaled the same way | annualization_valid is false; fewer than 2 returns; zero downside deviation |
| hit_rate | winning closed round trips divided by closed round trips | no closed round trips |
| profit_factor | gross profit of closed round trips divided by gross loss of closed round trips | no losing closed round trip |
| expectancy_lamports | mean realized P&L per closed round trip, Decimal lamports, not rounded | no closed round trips |
| annualization_valid | elapsed window of at least 7 days (boolean, never None) | never |

Notes:
- Closed round trip counts (all, winning, losing) and realized P&L are reported as inputs and denominators. They are not metrics of the set.
- Realized P&L excludes the ATA deposit refunded at close (Phase 15 decision 2).
- Money fields are int lamports, except expectancy_lamports, which is a mean. Ratios are Decimal. Undefined is None, never 0 or infinity.
- Annualization basis is 365 days, the constant in backtest/metrics.py. The 7-day floor is the value BT-08 names.
- Confirmed 2026-11-16 by the owner: total_return is a ratio; total_return_lamports, annualized_return and average_hold_seconds are dropped; expectancy_lamports is a Decimal lamports mean; the set is the metrics named above plus annualization_valid.
- Count confirmed 2026-11-16 by the owner (row I): seven metrics, Sharpe and Sortino counted separately, plus annualization_valid, which is a flag and not a metric. The earlier six-metric reading is withdrawn.

### Gap and grading thresholds and cooldown (16-03): APPROVED 2026-11-16 (values as proposed), decision 5

Values, reasons and the approval record: 16-GAP-THRESHOLDS-PROPOSAL.md. Approved: long dataset 7 days; gap-light single gap 300 s; total gap time at most 5 percent of the window; cooldown 300 s from gap end. Open question 1 (synthetic definition) is answered 2026-11-16 (row H): synthetic and hand-authored data, including datasets built in tmp_path, is never promotion evidence. The values are defined once, as APPROVED_THRESHOLDS in src/pumpgrok/backtest/grading.py. The flatten haircut of 500 bps is fixed by ROADMAP criterion 4 and is not part of the approval.

### Verb specs (16-04, 16-08): decided, decisions 1 to 3; amended 2026-11-16

| Verb | Definition |
|---|---|
| `replay trim --dataset <name> --max-events N --keep-mints-with-fills` (16-04) | Replays the full dataset offline into a temporary ledger (source replay) to find the mints that have an order. Keeps every event of those mints, and a seeded 5 percent of the other events (one `random.Random(settings.replay.seed)`, drawn only for those events), then keeps the last N kept events in merge order. Inserts no gap row (no 180 s hole). Writes a sealed dataset to `var/datasets/<name>-trimmed/`. Refuses an existing target. |
| `replay rebuild-ticks --dataset <name>` (16-04) | Rebuilds the derived tick file (`EVENTS_NAME`, `events.jsonl` in the code) only from the raw feed stream `feed.jsonl`, replayed in (ts, file_order, line_no) order through the live frame handling. Never reads `events.jsonl` or any other derived file. Writes a sealed dataset to `var/datasets/<name>-rebuilt/`. A dataset recorded before the amendment has no `feed.jsonl` and is refused (exit 4). |
| `replay import --from <ledger.sqlite> --dataset <name>` (16-04) | Accepts only a ledger this desk recorded: refused (exit 2) unless `LedgerStore.verify` passes from `GENESIS_PREV_HASH` and every row has source `paper`. Copies the file unchanged to `var/replay/<name>/imported-ledger.sqlite` and writes `imported-ledger.sqlite.sha256` beside it. Refuses an existing target (exit 1). Placed and verified, not converted. |
| `run --mode paper --record <dataset> --duration <s> [--mints <list>]` (16-08) | Records a live-paper session into `var/datasets/<dataset>/` through the websocket and JSON-RPC recording wrappers; `record_frame` runs before each observation; sealed on exit. `--record` with `--replay` exits 1; `--mode live` exits 3. |
| `live serve --rpc <url> [--once]` (16-08) | Runs the live-data paper root only. `--mode live` exits 3; any other `--mode` value is a usage error. `--rpc` is required and has no default. `--once` is exactly one paper cycle. |

Confirmed by the owner 2026-11-16:
- Source `paper` means recorded by this desk. CHIEF's reading of `SOURCES` in `ledger/store.py` (`paper`, `replay`, `manual`) is confirmed.
- `live serve` has no mode selector; it is paper-only (decision 2). `--mode live` exits 3; any other `--mode` value is a usage error.
- An imported ledger is placed and verified, not converted. Replayability of imports is undefined and is not decided here; 16-04 does not define it.

### Publication channel (16-05): decided, decision 6

Option A: each result is written as an existing ledger JournalNote with NoteKind `verdict`, carrying result id and grade, through the existing journal note path. The result is also stored in the sidecar table. Option B (a new `EventKind`) is not taken, and no waiver is requested.

Confirmed by the owner 2026-11-16: the JournalNote's ledger `source` must be one of the existing `SOURCES`. No value is added. If the existing writer cannot record a backtest result under an existing source, 16-05 STOPS.

## Stop conditions (apply to every plan)

- Any change under `contracts/` (criterion 11). Every plan keeps `contracts/` untouched.
- Any change to `tests/fixtures/replay/**`, to any pin file, or to any hash literal. Phase 16 moves no hash. Synthetic datasets are built in `tmp_path`.
- Any change to `src/pumpgrok/backtest/metrics.py` (v1). `tests/backtest/test_metrics.py` must stay green unchanged.
- Any new placement name, placement import, or allowlist entry for the legacy path (`docs/strategies-replay-exception.md`).
- Any network, RPC, LLM or Grok client reachable from `backtest/` or `replay/`, or constructed by a Phase 16 CLI handler. The one exception is the socket factory `make_read_transport` in `datafeed/transport.py` (plan 16-08), which the record and serve handlers receive by injection; `replay/` imports no network client. Backtests use the pinned offline rent value only. (Narrowed by the 2026-11-16 amendment; see "Amendment 2026-11-16".)
- Any token `grid` or `itertools.product` in `src/pumpgrok/engine` or `src/pumpgrok/backtest` (criterion 10 greps substrings, so comments count).
- Any phrase `expected return`, `expected profit`, `expected pnl` or `will earn` in `src/pumpgrok/backtest` or `src/pumpgrok/reporting` (criterion 2).
- Any approval minted outside `RiskEngine.check`. Phase 16 never mints an `autonomous_paper` approval.
- Any edit under `src/pumpgrok/execution/live/` or `services/`.
- Any second promotion or search path beside `upgrade/gate.py` and `upgrade/scheduled.py`.
- Any `SKIPPED` mark in a test named by a criterion.
- Any edit to a file outside the plan's table. A cross-seat need goes to the owning seat or to CHIEF first.
- Any `replay import` of a ledger that fails verification or holds a row whose source is not `paper` (decision 1).
- Any `live serve` option that selects a live root, or any RPC default (decision 2).
- Any `rebuild-ticks` input other than raw feed streams (decision 3).
- Any threshold value in `src/pumpgrok/backtest/` or `tests/backtest/` outside APPROVED_THRESHOLDS in `grading.py`, or a second definition (decision 5).
- Any new `EventKind`, `NoteKind` value or contract change for publication (decision 6).
- Any change to the seal allow-list beyond `feed.jsonl`, any changed signature on `LiveRecorder`, or any edit under `supervisor/` for the recorder wrap (amendment 2026-11-16, decision 2 and decision B). STOP and ask CHIEF.
- Any `run --record` or `live serve` code in plan 16-04 (moved to 16-08). Any `--mode live` path that does not exit 3 (decision E).
- Any `rebuild-ticks` read of `events.jsonl` or any other derived file (decision 3). Any `trim` insertion of a gap row (amendment decision 4).

## Execution order

1. 16-01 and 16-04 in parallel (RISK). 16-04 covers the replay verbs and the recorder amendment; run --record and live serve moved to 16-08 by the 2026-11-16 amendment.
2. 16-02 and 16-08 in parallel (RISK). 16-08 needs 16-04 merged. The file sets are disjoint: 16-02 uses backtest/ and tests/backtest/; 16-08 uses datafeed/, cli/ and tests/cli/.
3. 16-03 (RISK). Threshold approval and open question 1 answer received 2026-11-16; unblocked.
4. 16-05 (RISK). Publication confirmed (option A) 2026-11-16; runs after 16-03.
5. 16-06 (RISK + JOURNAL).
6. 16-07 (CHIEF + JOURNAL + RISK): gates, guards, pins, CHANGELOG, live refusal, owner close review. Runs after 16-08. Follow-up, not in this commit: the 16-07 frontmatter depends_on must add 16-08.

Each seat submits its own receipt for its completion claims (G-2). Journal owns the one CHANGELOG pull request. CHIEF owns the one `.planning` close update. No push in this planning step.
