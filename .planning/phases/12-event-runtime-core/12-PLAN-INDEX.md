# Phase 12 plan index

| Plan | Title | Wave | Seat | Tasks | Depends on |
|------|-------|------|------|-------|------------|
| 12-01 | Settings skeleton: every v4 section, config-gated off, in one unit | 1 | bot-02-risk | 4 | 11-01, 11-04 |
| 12-02 | Typed errors, harness fakes, the single event catalog, EventBus, store, DLQ and events CLI | 2 | bot-02-risk | 5 | 11-04, 12-01 |
| 12-03 | Deterministic drain with quiescence loop and trading-smoke parity; SourceSupervisor with the single SourceStateBook | 3 | bot-02-risk | 4 | 11-01, 12-02 |
| 12-04 | CHANGELOG entry for Phase 12 with both hash pairs | 4 | bot-09-journal | 2 | 12-01, 12-02, 12-03 |
| 12-05 | Phase 12 close: STATE, verification record, progress table | 5 | bot-00-chief | 3 | 12-01, 12-02, 12-03, 12-04 |

Branches and receipts: 12-01 to 12-03 share branch bot-02-risk/v4-p12-settings-events-core and receipt .receipts/bot-02-risk/v4-p12-settings-events-core.json (12-01 creates, 12-02 and 12-03 append claims; PR-09). 12-04 uses branch bot-09-journal/v4-p12-changelog (PR-10). 12-05 uses branch bot-00-chief/v4-p12-close (PR-11). No plan writes approved_by.
