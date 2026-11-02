---
phase: 20
status: passed
requirements: [LIV-01]
verified_head: c3898ec
branch: bot-00-chief/v3-closeout
---

# Phase 20 Verification: LIV-01 live adapter import path

Verified at HEAD `c3898ec` on branch `bot-00-chief/v3-closeout` in `/root/src/repos/pumpgrok-wt/v3-closeout`. All commands ran from the worktree root. Exit codes are the process exit codes captured in the shell. No product code, tests, CHANGELOG, or planning files were edited by this verification.

## Criteria

| # | Criterion | Command | Exit | Key output |
|---|---|---|---|---|
| 1a | Lint gate | `make lint` | 0 | `All checks passed!`; `814 files already formatted` |
| 1b | Typecheck gate | `make typecheck` | 0 | `Success: no issues found in 208 source files` |
| 1c | Test gate | `make test` | 0 | Suite runs to 100%. The Makefile target writes no junit file, so counts come from 1d. |
| 1d | Full-suite junit counts | `uv run python -m pytest -q --junitxml=/tmp/phase20-fullsuite.xml` | 0 | `tests="2404" failures="0" errors="0" skipped="2"`. The 2 skips are the pre-existing `intentional non-port per R5` cases in `tests/characterization/test_vendor_risk.py`. |
| 1e | Audit gate | `make audit` | 0 | `No known vulnerabilities found` |
| 1f | Repository check | `./scripts/check.sh` | 0 | `ok: 35 skills, 10 agents, 316 markdown files checked`; `PumpGrok repository structure looks healthy.` |
| 2 | Runtime `sys.modules` probe | `uv run python -c` importing `pumpgrok.cli`, `pumpgrok.cli.backtest`, `pumpgrok.cli.promotion`, then printing membership of `live_adapter` and `live_gate` | 0 | `adapter= False gate= True`. Expected `False` and `True`, so this passes. `pumpgrok.__file__` resolves to the worktree `src/`. |
| 3a | Guard suite junit | `uv run python -m pytest tests/safety/test_import_graph_no_live.py -q --junitxml=/tmp/phase20-guard.xml` | 0 | `tests="17" failures="0" errors="0" skipped="0"`. `test_guard_follows_parent_package_init` is present and has no failure child. |
| 3b | Guard assertions vs baseline | `git show 9bfb0f6:tests/safety/test_import_graph_no_live.py` diffed against HEAD | 1 | Differences exist, and all are additions. No assertion line was removed or changed. See "Guard fidelity" below. |
| 4a | Live refusal | `uv run pumpgrok run --mode live --once; echo "exit=$?"` | 3 | `exit=3`; header `LIVE GATE: refusing to start in mode=live. 8 of 9 preconditions unmet:` |
| 4b | Replay | `uv run pumpgrok verify --fixture smoke-10m` | 0 | `events.hash=b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`; `verify=CONSISTENT seq=2 events=41`. The hash matches the required value. |
| 5 | Scope | `git diff --stat 9bfb0f6..HEAD` | 0 | 7 files, 257 insertions, 5 deletions. All 7 are named in the plan or are the phase summary. No extra committed file. See "Scope" below. |
| 6 | Security notes | Pattern scan of added lines in `9bfb0f6..HEAD` for `src`, `tests`, `CHANGELOG.md` | 1 (no match) | No network import, no signing symbol, no secret-like token. See "Security notes" below. |

## Guard fidelity (check 3b)

Method: `git show 9bfb0f6:tests/safety/test_import_graph_no_live.py > /tmp/guard_9bfb0f6.py`, then `diff /tmp/guard_9bfb0f6.py tests/safety/test_import_graph_no_live.py`.

- The diff is additive only. Zero lines were removed or changed.
- Added: one sentence in the module docstring; the constants `GATE_PACKAGE` and `CLI_ROOT`; a root branch in `_module_name` (`if not parts: return "pumpgrok"`); the helper `_ancestors`; a parent-edge loop in `_edges`; the new test `test_guard_follows_parent_package_init`.
- Assertion lines: 14 in the baseline and 16 at HEAD. The two new ones are in the new test.
- The symbol scan, the network-root scan, and the `GATE_MODULE` reachability assertion are textually identical to baseline.
- The `_module_name` root key changes from `"pumpgrok."` to `"pumpgrok"`. This is a helper change, not an assertion change. The phase summary records it as deviation 6, and its side effects were measured only through the guard suite and the full suite (1d).

