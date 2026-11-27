# GSD inventory (Wave 1, ultrathink graph ut-f45d0da218-7d301dfb)

Source records are read-only: `.planning/` (ROADMAP.md, STATE.md, MILESTONES.md, phases/, milestones/v2-phases/). This file is the run-level index and points at them. Branch `bot-00-chief/phase-6-integrity`, HEAD `323abf0`.

## Milestones

| Milestone | Status | Member phases | Source |
|---|---|---|---|
| v2 PumpGrok Desk v2 | COMPLETE (shipped 2026-10-23) | 01-foundation, 02-restructure, 03-tools-and-skills, 04-paper-trading-and-autonomy, 05-hardening | .planning/MILESTONES.md |
| v3 PumpGrok Desk v3 | IN_PROGRESS (INTEGRATION_VERIFYING) | 06-integrity-closure, 07-documentation-upgrade, 08-backtest-and-paper-evaluation, 09-bounded-paper-self-upgrade, 10-live-readiness-kept-disabled | .planning/STATE.md, .planning/v3-MILESTONE-AUDIT.md |

Only v3 is outstanding. Its close needs the Phase 6 PR shipped and merged (draft PR #71 is `DIRTY`) plus the milestone waiver removal in `.github/workflows/gates.yml`.

## Phases

| Phase | Status | Plans / SUMMARY | VERIFICATION frontmatter | Notes |
|---|---|---|---|---|
| 06-integrity-closure | COMPLETE with owner-approved deviation (criterion 17 waived, PR-bound) | 9 / 10 (06-01b fix-up has no PLAN) | passed | Phase PR pending |
| 07-documentation-upgrade | COMPLETE | 6 / 6 | passed | |
| 08-backtest-and-paper-evaluation | COMPLETE | 10 / 10 | passed | |
| 09-bounded-paper-self-upgrade | COMPLETE | 7 / 7 | passed | |
| 10-live-readiness-kept-disabled | COMPLETE | 3 / 3 | passed | Live stays refused (exit 3) |
| v2 01..05 | ARCHIVED, COMPLETE | 14/14, 5/5, 7/7, 10/10, 8/8 | passed | Not reopened (no outstanding milestone depends on them) |

## Blocker register

| Blocker | Class | Basis |
|---|---|---|
| Linear rows not created (free issue quota exceeded; rate limited) | Human-only (billing/quota) | STATE.md owner decision; kickoff fail-open |
| G-4 consumer acknowledgements | Human-only (external action) | STATE.md deferred list |
| INT-10 VERIFIED needs a bonding-curve account | Human-only (external access) | v3-MILESTONE-AUDIT.md G2 |
| Criterion 17 foreign-owned paths (171) | Self-resolved as owner-accepted gap G1 | STATE.md decision 2026-10-26 |
| Live-path edits | Out of scope | q2 settled: STATE.md says live code needs per-change human sign-off |

## Assumptions

- q1: v3 is the only open milestone. q2: exclude live paths. q3: commits on `bot-00-chief/phase-6-integrity`, per STATE.md (not a new branch). q4: touched-code quality only.
- The planner's `docs/gsd/` default is kept for run artifacts only; authoritative phase state stays in `.planning/`.
