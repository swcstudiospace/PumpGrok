---
phase: 01-foundation
plan: 07
subsystem: contracts
tags: [contracts, tool-rosters, json-schema, prompts, agents, generators, g-7]

# Dependency graph
requires:
  - phase: 01-04
    provides: "18 strict R32 pydantic event models and event_json_schemas() in src/pumpgrok/ledger/events.py"
  - phase: 01-06
    provides: "G-1..G-7 gates, ownership.yaml with the ten seats, and the G-7 roster rules this plan must satisfy"
provides:
  - "contracts/events/<snake>.schema.json x18, generated from ledger/events.py by scripts/generate-event-schemas.py (byte-stable, --check mode)"
  - "contracts/tool-rosters/_core.yaml (desk.* core eight) and ten seat rosters at R35 sizes, dotted catalog names, G-7 green"
  - "prompts/_shared/core-directives.xml and ten prompts/bot-0N-<seat>.xml sources, seeded from agents/*.md bodies (signal and journal authored from ROSTER 5.9/5.10)"
  - "prompts-assembled/<SEAT>.xml x10 with the effective roster, zero placeholders"
  - "scripts/assemble-prompts.sh and scripts/generate-templates.py, both with --check; agents/signal.md and agents/journal.md"
affects: [01-08, 01-09]

# Actuals (#2632)
actuals:
  tokens: n/a
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Event schemas are generated from the pydantic models; the committed JSON is never hand-edited"
    - "Shared constitution is included by reference (<core ref/>) from one source, expanded in place by both generators"
    - "Generators validate roster and skills before writing anything; --check diffs and flags stale files"

