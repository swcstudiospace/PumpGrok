# Phase 11 Plan Index: Engineering foundation and quality

Source of the plan list: 11-CONTEXT.md (11 plans, 6 waves, 8 PRs in merge order PR-01, PR-02, PR-03, PR-04, PR-05, PR-06, PR-07, PR-08).

| Plan | Title | Wave | Seat | Tasks | Depends on | Branch / PR | Requirements |
|------|-------|------|------|-------|------------|-------------|--------------|
| 11-01 | Receipt glob, waiver removal and the two hash pins | 1 | bot-02-risk | 6 | none | bot-02-risk/v4-p11-receipts-pins-characterization / PR-01 | PRC-05, PRC-04, PRC-03, PRC-09 |
| 11-02 | Characterization for engine, backtest, settings, seat_task | 2 | bot-02-risk | 4 | 11-01 | bot-02-risk/v4-p11-receipts-pins-characterization / PR-01 | QLT-05, RSK-08 |
| 11-03 | Dev tooling lock, fast/soak split, coverage, services CI, SBOM, compose | 1 | bot-02-risk | 5 | none | bot-02-risk/v4-p11-quality-foundation / PR-06 | QLT-01, QLT-02, QLT-07, QLT-08, QLT-09, QLT-10, PRC-10 |
| 11-04 | Split evaluate, backtest, settings; narrow doctor/manifests | 3 | bot-02-risk | 4 | 11-01, 11-02 | bot-02-risk/v4-p11-quality-foundation / PR-06 | QLT-04, QLT-06 |
| 11-05 | Ratchet, property tests, mutation smoke, size/swallow guards | 4 | bot-02-risk | 5 | 11-03, 11-04, 11-06, 11-07, 11-08, 11-09 | bot-02-risk/v4-p11-quality-foundation / PR-06 | QLT-03, QLT-07, QLT-08, QLT-04, QLT-06 |
| 11-06 | Characterize and split paper_adapter sell, batch, confirm | 2 | bot-04-sniper | 4 | 11-01 | bot-04-sniper/v4-p11-paper-adapter-split / PR-02 | QLT-05, QLT-04 |
| 11-07 | Narrow rug excepts; pull forward pump event decoder | 2 | bot-05-rug | 3 | 11-01 | bot-05-rug/v4-p11-rug-excepts-event-decoder / PR-03 | QLT-06, MKT-02 |
| 11-08 | Narrow the jupiter except | 2 | bot-01-scout | 2 | 11-01 | bot-01-scout/v4-p11-jupiter-excepts / PR-04 | QLT-06 |
| 11-09 | Adopt v4 milestone, split seat_task, read-only probe | 3 | bot-00-chief | 4 | 11-01, 11-02 | bot-00-chief/v4-p11-adopt-milestone-seat-task / PR-05 | PRC-06, QLT-04, MKT-03 |
| 11-10 | CHANGELOG entry with both hash pairs | 5 | bot-09-journal | 2 | 11-01..11-09 | bot-09-journal/v4-p11-changelog / PR-07 | PRC-03, PRC-06 |
| 11-11 | Phase close: STATE, verification record, progress table | 6 | bot-00-chief | 2 | 11-01..11-10 | bot-00-chief/v4-p11-close / PR-08 | PRC-06 |

Waves and dependencies equal the CONTEXT exactly. Every files_modified path resolves to its plan seat via resolve_owner with load_manifest. Receipts live at .receipts/<seat>/<branch-slug>.json with task_id set to the receipt slug; no executor writes approved_by. All acceptance commands from the CONTEXT appear verbatim in each plan verification block. No plan uses collect-only, --co, --no-verify, output swallowing, --force, --dry-run or inline PUMPGROK_LIVE_ENABLE. Plans touching src run make lint and make typecheck; no plan runs full pytest -q or the soak test.
