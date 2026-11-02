# Phase 16 Plan Index: Backtest v2 and autonomous evaluation

Source: 16-CONTEXT.md plan list, research plans.json, PR plan PR-27 to PR-29.

| Plan | Title | Seat | Wave | Depends on | Requirements | Tasks | Branch |
|------|-------|------|------|------------|--------------|-------|--------|
| 16-01 | Metrics v2 and round trips | bot-02-risk | 1 | 15-01 | BT-08, BT-09 | 4 | bot-02-risk/v4-p16-backtest-v2 |
| 16-02 | Strategy-aware replay, gaps, grading | bot-02-risk | 2 | 12-03, 13-01, 15-01, 15-02, 15-03, 16-01 | BT-10, BT-11, BT-12, BT-13 | 4 | bot-02-risk/v4-p16-backtest-v2 |
| 16-03 | Scheduler, store, evidence provider | bot-02-risk | 3 | 12-02, 16-02 | BT-10, BT-11, BT-12, BT-13 | 4 | bot-02-risk/v4-p16-backtest-v2 |
| 16-04 | CLI record, replay, strategy backtest | bot-02-risk | 4 | 11-04, 13-01, 14-07, 15-06, 16-02, 16-03 | REC-03, BT-12 | 4 | bot-02-risk/v4-p16-backtest-v2 |
| 16-05 | Per-strategy report section | bot-09-journal | 4 | 11-01, 16-01, 16-02, 16-03 | BT-09, OBS-07 | 4 | bot-09-journal/v4-p16-reports-changelog |
| 16-06 | CHANGELOG entry with hash pairs | bot-09-journal | 5 | 16-01..16-05 | PRC-03, PRC-06 | 3 | bot-09-journal/v4-p16-reports-changelog |
| 16-07 | Phase close: verification record | bot-00-chief | 6 | 16-01..16-06 | PRC-06 | 3 | bot-00-chief/v4-p16-close |

Total: 7 plans, 26 tasks. Waves 1 to 6; 16-04 and 16-05 run in parallel (disjoint seats and files). PRs: PR-27 (16-01..16-04, agent approver bot-00-chief), PR-28 (16-05, 16-06, agent approver bot-02-risk), PR-29 (16-07, agent approver bot-02-risk), checkpoint CP17.

Seat purity: every files_modified path resolves to its plan seat via resolve_owner. Receipts: .receipts/bot-02-risk/v4-p16-backtest-v2.json (task_id v4-p16-backtest-v2), .receipts/bot-09-journal/v4-p16-reports-changelog.json (task_id v4-p16-reports-changelog), .receipts/bot-00-chief/v4-p16-close.json (task_id v4-p16-close). Executors never write approved_by and never write .planning files; summaries and receipt fragments go to /tmp/v4/summaries/.

Resolved inconsistencies:
- backtest/equity.py is absent at this HEAD because draft PRs 17 to 20 are not yet merged (EXT:PRS-16-20-MERGED). Plan 16-01 task 3 preflights for it and halts with an unverified blocker entry rather than inventing a second valuation function.
- CONTEXT lists 16-07 files under .planning while the standing rule says executors never write .planning files and STATE.md names the orchestrator as the only writer. Plan 16-07 produces drafts under /tmp/v4/summaries/ for the orchestrator to apply.
