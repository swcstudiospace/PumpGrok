---
phase: 20-close-gap-liv-01-live-adapter-import-path
plan: 01
status: code-complete; lint gate blocked by an untracked planning file
requirements-completed: [LIV-01]
branch: bot-00-chief/v3-closeout
commits:
  - 148dbfa test(live): add red LIV-01 regression tests
  - 02f5997 fix(live): keep live adapter off the CLI import path (LIV-01)
  - 21e99dd docs(changelog): record LIV-01 closure (phase 20)
---

# Phase 20 Plan 01: Close LIV-01 (live adapter import path)

## Outcome

The package-level re-export of `LiveAdapterStub` is removed from
`src/pumpgrok/execution/live/__init__.py`. Importing `pumpgrok.cli`,
`pumpgrok.cli.backtest` or `pumpgrok.cli.promotion` in a fresh interpreter no
longer loads `pumpgrok.execution.live.live_adapter`. `pumpgrok.execution.live.live_gate`
stays loaded. The import-graph guard now follows parent package `__init__` edges
and reports the CLI path that it previously missed. The guard assertions were
not weakened.

Requirement LIV-01 is closed in code and tests. `make lint` exited 2 at execution time
because of the planning document (Deviations, item 3). After the formatting fix recorded
there, `make lint` exits 0; see 20-VERIFICATION.md.

## Commits

| SHA | Subject | Paths |
|---|---|---|
| 148dbfa | test(live): add red LIV-01 regression tests | tests/safety/test_import_graph_no_live.py, tests/safety/test_cli_import_no_live_adapter.py (new) |
| 02f5997 | fix(live): keep live adapter off the CLI import path (LIV-01) | src/pumpgrok/execution/live/__init__.py, tests/safety/test_import_graph_no_live.py, tests/test_live_gate.py, tests/execution/test_live_gate_fails_fast.py |
| 21e99dd | docs(changelog): record LIV-01 closure (phase 20) | CHANGELOG.md |

This summary is committed separately with a docs(planning) message.

## Red and green evidence (pytest junit, form: `uv run python -m pytest ... -q --junitxml=...`)

| Run | XML | tests | failures | errors | skipped | Notes |
|---|---|---|---|---|---|---|
| Task 1 red | /tmp/phase20-task1.xml | 18 | 2 | 0 | 0 | the two red tests, see below |
| Task 2a guard edges only | /tmp/phase20-task2a.xml | 17 | 2 | 0 | 0 | closure tests now report the CLI path |
| Task 2 after 2b and 2c | /tmp/phase20-task2.xml | 46 | 0 | 0 | 0 | guard, runtime, test_live_gate, fails_fast |
| Task 3 verification | /tmp/phase20-task3.xml | 251 | 0 | 0 | 0 | tests/safety, test_live_gate, fails_fast, upgrade/test_no_live_imports |
| Task 4 docstring | /tmp/phase20-task4.xml | 22 | 0 | 0 | 0 | guard and test_live_gate |
| Full suite, after Task 5 | /tmp/phase20-fullsuite.xml | 2404 | 0 | 0 | 2 | skipped are pre-existing, see below |

Red failure text, observed before the fix (real text, not expected text):

- `tests/safety/test_import_graph_no_live.py::test_guard_follows_parent_package_init`:
  `AssertionError: live_gate has no edge to its parent package execution/live/__init__.py`
  with `assert 'pumpgrok.execution.live' in {'pumpgrok.core.units', 'pumpgrok.ledger.paths'}`.
- `tests/safety/test_cli_import_no_live_adapter.py::test_cli_backtest_promotion_import_loads_no_live_adapter`:
  `AssertionError: 1 1` with `assert ['1', '1'] == ['0', '1']`.
- `test_guarded_closures_never_reach_live_adapter` passed on the red tree. This is the
  blind spot the audit describes. After the guard edges were added, it fails with the witness
  `pumpgrok.cli -> pumpgrok.cli.dispatch -> pumpgrok.cli.verbs_state -> pumpgrok.execution.live.live_gate -> pumpgrok.execution.live -> pumpgrok.execution.live.live_adapter`.
  `test_gate_module_stays_reachable_but_adapter_free` failed the same way. Both pass after the
  re-export is removed.

Skipped tests in the full suite: `tests/characterization/test_vendor_risk.py::test_new_day_resets_counters_and_unhalts`
and `::test_day_roll_keeps_open_positions`, both marked `intentional non-port per R5`. They are
pre-existing and outside this change.

## Canonical gates (Makefile targets and scripts/check.sh)

| Gate | After Task 5 | After Task 6 |
|---|---|---|
| make lint | 2 | 2 at execution; 0 after the planning-doc format fix |
| make typecheck | 0 | 0 |
| make test | 0 | 0 |
| make audit | 0 | 0 |
| ./scripts/check.sh | 0 | 0 |

`make lint` exit 2 at execution came only from `ruff format --check .` on the untracked
planning document `.planning/phases/20-close-gap-liv-01-live-adapter-import-path/20-01-PLAN.md`,
line 160 (a Python code block line over 100 columns). The orchestrator then ran `ruff format`
on that document only. `ruff format --check .` now reports 814 files formatted and
`ruff check .` reports no issues. Every touched Python file passed both checks before.
`make typecheck` reports `Success: no issues found in 208 source files`. `make audit` reports
`No known vulnerabilities found`.

## Smoke and replay (exact lines)

Live refusal, `uv run pumpgrok run --mode live --once; echo "exit=$?"`:

