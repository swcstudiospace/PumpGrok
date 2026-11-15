# Phase 16 plans index: Backtest v2 and autonomous evaluation

Status: plan set drafted, not executed. Owner decisions of 2026-11-15 are recorded below and in each affected plan. The gap and grading thresholds and the cooldown await owner approval (16-GAP-THRESHOLDS-PROPOSAL.md). No code, test, fixture, pin, gate or CHANGELOG entry has been changed by this index.

Sources of truth:
- `.planning/ROADMAP.md` Phase 16 section (goal, depends-on, requirements, success criteria 1 to 13, deliverables, plan ids 16-01 to 16-07, six waves).
- `.planning/REQUIREMENTS.md`: REC-03 (line 78), BT-08 to BT-13 (lines 90 to 95), OBS-07 (line 210).
- `ownership.yaml` (last matching rule wins). Every file below was resolved with `resolve_owner` from `ci/gates/check_ownership.py`.
- Phase 15 record: `.planning/phases/15-strategy-framework-and-multi-strategy-paper/15-PLANS-INDEX.md` (owner decisions, stop conditions, parameter and fee proposals).
- `docs/strategies-replay-exception.md` (legacy replay-only exception), `docs/design/paper-engine.md` (CLI verbs at lines 494, 516, 886 to 893), `docs/upgrade-plan-desk-v2.md` (R12, STRUCT-005).
- Base: branch `bot-00-chief/v4-phase-14`, head `6281a39` (CHIEF commit: Phase 15 closed with criterion 1 deferred; Phase 16 criterion 12 amended to 1dffa784). Tag `v4-base` is the contract baseline.
- Hash baselines: smoke-10m `1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700` (owner amendment 2026-11-15; CHANGELOG records it since Phase 14). Trading-smoke `a4461e80f926e46f9d5b85b0305c41fb44c72b63a875369e2b825ea8b7cd9404` (Phase 15, refund era).

## Findings the owner must see

1. **Spec gaps, decided where marked.** The repo docs define none of the following: `replay import`, `live serve`, the Metrics v2 formula set, the gap and grading thresholds (long dataset, gap-light, cooldown), the semantics of `replay rebuild-ticks` beyond its one-line description, and the channel by which a backtest result is published to the promotion gate. The owner decided `replay import`, `live serve`, `replay rebuild-ticks`, the Metrics v2 set and the publication channel on 2026-11-15 (section "Owner decisions 2026-11-15"). The gap and grading thresholds and the cooldown remain PENDING OWNER APPROVAL. CHIEF's draft, with a reason for each value, is in 16-GAP-THRESHOLDS-PROPOSAL.md. No value there is pinned.
2. **Existing promotion path.** `src/pumpgrok/cli/promotion.py` and `src/pumpgrok/upgrade/scheduled.py` (UPG-05: autonomous-paper only, human-invoked) already run a promotion check. BT-13 must feed the existing gate (`upgrade/gate.py`) through `BacktestEvidenceProvider`. It must not add a second promotion or search path (criterion 10).
3. **Publication event.** The Phase 16 checkpoint says results are "published to the promotion gate as an event". Owner decision 6 (2026-11-15) selects option A: each result is written as an existing ledger JournalNote with NoteKind `verdict`. JournalNote is an existing event type. No new `EventKind`, no new `NoteKind` value and no contract change. The ROADMAP wording and criterion 11 are not edited here. Plan 16-05 carries the decision.
4. **Stale smoke-10m baseline in other phases.** Phase 15 criterion 14, and Phase 17, 18 and 19 criteria with their CHANGELOG greps, still name `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`. The CHANGELOG has recorded `1dffa...` since Phase 14, so those criteria will not pass as written. Owner amendment needed for those phases. Not edited here. Commit 6281a39 records the Phase 15 item as an open owner item.
5. **Stale fee doc comment.** `src/pumpgrok/execution/fees.py:22` still says ATA rent is 2039280. The owner decision of 2026-11-15 makes rent RPC-read at runtime with a pinned offline fallback. The fix belongs to Phase 15 (SNIPER seat). Phase 16 does not edit that file.
6. **Phase 15 criterion 1 deferral.** Phase 16 criterion 1 runs `pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke`. Commit 6281a39 records the deferral for Phase 15 only. Plan 16-07 assumes it does not carry forward to Phase 16. Owner to confirm.
7. **Budget.** The planner budget is at most 3 tasks and at most 5 files per plan (receipts excluded). Plan 16-06 has 8 files and is over budget. The roadmap fixes the plan list at seven, so it is not split here.

## Owner decisions 2026-11-15 (binding for Phase 16)

