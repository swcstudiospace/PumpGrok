---
phase: 05-hardening
plan: 08
subsystem: oracle-retirement
tags: [oracle-deletion, census, milestone-receipt, test-fixes, d4-gate, d6-rollover]
status: complete
commits:
  - 3d46332
  - 70a7df4
  - e3d7105
plan_head_before: 0f1d124
dependency_graph:
  requires: [05-02, 05-04, 05-07]
  provides: [oracle-deleted, milestone-receipt, green-full-suite]
  affects: []
tech_stack:
  added: []
  patterns: [pumpgrok-verb-docs, registry-tool-refs, exact-contract-pins]
key_files:
  created:
    - .receipts/bot-00-chief/complete-phase-5.json
  modified:
    - tests/test_tools_cli.py
    - tests/test_skip_cycle.py
    - tests/test_live_gate.py
    - tests/desk/test_doctor_and_once.py
    - tests/ledger/test_desk_bus_mirror.py
    - tests/safety/test_constitution_constants.py
    - tests/characterization/test_authority_check.py
    - tests/characterization/test_holder_check.py
    - tests/characterization/test_jupiter_quote.py
    - tests/characterization/test_priority_fee.py
    - tests/characterization/test_vendor_log.py
    - tests/tools/test_money_registry_tracer.py
    - src/pumpgrok/cli.py
    - docs/upgrade-plan-desk-v2.md
decisions:
  - "Census vocabulary is the port CLI (pumpgrok verbs, registry ids); skills point at schemas via `pumpgrok tools <id> --help` where no run verb exists."
  - "Stale test expectations from D4/D6/05-07 are pinned to the new exact contracts, never loosened."
  - "SC5 stays BLOCKED with verbatim 05-07 evidence; nothing invented."
metrics:
  duration: "1 session"
  tasks: 3
  commits_actual: 3
actuals:
  tokens: 60000
  tasks: 3
  commits: 3
---

# Phase 5 Plan 08: Oracle Deletion and Milestone Close Summary

One-liner: Root `tools/` oracle deleted at zero census hits (89 to 0) with the CLI
test migrated, requests dropped, receipt and 6.6 milestone report recorded, and the
full suite green including five root-caused test/product fixes.

## Tasks Completed

### Task 1: Migrate oracle-bound tests and drop requests (3d46332)

- `tests/test_tools_cli.py`: removed `TOOLS` root, `spec_from_file_location`
  loader, and the four oracle classes (`JupiterQuoteContract`,
  `FailClosedExitCodes`, `HermesScriptsExecutable`, `TicketHelperDocs`); kept
  `TestPaperRegistryPath`, `TestPaperFillPath`, `TestOperatorVerbs`,
  `TestCliRegressionSweep` and the approval-burst test untouched. Unused
  imports (`importlib`, `subprocess`, `sys`, `tempfile`, `unittest`, `mock`)
  pruned; `unittest.main` footer removed.
- Five characterization docstrings name the retired root oracle instead of live
  paths (imports already targeted the port); stale `tests/test_tools_cli.py:NN`
  line pointers replaced with the 05-08 retirement note.
- `tests/ledger/test_desk_bus_mirror.py`: file-path load replaced with a
  `_halt_flag` helper over the port's `desk_bus.HALT_RE`; docstring updated.
- `tests/safety/test_constitution_constants.py`: deleted `tools/desk_state.py`
  home dropped from the ticket-core tuple; `rglob` roots guarded with
  `path.exists()` so the missing `tools/` dir cannot raise.
- `requests` direct dev dep and its oracle comment removed from `pyproject.toml`;
  `uv.lock` relocked under uv 0.13.4 (`requests` persists only as a
  pip-audit/cachecontrol transitive dep; zero `import requests` in
  src/tests/ci/scripts).
- `tests/test_skip_cycle.py` (carry-over): 3 pre-existing failures root-caused.
  CLI replay ledgers now hold exactly JournalNote + the D6 DailyRollover, so the
  `[(1,)]` expectations went stale; `_replay_ledger_contract` pins type order,
  fixture day and `rollover_key`. The live test encoded the pre-D4 contract;
  it now pins the exact `mode_live ... [live] enabled is not true` line.
- `tests/tools/test_money_types.py` renamed to
  `tests/tools/test_money_registry_tracer.py` (carry-over collection issue, see
  Deviations).
- Rule 1 product fix: `src/pumpgrok/cli.py` referenced undefined `SEAT_RE` and
  `KillSwitch` (pre-existing at HEAD; every `--by human:*` / `killswitch clear`
  path raised NameError); now imported from `pumpgrok.risk.killswitch`.

Verify: `uv run --no-sync pytest -q tests/test_tools_cli.py
tests/characterization/ tests/tools/test_money_registry_tracer.py
tests/tools/test_verb_coverage.py tests/ledger/test_desk_bus_mirror.py
tests/safety/test_constitution_constants.py tests/test_skip_cycle.py` —
338 passed, 2 skipped (both pre-existing intentional R5 non-ports).

### Task 2: Census sweep and oracle deletion (70a7df4)

