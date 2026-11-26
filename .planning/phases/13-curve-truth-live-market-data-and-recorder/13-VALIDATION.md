---
phase: "13"
slug: "curve-truth-live-market-data-and-recorder"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-10"
---

# Phase 13 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution. This is a plan, not evidence that any test, probe, review, or gate has passed. Phase 12 verification remains stale and its TDD review unresolved.

## Test Infrastructure

| Property | Value |
|---|---|
| **Framework** | Existing pytest and pytest-asyncio; project constraints `pytest>=9.1.1,<10`, `pytest-asyncio>=1.4.0,<2` |
| **Config file** | `pyproject.toml` |
| **Quick run command** | Run the applicable focused command in the per-task map after its tests exist; no single early command assumes all later-wave files exist. |
| **Full suite command** | `make test` |
| **Additional final gates** | `make lint`, `make typecheck`, `./scripts/check.sh`, offline paper replay, all Phase 13 roadmap criteria including both replay pins, unchanged contracts and live refusal. |
| **Estimated runtime** | Not measured; record actual times during execution. |

## Sampling Rate

- **Before behavior implementation:** Write meaningful behavior tests, run the relevant focused command to capture a genuine semantic RED with classifier-accepted evidence, and record the plan-specific test commit and semantic assessment. For new modules, a temporary typed, importable, nonfunctional interface is permitted in the RED commit only to let the target execute and fail on its planned observable assertion; replace it with the complete working implementation in GREEN before delivery. Missing files, imports, collection, syntax or fixture failures, module-availability or absence assertions, fabricated or unrelated assertions and deliberately broken working code are not valid RED. Resolve invalid evidence and rerun the actual target before GREEN.
- **After every task implementation/commit:** Run its targeted command, capture GREEN output and plan-specific implementation commit; retain independent seat-owned receipts and cross-seat reviews. Exception: 13-03 Task 2b is a tests-only RED handoff, not an implementation GREEN. SNIPER must preserve the construction RED and capture the separate actual-fill semantic RED with real output, exit status, classifier acceptance and semantic assessment, then obtain a separate non-self independent reviewer approval of the receipt before handing off to Task 3. Task 3 must implement the behavior and run its full GREEN command, including these boundary tests; the RED handoff alone is not a passing result. For integration characterization over already working behavior, do not manufacture RED; rely on upstream RED/GREEN evidence.
- **After every wave:** Run the combined focused commands for the completed wave and affected integration seams, with the network blocked and deterministic fixtures. Run the full suite after the integration wave, not concurrently with sibling edits.
- **Before `/gsd:verify-work`:** Execute and retain outputs for every applicable Phase 13 roadmap criterion, the full gates and the human-only decisions below; no skipped critical assertions or zero-test collection. Do not treat planned commands as completed checks.
- **Feedback latency:** Target at most 180 seconds between a task change and its focused feedback; runtime is unmeasured. If the command exceeds this, record the observed latency and use a smaller relevant targeted selection without dropping the full task command at completion.
- **Human checkpoint:** Pause 13-05 for a real human even when auto-advance is enabled. The automated status tests do not replace human review.

**First RED, bridge/recorder tracer:** Create the tests and run `uv run pytest -q tests/datafeed/test_bridge.py tests/replay/test_live_recorder.py`; the named target must execute and fail on the planned observation-to-recording/publication assertion. A temporary typed, importable, nonfunctional interface may be committed only in RED to reach that assertion and must be replaced by complete working code in GREEN. Retain real exit status and unmodified output, require `RED_EVIDENCE_OK` and record semantic assessment; import, collection, fixture, syntax, absence or unrelated assertion failures do not qualify. In 13-02 Task 1, bot-05-rug independently packs asymmetric official-discriminator token-first bytes and runs `uv run pytest -q tests/tools/onchain/test_curve_layout.py::test_token_first_reserves` before decoder changes; the existing decoder must reach a named reserve assertion mismatch, with raw output and classifier outcome retained.

**Rejected prior attempt:** In `/root/src/repos/pumpgrok-wt/phase-13-tracer`, `uv run pytest -q tests/datafeed/test_bridge.py tests/replay/test_live_recorder.py` returned 10 failures solely on missing module availability. This observation is not a semantic RED, even if a classifier accepts it, and must not be counted or reused. No test was rerun for this planning revision.

## Deterministic Offline Test Contract

