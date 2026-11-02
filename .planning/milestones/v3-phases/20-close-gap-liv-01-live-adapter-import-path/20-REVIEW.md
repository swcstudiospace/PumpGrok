---
phase: 20-close-gap-liv-01-live-adapter-import-path
reviewed: 2026-11-01
scope: commits 148dbfa, 02f5997, 21e99dd (range 9bfb0f6..HEAD for src, tests, CHANGELOG.md)
status: issues_found
findings:
  blocker: 0
  major: 0
  minor: 1
  nit: 4
---

# Phase 20 Review: LIV-01 live adapter import path

## Verdict

No blocker or major findings. The LIV-01 fix is sound: the package-level re-export of `LiveAdapterStub` is removed, no caller depends on it, the guard gained only additive parent-package edges, and the runtime probe shows the adapter is absent from `sys.modules` after importing the CLI, backtest and promotion modules. One minor residual blind spot (dynamic imports, F-01) and four nits remain.

## Findings

### F-01 (minor): the guard cannot see imports made through `pkgutil` and `importlib`

- File: `tests/safety/test_import_graph_no_live.py:103-128` (`_imports_of` reads only `ast.Import` and `ast.ImportFrom`).
- Evidence: `src/pumpgrok/cli/wiring.py:19` imports `pumpgrok.contracts.projection`. `src/pumpgrok/contracts/projection.py:85-86` calls `pkgutil.walk_packages(tools_pkg.__path__, ...)` and `importlib.import_module(module_info.name)` over every `pumpgrok.tools.*` module. Those dynamic edges are absent from `_edges`. The runtime probe in `tests/safety/test_cli_import_no_live_adapter.py` does not call `implementation_specs()`, so it does not exercise them either.
- Current impact: none found. `grep` of `src/pumpgrok/tools` shows only `import pumpgrok.execution` (`tools/__init__.py:22`) and `pumpgrok.execution.paper_adapter` (`tools/__init__.py:84`). No tool module imports the live package. The walk runs only when `implementation_specs()` is called, not at CLI import time, so the LIV-01 import-path claim is unaffected.
- Risk: a future tool module that imports `pumpgrok.execution.live.live_adapter` would pass both the static guard and the runtime probe. The gap is invisible to any current test.
- Suggested follow-up (not blocking): state the limit in the guard docstring, or add an assertion that calls `implementation_specs()` in a fresh interpreter and checks the adapter stays absent.

### F-02 (nit): trailing empty `PYTHONPATH` entry

- File: `tests/safety/test_cli_import_no_live_adapter.py:29`.
- Evidence: `os.pathsep.join([str(SRC), os.environ.get("PYTHONPATH", "")])` yields `"<SRC>:"` when `PYTHONPATH` is unset. The empty entry means the current directory, which is `tmp_path` here, so the behaviour is harmless.
- Suggested: `os.pathsep.join(p for p in (str(SRC), os.environ.get("PYTHONPATH", "")) if p)`.

### F-03 (nit): guard docstring sentence appended after the scope sentence

- File: `tests/safety/test_import_graph_no_live.py:12`.
- Evidence: the new sentence "Each module also depends on every parent package __init__, because importing a child executes it." follows "Offline only, ASCII only." at line 11. It is accurate, but it sits outside the paragraph that describes the closure. Cosmetic only.

### F-04 (nit): second `## [Unreleased]` heading in CHANGELOG

- File: `CHANGELOG.md:5`.
- Evidence: the new heading `## [Unreleased] - v3 Phase 20: LIV-01 live adapter import path` follows the same pattern as the existing headings at `CHANGELOG.md:11` and `:37`. The entry is accurate; the repeated heading is pre-existing convention, not introduced here.

### F-05 (nit): phase summary records a stale `make lint` failure

- File: `.planning/phases/20-close-gap-liv-01-live-adapter-import-path/20-01-SUMMARY.md:25`, `:70`, `:76-79`.
- Evidence: the summary records `make lint` exit 2, caused by `ruff format --check .` on the untracked `20-01-PLAN.md`. In this worktree now, `uv run ruff format --check .` reports "814 files already formatted" (exit 0) and `uv run ruff check .` reports "All checks passed!" (exit 0). The code is unaffected. The summary should be re-run or annotated so the recorded gate result matches the current tree.

## Review of the five questions

