# Phase 12 Plan Check

**Phase:** 12-event-runtime-core
**Plans checked:** 5
**Status:** ISSUES FOUND
**Issues:** 3 blocker(s), 7 warning(s), 2 info

## ISSUES FOUND

**Phase:** 12-event-runtime-core
**Plans checked:** 5
**Issues:** 3 blocker(s), 7 warning(s), 2 info

### Blockers -- these properties must hold

**1. [cross_plan_data_contracts] Events that differ only by a field excluded from the derived id are not required to append twice.**
- Plan: 12-03
- Task: 1
- Evidence: Plan 12-02 derives event_id as sha256 of canonical JSON of kind, entity_id, and payload only, and drops correlation_id before hashing. Plan 12-03 task 1 behavior and acceptance require two kill_switch events with the same payload and different occurred_at values to call append twice, and say dedup suppresses only the same derived id. Under the plan 12-02 rule those events share an id if entity_id is unchanged, so dedup suppresses the second append. models.py is not in plan 12-03 files_modified, so the later plan cannot add occurred_at to the id without leaving its file set, and doing so would contradict plan 12-02.
- Example fix (non-binding): State the two-append case as two different derived ids, and the one-append case as a repeated id. Do not put occurred_at into the hash.

**2. [scope_reduction] Locked EVT-06 is delivered as an unchanged ledger row count, not an optional callback count.**
- Plan: 12-03
- Task: 1
- Evidence: CONTEXT and ROADMAP criterion 5 require a second delivery to write no new ledger row. RESEARCH.md requires a tmp LedgerStore at a path other than the sidecar, idempotency_key equal to the derived event id, and store.read() length unchanged. Plan 12-03 must_haves and acceptance require only that a caller-supplied append callback is invoked once. The action says the test may use a tmp ledger. Every listed acceptance criterion can pass with no ledger row assertion. Product code still correctly must not import the paper ledger store class; that constraint does not replace the row check.
- Example fix (non-binding): Require the idempotency test to append into a tmp ledger that is not the sidecar and assert the row count is unchanged on the second delivery.

**3. [research_resolution] RESEARCH.md carries no unresolved open question.**
- Plan: null
- Evidence: 12-RESEARCH.md heading is "## Open Questions" with no (RESOLVED) suffix. Question 1 (exact EventKind strings) and question 2 (whether core/errors.py should gain types) have Recommendation text and no inline RESOLVED marker. The plans already choose the twelve snake_case kinds and events/errors.py, but the research section is still unmarked.
- Example fix (non-binding): Mark the section resolved with the choices the plans already lock.

### Warnings -- these properties should hold

**1. [requirement_coverage] EVT-08 first half, as stated in ROADMAP criterion 8, includes a quiescence result, not only equal bytes.**
- Plan: 12-05
- Task: 1
- Evidence: Plan 12-05 behavior and acceptance require two drains to return equal bytes, with zero skips, and no fixture_compat test. They do not require pending count 0. RESEARCH.md validation sketch asserts pending count 0 on both test_determinism and test_smoke_trading. ROADMAP criterion 8 says the quiescence loop holds.
- Example fix (non-binding): Add a pending-count-0 assertion to both drain behaviors. Do not add a fixture_compat test and do not call verify from the drain test.

**2. [requirement_coverage] EVT-02 persisted overflow is an acceptance criterion of the plan that wires the store.**
- Plan: 12-03
- Task: 1
- Evidence: Plan 12-02 proves the 1001st P1 event reaches an injected sink and claims EVT-02. Plan 12-03 action says wire the store as the P1 overflow sink. Its behavior, acceptance criteria, and verify commands never assert a sidecar dlq row for that overflow, and they do not re-run tests/events/test_bus_backpressure.py. A constructor change can drop the plan 12-02 contract without failing plan 12-03 verify.
- Example fix (non-binding): Accept a sidecar dlq row for the cap-plus-one P1 event, and include the backpressure test in the plan 12-03 verify.

**3. [verification_derivation] Editing the CLI parser still leaves live refusal at exit 3, and a plan verify can fail if it does not.**
- Plan: 12-03
- Task: 2
- Evidence: The phase goal says live stays exit 3. verbs_state.py is not in any files_modified list, and every plan forbids editing the live refusal path. Plan 12-03 still edits parsing.py and dispatch.py. Acceptance says live parsers are unchanged, but no automated command runs pumpgrok run --mode live --once and asserts exit 3. 12-VALIDATION.md row 12-05 claims that outcome for a command that does not run live mode.
- Example fix (non-binding): Add an automated exit-3 check that does not edit verbs_state.py.

