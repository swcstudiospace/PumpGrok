# 09-04 SUMMARY: Exact rollback and escalation (UPG-03, UPG-04)

## Commits

- 0d7b516 feat(09-04): exact one-operation rollback to prior content hash (UPG-03)
- 8c611e2 feat(09-04): escalation with decision request for ineligible candidates (UPG-04)

## Changed files

- src/pumpgrok/upgrade/rollback.py (new): restore_active_set plus rollback_note_text
- tests/upgrade/test_rollback_exact.py (new): promote-then-rollback round-trip plus malformed-hash refusal
- src/pumpgrok/upgrade/escalate.py (new): escalate_candidate plus detail and note text helpers
- tests/upgrade/test_escalation.py (new): out-of-bounds and over-trial-count escalation plus eligible-verdict refusal

## Decisions

- Rollback builds its own ConfigChanged plus JournalNote pair rather than reusing active_set_rows, because a hash cannot be inverted into a ParamSet and the restore deserves distinct idempotency keys and journal text.
- Escalation kind is upgrade_blocked on seat desk, following the RISK_POLICY section 5 relay (supervisor relays Escalation rows to notify.alert); no active-set row is written on any escalation path.
- escalate_candidate returns the blocking reason and refuses eligible verdicts, so a passing candidate can never be escalated by mistake.

## Deviations

- None from the plan. RUF022 required isort-style __all__ ordering (escalate_candidate before escalation_detail_text, restore_active_set before rollback_note_text); applied with no behavior change.
- Test runner note: the `uv run pytest` wrapper in this environment collects zero tests even for pre-existing files, so verification ran the identical pytest via `.venv/bin/python -m pytest`. Same binary, same config, exit 0.

## Acceptance results

- `.venv/bin/python -m pytest -q tests/upgrade/test_rollback_exact.py tests/upgrade/test_escalation.py` exit 0 (5 passed)
- `.venv/bin/python -m pytest -q tests/upgrade/` exit 0 (42 passed, no regressions)
- `ruff check` on all four touched files: pass
- `ruff format --check` on all four touched files: pass (after applying ruff format to two files)
- `mypy --strict` on both new source files: no issues
- `git -C /root/src/repos/pumpgrok status --short`: empty (main checkout untouched)
- Known pre-existing failure tests/safety/test_no_backtest_to_live_path.py left untouched per plan (fails until 09-07)
