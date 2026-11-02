# Phase 14 plan index

| Plan | Title | Wave | Seat | Tasks | Depends on |
|------|-------|------|------|-------|------------|
| 14-01 | Grok gateway core with the explicit cache key payload, and the non-vacuous evidence fixture | 1 | bot-02-risk | 5 | 12-02 |
| 14-02 | Agents behind the gateway (AgentPort adapters, strict parse) | 2 | bot-08-signal | 4 | 11-01, 14-01 |
| 14-03 | Supervisor event wake: WakeRouter, heartbeat and allowed timers, DegradedBridge, shutdown hook | 1 | bot-00-chief | 4 | 11-01, 11-09, 12-02, 12-03 |
| 14-04 | Event and Grok metrics, call measurement script, Hermes cron cutover, delete the superseded probe script | 3 | bot-00-chief | 5 | 11-01, 12-02, 13-02, 14-01, 14-02, 14-03 |
| 14-05 | Event-mode seat cycle bodies, part 1: scout, signal, risk, sniper, exit | 3 | bot-00-chief | 3 | 11-01, 14-01, 14-02, 14-03 |
| 14-06 | Event-mode seat cycle bodies, part 2: whale, rug, shill, journal rollup, chief, heartbeat | 4 | bot-00-chief | 3 | 14-04, 14-05 |
| 14-07 | Event-mode CLI flag, doctor refusal and time-sync probe; cross-cutting failure suite and the idle-Grok gate in CI | 5 | bot-02-risk | 4 | 11-03, 12-03, 14-02, 14-03, 14-04, 14-06 |
| 14-08 | CHANGELOG: golden hashes events-smoke-10m and events-soak-3d; both legacy hash pairs unchanged | 6 | bot-09-journal | 2 | 14-01, 14-02, 14-03, 14-04, 14-05, 14-06, 14-07 |
| 14-09 | Phase 14 close: STATE, verification record, progress table | 7 | bot-00-chief | 2 | 14-01, 14-02, 14-03, 14-04, 14-05, 14-06, 14-07, 14-08 |

Branches and receipts: 14-01 uses branch bot-02-risk/v4-p14-grok-gateway and receipt .receipts/bot-02-risk/v4-p14-grok-gateway.json (PR-17, approver bot-00-chief agent). 14-02 uses branch bot-08-signal/v4-p14-gateway-agents and receipt .receipts/bot-08-signal/v4-p14-gateway-agents.json (PR-18, approver bot-02-risk agent). 14-03 14-04 14-05 14-06 share branch bot-00-chief/v4-p14-event-wake-cycles and receipt .receipts/bot-00-chief/v4-p14-event-wake-cycles.json (PR-19, approver bot-02-risk agent; each plan appends its claims). 14-07 uses branch bot-02-risk/v4-p14-doctor-failure-suite-idle-gate and receipt .receipts/bot-02-risk/v4-p14-doctor-failure-suite-idle-gate.json (PR-20, human batch at CP14; agent review first). 14-08 uses branch bot-09-journal/v4-p14-changelog and receipt .receipts/bot-09-journal/v4-p14-changelog.json (PR-21, approver bot-02-risk agent). 14-09 uses branch bot-00-chief/v4-p14-close and receipt .receipts/bot-00-chief/v4-p14-close.json (PR-22, approver bot-02-risk agent). No plan writes approved_by.
