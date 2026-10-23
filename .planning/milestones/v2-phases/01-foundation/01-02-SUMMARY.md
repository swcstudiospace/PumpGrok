---
phase: 01-foundation
plan: 02
subsystem: config
tags: [pydantic-settings, toml, startup-guards, paper-only]

# Dependency graph
requires: []
provides:
  - "Layered settings loader: CLI > PUMPGROK_* env > PUMPGROK_CONFIG > overlay > defaults"
  - "Startup refusal of forbidden names, unknown keys, key-bearing URLs (names only, exit 1 via ConfigError)"
  - "dev/paper/live overlays with [live] enabled = false; placeholder .env.example"
affects: [live-gate, cli, logging, replay, ledger]

# Actuals (#2632)
actuals:
  tokens: 6539
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: [pydantic-settings TomlConfigSettingsSource]
  patterns: [startup-guard scans before construction, loc-type-only error formatting]

key-files:
  created:
    - src/pumpgrok/config/settings.py
    - src/pumpgrok/config/overlays/dev.toml
    - src/pumpgrok/config/overlays/paper.toml
    - src/pumpgrok/config/overlays/live.toml
    - .env.example
    - tests/config/test_settings.py
    - tests/config/test_forbidden_keys.py
    - tests/config/test_secret_refusal.py
  modified: []

key-decisions:
  - "live.toml declares execution.mode live (live intent) with paper-equivalent risk and [live] enabled=false; the gate refuses until preconditions hold"
  - ".env.example omits the Grok section entirely (retired grok-4-fast/grok-4 names) and drops DATA__API_KEY plus the lite-api quote URL"
  - "Bare PUMPGROK_EXECUTION refused alongside PUMPGROK_EXECUTION__MODE so mode cannot enter via JSON section env"
  - "Missing PUMPGROK_CONFIG file is a startup error, not a silent skip"

patterns-established:
  - "Startup guards run in load_settings() over os.environ before any Settings construction; dotenv/file-secret sources excluded"
  - "All refusal and validation messages carry names/locations only; values never printed"

requirements-completed: [FOUND-004, STRUCT-008, SEC-002]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "Settings loader with defaults, mode precedence, overlays, nested overrides"
    requirement: "FOUND-004"
    verification:
      - kind: unit
        ref: "tests/config/test_settings.py (8 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Forbidden-name, unknown-key, URL-key, bad-type refusal without value echo"
    requirement: "SEC-002"
    verification:
      - kind: unit
        ref: "tests/config/test_forbidden_keys.py (14 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "STRUCT-008 invariant (no JitoConfig/wallet_private_key) and CLI secret refusal; overlays live-disabled; placeholder .env.example"
    requirement: "STRUCT-008"
    verification:
      - kind: unit
        ref: "tests/config/test_secret_refusal.py (4 tests)"
        status: pass
    human_judgment: false

# Metrics
duration: 35min
completed: 2026-10-21
status: complete
---

# Phase 01 Plan 02: Layered Settings Loader Summary

**pydantic-settings loader with CLI > env > PUMPGROK_CONFIG > overlay precedence, startup refusal of forbidden/unknown/key-bearing inputs (names only), and live-disabled overlays plus placeholder .env.example**

## Performance

- **Duration:** 35 min
- **Started:** 2026-10-21T02:20:00Z
- **Completed:** 2026-10-21T02:55:08Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- Fresh `load_settings()` resolves effective mode `paper`; `PUMPGROK_MODE` beats TOML `execution.mode`; init kwarg (CLI) beats both; `PUMPGROK_RISK__MAX_TRADE_FRACTION` overrides the nested default
- All six refusal behaviours hold with values never echoed: forbidden env names (exact `PUMPGROK_REPLAY__SEED` exemption), unknown `PUMPGROK_*` keys, `PUMPGROK_EXECUTION__MODE`, key-bearing URLs (`api-key=`/`key=`/`token=`), bad types reported as `(loc, type)` only
- Overlays complete with `[live] enabled = false` in all three; `PUMPGROK_CONFIG` overrides the overlay for the same key; model has no Jito/wallet material

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer loader skeleton** - `f4b44d5` (feat)
2. **Task 2: forbidden-name, unknown-key, URL-key refusal** - `ae3ac84` (test; guard code shipped in the Task 1 commit of the shared `settings.py`)
3. **Task 3: overlays, PUMPGROK_CONFIG last-wins, .env.example, STRUCT-008 proof** - `dc666fb` (feat)

## Files Created/Modified

- `src/pumpgrok/config/settings.py` - Settings, ConfigError, mask, guard scans, mode resolver, annotated settings_customise_sources
- `src/pumpgrok/config/overlays/{dev,paper,live}.toml` - profile overlays, `[live] enabled = false` in all three
- `.env.example` - placeholders only (no PumpPortal key, no lite-api URL, no wallet key, no Grok section)
- `tests/config/test_settings.py` - 8 loader/precedence tests
- `tests/config/test_forbidden_keys.py` - 14 refusal tests
- `tests/config/test_secret_refusal.py` - 4 STRUCT-008/CLI tests

## Decisions Made

- live.toml sets `execution.mode = "live"` (declares live intent so the gate has something to evaluate) while keeping paper-equivalent risk and `[live] enabled = false`
- Bare `PUMPGROK_EXECUTION` refused alongside `PUMPGROK_EXECUTION__MODE` (a JSON section value could otherwise smuggle mode in)
- Missing `PUMPGROK_CONFIG` path is a startup error; unreadable TOML is reported by filename with the exception type only

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CLI bare value attributed to its flag**
- **Found during:** Task 3 (secret-refusal tests)
- **Issue:** `refuse_cli_secrets(["--rpc", "https://...?api-key=x"])` labelled the bare URL `argv[1]` instead of the flag that carries it
- **Fix:** Bare matching args now attribute to the preceding `-` flag when present, else `argv[i]`
- **Files modified:** src/pumpgrok/config/settings.py
- **Verification:** `test_cli_flag_with_key_bearing_url_refused` passes
- **Committed in:** dc666fb (Task 3 commit; guard helper finalized there)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Cosmetic label fix, no scope change.

## Issues Encountered

- `uv run pytest -q tests/config/...` fails with `ModuleNotFoundError: No module named 'pumpgrok'` because the project has no `pyproject.toml`/installed package yet (plan 01-01 scope, halted for human approval). Ran the identical suites via system python with `PYTHONPATH=src`: **26 passed**. Also verified: `! grep -rn -e JitoConfig -e wallet_private_key src/pumpgrok` prints nothing (exit 1); `test ! -d config` passes (no root config dir); `mypy --strict src/pumpgrok/config/settings.py` passes with `--python-executable /usr/bin/python3` (bare `mypy` cannot see system dist-packages from its pipx venv).
- Sibling wave-1 files under `src/pumpgrok/core/` and `tests/core/` appeared during execution; left untouched. Untracked `__pycache__` dirs and `.planning/` scratch left alone (gitignore belongs to plan 01-01).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Settings loader ready as LiveGate input (plan 01-08) and CLI/doctor input; `load_settings()` is the entrypoint, `ConfigError` maps to exit 1
- Blocker for full `uv run` verification: plan 01-01 must land `pyproject.toml` + installed package first

## Self-Check: PASSED

- All 8 files exist on disk; commits f4b44d5, ae3ac84, dc666fb in `git log`

---
*Phase: 01-foundation*
*Completed: 2026-10-21*