| # | Decision | Where it binds |
|---|---|---|
| 1 | Replay import accepts only ledgers this desk recorded, verified by hash chain. Anything else is rejected. | 16-04 |
| 2 | `live serve` runs only the paper root and refuses any live mode. Live stays disabled. | 16-04; 16-07 criterion 13 |
| 3 | `replay rebuild-ticks` rebuilds only from the recorded raw feed, never from derived data. | 16-04 |
| 4 | Metrics v2 is the standard set: total return, max drawdown, Sharpe and Sortino annualized, hit rate, profit factor, expectancy. Undefined values are None. Annualization under 7 days is flagged annualization_valid=false. | 16-01; 16-06 |
| 5 | Gap and grading thresholds and the cooldown: CHIEF drafts values with a reason each in 16-GAP-THRESHOLDS-PROPOSAL.md. The owner approves before implementation. No value is pinned in code or tests before approval. | 16-03 (blocked); 16-05, 16-06, 16-07 (transitively) |
| 6 | Promotion-gate publication: option A, the existing journal note path. No new bus event kind. Criterion 11 stays unchanged. | 16-05; 16-07 |

## Owner decisions in force (Phase 15, binding)

| # | Decision | Where it binds in Phase 16 |
|---|---|---|
| 1 | Fee model v2 is the paper default (FEE-01). | 16-02 and 16-06 use `PAPER_DEFAULT_FEE_MODEL`. Backtest and paper fees agree. |
| 2 | Refund at close. The ATA deposit is held as an asset until the position closes in full, then refunded to cash and kept out of realized P&L. | 16-01 round trips and metrics exclude the refund from realized P&L. 16-03 flatten applies the same asset rule. |
| 3 | RPC-read rent with pinned offline fallback. Runtime reads rent from RPC. Offline replay uses the pinned value with its recorded epoch and source. | Backtest and replay never call RPC. 16-02 and 16-05 use the pinned offline value from the 15-07 receipt. |
| 4 | Legacy replay-only exception (`docs/strategies-replay-exception.md`). | 16-02 `strategy_run` adds no placement name, no import of legacy placement, and no allowlist entry. `tests/strategies/test_legacy_exception.py` stays green. |
| 5 | PENDING strategy values approved as recorded. | Phase 16 uses the Phase 15 `upgrade_bounds.toml` and strategy DEFAULTS values exactly. No retuning. |
| 6 | Live stays refused. The live-data root takes an RPC endpoint with no default (Phase 15 decision 4). | 16-04 `live serve` refuses `--mode live` (exit 3) and requires an explicit endpoint. 16-07 criterion 13. |

## Waves and dependencies

| Wave | Plan | Title | Seats | Depends on | autonomous | Criteria closed | Requirements |
|---|---|---|---|---|---|---|---|
| 1 | 16-01 | Metrics v2 and round trips | RISK | Phase 15 (15-03, 15-07) | true | 2 | BT-08, BT-09 |
| 1 | 16-04 | Recorder and replay verbs | RISK | Phase 13-01, Phase 14-07 | false | 7 (record half) | REC-03 |
| 2 | 16-02 | Event source and strategy-aware replay | RISK | 16-01; Phase 15 (15-03, 15-04, 15-06) | true | 5 | BT-12 |
| 3 | 16-03 | Gap segmentation and evidence grading | RISK | 16-02 | false | 3, 4 | BT-10, BT-11 |
| 4 | 16-05 | Autonomous scheduler, store, evidence provider | RISK | 16-03 (with 16-01, 16-02) | true | 6 | BT-13 |
| 5 | 16-06 | Strategy backtest verb and per-strategy report | RISK + JOURNAL | 16-01, 16-02, 16-05 | true | 7 (strategy half), 8, 9 | REC-03, OBS-07 |
| 6 | 16-07 | Phase close | CHIEF + JOURNAL + RISK | 16-01 to 16-06 | false | 1, 10, 11, 12, 13 | PRC-01, PRC-03, LIV-07 |

Waves: 6, matching the roadmap. Wave 1 has two plans with no shared files: 16-01 touches `backtest/` and `tests/backtest/`; 16-04 touches `cli/`, `replay/` and `tests/cli/`.

Seat keys: RISK = bot-02-risk, CHIEF = bot-00-chief, JOURNAL = bot-09-journal. Each plan file lists its seat and the `ownership.yaml` rule that resolves each path.

## Blocking status (2026-11-15)

