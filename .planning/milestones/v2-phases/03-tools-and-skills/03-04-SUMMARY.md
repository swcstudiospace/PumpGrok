---
phase: 03-tools-and-skills
plan: "04"
subsystem: least-privilege-rosters
tags: [botmanifest, least-privilege, r63, gateway-projection, cron-guard, g4]
requires:
- phase: 03-tools-and-skills plan 03
  provides: [all 37 catalog ToolSpecs with production factories]
provides:
- load_bot_manifests loader with fail-closed ten-seat contract
- 11 roster files with manifest blocks at v1.1.0 plus G-4 change document
- interfaces-4 least-privilege suite, R63 cron-seat guard, gateway projection units
affects: [03-05, 03-06, 03-07]
actuals:
  tokens: 19103
  tasks: 4
  commits: 6
  plan_head_before: 789f96f14c5e3d1371fe593e0bcded7dc962fba
tech-stack:
  added: []
  patterns: [loader-derived allowed_tools, single-source roster tools list, shared test registry harness]
key-files:
  created: [src/pumpgrok/core/manifests.py, tests/test_bot_manifests.py, tests/registry_harness.py, tests/test_registry_least_privilege.py, tests/safety/test_cron_seats_cannot_write.py, tests/test_gateway_projection.py]
  modified: [contracts/tool-rosters/bot-00-chief.yaml, contracts/tool-rosters/bot-01-scout.yaml, contracts/tool-rosters/bot-02-risk.yaml, contracts/tool-rosters/bot-03-whale.yaml, contracts/tool-rosters/bot-04-sniper.yaml, contracts/tool-rosters/bot-05-rug.yaml, contracts/tool-rosters/bot-06-exit.yaml, contracts/tool-rosters/bot-07-shill.yaml, contracts/tool-rosters/bot-08-signal.yaml, contracts/tool-rosters/bot-09-journal.yaml, contracts/tool-rosters/_core.yaml, contracts/changes/phase-3-seat-manifests.yaml, src/pumpgrok/cli.py, tests/test_forbidden_owners.py]
key-decisions:
- "Checkpoint pre-approved: user (ask: roster, Approve the additive version bump); proceeded without pausing"
- "allowed_tools derived by the loader from roster tools plus _core, never written in manifest blocks"
- "_paper fails closed with exit 1 on any paper trade (R63); approval-issue path is Phase 4"
- "Shill paper-write assertion is minus the shared core eight (core grants are by-design for every seat)"
requirements-completed: [TOOL-009, SKILL-003]
coverage:
- id: D1
  description: "Tracer: ten manifests load with no silent skip; chief resolves desk.brief; chief refused exec.place"
  requirement: "SKILL-003"
  verification:
  - kind: unit
    ref: "tests/test_bot_manifests.py#test_ten_manifests_load_with_expected_ids + test_chief_resolves_desk_brief + test_chief_cannot_resolve_exec_place"
    status: pass
  human_judgment: false
- id: D2
  description: "SKILL-003: R35 exact sizes, writes_to_exchange only sniper+exit, kill_switch only risk, notify.alert absent risk+rug, ledger_write absent everywhere, nine explicit R20 keys, non-empty forbidden"
  requirement: "SKILL-003"
  verification:
  - kind: unit
    ref: "tests/test_bot_manifests.py (14 tests)"
    status: pass
  human_judgment: false
- id: D3
  description: "TOOL-009 interfaces-4: live-write never resolvable with audit row, ceiling refusals, grant/spec equality, manifest subset, roster registration, journal-note/escalation-only writes"
  requirement: "TOOL-009"
  verification:
  - kind: unit
    ref: "tests/test_registry_least_privilege.py (14 tests)"
    status: pass
  human_judgment: false
- id: D4
  description: "R63/B2 both halves: READ ceiling refuses paper-write with exceeds_requested_max, PAPER_WRITE resolves (non-vacuous); CLI unknown approval exits 1 with no OrderPlaced; missing approval rejected"
  requirement: "TOOL-009"
  verification:
  - kind: unit
    ref: "tests/safety/test_cron_seats_cannot_write.py (7 tests)"
    status: pass
  human_judgment: false
- id: D5
  description: "Gateway projection units: effective roster equals YAML, transport map forward-built and injective over all 37 registry tools"
  requirement: "TOOL-009"
  verification:
  - kind: unit
    ref: "tests/test_gateway_projection.py (5 tests)"
    status: pass
  human_judgment: false
metrics:
  duration: 20min
  completed: 2026-10-21
  status: complete
---

# Phase 3 Plan 04: Seat Manifests and Least-Privilege Enforcement Summary

**Ten BotManifests load from roster files with least-privilege enforcement, the R63 cron-seat guard holds on both halves, and the gateway projection is unit-pinned in the root suite - 40 new tests green, full suite (681) green, G-4 and G-7 gates green.**

## Performance

- **Duration:** 20 min (first to last task commit, 13:02-13:22 UTC)
- **Started:** 2026-10-21T13:02:10Z
- **Completed:** 2026-10-21
- **Tasks:** 4
- **Files modified:** 20 (2 src, 11 rosters, 1 change doc, 6 tests)

