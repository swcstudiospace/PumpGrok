# 08-01 SUMMARY: Backtest run manifest (BT-01)

Plan 08-01 is complete. The backtest package now exists with a frozen run
manifest: whole-dataset digest, seed, FilterSettings hash, parameter-set hash
and code version, with the run id derived from the manifest. Per CONTEXT
D-01, D-02, D-11 and G-04.

## Commits

- 4673bb3 feat(08-01): BT-01 backtest run manifest with whole-dataset digest
  and derived run id
- fd57d1a test(08-01): BT-01 manifest regression test, determinism and
  single-byte sensitivity

## Changed files

- src/pumpgrok/backtest/__init__.py (new): package docstring only, no
  re-exports. Coordinated with Exec8Plan03: 08-03 consumes this file for
  pumpgrok.backtest.metrics and agreed to the docstring-only content so the
  merge stays clean.
- src/pumpgrok/backtest/manifest.py (new): RUN_ID_VERSION, dataset_digest,
  build_manifest, run_id, RunManifest, plus default_code_version,
  filter_settings_hash and param_set_hash helpers.
- tests/backtest/test_run_manifest.py (new): 8 tests covering manifest
  contents, run id determinism, per-file single-byte sensitivity, fixture
  name resolution, unknown-dataset refusal, settings hash behavior, code
  version shape and model frozenness.

## Design notes

- dataset_digest hashes every file in the dataset directory in sorted-name
  order with concatenated per-file sha256, then hashes the concatenation.
- build_manifest accepts a dataset directory path or a fixture name
  resolved under tests/fixtures/replay, so tmp_path copies and the
  wave-2 harness call shape both work with one signature. code_version
  defaults to default_code_version when omitted.
- default_code_version reads the git HEAD sha from the checkout files
  (worktree gitfile, commondir and packed-refs aware). No subprocess, so no
  S603 or S607 findings. Returns UNKNOWN-DEV only when git is unavailable.
- run_id is the sha256 of canonical_json over the manifest payload
  excluding run_id itself. No wall-clock timestamps anywhere.
- filter_settings_hash uses plain sorted JSON because FilterSettings
  thresholds are floats by definition and canonical_json forbids float
  leaves. Money is not involved. All hashes are lowercase hex strings.
- No angle brackets, no TODO markers, ASCII only.

## Acceptance commands and exit codes

- uv run --no-sync pytest -q tests/backtest/test_run_manifest.py: 8 passed,
  exit 0.
- uv run --frozen pytest -q tests/backtest/test_run_manifest.py: 8 passed,
  exit 0.
- uv run --frozen ruff check on the three touched files: All checks passed,
  exit 0.
- uv run --frozen ruff format --check on the three touched files: 3 files
  already formatted, exit 0.
- uv run --frozen mypy --strict src/pumpgrok/backtest/manifest.py: no issues
  found, exit 0.
- default_code_version sanity check returns the worktree HEAD sha
  27182860cf3d737356b7eb3bba6fce537c3c16b6 exactly, exit 0.

## Deviation

Plain `uv run pytest -q tests/backtest/test_run_manifest.py` (with implicit
sync) reports Pytest: No tests collected, exit 0, in this worktree. The same
happens for the pre-existing tests/replay/test_clock.py, so the cause is
environmental and unrelated to this change. The suite passes under
--no-sync, --frozen and direct .venv python execution. A stray
tests/backtest/.venv created during diagnosis was removed with rm -rf; no
other generated files remain.

## Main checkout

git -C /root/src/repos/pumpgrok status --short is empty.
