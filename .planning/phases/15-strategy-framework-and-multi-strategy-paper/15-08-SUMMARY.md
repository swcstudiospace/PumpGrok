# 15-08 Summary: Phase 15 close (strategy framework and multi-strategy paper)

Status: Phase 15 CLOSED on 2026-11-15 by owner decision, head f3c8472 (branch bot-00-chief/v4-phase-14). Criterion 1 (paper smoke checkpoint) is DEFERRED TO DEPLOYMENT, as Phase 14 criterion 1e was.

Base: commit 0052468 (Phase 14 close). Tag `v4-base` is 09f83be. Phase 15 range: 0052468..f3c8472, 90 commits.

This file is the only summary for Phase 15. Plans 15-01 to 15-07 did not write their own SUMMARY files, because `.planning/**` is owned by bot-00-chief. Their facts are taken from the receipts under `.receipts/` and from `git log`.

## Plans

| Plan | Title | Seat | Status | Primary commits |
|---|---|---|---|---|
| 15-01 | Parameter identity and strategy bounds (STR-06, criterion 2) | bot-02-risk | Complete | 1be0b26, 718dd84, 91cf977 (receipt), 196a638 (style) |
| 15-02 | Strategy protocol, static registry, paper-event overlay (STR-01, criteria 3 and 4) | bot-02-risk | Complete | 8d5814a, 0091c5c, 6fcad84, 87f9c73 (receipt) |
| 15-03 | Runtime, capital slices, attribution, legacy through runtime (STR-03, criterion 5) | bot-02-risk | Complete | e9ea8ea, 01f9088, 53c9b3f, e86ad93 (receipt) |
| 15-04 | Three baseline strategies, fixtures, no-LLM, recovery (STR-04, STR-05, RT-04 library half, criteria 6-8) | bot-02-risk | Complete | 62b2b07, b22d817, 99d512d, 223c882 (receipt) |
| 15-05 | Live-data paper root and exit-rule ticket filter (MKT-09, criteria 10 and 12) | bot-00-chief + bot-02-risk | Complete | b168841, 7e971dc, adb5231, 27bbf16, 27d4fff (receipts), 2deb724, 16fceb5 |
| 15-06 | Intent router to exec.place (RT-02, criterion 11) | bot-00-chief | Complete; legacy path accepted as replay-only exception | c831531, 2b697b9, 97d11f2, dcd1296 (receipt), 0ff4e5a, 563bf37 |
| 15-07 | Fee model v2 paper default and the trading-smoke re-pin (FEE-01, criteria 9 and 14 pin half) | bot-04-sniper + bot-02-risk (+ bot-00-chief) | Complete; re-pin owner-approved | a2b9045, 0b843d4, b7443db (receipt), 0713fc1 (receipt), e65a145, 4c83ee0, 4f7763d, 9384bf2, 4c6d7d0, bd69502 |
| 15-07 (follow-up) | ATA rent held as a deposit asset, refunded at close, deposit map through every fold (FEE-01) | bot-04-sniper, bot-02-risk, bot-00-chief | Complete; refund-era pin owner-approved | d7c61b3, df0bb73, c88e9e1, 6687d22, dd2bad7, 5ff5b7e, 8184f7a, de55a77, b558260, ec92f3f, a658710, 4d8dea9, 3b51946, 2e31eab, 1c9488d, be01a29, 2f4538a, e63d863, c01155c, 4ac43a6, 51e47f0, b46bfd8, f623aa7, 1e94963, 60f242d, 0251011, 45a40c0, f3c8472 |
| 15-08 | Phase close: gates, contract surface, CHANGELOG, live refusal (PRC-01, PRC-03, LIV-07) | bot-00-chief + bot-09-journal | Closed with criterion 1 deferred | ddb78a6, 189fa82 (blocked receipt), 8f116b0, c88e9e1, criterion 1 remediation commits 22cbd37, ceae6c4, bc8349f, 2d7ecae, a5c417e, abc17f7, 3f8d372, e918841, 1c44cef, 350e1ba, dec1acf, plus the closure commit for this file and ROADMAP.md |

