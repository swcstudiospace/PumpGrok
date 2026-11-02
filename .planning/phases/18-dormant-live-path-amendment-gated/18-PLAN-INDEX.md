# Phase 18 Plan Index: Dormant live path, amendment-gated

Source: 18-CONTEXT.md authoritiative plan list; research/plans.json; pr-plan.md merge order.

| Plan | Title | Seat | Wave | Depends on | PR / Branch | Tasks |
|------|-------|------|------|------------|-------------|-------|
| 18-01 | Stop-state reader, live event source contract, signer protocol schema | bot-02-risk | 1 | none | PR-35 bot-02-risk/v4-p18-dormant-live-path | 4 |
| 18-02 | Gate split entries vs exits, arm pairs with expiry, live verbs | bot-02-risk | 2 | 11-04, 12-01, 17-03, 18-01 | PR-35 bot-02-risk/v4-p18-dormant-live-path | 5 |
| 18-03 | desk-signer core: IPC, nonce window, single send, reconcile | bot-02-risk | 2 | 11-03, 12-01, 15-01, 18-01, 18-07, amendment_wait | PR-35 bot-02-risk/v4-p18-dormant-live-path | 5 |
| 18-04 | Signer tx policy: instruction allowlist, signer blockhash, final-bytes verify | bot-02-risk | 3 | 18-03, amendment_wait | PR-35 bot-02-risk/v4-p18-dormant-live-path | 5 |
| 18-05 | Live adapter client, registry, autonomous_live, reconcile verb, guards | bot-02-risk | 3 | 12-01, 12-02, 17-02, 18-01, 18-02, 18-07, amendment_wait | PR-35 bot-02-risk/v4-p18-dormant-live-path | 5 |
| 18-06 | Shadow-live adapter and stage kill halt mirror | bot-02-risk | 4 | 13-03, 17-03, 18-01, 18-03, 18-04, 18-05, 18-07, amendment_wait | PR-35 bot-02-risk/v4-p18-dormant-live-path | 4 |
| 18-07 | Constitution amendment: one owner-applied PR, HUMAN-GATED | owner-applied multi-seat | 1 | 11-01, 11-09 | PR-34 bot-00-chief/v4-p18-amendment | 4 |
| 18-08 | build_adapter dispatches to live factory only when gate open | bot-04-sniper | 4 | 11-01, 11-06, 18-05, 18-07, amendment_wait | PR-36 bot-04-sniper/v4-p18-live-dispatch | 4 |
| 18-09 | Arm signer rollback runbooks; dormant live wiring | bot-00-chief | 5 | 11-01, 17-04, 18-03, 18-04, 18-05, 18-06, 18-07, 18-08, amendment_wait | PR-37 bot-00-chief/v4-p18-runbooks-live-wiring | 4 |
| 18-10 | CHANGELOG entry with both hash pairs | bot-09-journal | 6 | 18-01..18-09 | PR-38 bot-09-journal/v4-p18-changelog | 3 |
| 18-11 | Phase 18 close: STATE, ROADMAP, verification record | bot-00-chief | 7 | 18-01..18-10 | PR-39 bot-00-chief/v4-p18-close | 3 |

Total: 11 plans, 46 tasks. Waves 1-7. Human-gated: 18-07. Amendment_wait: 18-03, 18-04, 18-05, 18-06, 18-08, 18-09.

Receipts: one fragment per plan under /tmp/v4/summaries/18-NN-RECEIPT.json, merged per PR into .receipts per the PR table. Executors never write approved_by. Amendment_wait plans refuse to execute until the approval record (frozen oracle on main plus green amendment test, proving PR-34 merged) exists; plan 18-07 executors prepare exact diffs from the approved draft only under the same condition.

Planner sign-off on CHECK warning W1: plans 18-02, 18-03, 18-04, and 18-05 carry 5 tasks each, which is acceptable. Each task is atomic with its own files, action, verify, and done; the fifth task is the receipt plus acceptance sweep shared by every plan. Folding it elsewhere would mix receipt duty into build tasks, so the count stays.
