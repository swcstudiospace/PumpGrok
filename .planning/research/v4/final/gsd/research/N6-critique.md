# N6 critique of Designs A, B, C and the amendment draft (repo HEAD 641927c)

Verdict: the designs are individually strong but do not yet compose into criteria (c), (e), (i) and (j). Eight items block. PRs 17 to 20 are not on main at this HEAD, so every claim about `backtest/equity.py`, `is_writer` and `verify_stored_content` is UNVERIFIED (only a private `_is_writer` exists, `ledger/active_set.py:51`).

## 1. Cross-design conflicts

- **Event vocabulary.** A's `EventKind` table (`TokenLaunched`, `PriceTick`, `PositionTick`, `SourceStatus`, `Timer`) and B's typed events (`NewTokenSeen`, `CurveTick`, `FeedGap`, `FeedResynced`, `MintEvicted`) are two models; B says "the bus is Design A's" but never maps them. B also assumes events A lacks: `DatasetSealed`, `LlmCallCompleted`, `BacktestCompleted`, `StrategyVersionRegistered`, `ParamsProposed`. A uses `ExitDeadline` in 4.2 and 4.3 but not in its kind table. B calls the interface `Publisher`, A `EventPublisher`. A's priority is a pure function of kind, so B must say whether a held-mint `CurveTick` becomes `PositionTick` (P0) or stays P2.
- **Packages.** `events/` (A1, A3) and `datafeed/` (B06 to B08) both own reconnect, staleness, resync and cursor logic. B07 depends only on B01 and B06, never A1 or A3. B09 (a "bus subscriber") and B16 (scheduler on bus events) also lack A1/A2 dependencies.
- **Ordering.** A's `DeterministicBus` orders by `(ts, priority_rank, source_seq)`; B's replay by `(ts, line)`. Same data gives different handler order, so backtest is not "the same pipeline".
- **Staleness has three owners:** `DegradedState.ws_data_stale` (A4), `FeedHealth` and the `data_stale` breaker (C-04), `LivePriceSource` returning None (B08). Nothing calls `FeedHealth.note_tick`; A3 and A4 do not mention it.
- **Attribution carrier** (`strategy:ID`, `param_set:HASH` after `refs[0]`) agrees between B and C. But `strategy_of` is in `risk/strategy_slice.py` (C-02), which depends on B's `allocation.py` (B10), which depends on "Design C ticket refs". That is a B10/C-02 cycle. Replay buys use the constant `REPLAY_TICKET` (`supervisor/scheduler/orders.py:50`), so per-strategy attribution does not exist on the replay path B16 reuses.
- **Param identity.** C binds stages to `ParamSet.content_hash`; `ParamSet` holds only `filter` and `exits` (`upgrade/params.py:31-33`), `load_bounds` reads only those two sections (`upgrade/bounds.py:86`), and `evaluate_candidate` takes a `ParamSet` (`upgrade/gate.py:84`). B's `[strategy.ID.PARAM]` bounds would be silently ignored. No unit generalizes this.
- **Contention.** `config/settings.py`: A0, B10, C-02, C-06, plus unowned datafeed/backtest keys (`watch_max`, `mtm_refresh_s`, `gap_haircut_bps`) and signer keys. `cli/parsing.py`: A1, B18, C-05, C-06. `cli/{dispatch,verbs_ops}.py`: C-05, C-06, C-10. `core/errors.py`: A0, B06. `Makefile`: A10 only. `tests/conftest.py`: B07 only. `registry.py` and `upgrade_bounds.toml`: B12 to B14 (B says serialize). `doctor.py`: C-06; A's "doctor refuses superseded job" has no unit.
- **Timers.** A's allowed-timer set (EVT-10) omits B's 45 s MTM refresh and C's reconcile-on-start; B17 would break EVT-10.
- **Ordering contradictions.** A2 acceptance EVT-08 needs `WakePolicy` (A4, chief, later wave); A4 acceptance omits EVT-08. C-05 needs `Timer(daily_rollover)` from A4 but is "parallel". C-04 needs A3 transports.

