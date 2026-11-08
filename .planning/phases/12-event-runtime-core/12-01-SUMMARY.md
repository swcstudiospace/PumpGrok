---
phase: 12-event-runtime-core
plan: 01
subsystem: config
tags: [pydantic, settings, v4-skeleton]

requires: []
provides:
  - Ten off-by-default v4 settings sections appended after health
affects: [12-02, 12-03, 12-04, 12-05]

actuals:
  tokens: 0
  tasks: 2
  commits: 1

tech-stack:
  added: []
  patterns:
    - "New v4 section is one frozen class plus one appended Settings field"

key-files:
  created:
    - src/pumpgrok/config/sections/v4.py
    - tests/config/test_v4_settings_skeleton.py
    - tests/config/test_events_settings.py
    - tests/config/test_live_settings_caps.py
  modified:
    - src/pumpgrok/config/settings.py
    - tests/config/test_settings_surface_characterization.py

key-decisions:
  - "wake_mode literal is cadence only"
  - "sidecar_path default is var/desk/events.sqlite"
  - "PRE-v4 classes and digest map were not edited"

patterns-established:
  - "A new settings section defaults enabled false and allowlist empty"

requirements-completed: [PRC-11]

coverage:
  - id: D1
    description: "Ten v4 sections load off when absent from TOML"
    requirement: PRC-11
    verification:
      - kind: unit
        ref: "tests/config/test_v4_settings_skeleton.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Notional cap above 1 SOL still refuses without editing LiveSettings"
    requirement: PRC-11
    verification:
      - kind: unit
        ref: "tests/config/test_live_settings_caps.py"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-11-08
status: complete
---

# Phase 12 Plan 01: v4 settings skeleton Summary

**Ten frozen v4 settings sections load off, and a notional cap above 1 SOL still refuses.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-11-08T09:54:00Z
- **Completed:** 2026-11-08T09:57:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added `src/pumpgrok/config/sections/v4.py` with ten extra=forbid sections, each `enabled` false and `allowlist` empty.
- Appended those fields on `Settings` after `health` in the locked order.
- Kept `PRE_V4_FIELDS` and `PINNED_SECTION_DIGESTS` unchanged. The surface test now checks a prefix plus the ten-name suffix.
- `events.wake_mode` is `cadence` only. `events.sidecar_path` defaults to `var/desk/events.sqlite`.

## Task Commits

1. **Task 1 and Task 2** - `cbb1a76` (feat)

**Plan metadata:** `dcc4bd8` (docs)

## Files Created/Modified

- `src/pumpgrok/config/sections/v4.py` - ten off sections
- `src/pumpgrok/config/settings.py` - import and appended fields
- `tests/config/test_v4_settings_skeleton.py` - suffix and absent-TOML tests
- `tests/config/test_events_settings.py` - cadence and sidecar default
- `tests/config/test_live_settings_caps.py` - cap refusal
- `tests/config/test_settings_surface_characterization.py` - prefix assertion only

## Decisions Made

None - followed the plan. `PromotionSettings` has no interval field. `PaperFeesSettings.model` is `v1`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Commands

- `uv run pytest -q tests/config/test_settings_surface_characterization.py tests/config/test_v4_settings_skeleton.py tests/config/test_events_settings.py tests/config/test_live_settings_caps.py` exit 0 (10 passed)
- `uv run ruff check src/pumpgrok/config` exit 0
- `uv run mypy src/pumpgrok/config` exit 0

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Wave 2 can import the events section. `EVENTS_SIDECAR_PATH` in plan 12-02 must equal `EventsSettings.sidecar_path`. Later stores must read `settings.events.sidecar_path`, not a second hardcoded path.

---
*Phase: 12-event-runtime-core*
*Completed: 2026-11-08*
