# Phase 14 integration receipt (plan 14-09)

Integrated head: `634d87e` on `bot-00-chief/v4-phase-14`, with the ROADMAP amendments committed at `2ec7e53`. Nothing is pushed.

Commands run by the orchestrator on the integrated tree. The commands are the roadmap criteria as amended on 2026-11-13. Venv `.venv/bin/*` replaces `uv run` in this worktree.

| Criterion | Result | Notes |
|---|---|---|
| 1a make lint | exit 0 | after `ruff format` on 18 Phase 14 files (commit `7db3974`) |
| 1b make typecheck | exit 0 | |
| 1c make test | exit 0 | full suite on 634d87e |
| 1d ./scripts/check.sh | exit 0 | |
| 1e paper smoke checkpoint | exit 1 | OPEN: seat tool decisions not yet authorized (human step) |
| 2 grok prefilter/cache/coalesce/budget | exit 0 | |
| 3 sanitize + gateway agents | exit 0 | |
| 4 fallback ladder | exit 0 | |
| 5 no grok in exit/risk + hang exit | exit 0 | after the exit-closure fix (`0cda2c6`) |
| 6 replay backend + determinism | exit 0 | |
| 7 event wake + run-once + scheduler, no skips | exit 0 | |
| 8 drain parity, no skips | exit 0 | |
| 9 idle-zero gate and wiring | exit 0 | |
| 10 hermes jobs, doctor event mode, time sync, no skips | exit 0 | |
| 11 metrics, no skips | exit 0 | |
| 12a evidence50 fixture | exit 0 | |
| 12b measure evidence-50 | exit 0 | ratio 0.166667 |
| 12c measure soak-3d-tokens (amended) | exit 0 | 216 admitted of 4320, ratio 0.05, after regeneration (commit 4715ede) |
| 13 event cycles + goldens, no skips | exit 0 | |
| 14 degradation, events, grok | exit 0 | |
| 15 probe retired | exit 0 | |
| 16 contracts diff vs v4-base | exit 0 | 0 files |
| 17 smoke-10m verify (amended) | exit 0 (amended check) | verify equals amended baseline `1dffa784...`; CHANGELOG pair recorded |
| 18 live refusal | exit 0 | exit code 3 |
| 19 onboarding, clean-env live doctor, paper refusal | exit 0 | |

## Owner decisions applied
- Criterion 17 now expects the seeded baseline `1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700`.
- Criterion 12 names `soak-3d-tokens`, a derived synthetic dataset. `soak-3d` has no token facts.
- Orphaned probe artifacts deleted; serve-path automatic promotion removed; human promotion path intact.
- Superseded Hermes jobs: one disabled (`chief-journal-rollup`), per the plan's criterion. OD-13 (all six) is not applied.
- Extended 166-byte curve layout stays refused, fail-closed (ASSUMED).

## Unverified or open
- Criterion 1e and the smoke checkpoint: the owner will authorize the seat tool decisions through onboarding; this is a human action.
- Independent reviews for each criterion: not performed. No seat reviewed another seat's receipt in this integration.
- JOURNAL attestation of the 14-01 baseline: waived by owner decision; open.
- Event-mode metrics and golden paths are not wired in production `serve`; the composition root is Phase 17.
- Known: `run --serve` no longer validates the declared space at startup (closure removed).

## Runner note
The criteria runner (/tmp/crit.sh) still uses the pre-amendment literals for 12c (soak-3d) and 17 (b69c hash); their amended forms were run separately on 634d87e and pass (see table).

## Post-merge record (2026-11-26)
Code merged to local main 8354ee6666139a7817ca246bef9ca2e5a0b3b4b8 via integration PR #75 (branch bot-00-chief/v4-phase-14, integrated head 634d87e). Local-only: GitHub PR still OPEN until push. Criterion 1e (paper smoke checkpoint, seat tool authorization human step) remains OPEN; this record does not close it.