Notes on the table:

- 15-08 receipt `.receipts/bot-00-chief/15-08-phase-close.json` (commit 189fa82) recorded the plan as BLOCKED at ddb78a6: make lint, make typecheck and make test failed, and the paper smoke replay refused to start. The remediation commits listed above came after it. The owner record of 2026-11-15 states that lint, typecheck, test and check.sh all exit 0 at f3c8472. The paper smoke is still deferred (see Criterion 1).
- Plan 15-07 has a second set of commits (the deposit-refund series, FEE-01) that followed its receipts. The CHANGELOG records them as the "refund era" entries.

## Owner decisions (binding, recorded for this phase)

1. Phase 15 is closed with criterion 1 (paper smoke checkpoint) deferred to deployment. Every other criterion passes on f3c8472 per the owner record of 2026-11-15.
2. Phase 16 criterion 12 baseline is amended from b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d to 1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700. The amendment is recorded in ROADMAP.md.
3. Paper fee model v2 is the paper default (`paper_fees.model = "v2"`). v1 stays accepted explicitly.
4. The live-data paper root has no default RPC endpoint. The owner chooses it at deployment (decision 4 of the plans index).
5. The intent router is below autonomous-paper: it refuses and journals, and approves nothing.
6. ATA rent: the live paper root reads the rent-exempt minimum from RPC at build time (`getMinimumBalanceForRentExemption(165)`). Replay keeps the offline pin: 1488440 lamports, epoch 1033, source SIMD-0437 public docs. The earlier proposal of 2039280 is superseded and is not used anywhere in the default.
7. Forced-close proceeds convention: a forced close on a ledger mark reports proceeds as market value less network cost. The mark already holds the open account's ATA deposit, so the deposit returns to cash once inside those proceeds. Cash credit equals proceeds, with no second credit (commits 45a40c0, f3c8472).
8. The trading-smoke pin a4461e80 is approved (see Hashes below).
9. The legacy_screening placement path, which calls exec.place directly, is accepted as a documented replay-only exception (`docs/strategies-replay-exception.md`, guarded by test commit 563bf37).

## Criteria status

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | make lint, make typecheck, make test, ./scripts/check.sh, paper smoke replay | DEFERRED TO DEPLOYMENT. Lint, typecheck, test and check.sh: owner record exit 0 at f3c8472 (make test coverage 91.86%). Paper smoke: not passed here (see below). | 15-08 receipt; owner record |
| 2 | Parameter identity and legacy hashes | Owner record pass | 15-01 receipt; tests/upgrade |
| 3 | Strategy base and registry; BOUNDS equal upgrade_bounds.toml | Owner record pass | 15-02 receipt |
| 4 | Paper-event overlay (6 positions, 40 trades per day; live unchanged at 3 and 20) | Owner record pass | 15-02 receipt; docs/runbooks/strategies.md |
| 5 | Attribution, allocation, legacy parity, strategy state, ticket refs | Owner record pass | 15-03 receipt |
| 6 | Fixture datasets strat-breakout, strat-launch, strat-reversion produce asserted fills | Owner record pass | 15-04 receipt |
| 7 | No LLM reachable from strategies; idle runtime makes zero calls | Owner record pass | 15-04 receipt (no_llm import graph check) |
| 8 | Strategy restart recovery, library half | Owner record pass | 15-04 receipt |
| 9 | Fee model v2 default; backtest and paper fees agree | Owner record pass | 15-07 receipts; c54c665 |
| 10 | Live-data paper root and exit-rule ticket filter; read-only | Owner record pass | 15-05 receipt |
| 11 | Intent router is the only path to exec.place for strategy Intents | Owner record pass, with the legacy replay-only exception | 15-06 receipt; docs/strategies-replay-exception.md |
| 12 | Import graph has no live or signing path | Owner record pass | 15-05 double receipt |
| 13 | git diff --name-only v4-base -- contracts is empty | 0 files changed (15-08 receipt; 15-05 and 15-06 checks) | 15-08 receipt |
| 14 | smoke-10m hash unchanged and trading-smoke pin | See Hashes. The literal b69c29... check in the criterion text does NOT match the measured 1dffa784... | 15-08 receipt; CHANGELOG |
| 15 | run --mode live --once exits 3 | Exit 3 (owner record; 15-08 receipt) | 15-08 receipt |

