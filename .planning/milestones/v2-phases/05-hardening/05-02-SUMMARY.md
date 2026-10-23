# Phase 05 Plan 02: Documentation surface Summary

**Phase:** 05-hardening
**Plan:** 02
**Status:** complete
**Date:** 2026-10-22

One-liner: Nine machine-checked operator runbooks, two doc-contract tests, CHANGELOG phases 2-5, and an AGENTS.md rules index.

## Objective

Ship the OBS-004/OBS-005 documentation surface: rewrite the stale setup runbook, write the eight missing runbooks (including go_live with the nine code-id preconditions), add the two doc-contract tests, extend CHANGELOG to all five phases, and append the AGENTS.md rules index after line 405 without touching GSD markers.

## Tasks completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Rewrite setup and write the eight missing runbooks | b64d3c1 | docs/runbooks/{setup,engine,start_stop,kill_switch,breaker_reset,outage,rollback,reading_reports,go_live}.md |
| 2 | Doc-contract tests for runbook commands and changelog phases | 585f73a | tests/docs/test_runbook_commands.py, tests/docs/test_changelog_phases.py |
| 3 | CHANGELOG phases 2-5 and AGENTS.md rules index | 9329250 | CHANGELOG.md, AGENTS.md |

## Verification

- SC3a existence loop: all nine runbooks present.
- SC3b loop (`grep -q "Phase $p"` for 1-5): exits 0.
- `./scripts/check.sh`: green (35 skills, 10 agents, 209 markdown files).
- `uv run pytest tests/docs/test_runbook_commands.py tests/docs/test_changelog_phases.py`: 18 passed.
- Fenced-block scan: no curl, cp, sed, awk, ed, vi, vim, nano, or emacs in any fenced bash block.
- `git diff AGENTS.md`: single hunk at `@@ -405,0 +406,18 @@`, after `GSD:profile-end`; GSD markers untouched.

## Key decisions

- Runbook fenced commands use `uv run pumpgrok ...` only in the dev-loop runbooks (setup, engine); all others use bare `pumpgrok` / `docker compose` so operators never depend on a venv. The test enforces this per-file split.
- `live confirm` documented from code behavior (writes HMAC-signed `var/live_confirmation.json`, human-only `--by`, never changes effective mode); preconditions 5, 6, 8, 9 documented as never-holding in this release.
- CHANGELOG Phase 2-4 entries grounded in ROADMAP completion lines; Phase 5 marked in-progress with doc-surface entries only, no soak/metrics/security outcome claims.
- Negative test direction lives inside the test file (synthetic curl/cp snippets), not by mutating runbooks.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None. New surface (runbook copy-paste to operator shell) is covered by the fenced-command allowlist test (T-05-04); no secrets added to docs (T-05-05, G-3 scans the tree).

## Self-Check

- b64d3c1, 585f73a, 9329250 all present in `git log`.
- All nine runbooks, both test files, CHANGELOG phases, and the AGENTS.md rules index exist on disk.
- Result: PASSED.
