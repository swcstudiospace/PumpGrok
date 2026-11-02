# Phase 12 plan check report

Verdict: PASS with warnings. No blocker found. All ten ROADMAP Phase 12 requirements are covered, dependencies and waves are valid, seat purity resolves clean, acceptance contains no bypass family, determinism and hash parity are pinned, scope stays inside CONTEXT, and every cited file or symbol either exists or is a declared Phase 11 precondition or a plan-created path.

## Evidence per checklist item

1. Requirement coverage. ROADMAP Phase 12 lists EVT-01, EVT-02, EVT-03, EVT-04, EVT-05, EVT-06, EVT-07, EVT-09, EVT-14, PRC-11. 12-01 claims EVT-01, PRC-11, LIV-04. 12-02 claims EVT-01 through EVT-07 plus EVT-14. 12-03 claims EVT-08, EVT-09, EVT-14. 12-04 claims PRC-03, PRC-06. 12-05 claims PRC-06. EVT-08 is in success criterion 8 though absent from the Requirements line; 12-03 covers it. LIV-07 stay-refused is exercised by the live refusal command in 12-01 Task 3, 12-02 acceptance, 12-03 acceptance.

2. Dependencies and waves. 12-01 wave 1 depends on 11-01, 11-04. 12-02 wave 2 depends on 11-04, 12-01. 12-03 wave 3 depends on 11-01, 12-02. 12-04 wave 4 depends on 12-01, 12-02, 12-03. 12-05 wave 5 depends on 12-01 through 12-04. Graph is acyclic, matches 12-PLAN-INDEX.md, one plan per wave so no same-wave coupling. Shared branch and receipt for waves 1 to 3 is sequential append, no race. Order-after 11-09, 11-10, 11-11 recorded in 12-04 and 12-05.

3. Seat purity. Resolved every files_modified path with load_manifest plus DEFAULT_MANIFEST from ci/gates/check_ownership.py: all src, tests, docs paths resolve to bot-02-risk; CHANGELOG.md to bot-09-journal; .planning paths to bot-00-chief; receipts to their seat dirs. Matches plan seats. No plan writes approved_by. Summaries go to /tmp/v4/summaries. 12-05 chief writing .planning is ownership clean by design.

4. Honesty of acceptance. Grepped all five plans: no verify command uses pytest collect-only, --co, --no-verify, stderr swallow, or dry-run; the only mentions are prose bans, which check_receipt.py exempts when searched for. Zero-skip proof uses negated grep which fails closed when SKIPPED appears; -k determinism and -k smoke_trading selections fail closed with exit 5 on no match. Trading-smoke value is read from the pins file with python3 json load, never hand-copied. Tests are RED first in 12-01 Task 1, 12-02 Task 1, 12-03 Tasks 1 and 2. No vacuous assertions found.

5. Determinism and hash safety. 12-02 freezes derived event_id as first 32 hex of sha256 of kind, entity, dedup_key with PRIORITY a pure function of kind; integer lamports per D-01; ledger reuse is Escalation rows with free-string kinds only. 12-03 Task 1 pins drain order by ts, priority_rank, source_seq from the source, quiescence over coalescing futures plus retry timers plus FixtureClock FIFO continuations before virtual time advance, coalescing OFF by default, DLQ entry fails the replay; Task 2 pins backoff min of cap and base times 2 to the nth times 0.5 plus rng.random with reset only after stable_s, 121 s silence on the 120 s timeout, resync seeding one PositionTick per held mint, cursors every 50 events or 5 s and at close, corrupt cursor starts clean, single SourceStateBook. Smoke-10m hash b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d before and after pairs appear in 12-01 Task 3, 12-02 acceptance, 12-03 Task 4, 12-04 Task 1; trading-smoke pins file value before and after in 12-04.

6. Scope. No plan adds live code; live refusal exit 3 is asserted in 12-01, 12-02, 12-03. No signing or key code: only signer socket config fields required by D-07. D-06 honored: only 12-01 touches settings.py and section files. D-08 honored: only 12-02 creates the catalog. No plan touches contracts, so the zero-diff criterion holds structurally.

7. Cited files and symbols. Verified present: settings.py, core/errors.py with PumpgrokError ToolTimeout ToolRateLimited LedgerUnavailable DataStale, replay/clock.py with FixtureClock advance_to timeout, replay/rng.py with make_rng, ledger/events.py with Escalation, core/ids.py idempotency.py datasource.py with Freshness Health, tests/harness/faults.py with FaultInjector FaultyLLMClient FaultyDataSource, cli/dispatch.py with _VERB_HANDLERS, degraded.py with assert_no_skew line 52 and signal_scoring_mode line 89. Plan-created paths tests/events, src/pumpgrok/events, config/sections are correctly absent. tests/fixtures/replay/pins/trading_smoke.json and tests/replay/test_trading_smoke_pin.py are absent here because Phase 11 has not executed in this worktree; they are 11-01 deliverables and 12-01 and 12-03 declare depends_on 11-01, so they are preconditions, not defects.

## Warnings

W-1. 12-01 over-claims LIV-04. Frontmatter requirements list includes LIV-04, whose REQUIREMENTS.md check also needs tests/live/test_arm_record.py, a Phase 18 artifact this phase never creates. 12-01 delivers only the settings-caps half through tests/config/test_live_settings_caps.py. Evidence: 12-01-PLAN.md frontmatter requirements field. Fix: drop LIV-04 from the 12-01 requirements list, or keep it and record LIV-04 as skeleton-fields-only partial in 12-VERIFICATION.md with the arm record left to Phase 18.

W-2. D-02 clock ban has no automated check in any plan. No verify block runs the CONTEXT grep banning datetime now, utcnow and time time, sleep under src/pumpgrok/events. Evidence: absence across 12-02-PLAN.md verification block and 12-03-PLAN.md verification block. Fix: append the CONTEXT D-02 grep command to 12-02 Task 5 verify so the bus, store, dlq and models land clock-clean.

W-3. Single-catalog count has no automated check in any plan. ROADMAP criterion 7 requires exactly one class EventKind definition in src, but no verify block runs that grep; 12-02 must_haves states the truth without wiring it to a command. Evidence: 12-02-PLAN.md verification block. Fix: append the EventKind count test to 12-02 Task 5 verify, or state in Task 4 that tests/events/test_models_v4_kinds.py asserts the repo-wide count of one.

W-4. Contracts zero-diff has no automated check in any plan. ROADMAP criterion 10 requires empty git diff of contracts against v4-base, but no plan verify runs it; coverage is structural only since no files_modified entry touches contracts. Evidence: absence across all five verification blocks. Fix: append the contracts diff test to 12-05 Task 3 verify next to the ownership manifest validation.

W-5. 12-02 is oversized against the generic budget at 5 tasks and 21 files_modified, and 12-01 at 4 tasks and 15 files with 12-03 at 4 tasks are borderline. Every file matches the CONTEXT 12-02 file list exactly, so this is in-scope weight, not creep. Evidence: 12-02-PLAN.md frontmatter files_modified list of 21 paths and five Task headings. Fix: keep as one unit to protect the frozen-interface intent, and let the executor stop after Task 3 for a checkpoint if review latency grows; no re-slice required.

## Advisories

A-1. EVT-08 appears in ROADMAP success criterion 8 but not in the Phase 12 Requirements line; 12-03 covers it, so delivery is safe and only the ROADMAP line drifts.

A-2. Pins preconditions tests/fixtures/replay/pins/trading_smoke.json and the pin tests arrive via Phase 11 plan 11-01; 12-01 and 12-03 declare the edge, 12-02 inherits it transitively through 12-01.
