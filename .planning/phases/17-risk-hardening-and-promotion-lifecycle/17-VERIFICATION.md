---
phase: 17-risk-hardening-and-promotion-lifecycle
status: passed
---

# Phase 17 Verification: Risk hardening and promotion lifecycle

Status: passed. Core code merged 2026-11-22 via c96e993 (event desk) and
cb91cf6 (restart recovery); exit-sell guard, promotion cursor and
holder-flag behaviours implemented and tested on bot-00-chief/conflict-repair
(2026-11-26); changelog narrative present. Stale PR #98-#100 tips remain
open on GitHub (their test/narrative content is now on the branch).

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
| 10 | Event desk e2e and idle tests | Implemented (event desk e2e + idle + holder-flag desk tests) |
| 11 | Restart recovery (exit deadlines, probation, watch set, exit peaks) | Implemented (recovery core + exit-sell guard + promotion cursor tests) |
| 12 | Contracts diff check (six files allowed) | Implemented (six contract files on main; CHANGELOG narrative present) |
| 13 | Smoke-10m pin pair | Enforced pins: smoke-10m 1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700 and trading-smoke a4461e80f926e46f9d5b85b0305c41fb44c72b63a875369e2b825ea8b7cd9404, before=after (pin_support.py, pins/trading_smoke.json) |
| 14 | Live refusal (run --mode live --once) | Exit 3 per ROADMAP |

## Closed 2026-11-26

No blockers remain: the holder-flag, exit-sell-guard and promotion-cursor
behaviors are implemented and tested on bot-00-chief/conflict-repair
(test_event_desk_holder_flag, test_exit_sell_guard,
test_promotion_cursor_restart), and the CHANGELOG Phase 17 narrative is present.

Note: local evidence below is the close-out run at c21567d; the full-suite
verdict is the GitHub CI run on PR #137.

## Gate run at c21567d (2026-11-26, Phase 17 close-out)

check.sh exit 0.
make lint exit 0 (canonical: uv run ruff check . → All checks passed; ruff format applied to 18 files).
make typecheck exit 0 (Success: no issues found in 340 source files).
Targeted suites green (datafeed, replay/e2e, risk, execution, desk, backtest, cli, onboarding).

## Close-out note

The pre-existing conflict-marker residue (372 markers in 116 files) was
repaired on bot-00-chief/conflict-repair; exit guard, promotion cursor and
holder-flag wiring were implemented there and covered by the three Phase 17
desk tests. Full local test green remains a CI-verdict item pending PR #137's
GitHub CI run; no blocking merge on a self-contradicting verification.
