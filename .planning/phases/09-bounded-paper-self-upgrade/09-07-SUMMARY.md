# 09-07 SUMMARY: Phase 9 replay hashes and live guard (UPG-01..UPG-06)

## One-liner

Phase 9 closed: smoke-10m replay before/after hash lines recorded in
CHANGELOG with gate-fill placeholders, and the no-backtest-to-live guard
extended to scan the upgrade package, with live refusal and the signing
guard untouched.

## Commits

- 8dd3cfa `docs(09-07): Phase 9 smoke-10m replay hash lines
  [UPG-01, UPG-02, UPG-03, UPG-04, UPG-05, UPG-06]` (Task 1, 1 file)
- d22297d `test(09-07): guard covers upgrade no-live-import plus live
  refusal [UPG-01]` (Task 2, 1 file)

## Files changed

Task 1 (replay hash lines):
- CHANGELOG.md (new `## [Unreleased] - v3 Phase 9: bounded paper
  self-upgrade` section with `### Verified` holding the Phase 8-format
  before/after lines, values PHASE9_BEFORE_HASH / PHASE9_AFTER_HASH for
  the orchestrator to fill at the gate)

Task 2 (live guard update):
- tests/safety/test_no_backtest_to_live_path.py (new UPGRADE_DIR constant;
  `_guarded_files` now also scans `src/pumpgrok/upgrade/**/*.py` with the
  same live-import AST check; the `assert not upgrade exists` line replaced
  with `assert UPGRADE_DIR.is_dir()`; docstring updated; live-refusal
  exit-3 test unchanged)

## Acceptance results (exit codes)

- Task 1 Verify `grep -qE "Phase 9: smoke-10m events.hash before:
  (PHASE9_BEFORE_HASH|[0-9a-f]{64})" CHANGELOG.md && grep -qE "Phase 9:
  smoke-10m events.hash after: (PHASE9_AFTER_HASH|[0-9a-f]{64})"
  CHANGELOG.md` exits 0.
- `.venv/bin/pytest -q
  tests/safety/test_no_backtest_to_live_path.py
  tests/upgrade/test_no_live_imports.py
  tests/safety/test_no_signing_outside_live_stub.py` exits 0 (26 passed:
  backtest/paper/upgrade no-live-import, live refusal exit 3, no signing
  symbols outside the refusing stub).
- `uv run ruff check` and `uv run ruff format --check` on the touched
  test file: clean.
- Plan acceptance commands `make lint`, `make typecheck`, `make test`,
  `./scripts/check.sh`, `pumpgrok verify`, and `pumpgrok run` were NOT run
  in the worktree per the executor rules (orchestrator gates own them);
  the orchestrator also fills the hash placeholders and runs the
  verify-twice criterion at the gate per CONTEXT D-11.
- Note: `uv run pytest` reports "No tests collected" in this worktree while
  the same files collect and pass under `.venv/bin/pytest`; used the venv
  binary for the proof above.

## Deviations from plan

Two, both orchestrator-directed:

1. Task 2 has no code changes in the plan as written ("any failure is
   fixed in its owning plan"), but the `test_no_backtest_to_live_path.py`
   `assert not (SRC / "upgrade").exists()` line fails now that the Phase 9
   upgrade package exists. Per the orchestrator note, replaced only that
   assertion with import-graph coverage (upgrade files join the same AST
   live-import scan). The live-path proof is kept in full: backtest/paper
   no-live-import scan unchanged, signing-symbol guard
   (`test_no_signing_outside_live_stub.py`, already covering all of SRC)
   untouched, live-refusal exit-3 test untouched.
2. The plan lists only CHANGELOG.md under `files_modified`; the Task 2
   test file falls outside it. Edited it per the explicit orchestrator
   note directing the update, keeping the change minimal (6 insertions,
   2 deletions, no test weakened).

## Self-Check: PASSED

CHANGELOG.md Phase 9 lines present, guard test file changes present,
both commits in worktree history, main checkout
`git -C /root/src/repos/pumpgrok status --short` empty.
