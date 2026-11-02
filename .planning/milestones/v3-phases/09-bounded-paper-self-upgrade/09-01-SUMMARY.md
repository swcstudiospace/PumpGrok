# 09-01 SUMMARY: Content-hashed ParamSet plus version-controlled bounds

Plan 09-01 (UPG-01) complete. Created the upgrade package core: a frozen
ParamSet model with a sha256 identity hash over the canonical_json of the
normalized overrides, the version-controlled upgrade_bounds.toml range
tables, typed OutOfBoundsError rejection, and a static guard proving the
package never touches the live order path.

## Commits

- 7104e4f feat(09-01): content-hashed ParamSet plus version-controlled bounds [UPG-01]
- 4eedd4a test(09-01): static guard proves upgrade package never touches live [UPG-01]

## Files

- src/pumpgrok/config/upgrade_bounds.toml (new): filter and exits range
  tables covering every tunable CandidateParams accepts (9 filter keys,
  5 exits keys, each with inclusive min and max; bool entries admit both
  values). min_total_score deliberately absent: inert scoring knob.
- src/pumpgrok/upgrade/__init__.py (new): package exports, no CLI verb.
- src/pumpgrok/upgrade/params.py (new): frozen ParamSet validated through
  CandidateParams; content_hash documented as identity only, never a
  score, metric, or verdict.
- src/pumpgrok/upgrade/bounds.py (new): load_bounds plus
  validate_against_bounds raising typed OutOfBoundsError (code
  out_of_bounds) naming key, value, and allowed range; never clamps.
- tests/upgrade/__init__.py (new): test package marker.
- tests/upgrade/test_param_set_hash.py (new): 7 tests.
- tests/upgrade/test_no_live_imports.py (new): 10 tests.

## Decisions

- Bool bounds use min false and max true, admitting both values while the
  bool type itself is the bound.
- Float override leaves normalize through Decimal(repr(v)) so the hash
  input stays deterministic while canonical_json keeps rejecting raw
  float leaves (G-03 wiring verified by an independent recomputation test).
- Malformed bounds files raise ValueError; out-of-range values raise
  OutOfBoundsError; keys with no version-controlled bound are refused
  rather than accepted.

## Deviations

None. Plan executed exactly as written.

## Known follow-up (not a deviation)

Creating src/pumpgrok/upgrade/ trips the existing assertion in
tests/safety/test_no_backtest_to_live_path.py that the upgrade path does
not exist. That guard file is outside this plan's files_modified, so it
was left untouched. Plan 09-07 Task 2 owns criterion 10 (live refused
with upgrade modules present) and updates the guard there.

## Acceptance

- `.venv/bin/pytest -q tests/upgrade/test_param_set_hash.py`: 7 passed, exit 0
- `uv run python -c "import tomllib; tomllib.load(open('src/pumpgrok/config/upgrade_bounds.toml','rb'))"`: exit 0
- `.venv/bin/pytest -q tests/upgrade/test_no_live_imports.py`: 10 passed, exit 0
- `uv run ruff check` on touched files: no issues found
- `uv run ruff format --check` on touched files: all formatted
- `git -C /root/src/repos/pumpgrok status --short`: empty