key-files:
  created:
    - scripts/generate-event-schemas.py
    - scripts/prompt_sources.py
    - scripts/assemble-prompts.sh
    - scripts/generate-templates.py
    - contracts/README.md
    - contracts/changes/README.md
    - contracts/events/*.schema.json (18)
    - contracts/tool-rosters/_core.yaml
    - contracts/tool-rosters/bot-00-chief.yaml
    - contracts/tool-rosters/bot-01-scout.yaml
    - contracts/tool-rosters/bot-02-risk.yaml
    - contracts/tool-rosters/bot-03-whale.yaml
    - contracts/tool-rosters/bot-04-sniper.yaml
    - contracts/tool-rosters/bot-05-rug.yaml
    - contracts/tool-rosters/bot-06-exit.yaml
    - contracts/tool-rosters/bot-07-shill.yaml
    - contracts/tool-rosters/bot-08-signal.yaml
    - contracts/tool-rosters/bot-09-journal.yaml
    - prompts/_shared/core-directives.xml
    - prompts/bot-00-chief.xml ... prompts/bot-09-journal.xml (10)
    - prompts-assembled/CHIEF.xml ... JOURNAL.xml (10)
    - agents/signal.md
    - agents/journal.md
  modified:
    - agents/exit.md
    - agents/shill.md
    - Makefile

key-decisions:
  - "Seat names follow ownership.yaml and ROSTER section 7: bot-05-rug, bot-06-exit, bot-07-shill. The plan's bot-05-exit, bot-06-shill and bot-07-social were not used anywhere."
  - "The security constitution (identical 11-line header in all eight existing bodies) lives once in core-directives.xml and is included in place. Seat bodies otherwise carry the existing prose verbatim; six of eight agent files regenerate byte-identical."
  - "agents/exit.md and agents/shill.md move from seat: Trading Floor to seat: DM, per ROSTER 5.7/5.8 and the ROSTER section 9 rule that seat becomes Trading Floor or DM. Frontmatter keys are unchanged."
  - "Seat tool grants follow ROSTER section 6 exactly: 7/7/7/6/7/7/7/3/6/7 own tools, effective 15/15/15/14/15/15/15/11/14/15. Sniper exec tools are buy-only and exit exec tools are sell-only; each seat's journal.append note_kind is restricted to the kinds ROSTER allows it."
  - "No placeholder source exists in Phase 1. The precedent DESK_* and SEAT_UUID substitutions are dropped rather than filled. The assembler and generator fail closed on any {{...}} that remains."
  - "Every paper-write tool is kind write with g6, approval_id and rollback_plan required, because the ported G-7 write rule demands it. TOOL_CATALOG section 10 tags only exec.place and exec.cancel with g6. See Deviations, item 5."

patterns-established:
  - "Generated artifacts (events schemas, agents, assembled prompts) each have a --check mode and are wired into make check"
  - "Roster files are the machine contract; assembled prompts list each seat's effective roster so prompt and gateway cannot disagree silently"

requirements-completed: ["FOUND-008", "FOUND-009"]

# Metrics
duration: not measured
completed: 2026-10-21
status: complete
---

# Phase 1: Foundation Plan 07 Summary

**18 generated R32 event schemas, core-eight plus ten seat rosters at R35 sizes passing G-7, and a prompt pipeline that assembles and regenerates every agent with no placeholder left**

## Performance

- **Tasks:** 3 planned (tracer, rosters, prompts and scripts)
- **Commits:** 5 (listed below)
- **Files:** 61 changed from the pre-plan base (2973d47): 5681 insertions, 2 deletions

## Accomplishments

- `scripts/generate-event-schemas.py` writes 18 `contracts/events/<snake>.schema.json` from `event_json_schemas()`. `--check` is byte-exact and fails on drift or a stale file.
- `contracts/tool-rosters/`: `_core.yaml` holds the `desk.*` core eight. Ten seat files hold their own tools and set `core: true`. Every name is a dotted catalog id. No live-write tool. Every write tool is g6 with `approval_id` and `rollback_plan` required.
- `prompts/` holds the shared constitution and ten seat sources. `scripts/assemble-prompts.sh` writes `prompts-assembled/<SEAT>.xml` with the seat's effective roster. `scripts/generate-templates.py` regenerates `agents/<seat>.md`. Both have `--check`.
- `agents/signal.md` and `agents/journal.md` are generated from new seat sources written from ROSTER 5.9 and 5.10.
- `make check` runs the event-schema `--check` alongside the two existing generator checks.

## Task Commits

1. **Tracer: 18 event schemas, READMEs** - `8418167` (feat)
2. **Ten seat rosters plus _core at R35 sizes** - `5547c92` (feat)
3. **Prompt sources, assembler and agent generator** - `e4c2bb4` (feat)
4. **Lint fixes in prompt and agent generators** - `be69518` (style)

**Plan metadata:** this SUMMARY commit (docs(01-07)).

## Files Created/Modified

See `key-files` above. Verification outputs are under Self-Check.

## Decisions Made

See `key-decisions` above.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Seat names in the plan's file list were wrong**
- **Found during:** Task 2 (rosters) and Task 3 (prompts)
- **Issue:** The plan named `bot-05-exit`, `bot-06-shill` and `bot-07-social`, which are not seats in ownership.yaml or ROSTER section 7.
- **Fix:** Used the real seats. Mapping, for every file the plan listed:
  - `contracts/tool-rosters/bot-05-exit.yaml` became `bot-05-rug.yaml`
  - `contracts/tool-rosters/bot-06-shill.yaml` became `bot-06-exit.yaml`
  - `contracts/tool-rosters/bot-07-social.yaml` became `bot-07-shill.yaml`
  - `prompts/bot-05-exit.xml` became `bot-05-rug.xml`
  - `prompts/bot-06-shill.xml` became `bot-06-exit.xml`
  - `prompts/bot-07-social.xml` became `bot-07-shill.xml`
- **Files modified:** all of the above
- **Verification:** `check_ownership.py --validate-manifest` exits 0; G-7 passes.
- **Committed in:** `5547c92`, `e4c2bb4`

**2. [Rule 3 - Blocking] G-7 could not pass until rosters existed**
- **Found during:** Task 1 (tracer verify)
- **Issue:** G-7 fails with "roster directory not found" until task 2 lands. The tracer's `<verify>` therefore could not pass in its own commit.
- **Fix:** Committed the tracer (schemas and READMEs) first and ran G-7 after the rosters. G-7 is green at the end.
- **Verification:** `python3 ci/gates/check_desk_integrity.py --repo .` exits 0.

**3. [Rule 2 - Missing] Schema generator and shared loader were not in the plan's file list**
- **Found during:** Task 1 and Task 3
- **Issue:** `events.py` exposes `event_json_schemas()` but has no entry point. The two prompt generators would otherwise duplicate the loader.
- **Fix:** Added `scripts/generate-event-schemas.py` (the entry point, with `--check`) and `scripts/prompt_sources.py` (shared stdlib loader used by both generators). Added one `make check` line for the schema check.
- **Committed in:** `8418167`, `e4c2bb4`, `5547c92`

**4. [Rule 1 - Bug] Frontmatter broke on the JOURNAL description**
- **Found during:** Task 3 (generator round-trip check)
- **Issue:** The description contains `: `, which an unquoted YAML scalar cannot hold.
- **Fix:** Frontmatter scalars are emitted through `yaml.safe_dump`. They stay plain, byte-identical to the existing files, unless YAML needs quotes. `writes_to_exchange` is passed as a real bool so it stays plain `false`.
- **Committed in:** `e4c2bb4`

### Items for review (not auto-fixed; decisions taken)

**5. Write-tool gating is broader than TOOL_CATALOG section 10.**
The ported G-7 rule requires every `kind: write` tool to carry `g6` and to require `approval_id` and `rollback_plan`. TOOL_CATALOG section 10 tags only `exec.place` and `exec.cancel` with g6. I followed the G-7 port, since the gate is binding and must not be weakened. Consequence: `journal.append`, `notify.alert`, `journal.render_report`, `risk.kill_switch` and the three `desk.*` writes now require an approval reference and a rollback description even though they are not trade actions. The schema text says so. This is worth a decision before 01-08 consumes these rosters.

**6. Agent frontmatter `seat:` changed for two existing agents.**
`agents/exit.md` and `agents/shill.md` now read `seat: DM`, per ROSTER 5.7 and 5.8. Keys are unchanged; this is a value change.

**Total deviations:** 4 auto-fixed (2 blocking, 1 missing critical, 1 bug), plus 2 review items above.
**Impact on plan:** None on the acceptance criteria. The gate was not weakened, and no live-write tool or placeholder was introduced.

## Issues Encountered

- 01-06 recorded the G-7 failure caused by a missing `contracts/tool-rosters/`. That is resolved: G-7 now passes.
- `ruff format` was not run, per the wave rules. `ruff check --no-fix` and `ruff format --check` were run read-only on the three new Python files and are clean.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 01-08 and 01-09 can consume `contracts/tool-rosters/` and `prompts-assembled/`.
- 01-09 rewrites `scripts/check.sh` and will see ten agents, not eight.
- The review item in deviation 5 should be settled before the gateway enforces write approvals.

## Self-Check: PASSED

Verification, run after the final commit:

- `python3 ci/gates/check_desk_integrity.py --repo .`: exit 0 (`G-7 PASS — desk integrity: 10 rosters, 0 packs, 21 prompt files checked`)
- `bash scripts/assemble-prompts.sh --check`: exit 0 (`assembled prompts clean: 10 prompts match prompts/`)
- `python3 scripts/generate-templates.py --check`: exit 0 (`agents clean: 10 agent files match prompts/`)
- `uv run python scripts/generate-event-schemas.py --check`: exit 0 (`event schemas clean: 18 schemas match ledger/events.py`)
- `grep -rn '{{' prompts-assembled/ agents/`: no matches
- `grep -rn -i 'lite-api\|pumpportal' prompts/ prompts-assembled/ agents/`: no matches
- `./scripts/check.sh`: exit 0 (`ok: 23 skills, 10 agents`)
- `python3 ci/gates/check_ownership.py --validate-manifest`: exit 0 (314 tracked paths, one owner each)
- `agents/chief.md`: unchanged in git (frontmatter byte-preserved). Six of eight existing agents regenerate byte-identical; `exit.md` and `shill.md` differ only in the `seat:` line.
- Roster sizes checked against ROSTER section 6: 15/15/15/14/15/15/15/11/14/15 effective.
- Every roster tool name appears in TOOL_CATALOG.md.
- Commits present in `git log`: `8418167`, `5547c92`, `e4c2bb4`, `be69518`.

---
*Phase: 01-foundation*
*Completed: 2026-10-21*