**4. [verification_derivation] The smoke-10m events.hash pin is proven by running verify, not only by copying the pin text.**
- Plan: 12-05
- Task: 2
- Evidence: ROADMAP criterion 11 runs pumpgrok verify --fixture smoke-10m twice and requires the first 64-hex digest to equal b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d. Plan 12-05 task 2 greps CHANGELOG.md for four copied lines and does not run verify. Plan 12-04 import guard is necessary and is not that measurement. Replay sources and the pin file are absent from files_modified, which is the preservation mechanism, not the proof.
- Example fix (non-binding): Add the existing criterion 11 comparison to a late plan verify. Do not remeasure the pin and do not rewrite the pin file.

**5. [task_completeness] The commit that appends Settings fields does not leave the existing full-tuple pin assertion red.**
- Plan: 12-01
- Task: 1
- Evidence: Task 1 appends ten Settings fields and says to commit. Task 2, a later commit, is the only edit to test_top_level_fields_are_pinned_in_order. After the task 1 commit, tuple(Settings.model_fields) == PRE_V4_FIELDS fails.
- Example fix (non-binding): Land the prefix assertion in the same commit that appends the fields.

**6. [scope_sanity] Each plan stays within the per-plan file budget.**
- Plan: 12-02
- Evidence: Plan 12-02 files_modified lists 10 paths (warning threshold). Plan 12-03 lists 11 paths. Neither reaches the 15-file blocker line. Both plans have 2 tasks.
- Example fix (non-binding): Split only on a clean dependency edge. Do not split the sidecar store from the bus methods that call it.

**7. [pattern_compliance] Every new file names its closest PATTERNS.md analog, or cites RESEARCH.md if none exists.**
- Plan: 12-02
- Evidence: Plan 12-02 creates docs/design/events-grok.md without naming docs/design/paper-engine.md lines 12-18. It creates events/__init__.py without naming the replay/sources.py __all__ analog. The actions state the required contents, so this does not by itself miss the phase goal.
- Example fix (non-binding): Name those two analogs in the task read_first.

### Advisories (info)

**1. [task_completeness] A disabled events verb has a measurable refusal result.**
- Plan: 12-03
- Task: 2
- Evidence: Behavior says the verb refuses when events.enabled is false. Acceptance criteria do not name an exit code. RESEARCH assumption A8 allows either a hard refuse (test expects exit 1) or file recovery with no socket. The plan chose refuse without locking the result.
- Example fix (non-binding): Name the exit the disabled case must return, or adopt the A8 recovery reading and test that.