1. Guard edges. `_ancestors` returns every parent prefix outermost first. `_edges` adds an edge from each module to each ancestor that exists in `modules`. Every added edge is a real import-time dependency, so there is no false positive. The root key change (`_module_name` returns `"pumpgrok"` for `src/pumpgrok/__init__.py`) is correct: that file defines only `__version__` and imports nothing, so it adds no edges. Relative imports resolve correctly (`from . import x` in a package `__init__` resolves against the package itself). The one false-negative path is dynamic import (F-01). Mutation checks on a scratch copy of HEAD (see Checks) confirm the guard fails when the re-export is restored and when a guarded package `__init__` imports the adapter.
2. Caller removal. No caller in `src`, `tests`, `scripts`, `ci`, `services`, `skills`, `contracts`, `vendor` or `.github` imports `LiveAdapterStub` from `pumpgrok.execution.live`. The seven test files that use the stub import it from `pumpgrok.execution.live.live_adapter`. `tests/upgrade/test_no_live_imports.py` and `tests/safety/test_import_graph_no_live.py` use the name only inside AST probe strings. The remaining package-level imports (`PRECONDITION_IDS`, `LiveGate`, `Precondition`, `refusal_lines`) are still in `__all__`. Submodule imports such as `from pumpgrok.execution.live import live_gate` are unaffected. Docs mention the class name only, not the package-level export, so no doc line needed changing (D-07).
3. Runtime test. It runs a fresh interpreter with `cwd=tmp_path`, so no repo-local config is read. `SRC` is first on `PYTHONPATH`, so the worktree source wins over any installed copy. The output is parsed to an exact list `["0", "1"]`, so the gate-present check guards against a vacuous pass. It is offline and clock- and RNG-free, and the 120 s timeout is generous. It imports the three named modules, and all three exist. It failed at `148dbfa` with `1 1`, as recorded in the summary. The only gap is F-01.
4. CHANGELOG accuracy. Each claim checks out. The package no longer re-exports the stub. A fresh import of `pumpgrok.cli`, `pumpgrok.cli.backtest` and `pumpgrok.cli.promotion` gives `0 1`. The guard follows parent `__init__` edges. The replay hash `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` reproduces on HEAD (CONSISTENT, seq=2, events=41). No automated test pins that hash, so the claim rests on the smoke run, not on a test assertion.
5. Weakened assertions. The test diff `9bfb0f6..HEAD` removes only two import lines, which were rewritten to import the same symbols from their new locations, minus `LiveAdapterStub` from the package. No `skip`, `xfail`, `noqa` or `type: ignore` was added under `tests`. Every existing guard assertion is unchanged; the fidelity change is additive (D-05).

## Checks run

- `git log 9bfb0f6..HEAD`, `git show` per commit, and `git diff --stat 9bfb0f6..HEAD -- src tests CHANGELOG.md` (6 files, +81 / -5).
- Targeted pytest, form `uv run python -m pytest tests/safety tests/test_live_gate.py tests/execution/test_live_gate_fails_fast.py tests/upgrade -q --junitxml=/tmp/review20-targeted.xml`: exit 0, 315 tests, 0 failures, 0 errors, 0 skipped. The console line "No tests collected" is the known misleading message; the junit counts are authoritative.
- Red check: `git archive 148dbfa` extracted to `/tmp/red20`, then the guard and runtime test modules run against it: 18 tests, 2 failures (`test_guard_follows_parent_package_init` and `test_cli_backtest_promotion_import_loads_no_live_adapter`), matching the summary.
- Mutation A: scratch copy of HEAD with `from pumpgrok.execution.live.live_adapter import LiveAdapterStub` prepended to `src/pumpgrok/execution/live/__init__.py`. Result: 3 failures (`test_guarded_closures_never_reach_live_adapter`, `test_gate_module_stays_reachable_but_adapter_free`, `test_cli_backtest_promotion_import_loads_no_live_adapter`).
- Mutation B: scratch copy of HEAD with the adapter import appended to `src/pumpgrok/backtest/__init__.py`. Result: 2 failures (`test_guarded_closures_never_reach_live_adapter`, `test_gate_module_stays_reachable_but_adapter_free`).
- Scratch HEAD copy: runtime probe prints `0 1`; `run --mode live --once` exits 3 with the nine-precondition refusal; `verify --fixture smoke-10m` prints `events.hash=b69c...` and `verify=CONSISTENT seq=2 events=41`.
- `uv run ruff format --check .` and `uv run ruff check .` in the worktree: both exit 0.
- Repo-wide grep for `LiveAdapterStub`, `execution.live`, `execution import live`, `importlib`, `__import__` across `src`, `tests`, `scripts`, `ci`, `services`, `skills`, `contracts`, `vendor`, `docs`.

Not run by this review: `make typecheck`, `make audit`, the full suite, and `./scripts/check.sh`. These belong to the main agent's verification pass.

## Observations outside the review scope

- The worktree carries uncommitted planning changes that are not part of the three phase commits: ` M .planning/ROADMAP.md` and untracked `20-01-PLAN.md`, `20-CONTEXT.md`, `.planning/pre-run-snapshot/`, `.planning/state.json`. The review did not touch them.
- This file is the only new artifact written by the review.
