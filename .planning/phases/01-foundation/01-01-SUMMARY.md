---
phase: 01-foundation
plan: 01
subsystem: infra
tags: [uv, uv_build, pyproject, lockfile, make, pytest, ruff, mypy, pip-audit]

# Dependency graph
requires: []
provides:
  - "Installable src-layout package `pumpgrok` (uv_build, requires-python >=3.12,<3.13) with the `pumpgrok` script entry declared"
  - "Committed uv.lock generated with uv 0.13.4; `uv sync --frozen --group dev` installs from it"
  - "Canonical make targets (lint, typecheck, test, audit, ...) wired to FOUNDATION_STACK section 6 commands"
affects: [01-02, 01-03, 01-04, 01-05, 01-06, 01-07, 01-08, 01-09]

# Actuals (#2632)
actuals:
  tokens: n/a
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: [uv_build 0.13.4 (build backend), pydantic 2.14.1, pydantic-settings 2.16.1, httpx 0.28.1, websockets 17.3, pyyaml 6.0.3, requests 2.34.2 (dev), ruff 0.17.1, mypy 2.4.0, pytest 9.1.1, pytest-asyncio 1.4.0, pip-audit 2.10.1, types-PyYAML 6.0.12.20260906]
  patterns: [lockfile-only install (`uv sync --frozen`), uv_build src-layout, make targets as the only operator entry point]

key-files:
  created:
    - pyproject.toml
    - .python-version
    - uv.lock
    - Makefile
    - .gitignore
    - src/pumpgrok/__init__.py
  modified: []

key-decisions:
  - "Dependency set and pins are exactly the 13 entries approved in 01-01-CHECKPOINT.md; tenacity, prometheus-client and respx are not declared (deferred per CONTEXT)"
  - "requests>=2.32,<3 is dev-only and is removed with tools/ in Phase 2 (tests/test_tools_cli.py imports it)"
  - "[project.urls] uses the git-origin URL https://github.com/swcstudiospace/PumpGrok (locked Q5), not the swcstudio/pumpgrok guess in FOUNDATION_STACK 3.1"
  - "uv.lock generated with uv 0.13.4 via `uvx --from uv==0.13.4 uv lock`; the local uv 0.11.26 only consumed the lock"
  - "mypy strict has no prometheus_client or respx overrides (V-5); pytest asyncio_mode=auto with function loop scope (V-9); audit exports with --no-emit-project (V-4)"

patterns-established:
  - "Install path is `uv sync --frozen --group dev`; no requirements.txt exists"
  - "Operator entry points are Makefile targets; recipes mirror FOUNDATION_STACK section 6"

requirements-completed: [FOUND-001, FOUND-002]

# Metrics
duration: ~4min (approximate; plan started after the 04:40Z checkpoint-approval commit)
completed: 2026-10-21
status: complete
---

# Phase 1: Foundation Plan 01 Summary

**Locked, installable `pumpgrok` package: uv_build src layout, 13 approved pins in a committed uv.lock (uv 0.13.4), and canonical make targets**

## Performance

- **Duration:** ~4 min (approximate)
- **Started:** ~2026-10-21T04:41Z (approximate; after checkpoint approval commit 716d177 at 04:40:15Z)
- **Completed:** 2026-10-21T04:43Z
- **Tasks:** 2 executed (Task 1 checkpoint pre-approved, not re-prompted; Task 2 tracer and Task 3 Makefile)
- **Files modified:** 6

## Accomplishments

- `pyproject.toml` declares the src-layout package, the `pumpgrok = "pumpgrok.cli:main"` script entry, the five runtime pins and the seven dev-group pins from the approved checkpoint record.
- `uv.lock` committed, generated with uv 0.13.4 (54 packages resolved); `uv sync --frozen --group dev` exits 0 and the venv imports `pumpgrok`, `pydantic_settings`, `httpx`, `websockets`, `yaml`.
- `Makefile` provides help, sync, lint, fmt, typecheck, test, audit, run-paper, replay, report, gates, prompts, check, doctor and clean. `make -n lint typecheck test audit` expands to the section 6 commands.
- `.gitignore` (FOUND-007 draft plus `.planning/research/.cache/`), `.python-version` (3.12).
- Legacy `tests/test_tools_cli.py` passes unmodified: 11 passed, exit 0.

## Task Commits

Each task was committed atomically:

1. **Task 1: Checkpoint approve the 13 pins** - no code commit; approval record committed earlier as `716d177` (docs(01-01): record blocking-human approval...). Approval was pre-recorded by the user; not re-prompted.
2. **Task 2: Tracer declare, lock, install** - `d4a6933` (build(01-01): declare pumpgrok package and commit uv.lock)
3. **Task 3: Makefile canonical targets** - `84ce840` (build(01-01): add canonical make targets)

**Plan metadata:** recorded in the docs commit that adds this SUMMARY (see git log).

