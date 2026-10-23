---
phase: 01-foundation
plan: 11
subsystem: gates
tags: [g4, g7, contracts, rosters, tool-catalog, acknowledgement, approval-gating, r56, r57]

# Dependency graph
requires:
  - phase: 01-10
    provides: "mushroom-free gate tree with R58/R60 conformance (ApprovalRecorded.token_units, regenerated schemas)"
provides:
  - "G-4 check_change_doc with the R56 acknowledger rule (consumers minus proposer, proposer acks ignored, presence-not-authorship)"
  - "G-7 check_tool with the R57 declared-gate rule (g6 demands approval_id plus rollback_plan; no blanket kind-write rule)"
  - "Roster g6 declarations equal to TOOL_CATALOG declarations (g6 on exec.place and exec.cancel only)"
  - "R56 semantics and the authorship residual limit stated in the cross-bot protocol, SECURITY.md and quality-gates.md"
affects: [phase-02-restructure]

# Actuals
actuals:
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns: ["required-acknowledger set as consumers minus proposer with proposer acks filtered before both ack scans", "declared-gate enforcement: gate tag in roster input schema must be backed by required fields", "catalog-derived parity test (YAML examples plus the section 10 gate-tag sentence)"]

key-files:
  created: []
  modified:
    - "ci/gates/check_contracts.py"
    - "ci/gates/check_desk_integrity.py"
    - "ci/tests/test_gates.py"
    - "docs/cross-bot-protocol.md"
    - "SECURITY.md"
    - "docs/quality-gates.md"
    - "contracts/tool-rosters/_core.yaml"
    - "contracts/tool-rosters/bot-00-chief.yaml"
    - "contracts/tool-rosters/bot-01-scout.yaml"
    - "contracts/tool-rosters/bot-02-risk.yaml"
    - "contracts/tool-rosters/bot-03-whale.yaml"
    - "contracts/tool-rosters/bot-07-shill.yaml"
    - "contracts/tool-rosters/bot-08-signal.yaml"
    - "contracts/tool-rosters/bot-09-journal.yaml"
  deleted: []

key-decisions:
  - "The 'no consumers resolved' error fires on the pre-subtraction derivation: a surface whose only consumer is the proposer yields an empty required set that passes, not an error."
  - "The R57 parity test pins the derived catalog set to exactly {exec.place, exec.cancel} so a catalog edit that adds g6 fails loudly and forces a deliberate roster update."
  - "Roster approval_id/rollback_plan schema properties stay optional; only the g6 tag and the input.required entries were removed."
  - "run() takes rosters and packs/prompts/templates keyword-only after repo+rosters_dir so PLR0917 is fixed without a calling-convention overhaul (main already used keywords; two test call sites updated)."

requirements-completed: ["FOUND-006", "FOUND-007", "FOUND-010", "SEC-001"]

# Coverage metadata
coverage:
  - id: T1
    description: "R56 acknowledger rule in G-4 with tests both directions and doc residual statements"
    requirement: "FOUND-006"
    verification:
      - kind: other
        ref: "python3 -m pytest ci/tests/ -q (exit 0)"
        status: pass
      - kind: other
        ref: "uv run ruff check --select B905,E741,PLR0912,PLR0915,PLW1510 ci/gates/check_contracts.py ci/tests/test_gates.py (no issues)"
        status: pass
    human_judgment: false
  - id: T2
    description: "R57 declared-gate rule in G-7 with roster alignment and catalog parity test"
    requirement: "FOUND-010"
    verification:
      - kind: other
        ref: "python3 ci/gates/check_desk_integrity.py --repo . (G-7 PASS, 10 rosters)"
        status: pass
      - kind: other
        ref: "python3 -m pytest ci/tests/test_gates.py -q -k roster_g6_matches_catalog (exit 0)"
        status: pass
      - kind: other
        ref: "uv run ruff check --select PLR0912,PLR0917,PLW1510 ci/gates/check_desk_integrity.py ci/tests/test_gates.py (no issues)"
        status: pass
    human_judgment: false

# Metrics
duration: n/a
completed: 2026-10-21
status: complete
---

# Phase 1, Plan 11: R56/R57 gate conformance Summary

**G-4 now passes exactly when every required acknowledger except the proposer has acked (a proposer ack is ignored, never rejected), and G-7 enforces approval fields only on tools whose roster entry declares gates [g6], with rosters matching the catalog.**

## Performance

- **Duration:** n/a
- **Completed:** 2026-10-21
- **Tasks:** 2 of 2 executed
- **Commits:** 2 (plus this SUMMARY commit)

## Accomplishments