Use injected `Clock`/fixture time, scripted read-only transports, fixed binary account/event frames, fake RPC/Portal responses, temporary datasets and fault injection. Block external sockets and prohibit wallet, signing and transaction-send access. Exercise the real event bus and replay loader, not a mocked substitute for their integration behavior. Verify emitted RPC/Portal frames and reject unauthorized operations before I/O; fixtures cannot prove provider availability or on-chain truth. Re-run equivalent inputs for identical ordering, bytes/digests and observable results. Use fake time for the rolling 30 operations per 10 seconds and the 60-second held-mark deadline; do not use real sleeps. Capture disconnect, never-framed, stale, timeout, reconnect, gap, duplicate signature with distinct event indices, overflow, malformed frames, corrupted files and recovery boundaries explicitly. Do not log credentials or use secret-bearing URLs.

## Per-Task Verification Map

All rows are **pending**; paths marked planned are Wave 0 or later implementation deliverables, not evidence of passing tests. Test file existence was inspected during planning but may change while plans are revised. Commands are run from the worktree root.

| Task ID | Wave | Requirement / phase slice | Secure behavior and targeted automated command | Status |
|---|---:|---|---|---|
| 13-01-01 | 1 | MKT-05, REC-01; CR-03/04 | Record before publication, fsync and fault propagation, reject conflicting JSONL; real loader: `uv run pytest -q tests/datafeed/test_bridge.py tests/replay/test_live_recorder.py` | pending; review fixes required |
| 13-01-02 | 1 | MKT-09 slice; CR-01/02 | Reject query secrets before I/O, correlated JSON-RPC envelopes: `uv run pytest -q tests/datafeed/test_readonly.py tests/test_network_block.py` | pending; review fixes required |
| 13-03-01 | 2 | MKT-04 | Preserve no-source operator startup, exits and baseline: `uv run pytest -q tests/test_tools_cli.py tests/characterization/execution` | pending; independent receipt required |
| 13-03-02 | 2 | MKT-04 | Entry policy binds source at both BUY stages; exits remain available: `uv run pytest -q tests/execution/test_entry_gate_hook.py tests/execution/test_curve_source_gate.py` | pending |
| 13-03-02b | 2 | MKT-04 | SNIPER owns the `tests/execution` boundary tests, preserves the construction RED, captures a separate actual-fill RED, and obtains receipt approval by a separate non-self independent reviewer before Task 3: `uv run pytest -q tests/execution/test_paper_factory.py tests/execution/test_curve_source_gate.py` | pending; final GREEN belongs to Task 3 |
| 13-03-03 | 2 | MKT-04 | Replay-bound factory, AST guard, no-source and replay exits and pins: `uv run pytest -q tests/execution/test_paper_factory.py tests/execution/test_entry_gate_hook.py tests/execution/test_curve_source_gate.py tests/test_tools_cli.py tests/replay/test_replay_trades.py tests/replay/test_replay_exits.py tests/replay/test_replay_flatten.py tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py tests/safety/test_import_graph_no_live.py tests/characterization/execution` | pending; review and receipts required |
| 13-02-00 | 3 | MKT-10 | Independent event-status characterization: `uv run pytest -q tests/tools/onchain/test_event_decode_status.py` | pending |
| 13-02-01 | 3 | MKT-01, MKT-02, MKT-04, MKT-10 | Token-first decoding, event and source admission. Decoder RED: `uv run pytest -q tests/tools/onchain/test_curve_layout.py::test_token_first_reserves`; GREEN: `uv run pytest -q tests/tools/onchain/test_curve_layout.py tests/tools/onchain/test_onchain_reads.py tests/tools/market/test_price.py tests/tools/market/test_market_reads.py tests/tools/onchain/test_pump_events.py tests/tools/onchain/test_price_gate.py tests/tools/onchain/test_event_decode_status.py tests/execution/test_curve_source_gate.py tests/cli/test_review_trade_prices.py tests/safety/test_blind_advisory.py` | pending |
| 13-02-02 | 3 | MKT-07 staged | Disconnected, never-framed and stale unavailable; fresh unverified data may support protective sells but never BUY or trusted marks; timeout zero only through test sink: `uv run pytest -q tests/datafeed/test_price_source.py tests/datafeed/test_graduation.py tests/execution/test_curve_source_gate.py` | pending; production timeout write disabled |
| 13-02-03 | 3 | MKT-08, staged MKT-07 | Fake-clock held marks, no flat timer, test-only timeout sink and production no-write/degraded safety: `uv run pytest -q tests/datafeed/test_marks.py` | pending; restart regression not proved fixed |
| 13-04-01 | 4 | MKT-05 | Capped watchset, held pins and overflow: `uv run pytest -q tests/datafeed/test_watchset.py tests/datafeed/test_mintbook.py` | pending |
| 13-04-02 | 4 | MKT-05, MKT-07 | Event mapping, live source stamping and actual-reserves observer: `uv run pytest -q tests/datafeed/test_watchset.py tests/datafeed/test_mintbook.py tests/datafeed/test_bridge.py tests/datafeed/test_price_source.py tests/datafeed/test_marks.py tests/events/test_models_v4_kinds.py` | pending; independent handoff required |
| 13-04-02b | 4 | MKT-04, MKT-07 | Exact live-source factory binding, observer and fee selection seam, without durable activation: `uv run pytest -q tests/execution/test_paper_factory.py tests/execution/test_curve_source_gate.py tests/datafeed/test_price_source.py tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` | pending; cross-seat review required |
| 13-04-03 | 4 | MKT-06, MKT-09 slice | Reconnect, dedup, gaps and rolling limiter: `uv run pytest -q tests/datafeed/test_feed.py tests/datafeed/test_readonly.py tests/test_network_block.py` | pending |
| 13-05-01 | 5 | MKT-03 | Probe evidence or exact error: `uv run pytest -q tests/desk/test_probe_pump_accounts.py tests/tools/onchain/test_probe_record.py tests/docs` | pending |
| 13-05-01b | 5 | FEE-01 slice, MKT-04 | V2 explicit selection, v1 default, real production integration and baseline-preserving migration: `uv run pytest -q tests/test_operator_budget_wiring.py tests/tools/test_verb_coverage.py tests/test_tools_cli.py tests/execution/test_fee_model_v2.py tests/execution/test_paper_factory.py tests/execution/test_entry_gate_hook.py tests/safety/test_import_graph_no_live.py tests/characterization/execution` | pending; reviewed baseline and receipt required |
| 13-05-02 | 5 | MKT-03, MKT-10 | Blocking human review, supporting tests only: `uv run pytest -q tests/tools/onchain/test_probe_record.py tests/tools/onchain/test_event_decode_status.py` | pending; explicit human decisions required |
| 13-05-03 | 5 | MKT-03, MKT-04, MKT-10 | Apply only human decisions: `uv run pytest -q tests/tools/onchain/test_event_decode_status.py tests/tools/onchain/test_probe_record.py tests/execution tests/cli/test_review_trade_prices.py tests/safety/test_blind_advisory.py` | pending |
| 13-06-01 | 6 | REC-01/02, MKT-06/07 | Seal ticks and gaps; degraded fail-closed fallback: `uv run pytest -q tests/replay/test_live_recorder.py tests/replay/test_live_recorder_manifest_strings.py tests/replay/test_fixture_manifest.py tests/datafeed/test_feed.py` | pending |
| 13-06-02 | 6 | REC-02 | Recover only torn unsealed tails; reject corruption: `uv run pytest -q tests/replay/test_live_recorder.py tests/replay/test_live_recorder_manifest_strings.py tests/replay/test_fixture_manifest.py` | pending |
| 13-06-03 | 6 | MKT-07/08 | Isolated trusted mark fold and lifecycle only: `uv run pytest -q tests/ledger/test_trusted_marks.py tests/ledger/test_ledger_restart_reconcile.py tests/execution/test_graduation_blind.py` | pending; no production trust |
| 13-06-04 | 6 | MKT-07/08 | Isolated writer reservation and anchor mechanics: `uv run pytest -q tests/ledger/test_store.py tests/ledger/test_trusted_marks.py tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` | pending; no production trust |
| 13-07-A | 7 | MKT-07/08 | Blocking human selection, independent review and G-4 disposition; supporting tests: `uv run pytest -q tests/execution/test_paper_factory.py tests/datafeed/test_price_source.py` | pending; automated output is not approval |
| 13-07-0a | 7 | MKT-07/08 | Independently review factory binding before activation: `uv run pytest -q tests/execution/test_paper_factory.py tests/datafeed/test_price_source.py` | pending; independent security approval required |
| 13-07-0b | 7 | MKT-07/08 | Authorized activation, original restart/forced-exit regression and adversarial suite: `uv run pytest -q tests/ledger/test_trusted_marks.py tests/ledger/test_ledger_restart_reconcile.py tests/ledger/test_store.py tests/execution/test_safe_mark_open_positions.py tests/execution/test_graduation_blind.py tests/execution/test_paper_factory.py tests/datafeed/test_price_source.py tests/datafeed/test_marks.py tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` | pending; actual integration and human decisions required |
| 13-07-01 | 7 | MKT-01 through MKT-08, MKT-10, REC-01/02, PRC-01/03, LIV-07 | Integration, verified import/trim and full acceptance: execute exact command in the following block and all additional roadmap gates. | pending |

