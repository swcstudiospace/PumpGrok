# Roadmap: PumpGrok Desk v3

> v3 is archived (2026-11-01, tech_debt recorded). Phase details: `.planning/milestones/v3-ROADMAP.md`. Phase evidence: `.planning/milestones/v3-phases/`. Milestone audit: `.planning/milestones/v3-MILESTONE-AUDIT.md`.

## Shipped

- [x] **v3: PumpGrok Desk v3** - archived 2026-11-01 with tech_debt recorded, 7 phases (6-10, 20, 21). Archived: [roadmap](milestones/v3-ROADMAP.md), [requirements](milestones/v3-REQUIREMENTS.md), [audit](milestones/v3-MILESTONE-AUDIT.md).
- [x] **v2: PumpGrok Desk v2** - shipped 2026-10-23, 5 phases, 44 plans. Archived: [roadmap](milestones/v2-ROADMAP.md), [requirements](milestones/v2-REQUIREMENTS.md), [audit](milestones/v2-MILESTONE-AUDIT.md).

## Progress

**Execution Order:**
Phases execute in numeric order: 6 -> 7 -> 8 -> 9 -> 10 -> 20 -> 21

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 6. Integrity closure | 9/9 (+ fix-up 06-01b) | Complete | 2026-10-26 |
| 7. Documentation upgrade | 6/6 | Complete | 2026-10-25 |
| 8. Backtest and paper evaluation | 10/10 | Complete | 2026-10-25 |
| 9. Bounded paper self-upgrade | 7/7 | Complete | 2026-10-25 |
| 10. Live readiness, kept disabled | 3/3 | Complete | 2026-10-25 |
| 20. Close gap: LIV-01 live adapter import path | 1/1 | Complete | 2026-11-01 |
| 21. Close gap: DOC-03 documentation accuracy | 1/1 | Complete | 2026-11-01 |

### Phase 20: Close gap: LIV-01 live adapter import path

**Goal:** The import graph has no path from the CLI, backtest, paper, or upgrade modules to the live adapter, proven at runtime and by the guard (audit gap LIV-01).
**Requirements**: LIV-01
**Depends on:** Phase 10
**Plans:** 1/1 plans complete

Plans:
- [x] 20-01-PLAN.md - red regression tests, package re-export removed, guard parent-package edges, CHANGELOG entry

### Phase 21: Close gap: DOC-03 documentation accuracy

**Goal:** The documents named by DOC-03 match the code: no retired vendor or unimplemented scout flow presented as live, no absent helper scripts, no read-only claims contradicted by ledger or setup writes, plugin manifests at the package version, and CLAUDE.md line anchors that resolve (audit gap DOC-03, plus DOC-01 anchors found during re-verification).
**Requirements**: DOC-03
**Depends on:** Phase 20
**Plans:** 1/1 plans complete (two documented closure rounds)

Plans:
- [x] 21-01-SUMMARY.md - red-first manifest test, manifest and wording corrections, ARCHITECTURE diagram, CLAUDE.md anchors, follow-up and round 2 fixes
