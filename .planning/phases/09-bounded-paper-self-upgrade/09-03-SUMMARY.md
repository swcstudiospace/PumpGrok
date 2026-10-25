# 09-03 SUMMARY: Promotion gate and evidence (UPG-02, UPG-03)

## Commits

- 8e8b414 feat(09-03): promotion gate with five ordered checks (UPG-02)
  - src/pumpgrok/upgrade/gate.py (new)
  - tests/safety/test_manual_ticket_no_upgrade.py (extended)
- 61bd0d2 feat(09-03): gate tests plus promotion evidence record (UPG-02, UPG-03)
  - src/pumpgrok/upgrade/evidence.py (new)
  - tests/upgrade/test_promotion_gate.py (new)
  - tests/upgrade/test_promotion_evidence.py (new)

## Changed files

- src/pumpgrok/upgrade/gate.py: evaluate_candidate with GateVerdict
  (promotion_eligible, typed reason, detail). Order: bounds (OutOfBoundsError
  via validate_against_bounds), trials (trial_count past MAX_ELIGIBLE_TRIALS
  20 or ledger ineligible; MAX_ALLOWED_TRIALS 50 referenced fail-closed),
  autonomy (read_autonomy must equal autonomous-paper), holdout
  (holdout_net_lamports must be positive measured net on the unseen window),
  divergence (Phase 8 check with D7 defaults via breach_line detail).
  Winner binding: candidate hash must equal search.best_params_hash.
- src/pumpgrok/upgrade/evidence.py: record_promotion writes
  var/upgrade/promotions/<hash>.json (candidate hash, run id, holdout id,
  divergence verdict, trial count, sorted bounds snapshot) via atomic write
  plus a desk JournalNote referencing the file. Deterministic bytes for
  identical inputs. Fail-closed on malformed inputs.
- tests/upgrade/test_promotion_gate.py: 10 tests (pass + 5 blocking reasons
  + negative holdout + gate order + winner binding + empty run id).
- tests/upgrade/test_promotion_evidence.py: 7 tests (every field matches,
  note reference, byte determinism, snapshot coverage, fail-closed x2, path).
- tests/safety/test_manual_ticket_no_upgrade.py: also asserts no
  active-set record (reader None, no ConfigChanged rows) and no
  var/upgrade directory after a manual-ticket paper cycle.

## Deviations

- Rule 3 (blocking): REASON_PASS tripped ruff S105 (hardcoded-password
  heuristic on the word "pass"). Kept the plan word with a justified
  `# noqa: S105` (noqa precedented in src/pumpgrok/core/interfaces.py).
- Holdout pass rule defined as holdout_net_lamports > 0 (positive measured
  net on the unseen window). The harness reports the net for completeness
  with no pass flag; the sign rule uses measured return only, no tuned
  threshold, no hash or random value.
- Environment: plain `uv run pytest` prints "Pytest: No tests collected" for
  every suite including pre-existing ones (uv sync step breaks collection);
  `uv run --no-sync pytest` and `./.venv/bin/pytest` (same venv) work. All
  results below use `./.venv/bin/pytest`.

## Acceptance (exit codes)

- `./.venv/bin/pytest -q tests/upgrade/test_promotion_gate.py
  tests/upgrade/test_promotion_evidence.py` -> exit 0, 17 passed
- `./.venv/bin/pytest -q tests/safety/test_manual_ticket_no_upgrade.py`
  -> exit 0, 1 passed
- `./.venv/bin/pytest -q tests/upgrade/test_no_live_imports.py` -> exit 0,
  10 passed (collateral: new modules import nothing live)
- `./.venv/bin/ruff check` on all 5 touched files -> All checks passed
- `./.venv/bin/ruff format --check` on all 5 touched files -> clean
- `./.venv/bin/mypy --strict src/pumpgrok/upgrade/gate.py
  src/pumpgrok/upgrade/evidence.py` -> no issues in 2 source files
- `git -C /root/src/repos/pumpgrok status --short` -> empty