**13-07 Task 1 exact automated command:**

```bash
uv run pytest -q tests/datafeed/test_phase13_integration.py tests/datafeed/test_readonly.py tests/safety/test_import_graph_no_live.py tests/test_network_block.py tests/datafeed/test_feed.py tests/replay/test_import_trim.py tests/replay/test_live_recorder.py && make lint && make typecheck && make test && ./scripts/check.sh && uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke && uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py && git rev-parse --verify 'v4-base^{commit}' && git diff --quiet v4-base -- contracts && test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0 && (uv run pumpgrok run --mode live --once; test $? -eq 3)
```

**Failure direction for every automated task row:** Treat a nonzero exit, no collected tests, or any skipped assertion central to that row's stated behavior as failure; retain output and resolve before marking it green. For 13-07 Task 1, failure also includes any failed chained command, skipped pin assertion, changed contract, unresolved base, live exit other than 3, or missing required hash, human, provider or receipt evidence. For 13-05-02 and 13-07-A, passing automation never substitutes for a human decision. These rules are requirements, not observed results.

**Scheduler dependencies:** Seven sequential waves are 13-01 -> 13-03 -> 13-02 -> 13-04 -> 13-05 -> 13-06 -> 13-07. Preserve the direct dependencies in every plan. The independent 13-01 receipt and integration handoff precede 13-03; replay-bound authority precedes 13-02. 13-02 requires actual fake-clock price and marks proof including test-only timeout zero and production-no-write safety, not proof of the production restart fix. 13-04 completes feed, exact live-source factory and observer handoff without claiming provider proof or durable activation. 13-05 supplies fee v2 and migrated integration acceptance before its blocking human layout/event decisions; 13-06 follows that human gate and implements recorder, fallback and isolated risk mechanics only. In 13-07, Tasks A, 0a, 0b and 1 run in that order, with actual independent review and authorized activation before production trust. The downstream production live-data composition remains Phase 15 scope; Phase 14 retains its 13-02 dependency without globally gating unrelated onboarding on anchor activation.

