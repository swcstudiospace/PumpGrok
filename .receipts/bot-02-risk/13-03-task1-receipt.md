# 13-03 Task 1 RISK receipt (no-source operator CLI test)

Seat: bot-02-risk (RISK). Branch: bot-02-risk/phase-13-observation.
Plan: .planning/phases/13-curve-truth-live-market-data-and-recorder/13-03-PLAN.md (read from bot-00-chief/v4-phase-13).

## Pre-change baseline

- Pre-change revision: fe0c2af940c0db9dfa35225889d1a2806fffaab5
- Command: `uv run --offline pytest -p no:cacheprovider -q --junitxml=... tests/test_operator_budget_wiring.py tests/tools/test_verb_coverage.py tests/test_tools_cli.py tests/characterization/execution`
- Result: tests=129 failures=0 errors=0 skipped=0
- Artifact: .receipts/bot-02-risk/13-03-task1-baseline.xml

## Change

- File: tests/test_tools_cli.py only.
- `TestPaperFillPath._fill_flags` no longer monkeypatches `pumpgrok.cli.wiring.build_operator_registry` to inject a scripted `price_source`. The `_ScriptedCurves` helper and its `CurveSnapshot` import are removed. The CLI now starts with no price source, the same no-source startup the production composition will enforce in 13-03 Task 3.
- All assertions are unchanged: buy and sell are refused with `code == "unavailable"` (exit 1), no `FillRecorded` or `OrderPlaced` is written, and the no-source denial message assertions remain.
- No production file, no execution/ path and no tests/execution path is touched.

## Post-change result

- Command: same as baseline.
- Result: tests=129 failures=0 errors=0 skipped=0
- Test identity set equal to baseline (sorted classname::name lists diffed identical).
- Artifact: .receipts/bot-02-risk/13-03-task1-post.xml

## Independent review

- Status: APPROVED by owner human:SomeRandmGuyy on 2026-11-12 as the independent non-self reviewer for this receipt only. Approval covers Task 1 (CLI test change) and the baseline and post runs listed above.

## Not done in this seat

- Plan Task 2, Task 2b and the paper_factory half of Task 3 belong to SNIPER and CHIEF. Their files (execution/**, supervisor/scheduler/replay_runtime.py) are not on this branch, and `src/pumpgrok/execution/paper_factory.py` does not exist here.
- The `src/pumpgrok/tools/__init__.py` edit in Task 3 is blocked on the SNIPER paper_factory commit and the independent receipts, so it is not made in this slice.
- tests/test_operator_budget_wiring.py and tests/tools/test_verb_coverage.py migrate in 13-05, not here. They were run as baseline only.