- Swept every census file to the port vocabulary: 7 skills, `skills/README`,
  `rules/pumpgrok-team.mdc`, `prompts/bot-01-scout.xml`, `agents/README`,
  `hermes/README`, both hermes scripts (verify script now smoke-checks
  `pumpgrok state status --seat chief` in a scrubbed mktemp dir; bootstrap
  creates the desk tree in bash mirroring `ensure_desk`), `scripts/README`,
  `SETUP.md`, `README.md`, `ARCHITECTURE.md` (Tools table rewritten to
  registry ids), 5 `src/pumpgrok` docstrings, `.planning/research/STACK.md`.
- `prompts-assembled/SCOUT.xml` and `agents/scout.md` regenerated via
  `scripts/assemble-prompts.sh` + `scripts/generate-templates.py` (one line
  each); `AGENTS.md` GSD lines mirror the STACK edits only (2 lines).
- Deleted `tools/` (8 modules, README, pycache) with no shim; `rmdir` after
  `git rm` since git leaves the empty dir behind.

Verify: census `rg -n --hidden -P ...` prints nothing (89 to 0);
`test ! -d tools` exit 0; `assemble-prompts.sh --check` and
`generate-templates.py --check` exit 0; `./scripts/check.sh` exit 0
(35 skills, 10 agents, 216 markdown files).

### Task 3: Milestone receipt, report and final verification (e3d7105)

- `.gitignore` exception tracks `.receipts/bot-00-chief/complete-phase-5.json`.
- `docs/upgrade-plan-desk-v2.md` 6.6 milestone report lists every SC command
  with real outcomes, the carry-over resolutions, and REVIEW items.
- Rule 1 test pins: `tests/test_live_gate.py` (D4 enabled-flag contract plus a
  positive `live_enabled=True` case; "9 of 9" refusal) and
  `tests/desk/test_doctor_and_once.py` (second documented warning shape
  `not served: health.port=0`, no network attempted).

Verify: SC3a loop + `./scripts/check.sh` exit 0; SC3b loop exit 0; checkpoint
smoke `uv run pumpgrok run --mode paper --once --replay
tests/fixtures/replay/smoke` exit 0 (`engine decision=skip
reason=data_unavailable`); `uv run pytest -q` exit 0 — 1529 collected,
1527 passed, 2 skipped (pre-existing intentional R5 non-ports).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `cli.py` used undefined `SEAT_RE` and `KillSwitch`.**
Found during: Task 1 verify (5 NameErrors in kept CLI suites).
Issue: names referenced but never imported (pre-existing at HEAD).
Fix: `from pumpgrok.risk.killswitch import SEAT_RE, KillSwitch` (no cycle;
killswitch imports stdlib only). Restored the accidentally dropped scheduler
import in the same edit.
Files: `src/pumpgrok/cli.py`.

**2. [Rule 1 - Bug] Duplicate test basename broke collection.**
Found during: carry-over collection investigation (`--no-sync` run errored
`import file mismatch`, exit 2).
Issue: `tests/tools/test_money_types.py` duplicated
`tests/safety/test_money_types.py` with no `__init__.py` anywhere, so
prepend-import mode collided order-dependently.
Fix: renamed to `tests/tools/test_money_registry_tracer.py` (matrix
references only the safety path; meta-test collects referenced files only).
Post-fix with-sync and `--no-sync` collects agree.
Files: `tests/tools/test_money_registry_tracer.py`.

**3. [Rule 3 - Blocking] Two test files loaded `tools/` by path and read it as data.**
Found during: Task 1 census (both match the literal pattern).
Issue: `test_desk_bus_mirror.py` exec'd `tools/desk_state.py`; the
constitution test asserted `tools/desk_state.py` as a ticket home and rglobbed
`tools/`. Both break on deletion.
Fix: port-reader helper + dropped home + `exists()` guard (details in Task 1).
Files: `tests/ledger/test_desk_bus_mirror.py`,
`tests/safety/test_constitution_constants.py`.

**4. [Rule 1 - Bug] D4-era gate tests and 05-07 doctor test encoded stale contracts.**
Found during: final full-suite runs.
Issue: `tests/test_live_gate.py` asserted row 1 met in live mode and "8 of 9";
`tests/desk/test_doctor_and_once.py` allowed only `not-yet-implemented`
warnings, but 05-07 probes emit `not served: health.port=0` warns.
Fix: pinned the exact D4 lines plus a positive `live_enabled=True` case;
pinned the second warning shape. No assertions loosened.
Files: `tests/test_live_gate.py`, `tests/desk/test_doctor_and_once.py`.

Orphaned-request note: `requests` remains in `uv.lock` only as a
pip-audit/cachecontrol transitive dependency. The plan acceptance (direct dep
gone, relock under 0.13.4, zero importers) is met.

## Known Stubs

None. No TODO/FIXME/placeholder added; deleted code leaves no shims.

## Threat Flags

None. No new network endpoints, auth paths, file access, or schema changes.
`pumpgrok state status` in the verify script runs scrubbed (no `PUMPGROK_*`
passthrough) in a temp dir to avoid `var/` side effects.

## Self-Check

- 05-08-SUMMARY.md: FOUND (this file)
- 3d46332, 70a7df4, e3d7105: FOUND in `git log`
- tools/: GONE (`test ! -d tools` exit 0, census empty)
- .receipts/bot-00-chief/complete-phase-5.json: FOUND and tracked
  (`git ls-files` lists it despite the `*.json` ignore)
- Final `uv run pytest -q`: exit 0 (1529 collected, 1527 passed, 2 pre-existing
  intentional skips)

## Self-Check: PASSED