Requirements MKT-01 through MKT-08, MKT-10 and REC-01/02 are mapped above. MKT-09 is the Phase 13 read-only slice only; its composition-root proof belongs to Phase 15. FEE-01 is the selectable v2 slice only; the default flip belongs to Phase 15. REC-03 CLI verbs are Phase 16 scope.

## Wave 0 Requirements

- [ ] Add targeted tests named in the map as their owning plans execute; do not create empty stubs or treat nonexistent files as coverage. `test_pump_events.py`, `test_curve_source_gate.py`, `test_probe_pump_accounts.py`, `test_fixture_manifest.py`, and `test_import_graph_no_live.py` exist in the inspected tree; existence does not establish that they pass or cover new cases.
- [ ] Provide fixed asymmetric account bytes for both supported lengths, five event types and malformed cases; trusted and untrusted source fixtures; separate layout/event review fixtures.
- [ ] Provide fake clock, fault-injected read-only frame transports and network-blocking setup for watchset, limiter, reconnect, freshness, marks and no-send checks.
- [ ] Provide isolated temporary unsealed/sealed datasets, gap sidecars, torn and corrupt cases, and deterministic import/trim examples; verify with the real loader.
- [ ] Capture authentic pre-Phase-13 replay hash evidence at the precise base, or explicitly report missing evidence and block closure. Do not copy a pin as a supposedly observed prior run.
- [ ] Resolve source/test ownership and independent cross-seat receipts; retain genuine RED/GREEN output and commit identifiers for applicable tasks.

## Durable Mark Security and Replay Evidence

