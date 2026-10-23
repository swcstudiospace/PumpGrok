---
phase: 05-hardening
plan: 05
subsystem: testing
tags: [safety-invariants, owning-tests, static-scan, config-gates, meta-test, obs-005]
status: complete
dependency_graph:
  requires: [05-01, 05-04]
  provides: [static-owning-tests, config-owning-tests, invariant-matrix-meta-test]
  affects: [05-06, verify-work]
tech_stack:
  added: []
  patterns: [alias-resolving-ast-scan, scratch-copy-probes, code-span-aware-matrix-parse, prefix-mapping-for-parametrised-owners]
key_files:
  created:
    - tests/safety/test_no_eval_or_shell.py
    - tests/safety/test_env_example_placeholders.py
    - tests/safety/test_constitution_constants.py
    - tests/safety/test_no_live_write_in_rosters.py
    - tests/safety/test_no_vendor_imports.py
    - tests/safety/test_money_types.py
    - tests/safety/test_no_direct_time.py
    - tests/safety/test_no_uuid_module.py
    - tests/safety/test_live_adapter_raises.py
    - tests/desk/test_hermes_cron_contract.py
    - tests/desk/test_check_sh_passes.py
    - tests/desk/test_doctor_and_once.py
    - tests/config/test_mode_defaults_paper.py
    - tests/config/test_invalid_config_fails_fast.py
    - tests/config/test_secrets_never_dumped.py
    - tests/config/test_forbidden_env_keys_refused.py
    - tests/config/test_overlay_precedence.py
    - tests/risk/test_limits_validation.py
  modified:
    - tests/safety/test_no_signing_outside_live_stub.py
    - tests/execution/test_live_gate_fails_fast.py
    - ci/tests/test_gates.py
decisions:
  - "Matrix paths are canonical: INV-S-10/INV-S-11/INV-C-12 tests live under tests/desk/ per SAFETY_INVARIANTS.md section 6, not the plan's tests/safety/ sketch (D2)."
  - "INV-S-04 element interpolation inside a list argv stays list-argv; the check asserts argv shape plus no shell=True. ci/tests/*.py joins the subprocess-import allowlist as the gate-test harness."
  - "INV-S-01 test renamed to the matrix-canonical test_no_signing_symbols_outside_quarantine."
  - "INV-S-06 numeric literals accepted as documented non-secret numerics; trailing # comments stripped before matching."
  - "INV-S-09 asserts against the real constant homes (risk/engine.py, core/approvals.py, ledger/tickets.py, tools/desk_state.py, cli.py); single-definition rule scoped to assignment, mirrors allowed."
  - "INV-S-14 allows MoneyInt, Decimal ratios/prices, paper_equity_sol, and the _sol_to_lamports boundary str input; schemas allow number only on fraction/price names."
  - "Meta-test inner collection overrides addopts: the repo -q plus an explicit -q collapses --collect-only to per-file counts."
metrics:
  duration: "1 session"
  completed: 2026-10-22
  tasks: 3
  commits_actual: 3
  plan_head_before: 73db97761723aecf9437c45b3904215993844387
  commits:
    - 93f66a5
    - 54c5aa6
    - 0b89097
---

# Phase 05 Plan 05: Static and Config Owning-Test Batches plus Matrix Meta-Test Summary

One-liner: Every INV-S and INV-C matrix row now has a collected owning test, proven by the new `test_invariant_matrix_tests_exist` meta-test, which is red only on the 31 runtime rows that later plans own.

## Tasks Completed

### Task 1: Static invariant owning tests (INV-S batch)

New files (all `tests/safety/`, AST alias-resolving scans with scratch-copy probes):

