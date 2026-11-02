# Phase 17 Plan Index: Risk hardening and promotion lifecycle

Source: 17-CONTEXT.md, the authoritative plan list. plans.json agrees on all seven ids, waves, seats, dependencies, and file sets.

| Plan | Title | Seat | Wave | Depends on | Tasks | Branch |
|------|-------|------|------|------------|-------|--------|
| 17-01 | Strategy slice and strategy kill on existing rows | bot-02-risk | 1 | 11-04, 12-01, 15-01, 15-02, 16-03 | 4 | bot-02-risk/v4-p17-risk-promotion |
| 17-02 | Entry checks and mint lists; feed health and live failure classes | bot-02-risk | 2 | 12-03, 13-03, 17-01 | 4 | bot-02-risk/v4-p17-risk-promotion |
| 17-03 | Promotion package, thresholds, gate paper parameter, demote verb | bot-02-risk | 2 | 12-02, 12-03, 15-01, 16-03, 16-04, 17-01 | 5 | bot-02-risk/v4-p17-risk-promotion |
| 17-04 | Event desk composition root and risk promotion entry wiring | bot-00-chief | 3 | 11-01, 12-02, 12-03, 13-02, 13-03, 14-01, 14-02, 14-03, 14-06, 15-02, 15-06, 17-01, 17-02, 17-03 | 4 | bot-00-chief/v4-p17-event-desk-recovery |
| 17-05 | Restart recovery wiring with crash tests | bot-00-chief | 4 | 11-01, 12-02, 15-03, 17-04 | 3 | bot-00-chief/v4-p17-event-desk-recovery |
| 17-06 | CHANGELOG entry with both hash pairs | bot-09-journal | 5 | 17-01, 17-02, 17-03, 17-04, 17-05 | 2 | bot-09-journal/v4-p17-changelog |
| 17-07 | Phase 17 close: STATE, verification record, progress table | bot-00-chief | 6 | 17-01, 17-02, 17-03, 17-04, 17-05, 17-06 | 2 | bot-00-chief/v4-p17-close |

PRs in merge order: PR-30 risk promotion covers 17-01 17-02 17-03, PR-31 chief event desk recovery covers 17-04 17-05, PR-32 journal changelog covers 17-06, PR-33 chief close covers 17-07. Checkpoint CP17.

Shared file chain: steps.py in 17-01 then 17-02 then 18-01 then 18-05, constants.py in 17-01 then 17-02, breakers.py in 17-02 then 18-05, gate.py 15-01 then 17-03. Later plans merge first only in that order.

Seat purity: every files_modified path resolves to the plan seat. 17-03 CLI files resolve to bot-02-risk because no cli double star pattern exists under ownership, so the default src pumpgrok double star risk rule applies, matching Design C. Chief plans touch tests only under tests desk. RSK-06 choke point proof belongs to Phase 18; 17-01 and 17-02 keep enforcement inside the engine check path and record the signer repeat as a Phase 18 dependency.
