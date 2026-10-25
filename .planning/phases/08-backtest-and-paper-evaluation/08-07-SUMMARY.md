# 08-07 SUMMARY: Autonomous paper e2e, manual-ticket guard, live-refusal guard, CHANGELOG before line

One-liner: PAP-03 recorded-dataset autonomy verification with manual-ticket and
no-live-path guards plus the Phase 8 CHANGELOG before-hash line.

## Commits

- 3aed6d8 test(08-07): PAP-03 autonomous paper e2e and manual-ticket guard
- 5ab24fc test(08-07): PAP-03 live-refusal guard and Phase 8 CHANGELOG before line

## Changed files

- tests/e2e/test_autonomous_paper_recorded.py (new): PAP-03 e2e on the recorded
  smoke and smoke-10m datasets at the human-set autonomous-paper level.
- tests/safety/test_manual_ticket_no_upgrade.py (new): manual-ticket cycle
  performs no parameter promotion, harness search or autonomy change.
- tests/safety/test_no_backtest_to_live_path.py (new): AST import-graph guard
  plus the live exit-3 refusal test.
- CHANGELOG.md: Phase 8 entry with one line per BT and PAP id plus the
  smoke-10m events.hash before line. No after line (orchestrator measures it).

## Design notes

- The level is set through the ledger autonomy path (ConfigChanged row with a
  human author via autonomy_rows); journal text alone never sets it, and a
  non-human author is ignored. Both invariants are pinned by tests.
- The replay sandbox runs under autonomous-paper by construction, so fills on
  the smoke set carry risk-engine-minted approvals with no presented human
  approval; the smoke-10m set completes its cycle with decision skip.
- The manual-ticket guard asserts the negative after a real paper cycle: no
  autonomy ConfigChanged rows in either ledger, level still manual-ticket,
  no var/backtest directory and no trials.jsonl anywhere under var.
- The import guard covers every module under src/pumpgrok/backtest/ plus the
  paper path (execution/paper_adapter.py) and fails if an upgrade path
  appears without extending the guard. Live refusal is asserted in-process
  (exit 3) and at the shell (exit status 3).

## Acceptance commands and exit codes

- uv run --frozen pytest -q tests/e2e/test_autonomous_paper_recorded.py
  tests/safety/test_manual_ticket_no_upgrade.py
  tests/safety/test_no_backtest_to_live_path.py: 6 passed, exit 0.
- uv run pumpgrok run --mode live --once; test $? -eq 3: passes, exit 0.
- uv run ruff check on all touched files: no issues, exit 0.
- uv run ruff format --check on all touched files: formatted, exit 0.
- uv run --frozen pytest -q tests/docs/test_changelog_phases.py: passes, exit 0.

## Deviation

- Plain `uv run pytest -q` collects no tests in this worktree (same
  environmental quirk recorded in the 08-01 summary); the suite passes
  under --frozen. No test was weakened; the smoke-10m skip verdict is
  asserted as observed from the recorded fixture.
- The file-edit tool held a shadow copy of CHANGELOG.md that would not
  flush to disk across three attempts; the entry was written with a
  whole-file write instead and verified byte-identical on disk with a
  +19-only git diff. No content difference from the planned edit.

## Main checkout

git -C /root/src/repos/pumpgrok status --short is empty.
