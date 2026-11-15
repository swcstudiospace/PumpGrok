# Phase 16 plans index: Backtest v2 and autonomous evaluation

Status: plan set drafted, not executed. No code, test, fixture, pin, gate or CHANGELOG entry has been changed by this index.

Sources of truth:
- `.planning/ROADMAP.md` Phase 16 section (goal, depends-on, requirements, success criteria 1 to 13, deliverables, plan ids 16-01 to 16-07, six waves).
- `.planning/REQUIREMENTS.md`: REC-03 (line 78), BT-08 to BT-13 (lines 90 to 95), OBS-07 (line 210).
- `ownership.yaml` (last matching rule wins). Every file below was resolved with `resolve_owner` from `ci/gates/check_ownership.py`.
- Phase 15 record: `.planning/phases/15-strategy-framework-and-multi-strategy-paper/15-PLANS-INDEX.md` (owner decisions, stop conditions, parameter and fee proposals).
- `docs/strategies-replay-exception.md` (legacy replay-only exception), `docs/design/paper-engine.md` (CLI verbs at lines 494, 516, 886 to 893), `docs/upgrade-plan-desk-v2.md` (R12, STRUCT-005).
- Base: branch `bot-00-chief/v4-phase-14`, head `6281a39` (CHIEF commit: Phase 15 closed with criterion 1 deferred; Phase 16 criterion 12 amended to 1dffa784). Tag `v4-base` is the contract baseline.
- Hash baselines: smoke-10m `1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700` (owner amendment 2026-11-15; CHANGELOG records it since Phase 14). Trading-smoke `a4461e80f926e46f9d5b85b0305c41fb44c72b63a875369e2b825ea8b7cd9404` (Phase 15, refund era).

## Findings the owner must see

1. **Spec gaps.** The repo docs define none of the following: `replay import`, `live serve`, the Metrics v2 formula set, the gap and grading thresholds (long dataset, gap-light, cooldown), the semantics of `replay rebuild-ticks` beyond its one-line description, and the channel by which a backtest result is published to the promotion gate. Each is written as a PENDING OWNER APPROVAL proposal with a reason, and each has a human checkpoint in its plan. Nothing is decided by this index.
2. **Existing promotion path.** `src/pumpgrok/cli/promotion.py` and `src/pumpgrok/upgrade/scheduled.py` (UPG-05: autonomous-paper only, human-invoked) already run a promotion check. BT-13 must feed the existing gate (`upgrade/gate.py`) through `BacktestEvidenceProvider`. It must not add a second promotion or search path (criterion 10).
3. **Publication event.** The Phase 16 checkpoint says results are "published to the promotion gate as an event". The contract surface has 18 event kinds in `contracts/events/`, none describing a backtest result. `EventKind` in `src/pumpgrok/events/models.py` is a closed bus enum with no backtest kind. Any new event type or `NoteKind` value is outside this phase's scope (Phase 15 rule 4 and criterion 11). Plan 16-05 carries the decision.
4. **Stale smoke-10m baseline in other phases.** Phase 15 criterion 14, and Phase 17, 18 and 19 criteria with their CHANGELOG greps, still name `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`. The CHANGELOG has recorded `1dffa...` since Phase 14, so those criteria will not pass as written. Owner amendment needed for those phases. Not edited here. Commit 6281a39 records the Phase 15 item as an open owner item.
5. **Stale fee doc comment.** `src/pumpgrok/execution/fees.py:22` still says ATA rent is 2039280. The owner decision of 2026-11-15 makes rent RPC-read at runtime with a pinned offline fallback. The fix belongs to Phase 15 (SNIPER seat). Phase 16 does not edit that file.
6. **Phase 15 criterion 1 deferral.** Phase 16 criterion 1 runs `pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke`. Commit 6281a39 records the deferral for Phase 15 only. Plan 16-07 assumes it does not carry forward to Phase 16. Owner to confirm.
7. **Budget.** The planner budget is at most 3 tasks and at most 5 files per plan (receipts excluded). Plan 16-06 has 8 files and is over budget. The roadmap fixes the plan list at seven, so it is not split here.

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
| 4 | 16-05 | Autonomous scheduler, store, evidence provider | RISK | 16-03 (with 16-01, 16-02) | false | 6 | BT-13 |
| 5 | 16-06 | Strategy backtest verb and per-strategy report | RISK + JOURNAL | 16-01, 16-02, 16-05 | true | 7 (strategy half), 8, 9 | REC-03, OBS-07 |
| 6 | 16-07 | Phase close | CHIEF + JOURNAL + RISK | 16-01 to 16-06 | false | 1, 10, 11, 12, 13 | PRC-01, PRC-03, LIV-07 |

Waves: 6, matching the roadmap. Wave 1 has two plans with no shared files: 16-01 touches `backtest/` and `tests/backtest/`; 16-04 touches `cli/`, `replay/` and `tests/cli/`.

Seat keys: RISK = bot-02-risk, CHIEF = bot-00-chief, JOURNAL = bot-09-journal. Each plan file lists its seat and the `ownership.yaml` rule that resolves each path.

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

Criteria: 2. Requirements: BT-08, BT-09. Metric set: PENDING OWNER APPROVAL (see proposals).

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

File: `16-03-PLAN.md`. Sizing: 3 tasks, 5 files (within budget). Autonomous: false (owner approves thresholds before they are committed).