```
exit=3
LIVE GATE: refusing to start in mode=live. 8 of 9 preconditions unmet:
  [ ] 1 mode_live effective mode is live but [live] enabled is not true
  [ ] 2 live_enable_env PUMPGROK_LIVE_ENABLE is not 1
  [ ] 3 min_paper_days no source=paper events in var/ledger.sqlite
  [ ] 4 performance_thresholds no source=paper events in var/ledger.sqlite
  [ ] 5 wallet_allowlist live.wallet_allowlist is empty; no public key is allowlisted
  [x] 6 notional_cap live.notional_cap_lamports is 1000000000 (ceiling 1 SOL)
  [ ] 7 confirmation_record var/live_confirmation.json missing
  [ ] 8 adapter_registered no live adapter implementation ships in this release
  [ ] 9 no_active_stop halt, kill switch and breaker state are not readable in this release
Fix every unmet line or run in mode=paper. No transaction was attempted.
```

Replay, `uv run pumpgrok verify --fixture smoke-10m`, exit 0:

```
events.hash=b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
verify=CONSISTENT seq=2 events=41
```

sys.modules probe, fresh interpreter (cwd /tmp, PYTHONPATH pointing at the worktree src):

- Before the fix: `1 1` (the runtime test failure text above).
- After the fix: `0 1` (adapter absent, gate present).

## Deviations

1. Misplaced guard edit in the phase-6 checkout (corrected). The first Task 1 guard edit used a
   relative path. It resolved against the session working directory `/root/src/repos/pumpgrok`
   rather than the worktree, so the two constants and the new test were written into
   `/root/src/repos/pumpgrok/tests/safety/test_import_graph_no_live.py`. I removed exactly those
   13 inserted lines with an absolute-path edit and confirmed `git diff` for that file is empty.
   No commit was made in the phase-6 checkout. Two pre-existing states there were not touched:
   `M tests/upgrade/test_scheduled_promotion.py` (109 insertions, 35 deletions, not mine) and an
   untracked `.claude/` directory I did not create. Consequence: the first Task 1 pytest run
   collected no guard test, so its single failure reflected only the runtime test. The Task 1
   red result above is the rerun after the edit landed in the worktree.
2. Smoke header wording. The plan expected `9 of 9`. The observed header is
   `8 of 9 preconditions unmet`, because precondition 6 (notional cap) is met at the
   default 1 SOL cap (`live.notional_cap_lamports` is 1000000000). This matches the existing
   CHANGELOG entry ("8 of 9 with default cap"). I reconciled the reported wording to the observed
   output and changed no code.
3. Lint gate exit 2 at execution, resolved by the orchestrator. The untracked planning
   document `.planning/phases/20-close-gap-liv-01-live-adapter-import-path/20-01-PLAN.md`,
   line 160, was a Python code block with a line over 100 columns. Running `ruff format`
   on that one document fixed it. `make lint` exits 0 after the fix (814 files formatted,
   `ruff check` clean). No lint exclusion was added.
4. Commit structure. The plan's Task 5 specifies one commit covering five paths. The orchestrator
   asked for one commit per task. I used three commits: the red tests (148dbfa), the fix
   covering Tasks 2 to 4 (02f5997, four paths, because Tasks 2 and 4 edit the same init file and
   partial staging would have been interactive), and the CHANGELOG (21e99dd). Tasks 3 and 5
   change no files and have no commit. The Task 5 acceptance line `git log -1 --name-only`
   listing five paths is therefore not met: 02f5997 lists four paths, and the fifth,
   tests/safety/test_cli_import_no_live_adapter.py, is in 148dbfa.
5. Git acceptance substitution (open item 2). The plan's `git diff` acceptance cannot see the
   untracked file and matches removed lines. I used `git status --short` for new files and
   `git show -U0 HEAD -- tests` plus `git diff -U0 -- tests`, filtered to added lines
   (`^\+.*(xfail|skip)`). Both returned no matches.
6. Guard `_module_name` root key (open item 3). The trailing-dot key `"pumpgrok."` came only from
   `_module_name` (grep found no other reference to that literal). The root package is now keyed
   `"pumpgrok"`, so the exact-key ancestor check can match it. Evidence: the closure from
   `pumpgrok.cli` contains the `pumpgrok` key, and the root `__init__.py` defines only
   `__version__`, so no current false negative exists. [INFERENCE] Had the root key stayed
   `"pumpgrok."`, any future root-package import would have been missed. The root change also
   makes `_resolve("pumpgrok")` an exact match instead of the prefix fallback, which may remove
   spurious edges. I did not measure that side effect.
7. Formatting. The plan's runtime test `env` line exceeds the 100-column limit. I moved the
   `PYTHONPATH` value into a variable. The subprocess environment is unchanged.
8. Full-suite junit. `make test` runs `pytest -q` with no junit file, so the full-suite counts
   come from a separate run using the plan's junit form. That run was on the tree after Task 5,
   before the CHANGELOG commit. The final make gates after Task 6 exit 0, but no junit file was
   written for them.

## Not verified

- `make lint` exit 0 after the planning-document format fix: verified by the orchestrator
  and in 20-VERIFICATION.md, not by the executor.
- A fresh full-suite junit run on the final tree after the CHANGELOG commit. The final `make test`
  exit 0 is recorded; the counts are from the earlier tree. The CHANGELOG change cannot affect pytest.
- The live smoke with a real venue or network: not applicable, and the live path stays refused.
- `make check`, the aggregate target. It also runs prompt assembly and schema checks, which the plan
  does not require. The plan's required commands were run.
- Doc prose outside `src`, `tests`, `docs`, `scripts`, `ci` and `skills`. `README.md` was included
  in the grep for the package-level export; no hits there.
- The origin of the untracked `.claude/` directory in the phase-6 checkout.
- Behaviour of the root-key change beyond the guard test module. Only the guard suite and the
  full junit run were run.