## Accomplishments

- G-4 change document `contracts/changes/phase-3-seat-manifests.yaml` (B6a, v1.1.0, ten consumer acks pending, B3 reading, one-way reversibility, approval record)
- `load_bot_manifests` fails closed on missing blocks, seat/id mismatch, unknown files, and any count other than exactly ten; `effective_roster` plus forward-built `transport_map` helpers for TOOL-010
- All 11 roster files at v1.1.0; ten seat manifest blocks with ROSTER section 5 fields and nine explicit R20 keys (decimal strings, no float); `_core` version bump only
- R63 end to end: READ-ceiling refusal with `exceeds_requested_max`, PAPER_WRITE non-vacuity, CLI unknown-approval exit 1 with no `OrderPlaced`, missing approval rejected
- Ten manifests resolve through the real 37-tool registry shape; no LIVE spec in the real registry; probe confined to the test registry

## Task Commits

Each task was committed atomically:

1. **Task 1: Checkpoint roster manifest contract (one-way, APPROVED)** - `7bef9bc` (docs)
2. **Task 2: Tracer** - `2615031` (test, RED: loader missing); `e390d7c` (feat, GREEN: loader)
3. **Task 3: Roster manifest blocks + SKILL-003 (B6, R35)** - `4085f28` (feat, GREEN: 11 files)
4. **Task 4: Least-privilege + cron-seat + projection (interfaces 4, R63/B2)** - `c648441` (test, RED: CLI returned 5); `d3acc1f` (feat, GREEN: R63 rejection + forbidden-owners migration)

_TDD tasks carry RED then GREEN commits per the tdd execution flow._

## Files Created/Modified

- `src/pumpgrok/core/manifests.py` - loader plus `effective_roster`/`transport_map` (new)
- `contracts/tool-rosters/bot-*.yaml` (10) - additive `manifest:` blocks, v1.1.0 (tool names/grants unchanged)
- `contracts/tool-rosters/_core.yaml` - v1.1.0 only (not a seat, so no manifest block)
- `contracts/changes/phase-3-seat-manifests.yaml` - G-4 doc (new)
- `tests/test_bot_manifests.py` - tracer + SKILL-003, 14 tests (new)
- `tests/registry_harness.py` - shared 37-tool registry builder (new)
- `tests/test_registry_least_privilege.py` - interfaces-4, 14 tests (new)
- `tests/safety/test_cron_seats_cannot_write.py` - R63/B2, 7 tests (new)
- `tests/test_gateway_projection.py` - projection units, 5 tests (new)
- `src/pumpgrok/cli.py` - R63 fail-closed approval rejection (scoped edit)
- `tests/test_forbidden_owners.py` - desk paper-buy 5 to 1 migration (scoped edit)

## Decisions Made

- Checkpoint pre-approved by the user (`user (ask: roster, Approve the additive version bump)`); recorded in the change doc and proceeded without pausing. Any other checkpoint would have stopped.
- `allowed_tools` is derived by the loader from each roster's `tools:` plus `_core`, never written in the manifest block: one source of truth for tool names.
- `_core.yaml` gets the version bump but no manifest block: `BotManifest` requires a seat id and `_core` is shared.
- R20 fractions written as YAML strings (`"0.02"`) so pydantic keeps exact `Decimal` values; ints stay ints.
- `_paper` rejects every paper trade with exit 1 in Phase 3: no approval-issue path exists yet, so every presented approval is unknown. Phase 4 replaces the rejection with registry resolution.
- Shill paper-write assertion is minus the shared core eight: `memory_retain`, `event_emit`, `doctor` are granted to every seat by design, so the interfaces wording pins to outside-core grants.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] CLI approval rejection needs `src/pumpgrok/cli.py` (outside files_modified)**
- **Found during:** Task 4 (RED: desk paper buy returned 5, plan demands 1)
- **Issue:** Task action requires unknown-approval exit 1 and the forbidden-owners migration requires desk 5 to 1, but files_modified lists no CLI file
- **Fix:** Minimal fail-closed `_paper` rejection (9 lines + comment); no ledger path added, nothing else in CLI touched
- **Files modified:** src/pumpgrok/cli.py
- **Committed in:** d3acc1f

**2. [Rule 3 - Blocking] Shared registry builder as `tests/registry_harness.py` (new file, outside files_modified)**
- **Found during:** Task 4 setup
- **Issue:** Three suites need the identical 37-tool registry shape; triplicating ~90 lines is dead weight
- **Fix:** One helper module (builder + `resolve` with bound correlation); LIVE probe stays in the test module that needs it
- **Files modified:** tests/registry_harness.py
- **Committed in:** c648441

**3. [Rule 2 - Missing critical] Shill assertion reconciled with core grants**
- **Found during:** Task 4 (interfaces wording vs roster reality)
- **Issue:** Interfaces says shill's only paper-write grant is `journal.append`, but the core eight grant every seat three paper-write tools
- **Fix:** Assert `shill_writes - core == {"journal.append"}` with the reconciliation in the test docstring
- **Files modified:** tests/test_registry_least_privilege.py
- **Committed in:** c648441