## Files Created/Modified
- `pyproject.toml` - package metadata, build backend, runtime and dev dependency groups, ruff/mypy/pytest config
- `uv.lock` - locked resolution (uv 0.13.4)
- `.python-version` - `3.12`
- `.gitignore` - venv, caches, `.env`, `var/`, receipts state, `.planning/research/.cache/`
- `Makefile` - canonical operator targets
- `src/pumpgrok/__init__.py` - `__version__ = "0.1.0"` only (see Deviation 1)

## Decisions Made
- Pins and dependency membership follow the approved checkpoint record exactly. No version was changed and no package added or removed.
- Tool configuration (`[tool.ruff]`, `[tool.mypy]`, `[tool.pydantic-mypy]`) was taken from FOUNDATION_STACK 3.1, because the plan's "tool.ruff default" wording is ambiguous and the existing committed code is formatted at line-length 100, which matches that block. Only the prometheus/respx mypy overrides were removed (V-5).
- Lint runs both `ruff check .` and `ruff format --check .` (FOUNDATION_STACK section 6 lists both; the plan's parenthetical named only the first). Both are check-only; no `--fix` or write is run by `lint`.
- The audit recipe writes the export to `/tmp/pumpgrok-req.txt` and passes it to `pip-audit -r`, rather than piping. This is the FOUNDATION_STACK 3.2 form; `--no-emit-project` was added per V-4.

## Deviations from Plan

**1. [Rule 3 - Blocking] Created `src/pumpgrok/__init__.py` early**
- **Found during:** Task 2 (tracer), `uv sync --frozen --group dev`
- **Issue:** uv_build refuses to build the editable project: `Error: Expected a Python module at: src/pumpgrok/__init__.py`. The package root did not exist (plans 01-02..01-08 add the rest of the package).
- **Fix:** Created the file with `__version__ = "0.1.0"` only, the exact content plan 01-08 specifies for this file. Plan 01-08 owns and may extend it.
- **Files modified:** src/pumpgrok/__init__.py
- **Verification:** `uv sync --frozen --group dev` exits 0; `uv run python -c "import pumpgrok; print(pumpgrok.__version__)"` prints `0.1.0`.
- **Committed in:** d4a6933

**2. [Clarification] Audit export form.** The plan wording said "piped to pip-audit". The recipe uses a temp file (FOUNDATION_STACK 3.2 form) with `--no-emit-project` added. Same content, same `--strict` audit.

**Total deviations:** 1 auto-fixed (1 blocking). **Impact:** None on scope; the file is the minimal stub the build requires and 01-08 retains ownership.

## Issues Encountered

- `uv.lock` does not record the build backend. `uv_build` is a build-system requirement (`>=0.13.4,<0.14.0`) resolved at build time in an isolated environment, not a locked package. The approved "uv-build 0.13.4" pin is therefore enforced only by the range, not by the lockfile. Noted for the phase gate; no change made, since the checkpoint approved this exact declaration.
- Six `.pyc` files remain tracked (`tests/__pycache__/...`, `tools/__pycache__/...`). The new `.gitignore` does not untrack them; that is STRUCT-001 hygiene (`git rm --cached`), outside this plan.
- A first `pytest -q` run was piped through `tail` and reported "No tests collected"; the raw rerun (`uv run pytest -q tests/test_tools_cli.py`, exit 0, 11 passed) is the authoritative result.

## Self-Check: PASSED (full phase-gate run deferred to 01-09; see last item)

Acceptance criteria re-run after the last edit:

- Checkpoint: approval record present (716d177); `uv.lock` did not exist before that commit (lock created after) - PASS
- Tracer: `uv.lock` committed; `git status --porcelain uv.lock` empty - PASS
- Tracer: `uv sync --frozen --group dev` exit 0 - PASS
- Tracer: `grep -c -e tenacity -e prometheus -e respx pyproject.toml` = 0 - PASS
- Tracer: `[project.urls]` uses `swcstudiospace/PumpGrok` (git origin) - PASS
- Tracer: `uv run python -c "import sys; print(sys.version)"` reports 3.12.3 - PASS
- Makefile: `make -n lint typecheck test audit` expands to section 6 commands - PASS
- Makefile: recipes are tab-indented (no space-indented recipe lines) - PASS
- `tests/test_tools_cli.py` passes unmodified (`uv run pytest -q tests/test_tools_cli.py`, exit 0) - PASS (`git status` shows the file unchanged)
- `make lint typecheck test audit` full run with exit 0 - NOT RUN here; the plan's success criteria defer the full gate to plan 01-09.

## Next Phase Readiness
- Toolchain is in place for 01-02 onward: `uv sync --frozen --group dev` works from the lock.
- `pumpgrok.cli:main` is declared but not yet implemented (plan 01-08); `pumpgrok` console script will not run until then.
- Full `make lint typecheck test audit` run is for the phase gate (01-09). Note: the lint and typecheck results over the already-committed `src/pumpgrok/{config,core,ledger}` code are unknown until that run.

---
*Phase: 01-foundation*
*Completed: 2026-10-21*