Criterion 1 detail. The 15-08 receipt at ddb78a6 ran the paper smoke replay (`uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke`). It exited 1 with "paper start refused: required inputs are missing". The worktree has no var/operator directory and no var/ledger.sqlite. Seat tool access is not recorded (`seat_tool_access` missing for paper). Recording those grants is an approval act, and it was not done. The owner deferred criterion 1 to deployment, as with Phase 14 criterion 1e.

Verification source. The gate results above are the owner's record for f3c8472. They were not re-run in this closure. This closure ran no make target, no lint, no formatter and no full gate, per the assignment.

## Hashes

| Fixture | Before | After | Notes |
|---|---|---|---|
| smoke-10m events.hash | 1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700 | 1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700 | Equal. seq 146, events read 41. Unchanged by this phase. |
| trading-smoke events.hash (pre-phase pin) | 106495a9e335ada1b2407811feda000eb6cd32dbae10372209b9ddf697161627 | a4461e80f926e46f9d5b85b0305c41fb44c72b63a875369e2b825ea8b7cd9404 | Current pin in tests/fixtures/replay/pins/trading_smoke.json. seq 155, row count 155, events read 5. Approved. |
| trading-smoke, fee-v2-only intermediate | 106495a9... | cac36d18896f6f36a7a5ab515047d309190b836a9a6370a780334a4bc9085a62 | Superseded by the refund-era pin. Recorded in the CHANGELOG. Rows 149, 150, 151 and 155 changed. |

Deviation from the plan on the smoke-10m before value. The plan text and criterion 14 cite b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d. The measured value at HEAD, and in the Phase 14 CHANGELOG, is 1dffa784. The CHANGELOG records 1dffa784 as both before and after. The owner amended only Phase 16 criterion 12. Phase 15 criterion 14 text is unchanged here. See Open items.

Deviation from the plan on the trading-smoke pin count. The plan and the owner decision describe one trading-smoke re-pin. The history has two moves: first to cac36d18 (fee v2, owner-approved, commits e65a145 and 9384bf2), then to a4461e80 (refund era, commit d7c61b3, with the 24 characterization digests and the event smoke golden re-pinned in df0bb73 and c88e9e1). The CHANGELOG records both. The owner decision approves a4461e80 as the pin.

## Deviations recorded in the plan reports

Plan 15-01 (bot-02-risk)
- gate.py and harness.py were not edited. ParamSet.candidate() and CandidateParams.content_hash already carry the strategy section.
- Strategy out-of-bound and unbounded-key errors name the key and range, without echoing the value. Filter and exits messages are unchanged.
- ParamSet serialization omits the strategy key when absent or empty, so legacy stored JSON and hashes are unchanged.
- Strategy parameters affect identity and bounds only. No replay or strategy code consumes them yet. Trials differ in identity but score the same until 15-03 and 15-04 wire them in.
- SUMMARY file not written by the seat (.planning is chief-owned).

Plan 15-02 (bot-02-risk)
- Intent carries a seventh field, version_id, which the plan's field list omitted. The task text requires it. Owner to confirm before the freeze is treated as final.
- TickSnapshot(mint, ts, launch_ts, price_lamports, unique_buyers, curve_progress) and TapePoint(ts, price_lamports) were chosen by the seat. Owner to review.
- version_id takes (strategy_cls, params), not (params), because the strategy id and module source are needed.
- Intent rejects size_lamports <= 0, float and bool field types, and sides other than buy or sell.
- legacy_screening was a stub in registry.py until 15-03 moved it to strategies/legacy.py with a re-export.
- Registry test asserted the deferred set rather than baseline equality. The 15-02 receipt asked 15-04 to replace that with per-strategy equality.

