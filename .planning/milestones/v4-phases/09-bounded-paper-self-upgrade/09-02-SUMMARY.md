# 09-02 SUMMARY: Active-set ledger record

Plan 09-02 (UPG-01, UPG-03). The ledger records the active parameter set so
promotion and rollback have an exact, hash-identified version to move from
and to, per CONTEXT D-01, D-02, D-06, D-10, D-12 and G-01.

## Commits

- 64d4b38 feat(09-02): active-set ledger record [UPG-01, UPG-03]
  (src/pumpgrok/ledger/active_set.py)
- 3a644b3 test(09-02): active-set ledger test [UPG-01, UPG-03]
  (tests/upgrade/test_active_set_ledger.py)

## Changed files

- src/pumpgrok/ledger/active_set.py (new): record_active_set appends a
  ConfigChanged row (keys_changed holds active_param_set, prior hash in
  old_hash, new hash in new_hash) plus a seat desk JournalNote naming the
  new hash and its source; read_active_set scans ConfigChanged rows in
  ledger order where the last valid row wins and an empty ledger reads as
  None. Only human: or gate: by rows count, mirroring the autonomy by
  rule; JournalNote text is never read as policy. No wall clock (ts_utc
  is a caller parameter), no network, no float money.
- tests/upgrade/test_active_set_ledger.py (new): two-record ordering and
  hash test, fresh-ledger None test, seat-row/note-text exclusion test.

## Deviations

None. One interpretation recorded: the plan's "human or gate-written"
extends the autonomy human: prefix rule with a gate: prefix (the gate
itself lands in plan 09-03); the second test record uses by
gate:UPGRADE-GATE to pin that gate-written rows count.

## Acceptance results

- .venv/bin/python -m pytest tests/upgrade/test_active_set_ledger.py -v:
  3 passed, exit 0. (Bare uv run pytest prints the known environment-quirk
  line Pytest: No tests collected; the venv-runner count is authoritative
  per prior phase summaries.)
- uv run ruff check on both touched files: No issues found, exit 0.
- uv run ruff format --check on both touched files: already formatted,
  exit 0.
- uv run mypy --strict src/pumpgrok/ledger/active_set.py: No issues
  found, exit 0.
- Sibling regression: test_param_set_hash.py plus
  test_manual_ticket_no_upgrade.py: 8 passed, exit 0 (guard untouched,
  D-12 holds; that test file was not modified per the plan note).

## Main-checkout state

git -C /root/src/repos/pumpgrok status --short is empty.
