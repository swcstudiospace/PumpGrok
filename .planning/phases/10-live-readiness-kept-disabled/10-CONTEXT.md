# Phase 10 CONTEXT: Live readiness, kept disabled

Last phase of milestone v3. Phases 7, 8 and 9 are complete and verified.
Phase 6 is blocked on owner decisions that do not affect Phase 10.
Live trading stays refused in this release per the constitution in
rules/pumpgrok-team.mdc clause 1 and PROJECT.md decision D4.

## Locked decisions

- D-01: Live stays refused end to end. `pumpgrok run --mode live --once`
  exits 3 at the end of this phase, exactly as today. No change to the
  exit code, no bypass flag, no operator override short of meeting all
  nine preconditions, which is structurally impossible in this release.
- D-02: The live refusal output lists the nine preconditions in R21 order
  with one line per precondition from refusal_lines in
  src/pumpgrok/execution/live/live_gate.py, and stderr names all nine ids.
- D-03: No live adapter is registered or enabled. build_adapter in
  src/pumpgrok/execution/__init__.py returns PaperAdapter only.
  The LiveAdapterStub stays a refusing stub that appends LiveWriteAttempted
  and raises LiveGateError. Precondition 8 adapter_registered stays unmet.
- D-04: No signing code and no key material enter the system. The AST guard
  in tests/safety/test_no_signing_outside_live_stub.py keeps passing with
  zero violations outside the quarantine. No new network call on the live
  path: modules under src/pumpgrok/execution/live/ import no venue client
  and open no socket.
- D-05: LIV-01 is proven by three tests that must all pass:
  tests/safety/test_live_refusal_lists_nine.py for the refusal text,
  tests/safety/test_no_live_adapter_registered.py for the empty registry,
  tests/safety/test_import_graph_no_live.py for the import-graph proof.
  The import-graph proof is an AST reachability test over the repo: it
  fails if any guarded root gains a transitive import path to the live
  adapter module. Imports of the gate module live_gate by the CLI and the
  weekly report stay allowed; only the adapter module is quarantined.
- D-06: LIV-02 is proven by docs/LIVE_READINESS.md, a deferred record that
  states what a future live decision requires: the custody model, the
  venue, the legal review, and the nine-precondition evidence, each with
  its owner and status. The desk stays paper-only. The record claims no
  readiness it has not measured.
- D-07: docs/LIVE_READINESS.md is ASCII only, carries a status deferred
  marker, and names custody, venue, legal and nine-precondition evidence
  so the roadmap grep gate passes unchanged.
- D-08: The replay ledger is expected unchanged. The smoke-10m events.hash
  recorded in Phases 6 through 9 is
  b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d.
  If this phase changes it, the executor says so and records the value.
- D-09: CHANGELOG.md uses the Phase 9 placeholder policy. The Phase 10
  entry carries smoke-10m events.hash before PHASE10_BEFORE_HASH and after
  PHASE10_AFTER_HASH. The orchestrator fills both at the gate; no executor
  runs pumpgrok verify.
- D-10: The CHANGELOG is written only by the last plan. Earlier plans
  touch no changelog lines.

## Grey areas with defaults and one-line reasons

- G-01: test_live_refusal_lists_nine asserts all nine PRECONDITION_IDS
  appear in R21 order on stderr, because order is part of the refusal
  contract and a reorder would hide a regression.
- G-02: The import-graph test treats pumpgrok.execution.live.live_adapter
  and the LiveAdapterStub name as the quarantine boundary, because the
  gate module is a legitimate reader dependency of the CLI and reports.
- G-03: Guarded roots are backtest, execution paper_adapter, upgrade,
  supervisor, and cli, because the roadmap names the first three and
  LIV-02 adds the CLI and the supervisor as the paths that must never
  reach a live adapter.
- G-04: The overlay check is a committed test file
  tests/safety/test_live_disabled_overlays.py rather than an inline gate
  snippet, because a committed test keeps the criterion green on every
  future run instead of only at the gate.
- G-05: Each open item in docs/LIVE_READINESS.md names owner human and
  status deferred, because no seat may own a live decision and no item
  is approved in this release.
- G-06: The record lists the nine preconditions by id with the current
  unmet reason quoted from the gate, because that is the exact evidence
  a future decision would re-evaluate.
- G-07: Style stays mypy --strict on src, ruff clean, no dead code, no
  swallowed exceptions, no TODO or placeholder text except the two
  CHANGELOG hash placeholders the orchestrator fills.

## Scope boundary

In scope: the refusal-output proof, the empty-registry proof, the
import-graph proof, the overlay-disabled proof, the deferred
live-readiness record, and the v3 closeout CHANGELOG entry with the
replay hash lines.

Out of scope: enabling live, registering or implementing a live adapter,
signing or custody code, key material, venue clients or network calls on
the live path, paid RPC procurement, legal or custody decisions, any
product code change beyond hardening the refusal output, any edit to
STATE.md or ROADMAP.md, and any commit, which the orchestrator owns.
