---
phase: 03-tools-and-skills
plan: "07"
subsystem: operator-cli
tags: [tool-011, registry-wiring, json-default, hidden-verb, r63, b5-partial]
requires:
- phase: 03-tools-and-skills plan 03
  provides: [37 catalog ToolSpecs with production factories, NotYetImplementedAdapter]
- phase: 03-tools-and-skills plan 04
  provides: [ten BotManifests, R63 cron-seat guard, fail-closed paper rejection]
provides:
- build_operator_registry full 37-tool composition for operator verbs
- section-12 verbs as thin JSON registry wrappers with mapped exits
- hidden tools schema verb, JSON default with run/doctor exemptions
affects: [04-paper-trading]
actuals:
  tokens: 28000
  tasks: 3
  commits: 7
  plan_head_before: 70e8b71f15caa77c5b12dde169a2f0973a36a8eb
tech-stack:
  added: []
  patterns: [spec-driven input construction via resolved tool.spec, find-then-tail verb runner, intent-bearing not-yet-implemented envelope]
key-files:
  created: []
  modified: [src/pumpgrok/cli.py, src/pumpgrok/tools/__init__.py, tests/test_tools_cli.py, tests/test_forbidden_owners.py]
key-decisions:
- "Operator registry lives in tools/__init__ so cli.py holds zero tool-module imports"
- "desk seat acts under the chief manifest; full seat ids accepted (R63 control is registry plus approval)"
- "Find-first ordering: registry refusal precedes the approval gate, so I1 is observable per seat"
- "Only ledger-local single-tool verbs call through; network/multi-tool verbs find then exit 5"
- "Hidden tools verb routed outside argparse after SUPPRESS leaked the name into top help"
requirements-completed: [TOOL-011]
coverage:
- id: D1
  description: "Tracer: paper buy/sell resolve exec.simulate+exec.place through find; unknown approval fails closed exit 1 with JSON and zero OrderPlaced rows"
  requirement: "TOOL-011"
  verification:
  - kind: unit
    ref: "tests/test_tools_cli.py::TestPaperRegistryPath (5 tests)"
    status: pass
  human_judgment: false
- id: D2
  description: "Killswitch set/flatten/status and state status call through and print JSON; clear/halt-clear/autonomy record intent and exit 5; hidden tools schema prints the tool JSON schema"
  requirement: "TOOL-011"
  verification:
  - kind: unit
    ref: "tests/test_tools_cli.py::TestOperatorVerbs (13 tests)"
    status: pass
  human_judgment: false
- id: D3
  description: "Regression sweep: every section-12 verb prints JSON with its mapped exit; top help exits 0 with tools verb absent; paper help lists five flags; cli.py has no direct tool imports"
  requirement: "TOOL-011"
  verification:
  - kind: unit
    ref: "tests/test_tools_cli.py::TestCliRegressionSweep (27 tests)"
    status: pass
  human_judgment: false
metrics:
  duration: 1 session
  completed: 2026-10-21
  status: complete
---

# Phase 3 Plan 07: Operator Verbs Summary

**Every section-12 operator verb is a thin JSON wrapper over the 37-tool registry: paper buy/sell fail closed on unknown approvals (exit 1), killswitch/state call through where backends exist (exit 0), absent backends print the JSON envelope (exit 5), and the hidden `tools <id> --help` schema verb stays out of top-level help. Full suite green (704 passed).**

## Performance

- **Tasks:** 3 (tracer paper path, killswitch/state/tools verbs, regression sweep)
- **Commits:** 7 (3 test RED/fix, 3 feat/fix, 1 sweep tests; TDD per task)
- **Files modified:** 4 (2 src, 2 tests)
- **Verification:** all plan commands run; exit codes recorded below

## Accomplishments