- `check_change_doc` derives the required set as `contract_consumers(surface)` minus `proposed_by` and drops proposer acks before both the breaking presence check and the non-breaking rejection scan; the gate verifies a truthy ack is present for every remaining consumer. No `--bot`, no seat comparison.
- `check_tool` enforces the declared-gate rule: `gates: [g6]` demands `approval_id` and `rollback_plan` in `input.required`; tools without g6 need no approval fields regardless of kind. Live-write tools stay refused outright by the `exec.live` prefix check.
- Roster g6 survives only on `exec.place` / `exec.cancel` (sniper, exit). Removed from 12 entries: `desk.memory_retain`, `desk.event_emit`, `desk.doctor` (core), `notify.alert` + `journal.append` (chief, journal), `journal.append` (scout, whale, shill, signal), `risk.kill_switch`, `journal.render_report`.
- The `test_roster_g6_matches_catalog` test derives the catalog g6 set from `docs/TOOL_CATALOG.md` (YAML example blocks plus the section 10 gate-tag sentence) and asserts per-entry equality across all eleven roster files.
- Protocol rule 4, SECURITY.md Gates section and the quality-gates G-4 row state the R56 wording and the residual limit (presence, not authorship; authorship evidenced by git history, reviewed by QUALITY).

## Task Commits

1. **Task 1: R56 contract-acknowledgement semantics in G-4 plus tests and docs** - `6af62c3` (fix)
2. **Task 2: R57 declared-gate rule in G-7 with roster alignment and tests** - `0d31c12` (feat)

## Files Created/Modified

- `ci/gates/check_contracts.py` - R56 helpers (`_required_acknowledgers`, `_visible_acks`, `_breaking_ack_problems`, `_non_breaking_rejection_problems`, `_version_bump_problems`, `_surface_coverage_problems`); B905/E741 fixes (modified)
- `ci/gates/check_desk_integrity.py` - `GATE_REQUIRED_FIELDS["g6"] = ["approval_id", "rollback_plan"]`, blanket kind-write block and `WRITE_REQUIRED_FIELDS` deleted, `_gate_field_problems` and `run()` section helpers extracted, `run()` dirs keyword-only (modified)
- `ci/tests/test_gates.py` - five R56 tests, `check=False` on both `subprocess.run` calls, rewritten g6 tests (`test_write_tool_without_g6_needs_no_approval_fields`, `test_g6_tool_must_require_approval_id`), `_catalog_g6_tool_names` helper plus parity test, keyword `run()` call sites (modified)
- `docs/cross-bot-protocol.md`, `SECURITY.md`, `docs/quality-gates.md` - R56 rewording plus residual limit (modified)
- Eight roster files - g6 tag and forced `input.required` entries removed (modified); sniper/exit/rug rosters intentionally untouched

## Decisions Made

- See key-decisions in the frontmatter.

## Deviations from Plan

**[Rename, behavior as specified] `test_write_tool_must_be_tagged_g6` renamed to `test_write_tool_without_g6_needs_no_approval_fields`** - Found during: Task 2.
Issue: the plan says to rewrite the test so a write without g6 passes; keeping a name that asserts the opposite (`must_be_tagged`) would misdescribe the new behavior.
Fix: renamed; the plan's literal `-k` verify string still selects the parity test and exits 0, and the full suite covers the renamed test.
Files modified: `ci/tests/test_gates.py`
Verification: `python3 -m pytest ci/tests/test_gates.py -q -k "roster_g6_matches_catalog or declared_gate or write_tool_must_be_tagged_g6"` exit 0; full suite exit 0
Commit: `0d31c12`

**Total deviations:** 1 test rename. No scope added beyond the plan's named files.

## Issues Encountered

- None. Both tasks' verify commands passed on the first full run after the edits; no auto-fix beyond the planned rewrites was needed.

## Verification (run on the final tree, after commit `0d31c12`)

| Command | Exit | Note |
|---|---|---|
| `python3 -m pytest ci/tests/ -q` | 0 | full gate suite green |
| `python3 ci/gates/check_desk_integrity.py --repo .` | 0 | G-7 PASS, 10 rosters, 21 prompt files |
| `uv run ruff check --select B905,E741,PLR0912,PLR0915,PLR0917,PLW1510` on the three files | 0 | All checks passed |
| `python3 -m pytest ci/tests/test_gates.py -q -k "roster_g6_matches_catalog or declared_gate or write_tool_must_be_tagged_g6"` | 0 | plan's literal filter |

## Self-Check: PASSED

- `git show --stat HEAD~2..HEAD` lists the Task 1 (5 files) and Task 2 (10 files) commits with no deletions.
- `grep -rn -- "- g6" contracts/tool-rosters/` returns only the four exec.place/exec.cancel entries.
- `test_roster_g6_matches_catalog` passes against the committed tree, so the committed rosters match the committed catalog.

## User Setup Required

None.

## Next Phase Readiness

- CR-01 is closed per R56 and the G-7 blanket kind-write rule is replaced per R57; no follow-up plans are needed for either rule.
- The parity test will fail loudly if a later plan adds g6 to a catalog tool without aligning the rosters (or vice versa).

---
*Phase: 01-foundation*
*Completed: 2026-10-21*