## 2. Claims checked against code

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | Ten cadences (60,10,5,120,1,30,15,300,1,300) | CONFIRMED | `supervisor/scheduler/supervisor.py:41-51` |
| 2 | 1 s `TICK_S` loop | CONFIRMED | `supervisor.py:37,409` |
| 3 | `Escalation.kind` is free str | CONFIRMED | `ledger/events.py:283` |
| 4 | `WS_STALE_S` 120 | CONFIRMED | `degraded.py:20` |
| 5 | Ladder "tied to `signal_scoring_mode`", `degraded.bus_backlog` | WRONG | modes are `llm`, `rule_fallback`, `observe_only_buys`, `replay` (`degraded.py:89-97`); no `bus_backlog` |
| 6 | `GrokOps(`/`CallBudget(` only in tests | CONFIRMED | `tests/degradation/test_llm_failure.py:135`, `tests/characterization/test_agents.py:319` |
| 7 | `precheck` per attempt via `try_spend` | CONFIRMED | `core/llm.py:35-41`, `engine/agents/base.py:167`; message reads `budget.max_per_day`, absent on a layered budget |
| 8 | Parser scavenges first balanced object | CONFIRMED | `base.py:238-259` |
| 9 | Cache key via `canonical_request_hash` strips volatile keys | CONFIRMED, HAZARD | `replay/recorder.py:38-41` substring regex drops `_at`, `seed`, `span`; `_freeze` raises TypeError on Decimal (`:58-65`) |
| 10 | `NINE_FAMILIES` and its test | CONFIRMED | `supervisor/metrics.py:64`, `tests/supervisor/test_metrics.py:40` |
| 11 | `_settle_on_virtual_time` | CONFIRMED | `replay_runtime.py:278` |
| 12 | `run_once_replay` untouched | WRONG | defined in `supervisor/scheduler/serve.py:43`, which A4 edits; `verify` calls it (`cli/verbs_ops.py:190`) |
| 13 | Monitor resets backoff on connect | CONFIRMED | `engine/monitor.py:243` |
| 14 | About 12 Hermes sessions per hour | CONFIRMED (10 idle) | `hermes/cron/jobs.yaml`; rug-watch is gated only inside the session (`prompts/rug-watch.md:14`) |
| 15 | `require_activity` makes idle cost 0 | WRONG | `[SILENT]` is printed by the model inside a running session (`prompts/*.md`), so the call is already spent |
| 16 | Curve layout swapped, `len == 49` | CONFIRMED | `tools/onchain/curve_layout.py:25,63,66` |
| 17 | `rpc_curve_price_allowed` fail-open; sites | CONFIRMED | `curve_layout.py:161`, `paper_adapter/buy.py:250`, `confirm.py:127` |
| 18 | `tick_to_candidate` divides virtual S by 85 SOL | CONFIRMED | `engine/pipeline.py:78-92`, `engine/monitor.py:46` |
| 19 | No `kind` filter; 120 s gap fails | CONFIRMED | `pipeline.py:108-113`, `replay/runner.py:53,173` |
| 20 | `data_stale` MTM limit 60 s | CONFIRMED | `risk/engine/steps.py:384-387`, `risk/limits.py:30` |
| 21 | ExitRules uses only curve source methods | CONFIRMED (two of three) | `supervisor/exit_rules.py:150,197`; `reserves` unused |
| 22 | CURVE_ACCOUNT_SIZE imported by four seats | WRONG, three | risk, rug, scout test dirs (`tests/safety`, `tests/tools/{onchain,safety,market}`) |
| 23 | Tests pin LAYOUT ASSUMED | CONFIRMED | `tests/execution/test_graduation_blind.py:201`; `tests/docs/test_verify_doc_commands_offline.py:158-160` |
| 24 | conftest blocks ws connect | CONFIRMED | `tests/conftest.py:35-37` |
| 25 | `run --record` is an exit-5 stub | CONFIRMED | `cli/verbs_state.py:88` |
| 26 | `FixtureManifest.sources` carries machine keys | PARTLY WRONG | `dict[str, str]` (`replay/fixtures.py:46`); integers must be strings; unlisted jsonl files are rejected (`:127`) |
| 27 | Load rejects ts regression | CONFIRMED | `fixtures.py:183` |
| 28 | `EventSource` is paper, replay, manual | CONFIRMED; wider than C-07 | `ledger/events.py:31`, `ledger/store.py:31`, plus `risk/engine/steps.py:222`, `tools/portfolio/ledger_{read,write}.py`, `execution/__init__.py:28`, `paper_adapter/{adapter,buy,marks}.py`, 18 schemas |
| 29 | `Fill.venue_tx_ref` pattern-locked | CONFIRMED | `core/adapter.py:112`; `FillRecorded` plain str (`events.py:137`) |
| 30 | LiveGate rows 5 to 9 hardcoded unmet; row 6 id | CONFIRMED | `live_gate.py:36-46,100-109` |
| 31 | confirm hashes `[]`, cap 1.0 | CONFIRMED | `cli/verbs_ops.py:69,100`; config_hash is the full Settings dump (`:88`) |
| 32 | 19 STEP_IDS | CONFIRMED | `risk/engine/constants.py:9-29` |
| 33 | `tx_dropped` already in exec errors; 3 per 10 min | CONFIRMED | `risk/breakers.py:35-37,63-64` |
| 34 | `data_stale` never trips before first tick | CONFIRMED | `breakers.py:227` |
| 35 | Live forces manual-ticket | CONFIRMED | `tools/__init__.py:360`, `ledger/autonomy.py:11` |
| 36 | Approval `kind` is plain str, no schema change | CONFIRMED | `ledger/events.py:306`; Literal in `core/approvals.py:46` |
| 37 | INV-S-01 exemption is `execution/live/` | CONFIRMED | `tests/safety/test_no_signing_outside_live_stub.py:23`; documented scope also lists `services/`, `scripts/` (`docs/SAFETY_INVARIANTS.md:33`), so the signer needs an explicit text change |
| 38 | `evaluate_candidate` checks 1 to 4 then divergence | CONFIRMED | `upgrade/gate.py:84-175`; `paper` is currently required |
| 39 | `build_adapter` always returns PaperAdapter | CONFIRMED | `execution/__init__.py:15-43` |
| 40 | PumpPortal fee "undocumented" | WRONG | 0.5 percent fee is documented (`/tmp/n1/research.md:8`); only the recipient account is unpinned |

