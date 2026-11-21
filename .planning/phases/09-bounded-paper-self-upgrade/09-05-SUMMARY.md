# 09-05 SUMMARY: BLIND advisory for SAFE-4/SAFE-8 (UPG-05)

## Commits

- 29d6a93 feat(09-05): advisory BLIND for SAFE-4/SAFE-8 holder pair [UPG-05]
- 7ecbec0 test(09-05): BLIND advisory coverage for holder pair [UPG-05]

## Changed files

- src/pumpgrok/tools/safety/provider.py (new): paid_rpc_provider_recorded reads
  env PUMPGROK_PAID_RPC_PROVIDER; empty or unset means none recorded; the value
  is never logged.
- src/pumpgrok/tools/safety/checks/__init__.py: added HOLDER_ADVISORY_PAIR
  frozenset {top10_concentration, deployer_history} with amendment-date comment.
  REQUIRED_IDS unchanged.
- src/pumpgrok/tools/safety/score_report.py: ScoreReportOut gains
  advisory_blind_checks; while no provider is recorded the holder pair keeps
  status blind with reasons, is listed as advisory, and is excluded from the
  forced-KILL set; every other required blind still KILLs; with a provider
  recorded the pair forces KILL again.
- tests/safety/test_blind_advisory.py (new): 6 tests (provider signal unit plus
  5 end-to-end verdict cases via MockTransport, env controlled by monkeypatch).

## Acceptance commands and exit codes

- uv run pytest -q tests/safety/test_blind_advisory.py -> exit 0
  (verbose run: 6 passed).
- uv run ruff check (4 touched files) -> exit 0, no issues.
- uv run ruff format --check (4 touched files) -> exit 0, all formatted.
- uv run mypy --strict on the 3 touched src files -> exit 0, no issues
  (tests/ is excluded from mypy per pyproject).

## Deviations

1. Auto-fix (Rule 3, blocking): the first checks/__init__.py patch used a range
   replace that clobbered the ADVISORY_IDS line (ImportError on next test run).
   Restored the line verbatim; no behavior change. Commit 29d6a93 carries the
   corrected file; verified by import plus green tests.
2. Out-of-scope conflict reported, not fixed: tests/tools/safety/
   test_score_report.py::test_blind_never_raises_and_forces_kill now fails
   (CLEAR vs KILL) because blind top10_concentration is advisory with no
   provider recorded. That file is outside this plan's files_modified, so per
   execution rule 4 it was left untouched. Proof the failure is exactly the
   intended behavior change: with PUMPGROK_PAID_RPC_PROVIDER set, that file is
   9 passed. The owning plan should set the provider env in that test (or
   delenv/setenv via monkeypatch) to pin the recorded-provider KILL path.
3. Branch note: this worktree sits on bot-00-chief/p9-05, outside the
   agent-*/worktree-agent-* namespace named in the generic commit protocol.
   The branch is the orchestrator-assigned per-plan branch (not a protected
   branch), so commits were made here as the exec rules require.

## State

- Main checkout git status: empty (clean).
- UPG-05 Task 1 and Task 2 complete; no TODOs, no stubs, no new thresholds,
  no network, no wall-clock time (FixtureClock only; provider reads env).
