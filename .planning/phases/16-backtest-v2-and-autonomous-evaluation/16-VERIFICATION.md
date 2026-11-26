---
phase: 16-backtest-v2-and-autonomous-evaluation
status: passed
verified: 2026-11-26 (evidence transcribed from CHANGELOG Phase 16 section; no re-run at this head)
---

# Phase 16 Verification: Backtest v2 and autonomous evaluation

All rows below are transcribed from the CHANGELOG.md v4 Phase 16 section.
No gate re-run was performed during documentation sync; orchestrator gate
run follows.

| Check | Result | Evidence |
|---|---|---|
| Lint (make lint) | exit 0 at f05381d | CHANGELOG: "At f05381d, make lint, make typecheck, make test and ./scripts/check.sh exit 0" |
| Typecheck (make typecheck) | exit 0 at f05381d | same line |
| Test (make test) | exit 0, coverage 91.30 percent (floor 89.9) | same line |
| check.sh (./scripts/check.sh) | exit 0 at f05381d | same line |
| smoke-10m events.hash | before=after 1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700 | before at 5fa947b, after at f05381d |
| trading-smoke events.hash | before=after a4461e80f926e46f9d5b85b0305c41fb44c72b63a875369e2b825ea8b7cd9404 | before at 5fa947b, after at f05381d |
| Criterion 1 (paper smoke) | DEFERRED TO DEPLOYMENT (row J) | CHANGELOG Changed section |

Criterion 1 DEFERRED: the paper smoke checkpoint
(`run --mode paper --once --replay tests/fixtures/replay/smoke`) needs
operator authority on the deployment host; it is not a repo-close gate.

Note: no gate re-run was performed during documentation sync; orchestrator
gate run follows.

## Gate run at local main 8354ee6 (2026-11-26, documentation sync)

Ran after the documentation sync. check.sh exit 0 (623 markdown files).
make lint FAIL: 8935 errors; make typecheck FAIL: 77 errors (SyntaxError
in src/pumpgrok/backtest/event_source.py, line 163); make test FAIL:
SyntaxError conflict marker in src/pumpgrok/strategies/__init__.py,
line 36 blocks test collection. 372 conflict-marker lines remain in
116 files under src/ and tests/. Proven pre-existing:
identical lint failure on clean main via git stash of the doc changes.
Cause: merge-conflict residue from the local PR merges. No fix attempted
in this documentation run; fix before push.