Plan 15-03 (bot-02-risk)
- The placement sink in strategies/legacy.py repeats the body of supervisor/scheduler/orders.py::_place_candidates for one intent. It imports private helpers (_await_order, _replay_trade, _replay_trading, _run_exit_rules, _ReplayTrading) from the scheduler package. orders.py and serve.py are chief-owned. CHIEF is asked to confirm the coupling or offer a public seam. Open.
- The exit pass and the risk halt check run from the driver's before/after stamp hooks, not as strategies. Parity holds on tests/fixtures/replay/smoke only.
- TickSnapshot.price_lamports is the fixture's curve reserve S, used as an integer price proxy. Per-token price S/T is fractional. The 15-04 strategies were written against this choice.
- Per-strategy P&L is folded from ledger rows through strategy_ticket_refs, attributed to the ticket's strategy or to the desk. The plan's fold of strategy_state snapshots is not implemented. The criterion needs only that the buckets equal the desk total, which attribute() checks.
- LedgerStore.append_batch gained an optional keyword-only sidecar writer, run in the same transaction before COMMIT. append() is unchanged.
- The seat wrote no SUMMARY file.

Plan 15-04 (bot-02-risk)
- probation is not defined by the plan or the repo. Encoded as the per-mint count of entries by the strategy. Breakout and reversion do not gate on it.
- peaks is not defined by the rules. Encoded as the highest price since entry for each open position.
- The three baseline strategies keep their own tape in StrategyBook, not StrategyContext.tape, because recovery must persist tapes and runtime.py is not in the plan's file list. StrategyContext.tape is unused by them.
- Fills are the Intents passed to the runtime sink. Placement through exec.place is the router's job (15-06).
- Decision ids are deterministic strings (strategy, side, mint, tick time), not ULIDs. Entry size is a module constant equal to the replay buy amount.
- Mean reversion uses population statistics in exact rational arithmetic. Zero variance and fewer than two points decide nothing.
- Files outside the plan list: registry.py and tests/strategies/test_registry.py (renamed to test_strategy_registry.py in dec1acf), for the registration and BOUNDS equality tests the task text requires.
- DEFAULTS in the three modules and the PROPOSALS table are PENDING OWNER APPROVAL.

Plan 15-05 (bot-00-chief with bot-02-risk)
- The exit fold tracks one open position per mint, so two strategies cannot hold concurrent positions on one mint. The reachable case (strategy A closes, strategy B re-enters under its own ticket) is covered by test_each_position_on_a_mint_is_filtered_by_its_own_ticket.
- The exit filter also skips a graduation close on a strategy position with a pending sell. The plan named only rule sells.
- build_live_paper_root takes budget, limits, max_age_s and max_observations as required keyword arguments with no defaults. Their values are deployment choices, not pinned here. Owner decision needed before deployment.
- The root uses the default manual-ticket autonomy and the host kill-switch file under data_dir. It has no event consumers. Its EventBus dead-letter sink raises instead of dropping an event.
- Open: build_live_paper_root has no production caller. A grep of src and tests finds only its definition and tests. Deployment must pass endpoint, rent_rpc, budget, limits, max_age_s and max_observations.
- Follow-up 2deb724 removed the pumpgrok.events.bus import from the guarded supervisor root. Its bridge is built through the datafeed factory added in 16fceb5.
- Handoff 16fceb5 (additive build_observation_bridge factory in datafeed) awaits bot-02-risk review. The commit records it as an owner-review handoff.

