# Phase 13 plan index

| Plan | Title | Wave | Seat | Tasks | Depends on |
|------|-------|------|------|-------|------------|
| 13-01 | Datafeed core, bridge onto the event catalog, live recorder and importer | 1 | bot-02-risk | 5 | 12-01, 12-02 |
| 13-02 | Portal and logs sources, LivePriceSource and marks, probe artifacts | 2 | bot-02-risk | 4 | 11-07, 11-09, 12-02, 12-03, 13-01 |
| 13-03 | Status-agnostic execution tests, fee model v2, paper factory, entry hook | 1 | bot-04-sniper | 5 | 11-01, 11-06 |
| 13-04 | Curve layout fix and allowlist price gate, status stays ASSUMED | 3 | bot-05-rug | 4 | 11-01, 13-02, 13-03 |
| 13-05 | Human-reviewed status flips, VERIFIED only with human reviewed_by | 4 | bot-05-rug | 4 | 11-01, 11-07, 13-02, 13-03, 13-04 |
| 13-06 | CHANGELOG entry with both hash pairs | 5 | bot-09-journal | 2 | 13-01, 13-02, 13-03, 13-04, 13-05 |
| 13-07 | Phase 13 close: STATE, verification record, progress table | 6 | bot-00-chief | 2 | 13-01, 13-02, 13-03, 13-04, 13-05, 13-06 |

Branches and receipts: 13-01 and 13-02 share
bot-02-risk/v4-p13-datafeed-recorder-probe (PR-12); 13-03 uses
bot-04-sniper/v4-p13-fees-paper-factory-hooks (PR-13); 13-04 and 13-05 share
bot-05-rug/v4-p13-curve-layout-status-flips (PR-14); 13-06 uses
bot-09-journal/v4-p13-changelog (PR-15); 13-07 uses bot-00-chief/v4-p13-close
(PR-16). Later plans extend the shared receipt, never overwrite earlier
claims. No plan writes approved_by. 13-05 is human-gated and autonomous
false; all others autonomous true.
