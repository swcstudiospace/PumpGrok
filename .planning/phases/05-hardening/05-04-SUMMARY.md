---
phase: 05-hardening
plan: 04
subsystem: testing
tags: [live-gate, risk-007, golive-003, static-scan, safety-invariants]

# Dependency graph
requires:
  - phase: 05-02
    provides: go_live runbook with the nine code-id preconditions
  - phase: 05-03
    provides: degradation suites and FixtureClock.jump backward move
provides:
  - LiveGate precondition 1 reads [live] enabled alongside effective mode
  - Nine-way isolated live-gate proof plus full RISK-007 scan in one owned file
  - Policy, matrix, and paper-engine citations repaired to real files and ids
affects: [05-05, 05-06, 05-07, 05-08, verify-work]

# Actuals (#2632)
actuals:
  tokens: 11634
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns: [evaluator-patch isolation proof for hard-coded-false gate rows, refusal-framed skill text scan]

key-files:
  created: []
  modified: [src/pumpgrok/execution/live/live_gate.py, src/pumpgrok/cli.py, tests/execution/test_live_gate_fails_fast.py, tests/safety/test_no_manipulation_tools.py, docs/RISK_POLICY.md, docs/SAFETY_INVARIANTS.md, docs/design/paper-engine.md]

key-decisions:
  - "LiveGate takes live_enabled (default False) and the CLI passes settings.live.enabled; no overlay edit needed"
  - "Evaluator-patch parametrisation is the approved proof for rows 5-9, which are hard-coded False"
  - "Skill wallet-UI text is allowed only on refusal-framed lines, never as an affirmative procedure"

patterns-established:
  - "Gate flag pattern: config-gated preconditions take an explicit keyword (default closed), wired at the CLI call site"
  - "Scan framing rule: forbidden-procedure text in skill docs must share its line with a refusal token"

requirements-completed: [RISK-007, GOLIVE-003]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "Live gate reads [live] enabled in precondition 1 and proves all nine preconditions independently"
    requirement: "GOLIVE-003"
    verification:
      - kind: unit
        ref: "tests/execution/test_live_gate_fails_fast.py#test_live_gate_fails_fast_per_precondition"
        status: pass
      - kind: unit
        ref: "tests/execution/test_live_gate_fails_fast.py#test_precondition_1_requires_live_enabled_flag"
        status: pass
    human_judgment: false
  - id: D2
    description: "Manipulation-tool scan covers social, notify allowlist sends, and browser-ops text"
    requirement: "RISK-007"
    verification:
      - kind: unit
        ref: "tests/safety/test_no_manipulation_tools.py#test_notify_posts_only_to_allowlisted_destinations"
        status: pass
      - kind: unit
        ref: "tests/safety/test_no_manipulation_tools.py#test_browser_ops_skill_has_no_posting_or_wallet_procedure"
        status: pass
    human_judgment: false
  - id: D3
    description: "Policy, matrix, and paper-engine cite real modules, real test files, and code precondition ids"
    requirement: "RISK-007"
    verification:
      - kind: other
        ref: "uv run pytest -q tests/safety/test_no_manipulation_tools.py tests/execution/test_live_gate_fails_fast.py"
        status: pass
    human_judgment: false

# Metrics
duration: 30min
completed: 2026-10-22
status: complete
---

# Phase 05 Plan 04: Live-Gate Proof and Boundary Docs Summary

**Gate precondition 1 now requires mode live AND [live] enabled, proven by nine isolated exit-3 cases; the manipulation scan spans social, notify, and browser-ops; policy and matrix cite real files and code ids.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-10-22T06:00:00Z
- **Completed:** 2026-10-22T06:32:06Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Precondition 1 reads `[live] enabled`: `LiveGate(mode, environ, root, live_enabled)` with row 1 met only when the effective mode is live AND the flag is true; `cli.py` passes `settings.live.enabled`.
- Nine-way isolated proof: `test_live_gate_fails_fast_per_precondition[*]` patches the evaluator to all-met-except-target and asserts exit 3 with exactly that id as the single `[ ]` line; aggregate header now `9 of 9`.
- Manipulation scan extended in the one owned file: roster YAML name scan, notify POST-target config-only plus social-endpoint literal scan with allowlist wiring check, browser-ops skill scan (no posting verbs; wallet UI only on refusal-framed lines).
- Docs repaired: `RISK_POLICY.md` points at `src/pumpgrok/core/risk_budget.py` and real test names; `SAFETY_INVARIANTS.md` INV-C-02 adopts code ids, INV-C-11 gains the `--serve` / `PUMPGROK_HEALTH__PORT` amendment, INV-R-20/INV-R-22 point at degradation tests and `FixtureClock.jump`, section 6 documents the pipe-in-code-span rule; `paper-engine.md` R21 row 1 and 6.6 amended per D1.

## Task Commits

Each task was committed atomically (TDD RED before GREEN for the behavior-adding task):

1. **Task 1 RED: row-1 enabled-flag tests plus nine-way proof** - `dcdac01` (test; RED evidence: `TypeError` on unknown `live_enabled` kwarg)
2. **Task 1 GREEN: gate reads enabled, CLI wires it, header 9 of 9** - `efd2985` (feat)
3. **Task 2 scan: full RISK-007 scan in the owned file** - `c66e568` (test)
4. **Task 2 docs: policy, matrix, and paper-engine repairs** - `d151b56` (docs)