**4. [Rule 1 - Bug] Unquoted colon in chief manifest purpose broke YAML**
- **Found during:** Task 3 (edit tool reported the syntax break)
- **Issue:** `purpose: Supervisor and process guardian: ...` has a colon-space inside a plain scalar
- **Fix:** Single-quoted the scalar; all 11 roster files re-validated as parseable
- **Files modified:** contracts/tool-rosters/bot-00-chief.yaml
- **Committed in:** 4085f28

### Intentionally unchanged (plan-listed, not needed)

- `tests/core/test_registry.py`: the research-3.5 retry split (write refuses attempts > 1, READ accepts) already landed in 03-01 (`test_write_retry_is_refused`, `test_read_retry_policy_validates`); no edit needed.
- `tests/safety/test_no_manipulation_tools.py`: 03-02 already delivered the non-vacuous SC4 guard per the interfaces scope; this plan's registrations do not touch its assertions.
- `tests/test_skill_manifests.py` does not exist yet (plan 03-06 owns it); the plan verification selector referencing it exits 4. Reported, not worked around.

### Process note (not a code deviation)

- The loader's fail-closed design means the tracer could only go green after the roster blocks existed, so verification ran after the roster commit rather than between the loader and roster commits. The loader's fail-closed behavior itself was verified first (it raised on the missing blocks). No plan content changed, only commit-time evidence order.

---

**Total deviations:** 4 auto-fixed (2 blocking, 1 missing-critical, 1 bug) plus 3 intentional no-changes with reasons.
**Impact on plan:** All required for correctness; no scope creep. No architectural changes (Rule 4 never triggered).

## Issues Encountered

- Two hashline appends landed inside test-file docstrings (anchor math on partially shown ranges); repaired by re-read plus targeted PUT; final files parse and the suites are green.
- `JournalAppendIn` requires `bot`: added the seat field to the I5 test inputs.
- `tests/` is not a package, so the shared harness is imported via a `sys.path` insert of the tests dir, matching the existing src-insert convention; no `__init__.py` files added.

## Verification evidence (all exit codes recorded)

- `uv run pytest -q tests/test_skill_manifests.py tests/test_bot_manifests.py` → exit 4 (`ERROR: file or directory not found: tests/test_skill_manifests.py`; 03-06 owns that file; bot suite run separately below)
- `uv run pytest -q tests/test_bot_manifests.py` → exit 0 (14 tests)
- `uv run pytest -q -k "least_privilege or gateway"` → exit 0 (19 tests)
- `python3 ci/gates/check_desk_integrity.py --repo .` → exit 0 (`G-7 PASS - desk integrity: 10 rosters, 0 packs, 21 prompt files checked`)
- `python3 ci/gates/check_contracts.py --base origin/main --change contracts/changes/phase-3-seat-manifests.yaml` → exit 0 (`G-4 PASS - phase-3-seat-manifests: non-breaking, v1.1.0, 0 acknowledgement(s)`)
- `uv run pytest -q` (full suite, once, for the shared cli.py change) → exit 0 (681 tests collected and passing)

## Known Stubs

None - no stubs, placeholders, or TODOs introduced. The `_paper` approval rejection names its Phase 4 successor in a code comment; it is an explicit fail-closed boundary, not a stub. The cron and least-privilege suites document the Phase 4 supervisor alert relay in test docstrings only.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: fail-closed tightening | src/pumpgrok/cli.py | `_paper` now refuses every paper trade with exit 1 (was exit 5 absent-verb for allowed seats); reduces accepted-state surface until Phase 4 approvals land |

No new trust boundaries: `manifests.py` reads the already-contracted roster YAML and validates through `BotManifest`; the LIVE probe is registered in a test-only registry and the vault test pins the real registry holds no LIVE_WRITE spec.

## Auth Gates

None - no authentication was required.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 03-05 consumes `effective_roster`/`transport_map` from `src/pumpgrok/core/manifests.py` for the gateway service; the root projection tests pin the contract it must serve.
- Plan 03-06 creates `tests/test_skill_manifests.py`; the joint selector in this plan's verification block will go green once that file exists (currently exit 4 on the missing file only).
- Blockers for the orchestrator: (a) G-4 acks from all ten seat consumers are PENDING (recorded in the change doc as `pending_acks`); only the user can collect them; (b) B9 ASSUMED curve layout still awaits user confirmation (unchanged by this plan).

---
*Phase: 03-tools-and-skills*
*Completed: 2026-10-21*

## Self-Check: PASSED

- All 6 created files present on disk (manifests.py, 4 test files, harness).
- All 11 modified roster files plus change doc, cli.py, and forbidden_owners present with expected content (YAML parses, grep counts).
- All 6 task commits present (`7bef9bc`, `2615031`, `e390d7c`, `4085f28`, `c648441`, `d3acc1f`); `git rev-list --count 789f96f..HEAD` = 6.
- Plan-level pytest exit 0 for all three gates (14 + 19 tests); full suite exit 0 (681); G-4 and G-7 PASS.
