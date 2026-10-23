# 01-12 SUMMARY — ci/ and tests/ manual lint gap closure

Tasks 1–2 complete. All 33 manual ruff findings fixed; full select clean; full suite green.

## Tasks

### Task 1: ci/ gate complexity and hygiene (commit 7f0029a)
- `ci/gates/check_ownership.py`: `zip(..., strict=True)` (B905); extracted
  `classify_files` / `report_ownership_failure` from `main` (PLR0912 14→6).
- `ci/gates/check_receipt.py`: split 104-statement `check` into 16 helpers
  (`_missing_field_problems`, `_structural_problems`, `_bot_problems`,
  `_self_approval_problems`, `_bypass_problems`, `_exit_code_problems`,
  `_claim_problems`/`_check_claim`/`_citation_problems`/`_exhaustive_problems`/
  `_unexplained_padding`/`_evidence_shape_problems`, `_loop_ack_problems`/
  `_check_loop_ack`/`_granter_problems`/`_condition_problems`/`_scope_problems`,
  `_unverified_problems`); keyword-only args on 3 helpers (PLR0917).
  Every bypass pattern, seat-id rule, message string, and print preserved.
- `ci/gates/check_rollback.py`: extracted `approval_problems`,
  `trade_approval_problems`, `check_destructive`, `check_deployments` (PLR0912).
  WR-03 rm forms and G-6 blast-radius rule untouched.
- `ci/gates/check_secrets.py`: `l`→`line` (E741); wrapped secrets help text (E501).
- `ci/gates/run_all.py`: explicit `check=False` (PLW1510, behavior unchanged).
- `ci/security/bandit_json_to_sarif.py`: `with` blocks for both opens (SIM115);
  rewrapped URI comments (E501).
- Verify: Task-1 select clean; `ci/tests/` 184 passed unmodified (plan 01-11 owned).

### Task 2: tests/ blind exceptions and structure (commit adbd72d)
- B017 narrowed to the exception actually raised: `ValidationError`
  (test_models RiskBudget/ApprovalRecord, test_registry ToolSpec — added pydantic
  imports), `sqlite3.IntegrityError` (test_store trigger/PK refusals).
- PLC0415: `tool` folded into top-level import (test_registry);
  `FillRecorded` to top-level import (test_events).
- SIM117: single multi-context `with` at all 5 sites (test_tools_cli) and both
  sites (test_registry).
- SIM102 merged in test_ids; B007 `_name` (test_events); E501 docstring wrap
  (test_static_guards).
- Verify: Task-2 select clean; 68 passed over the touched test paths.

## Verify results
- Plan select over all 13 files: `Ruff: No issues found`.
- Full suite `uv run pytest`: 335 passed.
- Note: bare `-q` runs print a bogus "No tests collected" line from the output
  wrapper while exiting 0; counts above are from `-v` tails. Pre-existing
  environment quirk, not caused by this plan.

## Deviations
1. `check_receipt._citation_problems`: original crashed with AttributeError when a
   cited command was a non-dict (exit_code None != 0 → `cited.get`). Helper
   renders the message without the cmd line instead. Latent-crash fix; no test
   covered the crash.
2. `test_ids.py`: merged the Import-branch nested if as well as the flagged
   terminal Attribute elif (ruff SIM102 only flags the last elif in a chain, so
   the ImportFrom branch stays nested and unflagged — same as before).
3. Keyword-only `*` markers added to 3 new receipt helpers to satisfy PLR0917
   (in-select for this plan); call sites updated accordingly.

## Commits
- 7f0029a fix(01-12): slim gate complexity and hygiene findings in ci/
- adbd72d fix(01-12): narrow blind exceptions and flatten tests structure
