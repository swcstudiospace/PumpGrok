# 08-09 Summary: Harness on realized lamports, search tests re-pinned

## Outcome

Rewired the single search entry point onto the real replay evaluator and
deleted every digest-as-score path. Both acceptance commands exit 0.

## Commits

- 2c6496e feat(08-09): harness scores candidates by realized replay lamports
  (Task 1, BT-07/BT-04): src/pumpgrok/backtest/harness.py
- 9e71a06 test(08-09): pin search engine to real replay behaviour
  (Task 2, BT-07/BT-04): tests/backtest/test_single_search_engine.py

## Changed files

- src/pumpgrok/backtest/harness.py: run_search keeps its signature and
  ledger behavior, validates each candidate with CandidateParams, scores
  the mean net realized lamports over pre-holdout fold_windows via
  evaluate_window, tracks best with strict greater-than in space order
  with no shuffle, replays the winner once on the holdout window.
  HarnessResult keeps trial_count, holdout_id, eligible_for_promotion,
  replaces holdout_score float with holdout_net_lamports int and adds
  best_net_lamports int. Deleted _score_candidate, _evaluate_holdout,
  _params_hash, the hashlib import and _DIGEST_SCALE; identity hashes
  use param_set_hash from manifest; _load_stamps is the only local
  identity helper; the tuning assert stays.
- tests/backtest/test_single_search_engine.py: kept the only-entry-point
  test, signature test, eligibility tests, bad-count and float rejections,
  and the recorded-fixture end-to-end (now asserting integer lamport
  fields, honest zero on smoke-10m). Digest spies replaced by a
  delegating evaluate_window spy (records windows, runs the real replay):
  tuning windows never reach past the cutoff and never cover a holdout
  stamp, the winner is evaluated on holdout exactly once. Added
  identical-inputs determinism with integer scores and an all-zero space
  order pin (first candidate kept, proven by reversal). No assertion
  weakened; the evaluator scoring function itself is never stubbed.

## Deviations

None. Plan executed exactly as written. No Rule 1-4 fixes were needed.

## Cross-wave note (not a deviation)

src/pumpgrok/cli.py reads only harness_result.trial_count and
harness_result.eligible_for_promotion (both kept), so the field swap
breaks nothing there today. The backtest verb still passes the --params
dict straight through and catches only TypeError for bad params files;
adapting it to CandidateParams validation belongs to the wave-6 verb and
report plan (08-10), which owns that surface.

## Acceptance results (exit codes)

- Task 1 verify: `! grep -q
  "sha256|hashlib|_DIGEST_SCALE|_score_candidate|_evaluate_holdout|def
  _params_hash" src/pumpgrok/backtest/harness.py` exits 0 (no match).
- Task 2 verify: `uv run pytest -q
  tests/backtest/test_single_search_engine.py` exits 0, 11 passed in
  about 70 seconds (316 real window replays).
- `uv run ruff check` and `uv run ruff format --check` on both touched
  files: clean.
- `git -C /root/src/repos/pumpgrok status --short`: empty (main checkout
  untouched).
