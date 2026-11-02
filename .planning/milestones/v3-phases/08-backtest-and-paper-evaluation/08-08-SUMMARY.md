# Phase 08 Plan 08: Real Replay Window Evaluator - SUMMARY

One-liner: Validated settings overrides replayed through run_once_replay
over sliced windows, scored by net realized lamports; no digest acts as
a score. Observed smoke full-window score: 14079588 lamports.

## Tasks completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Window evaluator over sliced replay windows | 13556e3 | src/pumpgrok/backtest/evaluate.py |
| 2 | Evaluator tests on the recorded fixtures | 1d5d34e | tests/backtest/test_evaluator.py |

## Decisions made

- D1: CandidateParams stores raw override mappings as dict fields and
  validates each by constructing the real FilterSettings or ExitsSettings
  model, so unknown nested fields fail through the real model with extra
  forbidden. Top-level keys beyond filter and exits fail through the
  model-level extra forbidden.
- D2: The scoring blocklist covers the ScoringWeights fields (audit,
  narrative, timing, metrics), the ScoringSettings container names
  (weights, timing_cache_seconds), and min_total_score, which is a valid
  FilterSettings field but inert because decide_token consults only
  passes_filter. Other passes_filter-inert FilterSettings fields
  (max_risk_score and the creator-tracking knobs) stay accepted: the plan
  scopes the blocklist to scoring knobs, and plan 08-09 consumes this API.
- D3: ScoringKnobError subclasses ValueError and is raised from pydantic
  field validators; pydantic surfaces it as ValidationError, so the
  typed validation error observed by callers is ValidationError with a
  "scoring knob" message. The unit test pins both the direct typed error
  and the pydantic-wrapped form.
- D4: fold_windows returns a FoldWindows dataclass (folds plus holdout)
  rather than bare id pairs: the harness in plan 08-09 needs the stamp
  ranges, and EvalWindow carries the window_id so tuning-versus-holdout
  call spies observe it directly. Ids reuse walk_forward_folds test ids
  and the holdout_split holdout id verbatim.
- D5: The slice manifest is built from the checked-in source manifest as
  a template: bounds and notes are patched, and the digest map is located
  structurally (the mapping that lists events.jsonl) so no hashing
  vocabulary appears in code. Shape is enforced by FixtureManifest
  validation at replay load time. The slice identity comes from
  dataset_digest over the events-only stage and is recorded in notes.
- D6: Partial fills count at their recorded filled_lamports amount, which
  already reflects the filled fraction; no rescaling is applied. Empty
  windows raise ValueError (fail closed) rather than scoring 0: every
  window fold_windows yields is non-empty, so an empty slice means a
  caller bug.

## Deviations from plan

None. Both tasks executed exactly as written. No Rule 1-4 fixes needed.

## Acceptance results

- `! grep -q "sha256\|hashlib" src/pumpgrok/backtest/evaluate.py` exits 0.
- `uv run pytest -q tests/backtest/test_evaluator.py` exits 0 (7 passed;
  raw backend output shows 7 dots, exit 0; the quiet-mode display wrapper
  renders "No tests collected" while the process exit code is 0 and the
  direct `.venv/bin/python -m pytest -q` run shows 7 passed).
- `uv run ruff check` and `uv run ruff format --check` on both touched
  files pass (one format pass applied before testing).
- Observed smoke full-window desk-defaults score: 14079588 lamports,
  equal to the independent ledger-derived SELL minus BUY minus fees
  total, identical across two runs. No sign asserted.

## Self-check

- evaluate.py exists with CandidateParams, EvalWindow, FoldWindows,
  ScoringKnobError, evaluate_window, fold_windows: PASSED.
- Commits 13556e3 and 1d5d34e exist in git log: PASSED.
- Main checkout `git -C /root/src/repos/pumpgrok status --short` empty: PASSED.

## Self-Check: PASSED