| Plan | Status | Blocked by |
|---|---|---|
| 16-01 | Ready. Metric set decided (decision 4). | none |
| 16-02 | Ready. Not affected by the decisions. | 16-01 |
| 16-03 | BLOCKED. Thresholds and cooldown await owner approval (decision 5). | owner approval of 16-GAP-THRESHOLDS-PROPOSAL.md |
| 16-04 | Blocked on one question. Decisions 1 to 3 recorded. Owner must confirm that `run --record` may wrap transports without a CHIEF supervisor edit. | owner answer (16-04 Task 1) |
| 16-05 | BLOCKED transitively. Publication decided (decision 6); grading from 16-03 is needed. | 16-03 |
| 16-06 | BLOCKED transitively. | 16-05 |
| 16-07 | BLOCKED transitively. | 16-01 to 16-06; owner close review |

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

File: `16-03-PLAN.md`. Sizing: 3 tasks, 5 files (within budget). Autonomous: false (owner approves thresholds before they are committed). BLOCKED on owner approval of 16-GAP-THRESHOLDS-PROPOSAL.md.

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/backtest/gaps.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/backtest/grading.py | bot-02-risk | src/pumpgrok/** |
| tests/backtest/test_lookahead.py | bot-02-risk | tests/** |
| tests/backtest/test_grading.py | bot-02-risk | tests/** |
| tests/backtest/test_gaps.py | bot-02-risk | tests/** |
| .receipts/bot-02-risk/16-03-grading.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 3, 4. Requirements: BT-10, BT-11. Thresholds: PENDING OWNER APPROVAL (16-GAP-THRESHOLDS-PROPOSAL.md; owner decision 5); not pinned in code or tests. No new fixture directory: gapped and traded-only datasets are built in `tmp_path` and labeled synthetic.

### 16-04 Recorder and replay verbs (wave 1, RISK)

File: `16-04-PLAN.md`. Sizing: 3 tasks, 5 files (at budget). Autonomous: false (verb specs decided 2026-11-15, owner decisions 1 to 3; one question open: confirmation that `run --record` may wrap transports without a CHIEF supervisor edit).

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/cli/parsing.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/cli/verbs_state.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/cli/record.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/replay/maintenance.py | bot-02-risk | src/pumpgrok/** |
| tests/cli/test_record.py | bot-02-risk | tests/** |
| .receipts/bot-02-risk/16-04-record.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 7 (record half). Requirement: REC-03. Read-only use of `replay/live_recorder.py` and `replay/clock.py`. If the recorder wrap needs an edit to `supervisor/` (CHIEF), the plan STOPS and asks CHIEF.

### 16-05 Autonomous scheduler, store and evidence provider (wave 4, RISK)

File: `16-05-PLAN.md`. Sizing: 3 tasks, 5 files (within budget). Autonomous: true (publication channel decided, owner decision 6). BLOCKED until 16-03 lands, because grading needs the approved thresholds.

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

File: `16-06-PLAN.md`. Sizing: 3 tasks, 8 files (OVER budget, finding 7). Autonomous: true. Prints the decided Metrics v2 table (decision 4). BLOCKED transitively until 16-05 lands.

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

File: `16-07-PLAN.md`. Sizing: 3 tasks, 4 files plus 3 receipts (within budget). Autonomous: false (owner reviews the hash record and approves the close). BLOCKED until 16-01 to 16-06 land, including owner threshold approval (decision 5).

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
| 7 | tests/cli/test_record.py and tests/cli/test_strategy_backtest.py; verbs rerun byte-identically | 16-04 (record), 16-06 (strategy) | 231 |
| 8 | `backtest --fixture smoke-10m` output byte-identical across two runs | 16-06 | 232 |
| 9 | Daily and weekly reports carry per-strategy section; parts sum to desk view | 16-06 | 233 |
| 10 | No grid or itertools.product in engine or backtest; single search engine test | 16-07 (guard; no plan adds the tokens) | 234 |
| 11 | Zero diff under `contracts/` against `v4-base` | 16-07 (guard; every plan keeps contracts untouched) | 235 |
| 12 | smoke-10m and trading-smoke pairs equal and unchanged; CHANGELOG records both pairs | 16-07 | 236 |
| 13 | `run --mode live --once` exits 3 | 16-07 | 237 |

Criterion 12 is amended per owner: the smoke-10m baseline is `1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700` (ROADMAP line 236 carries the amendment, commit 6281a39; the old value appears only inside the amendment note). The trading-smoke baseline is `a4461e80...`. Both hashes must be unchanged in Phase 16.

### Requirements (all 8, plus OBS-07 and PRC-03 close)

| Requirement | Plan(s) | Criteria |
|---|---|---|
| REC-03 | 16-04, 16-06 | 7 |
| BT-08 | 16-01 | 2 |
| BT-09 | 16-01 (breakdown sums), 16-06 (report sums) | 2, 9 |
| BT-10 | 16-03 | 3 |
| BT-11 | 16-03 | 4 |
| BT-12 | 16-02 | 5 (and 11 contract guard) |
| BT-13 | 16-05 | 6 |
| OBS-07 | 16-06 | 9 |

Uncovered: none in the sense of unassigned work. Open after the 2026-11-15 owner decisions: the gap and grading thresholds and the cooldown (16-GAP-THRESHOLDS-PROPOSAL.md, owner approval pending), and the record-wrap confirmation for `run --record` (16-04 Task 1). Every other item is decided; see "Decided definitions and pending items".

## Decided definitions and pending items

Decided on 2026-11-15 (decisions 1 to 4 and 6). Each affected plan states its decision inline. Open items are marked.

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
- CHIEF reading, for owner check: the earlier draft's total_return_lamports, annualized_return and average_hold_seconds are dropped, because the owner's set names total return and does not name them.

### Gap and grading thresholds and cooldown (16-03): PENDING OWNER APPROVAL, decision 5

Values, reasons and the approval record: 16-GAP-THRESHOLDS-PROPOSAL.md. Not pinned in code or tests. After approval, the values are defined once, as APPROVED_THRESHOLDS in src/pumpgrok/backtest/grading.py. The flatten haircut of 500 bps is fixed by ROADMAP criterion 4 and is not part of the approval.

### Verb specs (16-04): decided, decisions 1 to 3

| Verb | Definition |
|---|---|
| `replay rebuild-ticks --dataset <name>` | Rebuilds `ticks.jsonl` only from the raw stream files of that dataset (the files the recorder derivation reads; paper-engine.md section 4.3 names them), merged by `(ts, file_order, line_no)`, with the same derivation the recorder runs at record time. Never reads `ticks.jsonl` or any other derived file as input. |
| `replay import --from <ledger.sqlite> --dataset <name>` | Accepts only a ledger this desk recorded. Refused unless `LedgerStore.verify()` passes from `GENESIS_PREV_HASH` and every row has source `paper`. Rows with source `replay` or `manual` are refused. Copies the file unchanged to var/ under the dataset name, verifies the copy, records its sha256, and refuses to overwrite an existing target. |
| `live serve --rpc <url> [--once]` | Runs the live-data paper root only. No live root exists. `--mode live` exits 3. Any other `--mode` value is a usage error. `--rpc` is required and has no default. |

Points for the owner to confirm:
- Source `paper` as "recorded by this desk" is CHIEF's reading of `SOURCES` in `ledger/store.py` (`paper`, `replay`, `manual`).
- `live serve` has no mode selector; it is paper-only. This is CHIEF's reading of decision 2.
- An imported ledger is placed and verified, not converted. Whether it can be replayed is not decided here, and 16-04 does not define it.

### Publication channel (16-05): decided, decision 6

Option A: each result is written as an existing ledger JournalNote with NoteKind `verdict`, carrying result id and grade, through the existing journal note path. The result is also stored in the sidecar table. Option B (a new `EventKind`) is not taken, and no waiver is requested.

Point for the owner to confirm: the JournalNote's ledger `source` must be one of the existing `SOURCES`. No value is added. If the existing writer cannot record a backtest result under an existing source, 16-05 STOPS.

## Stop conditions (apply to every plan)

- Any change under `contracts/` (criterion 11). Every plan keeps `contracts/` untouched.
- Any change to `tests/fixtures/replay/**`, to any pin file, or to any hash literal. Phase 16 moves no hash. Synthetic datasets are built in `tmp_path`.
- Any change to `src/pumpgrok/backtest/metrics.py` (v1). `tests/backtest/test_metrics.py` must stay green unchanged.
- Any new placement name, placement import, or allowlist entry for the legacy path (`docs/strategies-replay-exception.md`).
- Any network, RPC, LLM or Grok client reachable from `backtest/`, `replay/` or the new CLI handlers in Phase 16 code. Backtests use the pinned offline rent value only.
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
- Any threshold value in `src/pumpgrok/backtest/` or `tests/backtest/` before owner approval, or a second definition after approval (decision 5).
- Any new `EventKind`, `NoteKind` value or contract change for publication (decision 6).

## Execution order

1. 16-01 and 16-04 in parallel (RISK). 16-04 waits for the record-wrap answer.
2. 16-02 (RISK).
3. 16-03 (RISK). Waits for owner approval of 16-GAP-THRESHOLDS-PROPOSAL.md.
4. 16-05 (RISK). Publication decided (option A); waits for 16-03.
5. 16-06 (RISK + JOURNAL).
6. 16-07 (CHIEF + JOURNAL + RISK): gates, guards, pins, CHANGELOG, live refusal, owner close review.

Each seat submits its own receipt for its completion claims (G-2). Journal owns the one CHANGELOG pull request. CHIEF owns the one `.planning` close update. No push in this planning step.