- `build_operator_registry()` in `src/pumpgrok/tools/__init__.py`: full 37-tool composition mirroring the gateway/harness (refusing adapter, tmp-safe data dir, closed notifier), returning registry plus manifests plus HTTP client. CLI imports only this composition root.
- `_run_wired` runner in `src/pumpgrok/cli.py`: registry build, seat resolve, find every capability (I1), then a tail (call / approval-gate / exit-5). JSON envelope `{ok, code, message}` with the exit map 5/2/3/else-1; no tracebacks; no direct tool imports.
- Paper path: forbidden-seat filter kept, `--size-sol` Decimal boundary kept, find `exec.simulate` + `exec.place`, then unknown-approval fail-closed exit 1 with zero writes. `desk` acts under the chief manifest; full seat ids accepted so `bot-04-sniper` proves the approval gate is reachable and still refuses.
- Killswitch/state: `set`/`flatten` call `risk.kill_switch`, `status` and `state status`/`halt` call `risk.halt_status` (exit 0 JSON). `clear`, `halt --clear`, `autonomy`, `live confirm` record their parsed intent in the envelope and exit 5 (R22/R17/R21; Phase 4 backends).
- Multi-tool verbs (scout, risk, chief, rug, journal, ticket, report, audit, verify): resolve every catalog tool through find, then exit 5 without network calls (B5 accepted partial).
- Hidden `pumpgrok tools <id> --help` prints the tool JSON schema; routed outside argparse because `help=SUPPRESS` leaked the name into top-level help on this Python.
- JSON by default documented in top-level help; `run` and `doctor` stay text (exemptions).

## Task Commits

1. `f1b1f93` test(03-07): RED paper registry path and approval envelope
2. `399cbbe` test(03-07): restore redirect_stdout import dropped by header edit
3. `f1c7677` feat(03-07): wire paper buy/sell through operator registry
4. `05e0c95` test(03-07): RED killswitch/state/tools verbs and JSON default
5. `de628bc` feat(03-07): wire killswitch/state/tools verbs with JSON default
6. `e196a11` test(03-07): CLI regression sweep with JSON envelope on every verb
7. `46f7c67` fix(03-07): route hidden tools verb outside argparse

## Files Created/Modified

- `src/pumpgrok/tools/__init__.py` - `build_operator_registry` composition (new function)
- `src/pumpgrok/cli.py` - wiring core, paper/state/killswitch/tools handlers, parser flags
- `tests/test_tools_cli.py` - TestPaperRegistryPath, TestOperatorVerbs, TestCliRegressionSweep
- `tests/test_forbidden_owners.py` - desk expectation migrated to the registry JSON envelope

## Decisions Made

- Composition lives in `tools/__init__.py` (mirrors `register_read_tools` precedent) so `cli.py` passes the no-direct-tool-imports static test.
- `desk` maps to the chief manifest with a code comment; unknown seats are usage errors. Full seat ids are accepted, demonstrating the R63 layering (string filter vs registry vs approval).
- Find runs before the approval gate so I1 refusal is seat-observable; the approval check stays as the second gate for writer seats (reachable in Phase 4).
- Only ledger-local single-tool verbs call through. Network reads and multi-tool flows find-then-5; the bot-04-sniper approval test proves find really runs (only registry success reaches the gate).
- Bare `pumpgrok tools <id>` prints the schema like `--help`; no calling surface is invented in Phase 3.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Static guard rejects unseeded random.Random()**
- **Found during:** Task 1 GREEN verification (full suite)
- **Issue:** `_with_tools` and `build_operator_registry` used `random.Random()`; `test_src_pumpgrok_has_no_forbidden_primitives` bans construction outside `replay/rng.py`
- **Fix:** `make_rng()` in the builder, `make_rng(settings.replay.seed)` for CLI correlation ids
- **Files modified:** src/pumpgrok/cli.py, src/pumpgrok/tools/__init__.py
- **Committed in:** f1c7677 (amended in place before push of the task commit chain)

**2. [Rule 1 - Bug] help=SUPPRESS leaks the verb name into top-level help**
- **Found during:** Task 3 sweep (`test_hidden_verb_absent_from_top_help`)
- **Issue:** this Python renders the suppressed subparser row as `tools ==SUPPRESS==`
- **Fix:** removed the subparser; `tools` is routed by argv pre-scan only
- **Files modified:** src/pumpgrok/cli.py
- **Committed in:** 46f7c67