The exact per-mint wire shapes and acceptance rules are in 13-07's durable-mark contract: supplied-mode live `"curve"` entries contain strict integer net mark and fee, finite decimal-string spot, strict UTC timestamp and exact `trusted_mark_v1` containing `"curve_source":"rpc"` and current positive `token_units`. Genuine admitted zero is a replacement, not a timeout. Authorized timeout is exactly source `"timeout"`, strict integer zero mark and fee, spot `"0"`, strict UTC timestamp, with no marker or additional fields. Invalid, malformed or unauthorized timeout must not preserve trusted evidence; untrusted non-timeout entries invalidate or fail. Gap omission preserves evidence without refreshing time. Preactivation rows cannot authorize any evidence, even when their marker or timeout is perfectly forged.

The protected external per-ledger anchor is exactly version 1, nonempty existing `ledger_id`, strict positive `activation_seq` and lowercase 64-hex `activation_hash`; verify a consistent full ordered chain and accept evidence only strictly after its matching verified head. No mutable SQLite metadata or snapshot is an anchor. The blocking human/operator decision selects protected storage, all-writer barrier, provisioning authorization, durable-sync/crash behavior and backup/restore; no default service or automatic re-anchoring. Independently review the production factory/observer authority and secure the write boundary before issuance or consumption. G-4 must review the proposed reserved JSON and operation: on a detected contract surface stop for the required change document and consumer review; preserve an empty `contracts/` diff. The guarantees do not extend to malicious authorized writers, arbitrary code, or attackers controlling both ledger and anchor; ledger hashes do not authenticate origin.

Before their respective changes, RISK in 13-06 and SNIPER in 13-07 preserve actual semantic RED output, exit status, classifier acceptance and human assessment, then record plan-specific GREEN commits and independently approved cross-seat receipts. Preserve the observed timeout-zero/restart regression unchanged; do not claim a fix until the real integrated test passes. The tests must cover:
The retained RED is `tests/execution/test_safe_mark_open_positions.py::test_zero_mark_preserves_last_good_exit_across_restart`, with `marks-restart-red.xml` reporting `no_mark` instead of `closed`. Preserve and integrate that exact assertion and raw evidence from the marks worktree; the separately written ledger test in `phase-13-mark-ledger` was not executed and is not this observed RED.

- Actual factory-bound admission, positive and genuine-zero replacement, strict timeout preservation and stale time, explicit malformed source/zero/fee/spot/time/extra-field cases, unknown marker/version, duplicate keys, non-finite values and boolean-as-integer rejection; unauthorized general writers and direct injection must fail.
- Legacy and preactivation forged marker/timeout rows, reversed, duplicated and out-of-order events, future observation relative to recorded envelope, equal timestamps with sequence ordering, and identical evidence at different wall clocks; mismatch in mint or current units must fail closed.
- Missing, malformed, wrong-ledger, substituted, wrong-hash and truncated anchors; concurrent writers during activation, crash before/during durable persistence, restart and authorized restore, with no trust crossing an unverified boundary.
- Full replay from genesis against anchored history for every trusted exit, including old, unknown and forged snapshots; compare versioned snapshots only to independently reconstructed evidence, preserve existing integrity checks and propagate their failures.
- Open, buy invalidation, partial sell conservative value cap and pro-rata venue fee, full close and reopen, gap, timeout, source-policy demotion, no reserve fabrication, restart and forced exit; a genuine zero must never resurrect an earlier positive value.
- Negative factory capability cases including source replacement, wrappers, injection, unreviewed observer and default direct-constructor fakes; no production trusted issuance or consumption until independent review and activation. Do not mistake test-only injected contexts for production authority.

Preserve actual default replay `MarkToMarket` row bytes and idempotency keys, not merely semantic equality. Capture genuine before/after pin outputs for both `tests/replay/test_replay_hash_pin.py` and `tests/replay/test_trading_smoke_pin.py`, and require the `v4-base` contracts guard in Final Phase Gates. None of these planned checks is a recorded result.

## Manual-Only Verifications