Plan 15-06 (bot-00-chief)
- Check order: allocate ticket, link ticket to strategy, slice check, RiskEngine.check, exec.place. The plan listed the link last. The link comes first so every routed decision is attributed and the link row is the idempotency record.
- IntentRouter takes two extra required keyword arguments: slices (computed by allocation.slice_lamports) and max_slippage_bps. exec_place is an async callable taking the place payload dict, not PlaceIn.
- Atomicity: the ticket row and the link row are separate transactions. A crash between them leaves an unlinked ticket with no order placed. Editing ledger/tickets.py was outside the file set.
- Idempotency key: route|strategy|decision. A repeat returns duplicate and never calls exec.place, including after a refused first attempt that was linked.
- Refusal reasons beyond the plan's list: unknown_strategy, approval_mismatch, ticket_allocation_failed, autonomy_manual_ticket (the last is the plan's below-autonomous-paper refusal).
- Autonomy comes from read_autonomy on the ledger. The RiskEngine's own constructor autonomy is separate. At manual-ticket RiskEngine returns approval_missing, so the router refuses.
- Legacy placement bypasses the router (src/pumpgrok/strategies/legacy.py, _place_buy calls trading.place). The receipt recorded this as a must-have not met, needing an owner decision. The owner accepted it as a documented replay-only exception. See docs/strategies-replay-exception.md and the guard test in 563bf37.
- Two files under src/pumpgrok/risk/engine (core.py, rules.py) differ from v4-base. They come from c50791f, which predates this plan. This plan did not change them.
- Test duplication: tests/desk/test_ticket_approval_allocation.py duplicates test_intent_router.py helpers, because tests/desk has no package __init__.py.

Plan 15-07 (bot-04-sniper, bot-02-risk, bot-00-chief)
- Fee model v2 was absent from the repository at base 0052468. The Phase 13 roadmap note saying v2 was selectable was wrong. Corrected in c54c665. v2 was built here.
- Terms: FeeModelV2 subclasses FeeModel with ata_rent_lamports, pumpportal_fee_bps = 0 (applies only when the PumpPortal builder is selected, which v4 paper does not use), priority_cap_micro_lamports_per_cu = 20000 (equal to the current default).
- ATA rent is charged on the first FILLED buy of a mint. first_buy is decided from FillRecorded rows, so a restart agrees. The rent is folded into network_cost_lamports on that fill. No event field was added.
- Gap closed: the receipt recorded read_ata_rent as wired into no composition root. Commit 4f7763d routes build_live_paper_root through read_ata_rent when rent_rpc is supplied. A failed read fails the build. Without rent_rpc, the offline pin is used (replay and tests).
- Cross-seat edits, owner route: buy.py (ATA rent on first buy) and test_paper_factory.py (assertion default flip; test name still reads defaults_to_v1).
- paper_fees.model is Literal[v1, v2], default v2. Unknown values fail ConfigError.
- Refund era (FEE-01 follow-up): the first-buy ATA rent is a refundable deposit held as an asset until the position closes (dd2bad7). It is stored in a sidecar table written in the opening's own transaction via append_batch sidecar, outside the hash chain. Ledger rows and schemas are unchanged. A partial sell keeps the deposit whole. A full close credits the deposit to cash on the close fill, and realized P&L is measured on cost basis net of the deposit (8184f7a). Forced closes do the same and book no rent as proceeds (de55a77). Forced-close proceeds follow the owner convention above (45a40c0, f3c8472).
- The deposit map (position_deposits_by_seq) is threaded through every reduce fold: ledger, risk engine state, reconcile replay, net_lamports, equity_curve, daily report, attribution, promotion, exit and shutdown, and day-start equity (commits 3b51946 to e63d863, c01155c, 4ac43a6). reduce(state, event, deposits) is the contract.
- Handoff e63d863: reporting/daily.py is owned by bot-09-journal. bot-02-risk committed the fold change. bot-09-journal review is awaited.
- Helper: the deposit reader was moved to pumpgrok.ledger.deposit_reader so ledger and risk do not import execution (b46bfd8, 0251011).
- The 15-07 receipts record the trading-smoke candidate as NOT PINNED. The pin movement was owner-approved in two steps (see Hashes).
- The offline ATA rent pin applies when no rent_rpc is supplied (replay and tests). When rent_rpc is supplied, the live root reads RPC (see Gap closed above).

Plan 15-08 (bot-00-chief, bot-09-journal)
- The receipt at ddb78a6 was BLOCKED. The owner closed the phase with criterion 1 deferred.
- docs/runbooks/strategies.md was written (189fa82). It states the owner open question on new_launch_sniper.max_age_seconds versus filter.min_age_seconds (120).
- The CHANGELOG Phase 15 section was extended, not duplicated (ddb78a6, 4c83ee0, 8f116b0). Its title is "v4 Phase 15: strategy framework and multi-strategy paper". It records the smoke-10m 1dffa784 pair and both trading-smoke moves.
- The ROADMAP Phase 15 list line is marked [x] with the closure note (this closure).