| File | Seat | Rule |
|---|---|---|
| src/pumpgrok/backtest/gaps.py | bot-02-risk | src/pumpgrok/** |
| src/pumpgrok/backtest/grading.py | bot-02-risk | src/pumpgrok/** |
| tests/backtest/test_lookahead.py | bot-02-risk | tests/** |
| tests/backtest/test_grading.py | bot-02-risk | tests/** |
| tests/backtest/test_gaps.py | bot-02-risk | tests/** |
| .receipts/bot-02-risk/16-03-grading.json | bot-02-risk | .receipts/bot-02-risk/** |

Criteria: 3, 4. Requirements: BT-10, BT-11. Thresholds: PENDING OWNER APPROVAL. No new fixture directory: gapped and traded-only datasets are built in `tmp_path` and labeled synthetic.

### 16-04 Recorder and replay verbs (wave 1, RISK)

File: `16-04-PLAN.md`. Sizing: 3 tasks, 5 files (at budget). Autonomous: false (three verb specs have no definition in the repo; owner decides before implementation).

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

File: `16-05-PLAN.md`. Sizing: 3 tasks, 5 files (within budget). Autonomous: false (publication channel is an owner decision).

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

File: `16-06-PLAN.md`. Sizing: 3 tasks, 8 files (OVER budget, finding 7). Autonomous: true.

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

File: `16-07-PLAN.md`. Sizing: 3 tasks, 4 files plus 3 receipts (within budget). Autonomous: false (owner reviews the hash record and approves the close).

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

Uncovered: none in the sense of unassigned work. Open items, each planned as a proposal with a checkpoint: `replay import`, `live serve`, `replay rebuild-ticks` semantics, the Metrics v2 formula set, gap and grading thresholds, the cooldown, and the publication channel. None is decided here.

## PENDING OWNER APPROVAL proposals

None of the values or definitions below is final. Each is a proposal with a reason. They are not pinned.

### Metrics v2 set (16-01)

| Metric | Proposed definition | Undefined (None) when |
|---|---|---|
| total_return_lamports | closing equity minus opening equity, lamports | never |
| realized_pnl_lamports | sum over closed round trips of sell proceeds minus buy cost minus fees, excluding the refunded ATA deposit | never |
| trade_count | closed round trips | never |
| win_rate | winning closed round trips over closed round trips | no closed round trips |
| profit_factor | gross profit over gross loss | no losing round trip |
| expectancy_lamports | realized_pnl over closed round trips | no closed round trips |
| average_hold_seconds | mean hold of closed round trips | no closed round trips |
| max_drawdown | largest peak-to-trough decline of equity, as a fraction of peak | non-positive peak |
| annualization_valid | elapsed_days >= 7 (boolean, never None) | not applicable |
| annualized_return | (1 + total_return) ^ (365 / elapsed_days) - 1 | annualization_valid is false, or total_return <= -1 |
| sharpe_ratio | mean per-step return over its sample standard deviation, scaled by sqrt(365 / step_days) | annualization_valid is false, fewer than 2 returns, or zero deviation |
| sortino_ratio | mean per-step return over downside deviation, same scaling | annualization_valid is false, fewer than 2 returns, or zero downside deviation |

Reason: the 7-day floor is the value BT-08 names; the 365-day basis matches `backtest/metrics.py`. Ratios are Decimal; money stays integer lamports. Undefined is None, never 0 or infinity.

### Gap and grading thresholds (16-03)

| Parameter | Proposed | Reason |
|---|---|---|
| long dataset | recorded window of at least 7 days | Same 7-day floor as the annualization validity in BT-08. |
| gap-light | no single gap longer than 300 s, and total gap time at most 5 percent of window | Keeps evidence from being dominated by flattened positions. |
| cooldown after a gap | 300 s, no entries | Matches the 300 s default lookback in momentum_breakout (Phase 15). |
| flatten haircut | 500 bps | Fixed by ROADMAP criterion 4. Not a proposal. |

### Undefined verb specs (16-04)

| Verb | Proposed | Reason |
|---|---|---|
| `replay rebuild-ticks --dataset <name>` | Rebuild the tick stream from the sealed curve observations of one recording, in the paper-engine.md:488 merge order (ts, file_order, line_no). | Only "rebuild ticks from a recording" is written. |
| `replay import --from <dir> --dataset <name>` | Copy one sealed dataset directory after `load_dataset` validation, record its digest, and refuse to overwrite. | No definition exists in the repo. |
| `live serve --mode paper --rpc <url> [--once]` | Runs the live-data paper root. `--mode live` exits 3. The RPC URL is required and has no default. | No definition exists. Phase 15 decision 4 forbids a default endpoint. |

### Publication channel (16-05)

Option A (default proposal): publish a result as an existing `journal_note` with the existing NoteKind `verdict`, carrying result id and grade. No contract change. Option B: add an `EventKind` member on the in-process bus. This is a new event type and needs an explicit owner waiver under Phase 15 rule 4. The plan STOPS on Option B unless the owner waives it in writing.

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

## Execution order

1. 16-01 and 16-04 in parallel (RISK; 16-04 after its owner checkpoint).
2. 16-02 (RISK).
3. 16-03 (RISK, owner threshold checkpoint).
4. 16-05 (RISK, owner publication checkpoint).
5. 16-06 (RISK + JOURNAL).
6. 16-07 (CHIEF + JOURNAL + RISK): gates, guards, pins, CHANGELOG, live refusal, owner checkpoint.

Each seat submits its own receipt for its completion claims (G-2). Journal owns the one CHANGELOG pull request. CHIEF owns the one `.planning` close update. No push in this planning step.
