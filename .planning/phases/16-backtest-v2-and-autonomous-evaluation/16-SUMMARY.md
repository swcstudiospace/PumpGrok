---
phase: 16-backtest-v2-and-autonomous-evaluation
status: complete
---

# Phase 16 Summary: Backtest v2 and autonomous evaluation

Status: complete. Phase 16 was implemented on branch v4-phase-14 and merged
via integration PR #75 to local main
8354ee6666139a7817ca246bef9ca2e5a0b3b4b8. This is a local-only record:
no SUMMARY or VERIFICATION for Phase 16 existed on disk before this file;
the evidence below is transcribed from CHANGELOG.md (the v4 Phase 16
section), not re-run at this head. No gate was run during this sync.

## Plans

| Plan | Title | Status |
|---|---|---|
| 16-01 | Metrics v2 and round trips | Complete (commit a3696ec) |
| 16-02 | Event source and strategy-aware replay | Complete (commit c00dfe3) |
| 16-03 | Gap segmentation and evidence grading | Complete (commit 338528e) |
| 16-04 | Replay verbs and recorder amendment | Complete (commits 6a65c40, f776c7f, 0953087) |
| 16-05 | Autonomous scheduler, store and evidence provider | Complete (commit ebab2df) |
| 16-06 | Strategy backtest verb and per-strategy report | Complete (commits bf74098, dca5105) |
| 16-07 | Phase close | Complete (PR #75) |
| 16-08 | run --record, transports and live serve | Complete (commit ea2a22d) |

Plan titles are from 16-PLANS-INDEX.md (wave table); commits from CHANGELOG.md.

## Evidence (transcribed from CHANGELOG.md, v4 Phase 16 section)

- Phase 16: smoke-10m events.hash before: 1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700
- Phase 16: smoke-10m events.hash after: 1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700
- Phase 16: trading-smoke events.hash before: a4461e80f926e46f9d5b85b0305c41fb44c72b63a875369e2b825ea8b7cd9404
- Phase 16: trading-smoke events.hash after: a4461e80f926e46f9d5b85b0305c41fb44c72b63a875369e2b825ea8b7cd9404
- Before values measured at 5fa947b (integration head before the first
  Phase 16 merge 22dd90b); after values measured at f05381d.
- At f05381d, make lint, make typecheck, make test and ./scripts/check.sh
  exit 0 (coverage 91.30 percent, floor 89.9 percent).
- Criterion 1 paper smoke is deferred to deployment by owner decision
  (16-PLANS-INDEX.md row J).
- The CI receipt allowlist admits .receipts/*/16-*.json (commit 81ddc31).

## Merge record

Merged via PR #75 to local main 8354ee6. Local-only: GitHub PR still OPEN
until push. Criterion 1 (paper smoke checkpoint) is deferred to deployment.
