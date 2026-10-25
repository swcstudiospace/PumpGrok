---
phase: 06-integrity-closure
plan: 09
status: complete (orchestrator gate run on the closing head)
requirements: [PRC-01, PRC-02]
---

# Phase 06 Plan 09: closing gates and record (PRC-01, PRC-02)

## Done

- CHANGELOG.md: Phase 6 entry with both smoke-10m hash lines (before and after, identical), a summary of INT-01 to INT-10, and the review of the Omega CI runner migration commits 5b5d6a1 and 9772655.
- Receipt .receipts/bot-00-chief/phase-6.json written with commands, claims, unverified items and a rollback plan. It is gitignored and is force-added.
- Gate runner: G-3 PASS, G-4 PASS, G-5/G-6 PASS, G-7 PASS. G-1 FAIL (67 foreign paths) and G-2 FAIL (approved_by missing) remain. See Open below.

## Closing-head verification (orchestrator, run after the last merge)

| Command | Exit | Result |
|---|---|---|
| make lint | 0 | ruff check and format check pass, 647 files |
| make typecheck | 0 | mypy strict, 159 source files |
| uv run pytest -q -rfE --tb=no | 0 | no FAILED or ERROR; 2 skipped (pre-existing) |
| ./scripts/check.sh | 0 | 35 skills, 10 agents, 243 markdown files |
| uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke | 0 | cycle complete |
| uv run pumpgrok verify --fixture smoke-10m (twice) | 0, 0 | events.hash b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d, identical to the pre-edit baseline |
| uv run pumpgrok run --mode live --once | 3 | live refused, nothing sent |
| cd services/desk-gateway && uv run pytest -q | 0 | pass |
| uv run python scripts/probe_curve_layout.py | 0 | Status ASSUMED, no account configured, no RPC call |

## Open

- G-1 ownership: 67 foreign paths across seven seats. The owner decided on 2026-10-25 to re-own the milestone paths to bot-00-chief. ownership.yaml is owned by bot-02-risk, so that change lands as a separate bot-02-risk change, merged before the milestone PR.
- G-2 approved_by: needs a human reviewer. The seat never approves its own work.
- PRC-02: the requirement text says draft PRs only. The owner decided on 2026-10-25 to open a ready PR with auto-merge on Greptile 5/5. The requirement text is not edited.
- Omega CI migration: a policy reversal of the no-self-hosted-runners stance, which needs owner sign-off (recorded in CHANGELOG).
