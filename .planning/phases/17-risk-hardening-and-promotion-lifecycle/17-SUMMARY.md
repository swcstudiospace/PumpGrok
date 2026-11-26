---
phase: 17-risk-hardening-and-promotion-lifecycle
status: partial
---

# Phase 17 Summary: Risk hardening and promotion lifecycle

Status: partial. Core code is on origin/main and local main via the
2026-11-22 integration commits c96e993 (17-05 event desk root) and
cb91cf6 (17-06 restart recovery). PRs #98-#100 remain OPEN on GitHub;
their stale tip commits (d44cf93, cd68a68, 71ac14d) are not merged.
Absent on main: test_event_desk_holder_flag, test_exit_sell_guard,
test_promotion_cursor_restart and the changelog narrative entry.

## Plans

| Plan | State |
|---|---|
| 17-01 | merged (PRs #76-#88) |
| 17-02 | merged (#89-#90) |
| 17-03 | merged (#89, #95) |
| 17-04 | merged (#91-#92) |
| 17-05 | Code on main (c96e993); holder-flag test absent (PR #98 OPEN) |
| 17-06 | Code on main (cb91cf6); exit-sell guard + promotion cursor tests absent (PR #99 OPEN) |
| 17-07 | Pending: changelog narrative absent, only hash pairs (PR #100 OPEN; #101 planning merged) |

## Criterion 1

Criterion 1 (paper smoke) is deferred to deployment (owner decision D17-2).

## Hash record (CHANGELOG.md lines 5-8)

- Phase 17: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
- Phase 17: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
- Phase 17: trading-smoke events.hash before: bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54
- Phase 17: trading-smoke events.hash after: bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54
- Before=after for both pairs.

## Merge record

Merged to local main 8354ee6 (22 of 25 stack PRs). Local-only: GitHub
PRs still OPEN until push. Phase 17 does not close until #98, #99 and
#100 merge.