- `test_no_eval_or_shell.py::test_no_eval_exec_or_shell_true` (INV-S-04): bans eval/exec/compile, os.system/popen, shell=True; requires list/tuple argv; subprocess imports limited to `ci/gates/*.py`, `ci/tests/*.py` and the named `cli.py` member; skips `.venv` and cache dirs.
- `test_env_example_placeholders.py::test_env_example_has_only_placeholders` (INV-S-06): `PUMPGROK_` prefix, no forbidden key names, placeholder or documented numeric values, `#` comments stripped.
- `test_constitution_constants.py::test_constants_match_rule_file_bytes` (INV-S-09): rule-file backtick bytes versus `FLOOR_HALTED_DAILY`, ticket-core pattern in all four homes, approval grammar, 0.05 cap, single definition home, en-dash preservation.
- `test_no_live_write_in_rosters.py::test_rosters_have_no_live_write` (INV-S-02): no live-write, no `exec.live*`, R19 names, effective size 8..15 over the union with `_core.yaml`.
- `test_no_vendor_imports.py::test_src_never_imports_vendor` (INV-S-12).
- `test_money_types.py::test_no_float_money_fields` (INV-S-14): int (or MoneyInt) money, Decimal only for ratios/prices, JSON Schema walk.
- `test_no_direct_time.py::test_no_wall_clock_outside_clock_module` (INV-S-13): wall-clock ban plus tenacity `sleep=` requirement.
- `test_no_uuid_module.py::test_uuid_never_imported` (INV-S-15).
- `test_live_adapter_raises.py::test_live_adapter_place_raises_and_audits` plus cancel and precondition-8 cases (INV-C-03).
- `tests/desk/test_hermes_cron_contract.py::test_cron_never_trades` (INV-S-10) and `tests/desk/test_check_sh_passes.py::test_check_sh_exit_zero` (INV-S-11), both at matrix-canonical paths.

Other edits: renamed `test_no_signing_symbols_outside_live_stub` to the matrix-canonical `test_no_signing_symbols_outside_quarantine` (INV-S-01); added `test_g3_trading_patterns` to `ci/tests/test_gates.py` (INV-S-05, one case per trading regex, runtime-built fixtures in the existing concatenated style).

Verify: `uv run pytest -q tests/safety/ tests/test_registry_least_privilege.py` exit 0 (69 passed).

### Task 2: Config invariant owning tests (INV-C batch)

New files (all `tests/config/` plus two matrix-canonical homes):

- `test_mode_defaults_paper.py::test_mode_defaults_paper` (INV-C-01): paper defaults plus a LiveGate.evaluate spy proving a paper cycle never evaluates the gate.
- `test_invalid_config_fails_fast.py::test_invalid_config_exit_1[*]` (INV-C-05): eight invalid configs raise ConfigError with `loc: type` lines and exit 1 through `main`.
- `test_secrets_never_dumped.py::test_secret_values_absent_from_dumps` (INV-C-07): planted secrets absent from dumps, repr, health body, ConfigChanged payloads, config-hash input and `state status` output; confirmation key is no Settings field.
- `test_forbidden_env_keys_refused.py::test_forbidden_key_names_abort_startup[*]` (INV-C-08): nine names abort startup naming the key, value never printed; replay seed exempt.
- `test_overlay_precedence.py` with `test_mode_precedence_cli_env_toml` and `test_profile_then_operator_file_then_env` (INV-C-04, INV-C-10).
- `tests/desk/test_doctor_and_once.py::test_once_skip_only_cycle_and_doctor_rows` (INV-C-12): skip-only cycle exit 0 with JournalNote in `var/replay/smoke/ledger.sqlite`; doctor rows ok or warn not-yet-implemented.
- `tests/risk/test_limits_validation.py::test_daily_loss_halt_cannot_exceed_constitution` (INV-C-06).
- `tests/execution/test_live_gate_fails_fast.py` gained `test_live_flag_requires_both_sources`, `test_adapter_precondition_always_unmet_in_this_release`, `test_live_gate_refuses_replay_source` (INV-C-04, INV-C-03, INV-C-09).

Verify: `uv run pytest -q tests/config/ tests/execution/` exit 0 (44 passed).

### Task 3: Invariant-matrix meta-test