**2. [claude_md_compliance] Criterion 9's banned call spellings are absent from events source, including comments.**
- Plan: 12-02
- Evidence: ROADMAP criterion 9 greps src/pumpgrok/events for datetime.now, datetime.utcnow, time.time(, and time.sleep(. Plan 12-02 tells the executor not to call those helpers, and it writes the spellings in the action. No plan verify runs the grep. RESEARCH.md says a comment that contains those spellings fails the criterion grep.
- Example fix (non-binding): Forbid those spellings in comments under src/pumpgrok/events, and run the criterion 9 grep in a late verify.

### Structured Issues

```yaml
issues:
  - plan: "12-03"
    dimension: cross_plan_data_contracts
    severity: blocker
    required_property: "Events that differ only by a field excluded from the derived id are not required to append twice."
    description: "Plan 12-02 derives event_id from kind, entity_id, and payload only. Plan 12-03 task 1 requires two kill_switch events with the same payload and different occurred_at to call append twice. Those events share an id under the plan 12-02 rule when entity_id is unchanged, so dedup suppresses the second append. models.py is not in plan 12-03 files_modified."
    task: 1
    fix_hint: "State the two-append case as two different derived ids, and the one-append case as a repeated id. Do not put occurred_at into the hash."
  - plan: "12-03"
    dimension: scope_reduction
    severity: blocker
    required_property: "A second delivery writes no new ledger row, proven on a ledger file that is not the sidecar."
    description: "CONTEXT and ROADMAP criterion 5 require ledger rows unchanged. Plan 12-03 requires only that an append callback is invoked once, and says the test may use a tmp ledger. The ledger assertion is optional."
    task: 1
    fix_hint: "Require a tmp LedgerStore that is not the sidecar, idempotency_key equal to the derived event id, and an unchanged row count on the second delivery. Product events code still must not import the paper ledger store class."
  - plan: null
    dimension: research_resolution
    severity: blocker
    required_property: "RESEARCH.md carries no unresolved open question."
    description: "12-RESEARCH.md ## Open Questions has no (RESOLVED) suffix. The EventKind-strings question and the core/errors.py question have Recommendation text and no RESOLVED marker."
    fix_hint: "Mark the section resolved with the choices the plans already lock."
  - plan: "12-05"
    dimension: requirement_coverage
    severity: warning
    required_property: "EVT-08 first half includes a quiescence result, not only equal bytes."
    description: "Plan 12-05 acceptance requires equal bytes and zero skips. It does not require pending count 0. RESEARCH.md and ROADMAP criterion 8 require quiescence."
    task: 1
    fix_hint: "Assert pending count 0 on both drain tests. Do not add fixture_compat and do not call verify from the drain test."
  - plan: "12-03"
    dimension: requirement_coverage
    severity: warning
    required_property: "EVT-02 persisted overflow is an acceptance criterion of the plan that wires the store."
    description: "Plan 12-03 wires the store as the P1 overflow sink in the action only. Acceptance and verify do not assert a sidecar dlq row and do not re-run test_bus_backpressure.py."
    task: 1
    fix_hint: "Accept a sidecar dlq row for the cap-plus-one P1 event and include the backpressure test in the plan 12-03 verify."
  - plan: "12-03"
    dimension: verification_derivation
    severity: warning
    required_property: "Editing the CLI parser still leaves live refusal at exit 3, and a plan verify can fail if it does not."
    description: "Plan 12-03 edits parsing.py and dispatch.py. No automated command asserts pumpgrok run --mode live --once exits 3. verbs_state.py is not in files_modified."
    task: 2
    fix_hint: "Add an automated exit-3 check that does not edit verbs_state.py."
  - plan: "12-05"
    dimension: verification_derivation
    severity: warning
    required_property: "The smoke-10m events.hash pin is proven by running verify, not only by copying the pin text."
    description: "Criterion 11 compares pumpgrok verify --fixture smoke-10m output to b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d. Plan 12-05 task 2 only greps the copied CHANGELOG lines."
    task: 2
    fix_hint: "Add the existing criterion 11 comparison to a late plan verify. Do not remeasure or rewrite the pin file."
  - plan: "12-01"
    dimension: task_completeness
    severity: warning
    required_property: "The commit that appends Settings fields does not leave the existing full-tuple pin assertion red."
    description: "Task 1 commits the ten new fields. Task 2 is the only edit to the equality assertion. The characterization test is red between those commits."
    task: 1
    fix_hint: "Land the prefix assertion in the same commit that appends the fields."
  - plan: "12-02"
    dimension: scope_sanity
    severity: warning
    required_property: "Each plan stays within the per-plan file budget."
    description: "Plan 12-02 lists 10 files_modified. Plan 12-03 lists 11. Warning threshold is 10. Blocker threshold is 15. Both plans have 2 tasks."
    fix_hint: "Split only on a clean dependency edge. Do not split the sidecar store from the bus methods that call it."
  - plan: "12-02"
    dimension: pattern_compliance
    severity: warning
    required_property: "Every new file names its closest PATTERNS.md analog, or cites RESEARCH.md if none exists."
    description: "Plan 12-02 creates docs/design/events-grok.md without naming docs/design/paper-engine.md, and events/__init__.py without naming the replay/sources.py __all__ analog."
    fix_hint: "Name those two analogs in the task read_first."
  - plan: "12-03"
    dimension: task_completeness
    severity: info
    required_property: "A disabled events verb has a measurable refusal result."
    description: "The disabled-events behavior says the verb refuses, and acceptance does not name an exit code. A8 allows either hard refuse or socket-free recovery."
    task: 2
    fix_hint: "Name the exit the disabled case must return, or test the A8 recovery reading."
  - plan: "12-02"
    dimension: claude_md_compliance
    severity: info
    required_property: "Criterion 9 banned call spellings are absent from events source, including comments."
    description: "No plan verify runs the criterion 9 grep. Plan 12-02 action text names the banned spellings. A comment that copies them fails the grep."
    fix_hint: "Forbid those spellings in comments under src/pumpgrok/events and run the criterion 9 grep in a late verify."
```

### Coverage Summary

| Requirement | Plans | Status |
|-------------|-------|--------|
| PRC-11 | 12-01 | Covered, with a commit-order warning |
| EVT-01 | 12-02 | Covered |
| EVT-02 | 12-02, wiring in 12-03 | Partial: injected sink is tested; persisted overflow is not an acceptance criterion |
| EVT-03 | 12-02 | Covered |
| EVT-04 | 12-03 | Covered |
| EVT-05 | 12-03 | Covered |
| EVT-06 | 12-03 | Reduced: callback count, ledger row optional |
| EVT-07 | 12-03 | Covered |
| EVT-08 first half | 12-05 | Partial: equal bytes and zero skips; quiescence assertion absent; fixture_compat correctly excluded |
| EVT-09 | 12-04 | Covered as SourceStatus in the events package. Writing DegradedState would contradict the locked no-wiring decision. |
| EVT-14 | 12-02, 12-04 | Covered |
| EVT-10, EVT-12, EVT-13 | none | Correctly absent (Phase 14) |

### Plan Summary

| Plan | Tasks | Files | Wave | depends_on | Structure |
|------|-------|-------|------|------------|-----------|
| 12-01 | 2 | 6 | 1 | none | valid |
| 12-02 | 2 | 10 | 2 | 12-01 | valid |
| 12-03 | 2 | 11 | 3 | 12-02 | valid |
| 12-04 | 2 | 5 | 4 | 12-03 | valid |
| 12-05 | 2 | 3 | 5 | 12-04 | valid |

Dependency graph is acyclic. Wave numbers match the chain. depends_on ids use the repo NN-PP form. No same-wave pair, so no undeclared temporal coupling.

### Checked constraints that hold

- No plan lists a PRE-v4 section class in files_modified. Plan 12-01 forbids editing those classes, overlays, and the digest map. The surface edit is a prefix check only.
- No plan lists contracts/ in files_modified. Every plan forbids that edit.
- No plan wires the bus into supervisor, execution, engine, or the replay runner. Plan 12-04 tests that those roots, and verify/run parser construction, do not import the bus. degraded.py is not edited.
- Plan 12-03 refuses a resolved path equal to PAPER_LEDGER_PATH before connect. The sidecar is not the paper ledger. Product events code must not import the paper ledger store class.
- CHANGELOG.md is plan 12-05 task 2, owned by bot-09-journal, on bot-09-journal/phase-12-event-runtime. Task 1 forbids including that file in the risk commit. The four lines copy the known pins, including b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d. They do not remeasure.
- No plan adds mainnet, devnet, faucet, a 200 USD router, solders, solana, a socket client, or a Grok gateway. FaultyGrokTransport is a raising test fake. PromotionSettings has no 3600 interval. wake_mode stays cadence.
- Live enablement is not planned. The exit-3 proof gap is the warning above, not a planned live path.

### Other dimensions

- Dimension 7 Context compliance: locked decisions are otherwise honored. Deferred ideas are not tasks. Discretion (caps, TTLs, events/errors.py, module split) is used inside the recorded bounds. The EVT-06 reduction is the exception, filed above.
- Dimension 7b: no v1/stub reduction except the EVT-06 "may" ledger, filed as a blocker. "First half" of EVT-08 matches the phase boundary. fixture_compat is correctly deferred to Phase 14.
- Dimension 7c Architectural tier: PASS. Settings, catalog, lanes, drain, and SourceSupervisor stay in the library. DLQ and cursors stay in the sidecar. The CLI opens the sidecar only. DegradedState, the desk loop, and the Grok gateway are not assigned work.
- Dimension 8 Nyquist: VALIDATION.md exists. Every plan task has an automated command and a non-vacuous fails_when. No MISSING sentinel. No watch mode. No 3-task sampling gap. Probe severities were none (verify-path status not_applicable; failing-direction status ok). See table.
- Dimension 8 sampling-map drift is recorded here rather than as a plan-task fail: 12-VALIDATION.md row 12-02 runs tests/events/test_models_v4_kinds.py, which plan 12-04 creates. Row 12-03 runs lane and backpressure tests owned by plan 12-02. Row 12-05 claims live exit 3 for a command that does not run live mode. Execute-phase consumes PLAN.md verifies, which are internally consistent.
- Dimension 9: FAIL on the occurred_at / event_id contract, filed as the first blocker. Other shared values agree: sidecar path var/desk/events.sqlite, cadence-only wake_mode, tick mapped to curve_tick only inside the drain test, paper ledger path refused.
- Dimension 10: plans use pytest, uv, integer lamports, injected Clock, and seeded RNG. They do not add a package. No CLAUDE.md toolchain contradiction. The comment-spelling footgun is info.
- Dimension 11: FAIL, filed as the third blocker.
- Dimension 12: FAIL as warning 7. Production analogs used by the implementation tasks are cited. The design doc and package init omit their analog names.
- Verify-command path probe: 10 commands, severity none, status not_applicable. No finding.
- Failing-direction probe: 10 commands, severity none, status ok. Statements name non-zero exit, a 0 passed summary, or SKIPPED. No vacuous statement. No finding. pending_creation did not appear.
- No estimate blocks. Not a defect.
- gsd-tools verify.plan-structure: all five plans valid. Every task has files, action, verify, and done.

## Dimension 8: Nyquist Compliance

| Task | Plan | Wave | Automated Command | Failing Direction | Status |
|------|------|------|-------------------|-------------------|--------|
| Task 1 | 12-01 | 1 | uv run pytest -q tests/config/test_v4_settings_skeleton.py tests/config/test_events_settings.py tests/config/test_live_settings_caps.py | non-zero exit, or the summary line contains 0 passed | PASS |
| Task 2 | 12-01 | 1 | uv run pytest -q tests/config/test_settings_surface_characterization.py tests/config/test_v4_settings_skeleton.py tests/config/test_events_settings.py tests/config/test_live_settings_caps.py | non-zero exit, or the summary line contains 0 passed | PASS |
| Task 1 | 12-02 | 2 | uv run pytest -q tests/events/test_models.py | non-zero exit, or the summary line contains 0 passed, or the output contains SKIPPED | PASS |
| Task 2 | 12-02 | 2 | uv run pytest -q tests/events/test_models.py tests/events/test_bus_lanes.py tests/events/test_bus_backpressure.py | non-zero exit, or the summary line contains 0 passed, or the output contains SKIPPED | PASS |
| Task 1 | 12-03 | 3 | uv run pytest -q tests/events/test_bus_dedup_coalesce.py tests/events/test_bus_retry_dlq.py tests/events/test_handler_idempotency.py tests/events/test_bus_shutdown.py | non-zero exit, or the summary line contains 0 passed, or the output contains SKIPPED | PASS |
| Task 2 | 12-03 | 3 | uv run pytest -q tests/cli/test_events_cli.py tests/events/test_bus_retry_dlq.py tests/events/test_bus_shutdown.py tests/events/test_handler_idempotency.py tests/events/test_bus_dedup_coalesce.py | non-zero exit, or the summary line contains 0 passed, or the output contains SKIPPED | PASS |
| Task 1 | 12-04 | 4 | uv run pytest -q tests/events/test_sources.py tests/degradation/test_event_source_faults.py | non-zero exit, or the summary line contains 0 passed, or the output contains SKIPPED | PASS |
| Task 2 | 12-04 | 4 | uv run pytest -q tests/events/test_models_v4_kinds.py tests/safety/test_events_not_wired.py tests/events/test_sources.py | non-zero exit, or the summary line contains 0 passed, or the output contains SKIPPED | PASS |
| Task 1 | 12-05 | 5 | uv run pytest -q tests/replay/test_event_drain_parity.py -k "determinism or smoke_trading" | non-zero exit, or the summary line contains 0 passed, or the output contains SKIPPED | PASS |
| Task 2 | 12-05 | 5 | grep -qF pin lines in CHANGELOG.md | non-zero exit | PASS |

Sampling: Wave 1: 2/2 verified. Wave 2: 2/2 verified. Wave 3: 2/2 verified. Wave 4: 2/2 verified. Wave 5: 2/2 verified.
Wave 0: no MISSING sentinel. Tests are created by the TDD tasks that verify them.
Failing directions: 10/10 stated.
Overall: PASS on plan-task Nyquist. Sampling-map drift is noted above and is not a plan-task fail.

### Recommendation

3 blocker(s), 7 warning(s) require revision. Returning to planner with feedback.