## 3. Hash and determinism risks

1. **smoke-10m is nearly blind.** Its 41 ticks carry no name or buyers, so the filter never admits a trade (`tests/fixtures/replay/smoke-10m` keys; the trading fixture is `smoke`, `tests/replay/test_replay_trades.py:3`). The pinned hash covers the verdict note and rollover rows only, so "hash unchanged" proves almost nothing about risk, strategy or adapter edits. soak-3d has 2 mints and no evidence fields. Pin the trading `smoke` ledger hash and full row dump as well, before any engine unit.
2. A4 edits `serve.py` (hosts `run_once_replay`), `supervisor.py`, `seat_task.py`: the claim "by construction" is really "by test". A2's parity drives smoke-10m, which has no trades, so it cannot prove wake ordering. Run parity on `smoke`.
3. `verify` passes `operator_active_set(settings)` from `var/ledger.sqlite` (`cli/verbs_state.py:59`). A persisted live-paper ledger with an active set changes the hash; receipts must run in a clean cwd.
4. `FixtureCurveSource._latest` scans all ticks per call (`replay/sources.py:58-75`); `DatasetCurveSource` must index per mint with bisect or multi-day backtests are quadratic.
5. `FixtureClock` timers only wake futures; continuation order depends on loop FIFO (`replay/clock.py:101-117`). Gateway in-flight coalescing futures and retry timers need a drain loop that yields until quiescent before advancing.
6. Gateway cache key: Decimal in payload raises; age-like fields never stabilize; `_at` and `seed` keys vanish. Define an explicit key payload of ints and strings.
7. `ledger_events_hash` is the hash column chain (`runner.py:135`); any new JournalNote text in replay (A's `Escalation` kinds, B `JournalNote backtest-result`) moves it only if emitted there. Record equal before and after lines per phase, as Phases 6 to 10 did in CHANGELOG, instead of "no pair needed".
8. GRK-11 on soak-3d is vacuous: no candidate passes the filter, so before and after are both 0.

## 4. Process traps

- **Seat purity** verified with `resolve_owner` for all A, B, C unit files: every declared owner matches. Exceptions: C-07 touches 8 more files owned by sniper and journal (section 2, row 28), so it is not risk-pure; the amendment touches three seats, not two (below).
- **importorskip.** pytest 9 probably skips only on ModuleNotFoundError [INFERENCE], so the pattern likely runs, but chief cannot fix risk-owned tests that guess its API, and `tests/desk/**` is chief-owned: chief units can ship their own tests there. T4's acceptance "collect-only" matches the G-2 bypass pattern `pytest.*--co\b` (`ci/gates/check_receipt.py:45`), so it cannot appear in a receipt. Drop T4; move its files to `tests/desk/`.
- **C-07 and G-4.** `contract_consumers` for `contracts/events/**` is all ten seats (`ownership.yaml:473-484`); acks are required only if `breaking: true`, otherwise a rejection merely blocks. Declare additive, non-breaking, with `semantic_changes`. Regenerate schemas with `scripts/generate-event-schemas.py` (checked by `make check`).
- **Tests owned by risk.** `tests/**` is risk by default, so every chief and sniper unit with `tests/live` or `tests/safety` edits is a second seat.
- **Amendment PR.** The draft says no agent applies it; C-13 and C-14 are agent units. The 2026-10-25 precedent applied after approval, but the owner's rule here is stricter: a human applies and merges. The waiver in `.github/workflows/gates.yml` (PR number match, as `fa01021`) waives G-1, G-2, G-5 and G-6 for that PR only. Copies the draft misses: `prompts/bot-04-sniper.xml:6,27` (sniper), `prompts/bot-00-chief.xml:65` and `agents/chief.md:72` ("never allow SNIPER without the exact human approval phrase"), `AGENTS.md:91`, `ARCHITECTURE.md:170`, `SETUP.md:120,203,241`, `docs/ROSTER.md:116`, `docs/runbooks/setup.md:27`, RISK_POLICY 3.3 "R17: no live auto-exit exists" (`docs/RISK_POLICY.md:128`).
- **CI.** `ci.yml` runs `make lint typecheck test audit` only; `mypy src/` omits `services/`; `ci/gates/` is overlaid from base so a new gate (A10) is inert in its own PR and absent from `run_all.py`. Full `pytest -q` is about 50 minutes (soak), required per unit by B.
- **Import graph.** `test_import_graph_no_live.py` takes the transitive closure of `supervisor`, `cli`, `backtest`, `upgrade` and `paper_adapter`, including function-level imports. C's "supervisor and CLI may reach the registry but not the client" is impossible if the registry names the class literally. B17's paper root sits inside the guarded `supervisor` prefix and must not import `build_adapter`. Split paper and live factories.
- **Dependencies.** pyproject has no solders, base58 or crypto library; `testpaths` is `tests`, so `tests/services/desk_signer/` would import them in the root suite. Keep signer tests only in the service.

## 5. Live-path security review

1. **Exits blocked (BLOCKER).** `_step_live_gate` runs for sells (`risk/engine/steps.py:239-245`; `live_gate` is not in `EXIT_SKIP_STEPS`, `constants.py:32-47`). Row 9 `no_active_stop` is unmet during any halt, kill or breaker, row 7 on arm expiry, and demotion maps to `live_gate`. So kill-flatten and stop-loss exits are refused in exactly the states they matter. `approval_missing` also needs a minted approval for rule exits (`steps.py:249`; only `kill_flatten` and `rug_alert` are system reasons). Amendment clause 2's last sentence suspends "autonomous sends", which includes exits.
2. **Arm scope.** The arm binds strategy ids, not param hashes, and the config hash is the Settings dump, which excludes ledger-held param sets. Autonomous paper param promotion plus automatic LIVE_ELIGIBLE can put an unreviewed hash live. No maximum expiry is stated.
3. **Signer boundary.** Socket mode 0600 with a separate uid cannot admit the desk; use 0660 plus group. SO_PEERCRED across containers reads mapped uids and, with one shared uid, authenticates nothing beyond signer policy. `attestation.json` and `identity.json` live in a shared `var/` the desk can write, so a fake signer or forged attestation is possible; serve them over the authenticated socket. Stage, strategy kill and halts come from a desk-writable ledger, so the signer's re-derivation is consistency, not independence; the independent controls are the HMAC arm, wallet, caps and tx verification. Say so. Nonce and timestamp need a persisted window and a time-sync check (arm expiry is evaluated on two clocks).
4. **Decode-and-verify is incomplete.** Required: instruction-level allowlist, not program-level. System: Transfer only, to a pinned recipient, amount at most fee rate times size; reject Assign, Allocate, AdvanceNonce, CreateAccount to other owners. Token and Token-2022: reject Transfer, TransferChecked, Approve, ApproveChecked, SetAuthority, Burn, Freeze, and CloseAccount unless account owner and destination are the wallet. ATA program: create only for the wallet owner and intent mint. Pump program: discriminator allowlist; bonding curve and associated curve equal PDAs derived from the intent mint; user is the wallet. Resolve v0 address lookup tables or refuse them. Verify the final signed bytes after compute-limit edits, not the simulated copy. The signer must set its own recent blockhash and fetch `lastValidBlockHeight` (trade-local gives only the hash), else DROPPED cannot be proven. After simulation, check post-state delegate, close authority, frozen state and owner of the wallet token account, not only the token delta.
5. **Single send.** The persist-then-send ordering is right. Add: fsync directory; reconcile treats a signed row older than validity as DROPPED only after a finalized check; a second RPC for confirmation (one lying RPC can fake success).
6. **UNKNOWN and drift.** UNKNOWN halts and exits stay blocked (point 1). Drift compares SOL only; add on-chain token balances to ledger positions, include ATA rent (about 0.002 SOL) and creator-fee vault effects in the tolerance to avoid false `wallet_drift` halts.
7. **Strand risk.** C forbids sells on a completed curve and v4 trades no PumpSwap, so a live position through graduation cannot exit (marked 0 after 600 s). Live-eligible strategies must exit before completion, or the signer must support `pool=pump-amm` sells.
8. **Token-2022.** Entry checks are right; add the wallet's own ATA extensions (ImmutableOwner fine, CpiGuard and default-frozen reject) and re-check authority immediately before send.
9. **Amendment.** Clause 3 drops "wait for fresh human approval" after a failed (on-chain error) result and the exec_errors breaker auto-resets after 900 s (`breakers.py:65`), so failed sends can resume without a human: weakening; make live `tx_failed_onchain` latch human-clear. Closing paragraph says no overlay enables live, but the runbook step 4 commits an overlay with `enabled=true`; use an operator-local `PUMPGROK_CONFIG` outside git. Throwaway limit is 200 USD while the cap is 1.0 SOL: at SOL above 200 USD the runbook funding rule "cap plus fees" breaks clause 1. Core item 1 appended sentence is acceptable. Clauses 4 to 7 untouched: consistent. Item 3 trading-seats variant still holds pre-2025 wording (`prompts/_shared/core-directives.xml:15`), covered by the draft.

## 6. Owner criteria coverage

(a) GAP: no GSD phases, CONTEXT, PLAN, SUMMARY units; ROADMAP has only Phases 6 to 10, all done; `.planning/**` is chief. (b) PARTIAL: no unit for ci.yml, signer typecheck, soak split. (c) PARTIAL: modeled counterfactual only, vacuous fixtures, Hermes idle session remains, no seat cycle bodies (section 7). (d) COVERED by A5; verify fallback with real budget exhaustion in e2e. (e) GAP: needs autonomous-paper set by a human (else `approval_missing`), human review flipping `EVENT_DECODE_STATUS` (unowned; without it "logs" prices refuse buys), and a restart recovery unit. (f) COVERED, but undefined formulas for annualization under 7 days. (g) PARTIAL: desk caps `max_open_positions` 3 and `max_trades_per_day` 20 (`core/risk_budget.py:31-32`) starve four strategies; tickets cap at 999 per day (`ledger/tickets.py:21`, `core/approvals.py:55`). (h) GAP for non-legacy strategies (section 1, param identity). (i) PARTIAL: static proof conflicts (section 4). (j) COVERED by C 1.8. (k) PARTIAL: signer logs only; desk log redaction test for strategies absent. (l) PARTIAL: live reconcile yes; paper restart of runtime state no. (m) GAP: P and L metrics absent, `stop_loss_poll_seconds` and `[exits.stop_loss_poll_seconds]` become dead config, no TODO or dead-code unit.

## 7. Missing units and risks

Seat cycle bodies for event mode (all exist only as `_replay_*`, `supervisor/scheduler/replay_cycles.py:27-136`), including Intent to sniper `exec.place` routing with ticket and approval allocation. Restart recovery: re-arm `ExitDeadline` timers, tapes, watch set, probation state, per-strategy exit peaks. Bus capacity and event rates on public RPC (`rpc.endpoints` default is the public mainnet endpoint, `config/settings.py:75-93`): 128 curve log subscriptions, 100 MB per 30 s cap; a paid-RPC owner decision is not recorded. pump.fun REST (`frontend-api.pump.fun`) availability and Cloudflare blocking: fallback must degrade, not assume. Time sync (NTP) check in doctor; `assert_no_skew` (`degraded.py:52`) refuses appends on backward steps. Docs and runbooks for event mode, recorder, backtest, signer; `docker-compose.yml` still runs the replay loop; a separate signer image and compose service. Paper fee model omits PumpPortal 0.5 percent, ATA rent, priority fee; paper P and L is optimistic against live costs and promotion uses it. Settings fields named seed hit `FORBIDDEN_SUBSTRINGS` (`config/settings.py:229`); use another name.

## 8. Ranked change list

**BLOCKER**
1. C section 1.7 and 3, amendment clause 2: split `live_gate` so exit sells check only rows 1, 2, 5, 6, 8; mint `autonomous_live` for exit-rule and flatten sells while any live position is open; reword clause 2 last sentence to suspend entries only.
2. C section 2, 3 and amendment clause 2: arm lists (strategy id, param hash) and has a stated maximum expiry; any hash change needs a new arm.
3. C section 4 Transaction build: replace with the instruction-level allowlist and signer-owned blockhash of section 5 point 4.
4. C section 2, B section 4, new unit R0 (risk): generalize `ParamSet`, `CandidateParams`, `load_bounds`, harness trial identity to strategy params; before B12, C-05.
5. A section 4 and B section 7: new chief unit E2E runtime: seat cycle bodies, composition root wiring bus, sources, runtime, gateway, promotion edges and Timer; deps A1, A3, A4, A5, A6, B07, B08, B10, C-05.
6. C section 10 C-13, C-14: human applies and merges; add the missing copies and the sniper-owned source; record the waiver PR number and approver.
7. C section 10 C-07: list all 8 literal files or fold into one waived PR; declare non-breaking.
8. B section 9 B10 and C-02: break the cycle by moving `allocation.py` and `strategy_of` into C-01.

**MAJOR**
9. A section 4.4: pin `smoke` trading ledger hash and rows; parity on `smoke`; edit A4 text (serve.py is touched).
10. A section 10: delete T4; put wake, metrics and Hermes tests in `tests/desk`; add EVT-08 to A4 acceptance.
11. A and B section 1: one event catalog in `events/models.py` including all B and C events; B depends on A1; one source layer (A3) and `datafeed` only decodes.
12. A section 4.2 and C section 1.4: one staleness owner; add MTM refresh to allowed timers.
13. A section 6: disable the daily Hermes rollup in event mode, or make it event-triggered from the supervisor; drop `require_activity`.
14. A section 5 step 3: explicit cache key payload (ints and strings); stringify Decimal.
15. A section 9 GRK-11: use a synthetic evidence dataset with at least 50 admitted candidates.
16. B and C: desk `max_open_positions` and `max_trades_per_day` owner decision; widen ticket number to 4 digits via contract change or per-strategy day counters.
17. B section 3: manifest values as strings; B section 6: bisect index in `DatasetCurveSource`.
18. C section 5 and 6: registry loads the live class by dotted path only in the live factory; separate paper factory; update import-graph test text.
19. C section 4: socket mode 0660, attestation over the socket, persisted nonce window, time sync.
20. C section 2 and 4.3: state which ledger holds stage rows; the signer fold reads the live ledger; stage rows must be mirrored.
21. A0, B10, C-02, C-06: one settings skeleton unit first; later units add no fields to the same file concurrently.
22. B section 1: live strategies exit before completion or signer supports PumpSwap sells; add human review unit for `EVENT_DECODE_STATUS`.
23. A and B: restart recovery unit; paper fee model unit with before and after hash lines.
24. A10: wire the idle-Grok gate into `run_all.py` or a test, and `ci.yml`; add signer lint, mypy and pip-audit.

**MINOR**
25. Fix claim errors 5, 12, 22, 26, 40. 26. Rename `seed` settings. 27. Add P and L metric families. 28. Document the USD cap versus 1.0 SOL. 29. Remove `stop_loss_poll_seconds` from bounds when event mode is default.