`ci/tests/test_gates.py::test_invariant_matrix_tests_exist` parses section 6 rows only, splits cells on pipes outside backtick spans, resolves `::name` continuations against the row path, maps `[*]` and `[<variant>]` placeholders to collected node-id prefixes, runs `pytest --collect-only` over the referenced files (CI-only `--co` use) and fails listing every uncollected reference.

Verify: `uv run pytest -q ci/tests/test_gates.py::test_invariant_matrix_tests_exist` is RED with exactly the 31 INV-R rows outstanding (INV-R-01 through INV-R-35 minus rows already covered by existing tests: INV-R-14, INV-R-20, INV-R-22, INV-R-24, INV-R-33 failover half, INV-R-36). Zero INV-S or INV-C rows missing.

Full plan verification (`tests/safety/ tests/config/ tests/execution/ tests/desk/ tests/risk/test_limits_validation.py tests/test_registry_least_privilege.py ci/tests/test_gates.py`): everything passes except the designed-red meta-test.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Matrix-canonical paths and names differ from the plan sketch and the tree.**
- **Found during:** Tasks 1-3.
- **Issue:** The plan listed `tests/safety/test_hermes_cron_contract.py`, but the matrix (authoritative per D2) says `tests/desk/...`; the tree defined `test_no_signing_symbols_outside_live_stub` while the matrix names `..._quarantine`.
- **Fix:** Created desk tests at the matrix paths; renamed the signing test to the matrix name (single definition, no other references).
- **Files modified:** `tests/desk/*`, `tests/safety/test_no_signing_outside_live_stub.py`.

**2. [Rule 1/3 - Over-match] Strict readings failed on legitimate tree shapes; narrowed to the real security boundary.**
- **Found during:** Task 1.
- **Issue:** `services/desk-gateway/.venv` site-packages; f-string/list interpolation inside list argv (`[sys.executable, str(...)]`, `f"{base}...HEAD"`); `MoneyInt` alias; `size_sol: str` boundary converters; `paper_equity_sol` Decimal; `.env.example` numerics and `#` comments; capture-group ticket patterns; `str()` argv elements.
- **Fix:** Venv/cache skip set; argv-shape (not interpolation) check; MoneyInt-as-int; boundary-converter and ratio/price carve-outs with normalization; comment stripping and numeric allowance; all documented in the test module docstrings.
- **Files modified:** the corresponding new static tests.

**3. [Rule 3 - Blocking] Meta-test inner collection collapsed to per-file counts.**
- **Found during:** Task 3.
- **Issue:** Repo `addopts` already carries `-q`; the explicit `-q` made `-qq`, which prints `file: count` instead of node ids.
- **Fix:** Inner run passes `-o addopts=--strict-markers`.
- **Files modified:** `ci/tests/test_gates.py`.

**4. [Rule 3 - Blocking] `var/replay/<dataset>/ledger.sqlite` is the replay ledger home.**
- **Found during:** Task 2.
- **Issue:** Doctor test read `var/ledger.sqlite` and found no rows.
- **Fix:** Read `var/replay/smoke/ledger.sqlite` per R21.
- **Files modified:** `tests/desk/test_doctor_and_once.py`.

### G-3 pragma additions (no behavior change)

Synthetic secret shapes and long `PUMPGROK_*` names in new tests carry `# pragma: allowlist secret` per the established precedent (verified with `check_secrets.scan_file`: all touched files clean).

## Auth Gates

None - no authentication was required.

## Known Stubs

None - every new test asserts against the current tree and passes; no placeholders or skipped verifications.

## Threat Flags

None - no new security-relevant surface. The meta-test parser fails loudly on unparseable rows and asserts the 63-invariant count, so doc edits that narrow the proof surface fail the test (T-05-12, T-05-13 mitigations hold).

## Self-Check: PASSED

All 18 created and 3 modified files exist; commits 93f66a5, 54c5aa6, 0b89097 resolve; no tracked-file deletions across the three commits.