## Scope (check 5)

Committed diff `9bfb0f6..HEAD`, 7 files:

- Plan files (6): `CHANGELOG.md`, `src/pumpgrok/execution/live/__init__.py`, `tests/execution/test_live_gate_fails_fast.py`, `tests/safety/test_cli_import_no_live_adapter.py`, `tests/safety/test_import_graph_no_live.py`, `tests/test_live_gate.py`.
- Phase document (1): `.planning/phases/20-close-gap-liv-01-live-adapter-import-path/20-01-SUMMARY.md`.

No extra committed file.

Working-tree state outside the committed range, not part of `9bfb0f6..HEAD`, reported for the owner:

- `.planning/ROADMAP.md` is modified and unstaged (+10 lines, a Phase 20 stub).
- Untracked: `20-01-PLAN.md`, `20-CONTEXT.md`, `20-REVIEW.md` in the phase directory, plus `.planning/pre-run-snapshot/` and `.planning/state.json`.

None of these is product code. `git status` shows no product-code change in the working tree.

## Security notes (check 6)

Method: `git diff 9bfb0f6..HEAD -- src tests CHANGELOG.md`, keeping only added lines (`^\+`), then a case-insensitive scan for:

- network modules: `socket`, `http`, `requests`, `httpx`, `urllib`, `aiohttp`, `websockets`, `ssl`, `grpc`;
- signing and chain libraries: `solana`, `solders`, `nacl`, `ed25519`, `cryptography`, and the word `sign`;
- secret-like terms: `keypair`, `private_key`, `secret`, `api_key`, `token`, `password`, `PRIVATE`.

Result: no matches. A control run of the same pipeline with `import|subprocess` matched 25 lines, so the scanner is live.

The only new imports are in the new test file: `os`, `subprocess`, `sys`, `pathlib`. The new runtime test runs a local subprocess with `PYTHONPATH` set. It makes no network call and reads no secret. This scan is pattern-based. It is not a semantic review.

## Notes on the phase summary

1. The phase summary records `make lint` exit 2, caused by a line over 100 columns in the untracked `20-01-PLAN.md`. At verification time that line is 14 columns and `make lint` exits 0 (check 1a). The earlier failure does not reproduce. I did not investigate the cause beyond measuring the current exit code.
2. The Task 5 text in the plan expects the header `9 of 9`. The observed header is `8 of 9 preconditions unmet`, because precondition 6 (notional cap) is met at the default 1 SOL cap. The contract checks only the exit code (3). The wording difference is recorded in the summary (deviation 2) and is not a failure.
3. The red-state evidence (the two tests failing before the fix) comes from the phase summary. It was not re-observed in this verification, because the fix is already committed.

## Requirements

### LIV-01: CLI import path does not load the live adapter

**Status: passed.** Checks 1a through 1f, 2, 3a, 4a, 4b, and 5 all pass. Check 3b confirms that the guard assertions are unchanged, and check 6 finds no network, signing, or secret addition.

**Requirement:** A fresh interpreter importing `pumpgrok.cli`, `pumpgrok.cli.backtest`, and `pumpgrok.cli.promotion` must leave `pumpgrok.execution.live.live_adapter` out of `sys.modules`. `pumpgrok.execution.live.live_gate` must stay loaded. The import-graph guard must follow parent package `__init__` edges. `run --mode live --once` must still exit 3, and the replay hash must not change.

**Evidence:**

- Runtime probe (check 2): `adapter= False gate= True`, from the worktree `src/`.
- Guard suite (check 3a): 17 tests, 0 failures. `test_guard_follows_parent_package_init` passes.
- Guard fidelity (check 3b): additive-only diff against `9bfb0f6`; no assertion changed.
- Smoke (checks 4a and 4b): live refusal exits 3; replay reports `CONSISTENT` with hash `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`.
- Canonical gates (checks 1a to 1f): all exit 0. Full suite 2404 tests, 0 failures, 0 errors.
- Scope (check 5): committed changes are limited to the plan's files and the phase summary.
- Commits: `148dbfa` (red regression tests), `02f5997` (fix), `21e99dd` (CHANGELOG), and the summary commit, with `c3898ec` at HEAD.