## Open items for the owner

1. Criterion 14 literal. The Phase 15 criterion 14 verify command and CHANGELOG grep still name b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d. The measured and recorded value is 1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700. The literal check does not pass as written. The owner amended only Phase 16 criterion 12. Decide whether to amend Phase 15 criterion 14 the same way.
2. Criterion 1 deployment checkpoint. The paper smoke needs operator seat tool-access records in the deployment environment. Recording them is an approval act.
3. Strategy parameters are PENDING OWNER APPROVAL: the DEFAULTS in momentum_breakout, new_launch_sniper and mean_reversion, the PROPOSALS table in tests/strategies/test_strategy_registry.py, and the strategy sections of src/pumpgrok/config/upgrade_bounds.toml. Do not treat them as final pins.
4. Fee v2 terms: pumpportal_fee_bps = 0 and priority_cap_micro_lamports_per_cu = 20000 are PENDING OWNER APPROVAL as proposals. The ATA rent offline pin 1488440 at epoch 1033 is owner-set for replay.
5. Intent.version_id as a seventh field (15-02). Owner to confirm.
6. new_launch_sniper.max_age_seconds versus filter.min_age_seconds (120). Owner to confirm the interaction.
7. read_ata_rent is outside the read-only boundary. ReadOnlyBoundary._RPC_METHODS in src/pumpgrok/datafeed/readonly.py allows only logsSubscribe, getAccountInfo and getTransaction. getMinimumBalanceForRentExemption is called through the injected rent_rpc client, not through ReadOnlyBoundary. The 15-04 receipt carried this as a gap, and it was not re-verified in this closure. Owner or bot-02-risk decision needed.
8. build_live_paper_root has no production caller, and deployment values are unset: endpoint (owner, owner decision 4), budget, limits, max_age_s, max_observations, and rent_rpc. Owner and chief decision needed.
9. Placement sink coupling (15-03): strategies/legacy.py imports private scheduler helpers and repeats _place_candidates. CHIEF to confirm or offer a public seam.
10. Legacy replay-only exception (15-06). Accepted by the owner. Criterion 11's must-have "no other path exists" holds only with this exception.
11. Handoffs awaiting review: 16fceb5 (datafeed build_observation_bridge factory, bot-02-risk) and e63d863 (reporting/daily.py deposit fold, bot-09-journal).
12. Adjacent exit tests named by the 15-05 receipt (tests/integrity/test_peaks_survive_restart.py, tests/integrity/test_serve_restart_keeps_peaks.py, tests/degradation/test_grok_hang_exit.py) are not recorded as run in any receipt. The 15-05 receipt asked for them to be run before phase close.
13. Test basename collision: tests/strategies/test_registry.py and tests/core/test_registry.py shared a basename and failed collection. Fixed by renaming to tests/strategies/test_strategy_registry.py (dec1acf). Recorded here for the record.
14. The trading-smoke pin moved twice (see Hashes). The owner decision approves a4461e80. The plans index said one re-pin.
15. Plans 15-01, 15-02, 15-03, 15-04 and 15-07 exceed the planner's file budget (plans index finding 5). The owner accepted the roadmap's fixed plan list.

## Files changed by this closure

- .planning/ROADMAP.md: Phase 15 list line marked [x] with the closure note. Phase 16 criterion 12 baseline amended to 1dffa784 with an owner amendment note.
- .planning/phases/15-strategy-framework-and-multi-strategy-paper/15-08-SUMMARY.md: this file.

No code, test, fixture, pin, contract or CHANGELOG file was changed by this closure. Nothing was pushed.

## Post-merge record (2026-11-26)
Phase 15 code merged to local main 8354ee6666139a7817ca246bef9ca2e5a0b3b4b8 via integration PR #75. Criterion 1 remains deferred to deployment. Local-only: GitHub PR still OPEN until push.
