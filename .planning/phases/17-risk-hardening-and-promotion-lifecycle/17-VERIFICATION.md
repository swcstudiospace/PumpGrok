---
phase: 17-risk-hardening-and-promotion-lifecycle
status: partial (gaps_found)
---

# Phase 17 Verification: Risk hardening and promotion lifecycle

Status: partial (gaps_found). Core code is on main via c96e993/cb91cf6
(2026-11-22); three desk test files and the changelog narrative are
absent (PR tips d44cf93/cd68a68/71ac14d not merged). Phase 17 does
not close until they land and gates pass.

## Criteria 1-14 checklist

| # | Criterion | Status |
|---|---|---|
| 1 | Paper smoke checkpoint | DEFERRED TO DEPLOYMENT (owner decision D17-2) |
| 2 | Strategy slice and kill tests | Implemented in merged PRs (17-01) |
| 3 | Feed health, loss-velocity reset, halt-verdict tests | Implemented in merged PRs (17-02) |
| 4 | Entry checks and mint list | Implemented in merged PRs (17-03) |
| 5 | STEP_IDS and risk_json stability | Implemented in merged PRs (17-01) |
| 6 | Promotion stages, thresholds, gate reuse | Implemented in merged PRs (17-04) |
| 7 | Demotion test and promotion demote --help | Implemented in merged PRs (17-04) |
| 8 | No timers, no Grok, composition-root subscription | Implemented in merged PRs, bot-02 half of 17-05 |
| 9 | Writer discipline | Implemented in merged PRs (17-04) |
| 10 | Event desk e2e and idle tests | Implemented on main (event desk e2e, c96e993); holder-flag desk test absent |
| 11 | Restart recovery (exit deadlines, probation, watch set, exit peaks) | Partially implemented (restart recovery on main cb91cf6; exit-sell guard and promotion cursor tests absent) |
| 12 | Contracts diff check (six files allowed) | BLOCKED (changelog narrative absent; hash pairs on main) |
| 13 | Smoke-10m pin pair | Measured: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d and bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54, before=after (CHANGELOG) |
| 14 | Live refusal (run --mode live --once) | Exit 3 per ROADMAP |

## Blocked by

- tests/desk/test_event_desk_holder_flag.py (PR #98 tip d44cf93)
- tests/desk/test_exit_sell_guard.py and tests/desk/test_promotion_cursor_restart.py (PR #99 tip cd68a68)
- CHANGELOG Phase 17 narrative entry (PR #100 tip 71ac14d; only hash pairs on main)

Note: this verification does not claim a re-run at the current head;
hash and exit-code evidence is transcribed from ROADMAP and CHANGELOG.md.

## Gate run at local main 8354ee6 (2026-11-26, documentation sync)

check.sh exit 0. make lint, make typecheck and make test all FAIL at
main HEAD due to conflict-marker residue (372 markers in 116 files;
proven pre-existing via stash; details in 16-VERIFICATION.md gate-run
section). No fix attempted in this documentation run. Push to origin
is blocked until the markers are resolved.
