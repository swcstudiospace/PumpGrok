# Phase 19 Plan Index: Observability, docs, hardening and milestone audit

Source: 19-CONTEXT.md, the authoritative plan list. plans.json agrees on all nine ids, waves, seats, dependencies, and file sets.

| Plan | Title | Seat | Wave | Depends on | Tasks | Branch |
|------|-------|------|------|------------|-------|--------|
| 19-01 | Skill solana-market-data covers the live feed, watch set and fail-closed price rules | bot-01-scout | 1 | 11-01, 13-02 | 4 | bot-01-scout/v4-p19-market-data-skill |
| 19-02 | Skill replay-and-backtest covers record, trim, import, strategy backtest and autonomous runs | bot-08-signal | 1 | 11-01, 16-04 | 4 | bot-08-signal/v4-p19-backtest-skill |
| 19-03 | health.json event and strategy sections, per-strategy P and live L metric families | bot-00-chief | 1 | 11-01, 14-04, 17-04 | 4 | bot-00-chief/v4-p19-health-metrics |
| 19-04 | Doctor v4 report, nightly event-mode soak and removal of the amendment waiver | bot-02-risk | 1 | 11-03, 14-07, 17-02, 17-03, 17-04, 18-02, 18-07 | 5 | bot-02-risk/v4-p19-doctor-soak-alerts-docs |
| 19-05 | Alert rules checked against the metric registry; risk-owned docs describe v4 | bot-02-risk | 2 | 14-04, 18-07, 19-03 | 4 | bot-02-risk/v4-p19-doctor-soak-alerts-docs |
| 19-06 | CHANGELOG v4 closeout entry with the final hash lines | bot-09-journal | 3 | 19-01, 19-02, 19-03, 19-04, 19-05 | 3 | bot-09-journal/v4-p19-changelog |
| 19-07 | Docs (chief-owned): README, SETUP, desk skills, datafeed, recorder and promotion runbooks | bot-00-chief | 2 | 11-01, 16-04, 18-07, 19-04 | 4 | bot-00-chief/v4-p19-docs-audit-close |
| 19-08 | Milestone audit: every v4 requirement traced to evidence, live still refused | bot-00-chief | 4 | 19-01, 19-02, 19-03, 19-04, 19-05, 19-06, 19-07 | 5 | bot-00-chief/v4-p19-docs-audit-close |
| 19-09 | Phase 19 close: STATE, milestone archive, progress table | bot-00-chief | 5 | 19-01, 19-02, 19-03, 19-04, 19-05, 19-06, 19-07, 19-08 | 3 | bot-00-chief/v4-p19-docs-audit-close |

PRs in merge order: PR-40 scout skill covers 19-01, PR-41 signal skill covers 19-02, PR-42 chief health metrics covers 19-03, PR-43 risk doctor soak alerts docs covers 19-04 19-05, PR-44 journal changelog covers 19-06, PR-45 chief docs audit close covers 19-07 19-08 19-09. Checkpoint CP19. Human-gated: 19-08 (owner reads the audit, OD-19); PR-43 and PR-45 carry agent review first with human:SomeRandmGuyy approval in the CP19 batch.

Shared file chain: gates.yml 11-01 then 18-07 then 19-04; ci.yml 11-03, 14-07 then 19-04; README, SETUP 18-07 then 19-07; AGENTS and ARCHITECTURE 18-07 then 19-05; tests/docs grows in 19-05; CHANGELOG ends with 19-06. Later plans merge first only in that order. 19-06 runs order_after 18-10; 19-09 runs order_after 18-11.

Seat purity: every files_modified path resolves to the plan seat via resolve_owner (verified against ownership.yaml before writing). Chief plans touch tests only under tests/desk (19-03). 19-08 and 19-09 write chief-owned .planning paths as the explicit CONTEXT exception; all other plans write summaries and receipt fragments to /tmp/v4/summaries only.
Check-warning fixes (19-PLAN-CHECK.md W-1 to W-3, waves deps and seats unchanged): W-1 soak double-run owned by 19-04 (determinism marker, Test 4, byte-identical drains) with the replay-report double-run and two-sample verify owned by 19-08 audit evidence; W-2 criterion-5 wording grep across README SETUP CLAUDE owned by 19-08 with the README and SETUP self-gate in 19-07 and opt-in plus cadence-default prose required there; W-3 repo-wide marker scan recorded with dispositions in 19-08 and the live-paths absence gate enforced in 19-08 verification and 19-09 close verification.