**Plan metadata:** none (no plan-doc commit in this run)

## Files Created/Modified

- `src/pumpgrok/execution/live/live_gate.py` - `live_enabled` parameter, row-1 logic and reason strings, docstring R21 amendment
- `src/pumpgrok/cli.py` - passes `settings.live.enabled` into the gate
- `tests/execution/test_live_gate_fails_fast.py` - two row-1 tests, nine-way parametrised proof, `9 of 9` header
- `tests/safety/test_no_manipulation_tools.py` - extended stems, roster/notify/skill scans, completed docstring
- `docs/RISK_POLICY.md` - `core/risk_budget.py` home, real 4.4 test names and stem regex
- `docs/SAFETY_INVARIANTS.md` - code ids in INV-C-02, INV-C-11 serve rule, INV-R-20/INV-R-22 real tests, pipe rule
- `docs/design/paper-engine.md` - `[live] enabled` config key, R21 row 1, 6.6 serve bullet

## Decisions Made

- `LiveGate` takes `live_enabled: bool = False` (default closed) rather than reading settings itself, keeping the evaluator a pure function of explicit inputs; the CLI is the single wiring point. `LiveSettings.enabled` already existed and every overlay already ships `enabled = false`, so no settings or overlay edit was needed (plan-listed `settings.py` change was a no-op).
- Evaluator-patch parametrisation is the isolation proof for rows 5-9 because those rows are hard-coded `False`; documented in the test that row 8 stays structurally unmet and row 9 reads halt/kill/breaker state where readable.
- Skill wallet-UI scan uses refusal framing (forbidden text allowed only beside never/refuse/stop/hand/escalate/BLIND/cannot) because the skill legitimately names refusal scenarios; posting verbs use plain word matching after verifying no legitimate noun collides (bot roster mentions live in frontmatter, not procedures).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Restored lines dropped by the row-1 edit**
- **Found during:** Task 1 (Live gate reads enabled)
- **Issue:** The row-1 replacement edit clobbered the `env_enabled` lookup and `_paper_window` call, causing `NameError` across the suite.
- **Fix:** Re-added both lines after the mode-reason block; verified SC4a green.
- **Files modified:** src/pumpgrok/execution/live/live_gate.py
- **Verification:** `uv run pytest -q tests/safety/test_no_manipulation_tools.py tests/execution/test_live_gate_fails_fast.py` exits 0
- **Committed in:** efd2985 (part of task commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** No scope change. The fix restored planned behavior; no architectural decision was needed.

## Issues Encountered

- Intermediate `pytest | tail` invocations printed `No tests collected` while the same command redirected to a file showed all tests passing; treated as output-pipeline truncation, not a test problem. All acceptance evidence below comes from file-redirected runs.
- `settings.py` required no change: `LiveSettings.enabled: bool = False` was already present, so the plan-listed settings edit was confirmed unnecessary rather than skipped.

## Automated Verification

- SC4a `uv run pytest -q tests/safety/test_no_manipulation_tools.py tests/execution/test_live_gate_fails_fast.py`: exit 0, 27 passed.
- SC4b overlay loop (tomllib `live.enabled is False` for dev, paper, live): exit 0, all three overlays.
- Checkpoint smoke `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke`: exit 0.
- Id vocabulary check: all nine `PRECONDITION_IDS` appear verbatim in matrix INV-C-02 and in `docs/runbooks/go_live.md`.

## Known Stubs

None. No stubs, placeholders, or TODOs were added; scans assert non-vacuous fixture content (social dir, roster count, POST call sites, skill files).

## Threat Flags

None. No new network, auth, or file-access surface: the gate reads one more boolean from already-loaded settings, and the scan additions are test-only AST/text checks. `PUMPGROK_LIVE__ENABLED` as an env override of `[live] enabled` remains an explicit operator action at the process boundary, consistent with the T-05-09 mitigation.

## Deferred Follow-ups (out of plan scope, for later waves)

- Matrix rows outside this plan's list still cite planned-but-missing tests (INV-C-03 `test_adapter_precondition_always_unmet_in_this_release`, INV-C-04 `test_live_flag_requires_both_sources`, INV-C-09 `test_live_gate_refuses_replay_source` vs real `test_replay_ledger_is_refused_for_metrics`); owned by the matrix meta-test plan under D2.
- `docs/runbooks/go_live.md:35` ("flipping it without the R21 amendment changes nothing the gate reads") is now stale since the amendment landed; plan 05-04 forbade rewriting that file.

## Self-Check

- `src/pumpgrok/execution/live/live_gate.py`, `src/pumpgrok/cli.py`, both test files, and all three docs exist with the described changes: FOUND.
- Commits `dcdac01`, `efd2985`, `c66e568`, `d151b56` present in `git log`: FOUND.
- Result: PASSED.

## Next Phase Readiness

- RISK-007 and GOLIVE-003 evidence is green: SC4a, SC4b, and the paper smoke all exit 0.
- Remaining matrix repairs and the `test_invariant_matrix_tests_exist` meta-test belong to their own plan; this plan's rows are ready for it.

---
*Phase: 05-hardening*
*Completed: 2026-10-22*