| Behavior | Requirement | Why manual | Required instructions and failure state |
|---|---|---|---|
| Separate layout and event status decisions | MKT-03, MKT-10 | An identifiable independent human must assess actual evidence; a test or successful decode cannot authorize `VERIFIED`. | Present sanitized evidence identifiers, public account bytes, reference revision, probe errors and separate interpretations. A human explicitly chooses each status and supplies `human:` reviewer identity and corresponding evidence reference for each `VERIFIED`. Otherwise preserve `ASSUMED` and the exact probe error. An explicit human decision to retain `ASSUMED` is valid; an absent human or undecided status blocks 13-05. Never invent a reviewer or infer approval. |
| Real read-only feed checkpoint | MKT-05/06, REC-01/02 | Injected frames cannot establish that the permitted provider configuration works or that actual observations reach the recorder. | Obtain human/operator authorization and policy review of a keyless endpoint; perform an authorized read-only probe for actual create and migration subscriptions, observe both frame types, and record actual live-feed ticks in a dataset verified by the loader. Retain sanitized provenance, subscription methods, timestamps and observed frames. Do not use a wallet, paid stream, secret-bearing URL or workaround. If unavailable or unsuccessful, record the exact blocker and do not claim the live-feed checkpoint or phase closure. |
| Independent process evidence | PRC-03 and phase safety/process | Human/seat review and pre-change observations cannot be recreated by an automated success assertion. | Review independent ownership receipts and real baseline/head hashes, including all four changelog lines. Do not claim Phase 12 verification was refreshed or its TDD review resolved without actual independent evidence. |
| Protected activation and factory authority | MKT-07/08 | An operational anchor and writer fence are deployment choices; neither marker syntax nor automated tests authorize a production producer. | After 13-03, obtain an independent security review of factory/observer capability and negative tests. Obtain the responsible owner's explicit choice and approval for protected anchor storage, all-writer fencing, provisioning, sync, backup/restore and recovery. Run G-4 and stop for its required change document and consumer review if it detects a contract surface. Missing decisions or review block activation, trusted issuance/consumption and Phase 13 closure. |

## Final Phase Gates

Execute the exact Phase 13 roadmap criteria 1-16 in `.planning/ROADMAP.md`, not a shortened substitute; preserve commands, exit status, collection counts, skips and raw outputs. In particular:

1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh`, and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` must all succeed.
2. Run all roadmap-named focused suites, including the recorder `-k 'gap or torn'` selection, execution/status tests, feed/marks and read-only tests; check the roadmap's probe-record and event-status textual assertions. Human approval remains a separate prerequisite.
3. Run `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` without skipped pin assertions. Execute the roadmap criterion 15's exact two-run `smoke-10m` hash and changelog checks. The expected smoke hash is `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`; obtain the trading hash from the pinned fixture as the roadmap specifies. The before and after values must be actual observations, both pairs equal their pins, and all four exact Phase 13 changelog lines must exist.
4. Run `git rev-parse --verify 'v4-base^{commit}' && git diff --quiet v4-base -- contracts` before the roadmap's exact `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0`, retaining base resolution, diff exit status and stderr; the count alone does not propagate diff errors. Run `(uv run pumpgrok run --mode live --once; test $? -eq 3)`; no changed contracts and live remains refused. These commands are specified for the execution owner, not run in this planning assignment.
5. Complete the human gates and evidence requirements above. Missing provider access, reviewer decision, baseline evidence, or valid TDD evidence is a blocker, not a pass or a reason to enable live execution.
6. Complete the durable seam gate above, including independently reviewed factory binding, human-selected and securely activated anchor, risk/sniper receipts, semantic RED/GREEN, adversarial replay and lifecycle evidence; otherwise do not expose the unverified seam or claim Phase 13 complete.

## Validation Sign-Off

- [ ] All requirements and plan tasks have targeted automated verification or an explicit human-only gate.
- [ ] Wave 0 gaps are filled; no critical assertion skipped and no zero-test collection accepted.
- [ ] Semantic RED/GREEN evidence, sampling cadence and independent ownership receipts are recorded.
- [ ] All roadmap criteria and both replay pin pairs have actual passing evidence.
- [ ] Human layout and event decisions and authorized live-feed evidence are recorded, or precise blockers remain open.
- [ ] Phase 12 stale verification and unresolved TDD review are reported accurately.
- [ ] Set `wave_0_complete: true`, `nyquist_compliant: true` and appropriate validation status only after actual verification and review.

**Prior approval:** The user approved the earlier test strategy on 2026-11-10. That approval is not evidence of results, provider access, status changes, approval of this later proposed durable wire design, factory binding, or the unresolved anchor operation. No tests, builds, formatters or live probes were run for this revision.