**3. [Rule 3 - Blocking] Overlapping hashline edits clobbered imports/constants**
- **Found during:** Task 1/2 GREEN verification (NameError collection failures)
- **Issue:** three edits dropped `CorruptFixture`, `setup_logging`, `RiskBudget`, and the capability tuples
- **Fix:** restored each with targeted edits and re-verified imports
- **Committed in:** f1c7677, de628bc, 46f7c67

### Intentionally unchanged (plan-listed, not needed)

- `tests/test_forbidden_owners.py` cron tests and `tests/safety/test_cron_seats_cannot_write.py` pass unchanged: sniper/exit refused, desk permission-denied, all exit 1 with no rows.

## Verification evidence (all exit codes recorded)

- `uv run pumpgrok paper buy --help | grep -E "ticket|mint|size-sol|slippage-bps|approval-id"` -> exit 0, all five flags
- `uv run pumpgrok killswitch clear --help | grep -E "by|reason"` -> exit 0, `--by`/`--reason`
- `uv run pumpgrok tools exec.quote --help | head -5` -> exit 0, schema JSON with `input_schema.properties`
- `uv run pumpgrok --help | grep -c "  tools "` -> 0 (hidden verb absent)
- `uv run pumpgrok scout discover >/dev/null` -> exit 5 with JSON envelope
- `uv run pumpgrok killswitch set --reason probe >/dev/null` -> exit 0 (writes gitignored var/desk ledger)
- `uv run pumpgrok --help >/dev/null` -> exit 0
- `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` -> exit 0 (`engine decision=skip`)
- `! grep -rnE "\b(post|put|patch|delete)\b|method=['\"](POST|PUT|PATCH|DELETE)" src/pumpgrok/tools/social/` -> clean (ROADMAP SC4 social half)
- `uv run python -m pytest tests/ -v` -> 704 passed (full suite; `-q` collection flakes in this sandbox, `-v` runs used)
- `uv run python -m pytest tests/test_tools_cli.py tests/test_forbidden_owners.py -v` -> 80 passed

Note: bare `uv run pytest -q <file>` intermittently reports "No tests collected" in this sandbox while `-v` runs of the same selection pass; retried with backoff. The `-v` runs above are the recorded evidence.

## Known Stubs

None - no stubs, placeholders, or TODOs introduced. The find-then-5 verbs and human-only intent envelopes name their Phase 4 successors (PaperAdapter, RiskEngine, supervisor orchestration, ledger human-only writes) in code comments; these are explicit B5/A3 accepted partials, not stubs.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: approval-gate ordering | src/pumpgrok/cli.py | find() precedes the approval check so I1 is observable; writer seats reaching the gate still fail closed exit 1 with no write (R63) |

No new trust boundaries: registry grants plus the approval record remain the control; `--seat` stays a policy filter (T-03-07-01). Error output is code+message JSON only (T-03-07-03). Money stays Decimal-in at the boundary (T-03-07-02). No tool logic in the CLI (T-03-07-SC).

## Auth Gates

None - no authentication was required.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 4 consumes `build_operator_registry` for the supervisor loop; only the adapter (`NotYetImplementedAdapter` -> `PaperAdapter`) and limits checker (`_refuse_all` -> RiskEngine) need swapping.
- Paper `use` tail is the hook for approval consume-and-order (decision_id minting noted at the call site, R23).
- Human-only verbs carry machine-readable intent envelopes ready for the Phase 4 ledger writes.
- Blocker for orchestrator: B5 full verb coverage stays partial until Phase 4 backends land (A3 accepted).

---

*Phase: 03-tools-and-skills*
*Completed: 2026-10-21*

## Self-Check: PASSED

- All modified files present with expected content (builder, wiring, 45 new tests).
- All 7 task commits present (`git rev-list --count 70e8b71..HEAD` = 7).
- Plan-level pytest gates green (80 targeted, 704 full suite); replay checkpoint exit 0; help/schema verifications exit 0.
