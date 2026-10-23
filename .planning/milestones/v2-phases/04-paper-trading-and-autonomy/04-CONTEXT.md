# Phase 4: Paper Trading and Autonomy - Context
**Gathered:** 2026-10-21
**Status:** Ready for planning
**Mode:** Seeded from design docs (discuss replaced; decisions locked by R16-R49)

<domain>
## Phase Boundary
Fixture-driven paper desk: curve fills, ledger, replay, risk, supervisor, reports, live refusal, vendor retirement.
Requirement ids (24, equal to ROADMAP Phase 4): STRUCT-004, STRUCT-006, PAPER-001..007, RISK-001..006, AUTO-001..006, SEC-004, GOLIVE-001, GOLIVE-002.
</domain>

<decisions>
## Implementation Decisions

### Locked
- PAPER-001 (R38, R6): fills come only from curve reserves (S0,T0 at decision; S1,T1 at CONFIRMING). Jupiter quote is informational, stored as OrderPlaced.quote source=curve.
- Liquidity: S0 < 10*size -> below_liquidity_floor. fill_cap = S0*2//100; larger orders fill partially at cap, threshold recomputed for executed size, remainder cancelled.
- slippage_exceeded when confirm-out < threshold. tx_dropped (seeded): no cash, no retry. Idempotency on (ticket_id, side, decision_id) (R23).
- Fees integer lamports: venue 100 bps, base 5000, priority micro*CU//1e6, CU 200000 (REVIEW). Network cost on slippage_exceeded only.
- PAPER-005 graduation (R8, R38): BUY on complete curve -> post_graduation_no_reserves. Open position on completion -> PositionClosed reason=graduated at last pre-graduation sell_out, mtm_frozen, Escalation graduated.
- PAPER-005 blind (R25): no price for 300 virtual seconds (blind_max_s) -> PositionClosed reason=blind_flatten at last_good, mtm_frozen, Escalation blind_flatten.
- R24: RiskEngine.check runs inside PaperAdapter.place for every order; no fill without a passing RiskDecision whose order_hash matches. Only RiskEngine appends HaltSet and BreakerTripped.
- RISK-001 check order, 19 steps, first failure wins (R34 ids): ledger_inconsistent, kill_switch, halted, breaker_open, live_gate, approval_missing, approval_mismatch, seat_may_trade, max_trades_per_day, max_open_positions, already_open, creator_already_open, max_trade_fraction, max_token_fraction, daily_loss_halt, drawdown_halt, data_stale, size_too_small, below_liquidity_floor. R34 and paper-engine 5.2 define 19, not 16.
- Sells for exit rules, rug_alert, kill_flatten, blind_flatten, graduated skip steps 2-4 and 9-19.
- R20: nine fraction keys only, in TOML [risk], loaded as RiskBudget; paper_equity_sol converted to lamports once.
- RISK-002 (R5): daily_loss >= 0.05 of day-start equity -> HaltSet daily_loss; drawdown >= 0.15 of peak -> drawdown. Key sha256("HaltSet|reason|utc_day"). Cleared only by `state halt --clear --by human:<name>` (HaltCleared + ApprovalRecorded halt_clear). UTC rollover never clears. FLOOR_HALTED_DAILY keeps U+2013 bytes (R7).
- RISK-003: breakers DataStale (120 s silent or 3 misses; cooldown 60 s), LossVelocity (2 % over 15 min; 30 min), ExecErrors (3 rejects in 10 min; 15 min). Half-open admits one probe; state rebuilt from ledger. Re-check at CONFIRMING (kill switch, halts, breakers, limits): failure rejects with that reason, no fill, no fee.
- RISK-004 (R22): env PUMPGROK_KILLSWITCH read at start; var/KILLSWITCH and alert "KILL <reason>" polled every 5 s and at CONFIRMING. Tool risk.kill_switch: set and flatten_request only; clear is CLI-only. Flatten waits on in-flight barrier, then sells each position (kill_flatten) via PaperAdapter.place.
- PAPER-002 (R26, R28, R32): sqlite WAL, synchronous=FULL; every append in BEGIN IMMEDIATE with seq, prev_hash, hash computed inside; append-only triggers; canonical JSON. Exactly 18 CamelCase types in ledger/events.py; snake_case kinds generated. Restart = snapshot + tail + verify. Tamper -> INCONSISTENT, HaltSet ledger_inconsistent.
- R28/R29: integer lamports and token units; Decimal only for prices and ratios; ULIDs from core/ids.py for correlation_id, decision_id, order_id; approval ids apr-<ULID>; tickets SOL-YYYYMMDD-NNN.
- R21/R41: source in {paper, replay, manual} on every row. paper_started_at = ts_utc of first source=paper row. Replay ledger at var/replay/<dataset>/ledger.sqlite. LiveGate counts source=paper only; refuses ledgers containing source=replay.
- PAPER-004 (R27): FixtureClock; one seeded rng (default 20260101); ts_utc from fixture; LLM lookup by canonical_request_hash; missing record raises ReplayMissingRecord. All waits via Clock.
- PAPER-007 (R33): approval kinds exactly human_buy, human_sell, exit_rule, autonomous_paper, killswitch_clear, halt_clear, live_gate, stored as ApprovalRecorded; consumption is a second row in the OrderPlaced transaction. Manual phrase matched token for token, else approval_mismatch.
- AUTO-001 (R16, R17): manual-ticket and autonomous-paper only; live forces manual-ticket; `state autonomy` appends ConfigChanged plus JournalNote.
- AUTO-002: task per seat; cycle timeout max(30 s, 4*cadence) counts as crash; stale at 3 cadences -> Escalation heartbeat_stale. Restarts: 5 per hour, backoff min(16, 2**n) plus rng jitter; then observe-only latch with Escalation bot_restart_exhausted. Sniper latch: no buys. Exit latch: HaltSet manual. Risk latch: buys rejected, exits continue. Clear: `state resume --seat`.
- AUTO-003: SIGTERM/SIGINT stops scheduling, drains 30 s, snapshots, flushes JSONL, writes status=stopped, exits 0; second signal does not force.
- AUTO-004: /healthz 200 only when status ok; /readyz 200 after CONSISTENT ledger and one cycle per seat; var/health.json every 10 s. No /metrics here.
- AUTO-005: paper-engine 6.7. Unwritable ledger refuses orders, buffers 1000 non-order events (persistence_down); clock skew over 5 s refuses appends (clock_skew).
- SEC-004/GOLIVE-001/002 (R21): nine preconditions in R21 order; check() returns all unmet ids; stderr one [x]/[ ] line per id; exit 3; precondition 8 always unmet. `live confirm` writes HMAC-SHA256 record bound to config hash; never changes mode. LiveAdapter raises LiveGateError after LiveWriteAttempted. No signing code.
- PAPER-006 (R9): str.format; daily 00:05Z, weekly Monday 00:15Z; paper-engine 8.3 sections; ASCII only.
- STRUCT-004/006: port vendor executor, risk, ops, state, log (MIGRATION_MAP 3.1); tests/characterization holds 13 files, at least 164 tests; daily-loss auto-clear (risk.py:106-117) not ported. Delete vendor last (six MIGRATION_MAP 3.4 checks).

### Claude's Discretion
- Tickets: JournalNote note_kind=ticket; NNN = 1 + day's count, same BEGIN IMMEDIATE transaction.
- Files: execution/{__init__,paper_adapter,curve_math,fees,latency}.py; supervisor/{scheduler,seat_task,health,lifecycle}.py; ledger/{store,events,reducer,views,reconcile,export,desk_bus,tickets}.py; reporting/{__init__,daily,weekly,render}.py.
- Conflicts go to R31 and paper-engine 7.1: no quote, escalation, snapshots, journal, dashboard, summary, evidence modules; live tests in tests/execution/; R29 beats cid_/ord_/fill_ prefixes.
- smoke-10m: hand-authored via committed generator, manifest sha256 digests.
</decisions>

<code_context>
## Existing Code Insights
### Reusable Assets
- Vendor (cite): executor.py:85-97,103-134; risk.py:106-117,143-178,238,283-382; ops.py:131,299,406; state.py:48-92; log.py:40-153; models.py:318-328.
### Established Patterns
- Pydantic v2 frozen models; Protocol contracts (interfaces.md 2.7); ledger idempotency via UNIQUE idempotency_key.
### Integration Points
- PaperAdapter -> RiskEngine.check, LedgerStore.append, Clock, PriceSource; ownership.yaml rule execution/live/** after execution/**; Phases 1-3 modules are inputs.
</code_context>

<specifics>
## Specific Ideas
(a) Verification automated: each criterion is a command; no live network; recorded or hand-authored fixtures only.
(b) Checkpoint: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` (ten-seat cycle); other ROADMAP Phase 4 criteria apply.
(c) Fixtures: smoke (Phase 2) and smoke-10m (this phase); no soak-3d.
</specifics>

<deferred>
## Deferred Ideas
- RISK-007, AUTO-007/008, OBS-003..005, GOLIVE-003, SEC-005: Phase 5. Later: soak-3d, CPMM, PumpPortal trade key (R49).
</deferred>

## Orchestrator resolutions (binding, from Phase 2 review)
- R62 (degraded reputation book, fail-closed): the Phase 2 port of reputation.py quarantines a corrupt file and returns a degraded (empty) book (CR-03 fix, commit baa4a47). In the paper engine, a degraded reputation book refuses NEW entries (buys) until the book is restored or rebuilt from the ledger; it never silently treats every creator as clean. Exits, kill-flatten and read-only views still run. RiskEngine reports the degraded state as a breaker-style reason (reputation_degraded) and writes an Escalation event. Add tests in tests/safety/ that corrupt the reputation file and assert that a buy is refused while exits still execute.
- R64 (carry-over from Phase 3, user-approved partials): deliver the TOOL-004 atomic consume-and-order transaction (approval consumption in the same ledger transaction as the order; a repeated decision returns the first Fill; a new read-by-idempotency-key path in the ledger store). Also deliver TOOL-011 full verb coverage: every wired CLI verb runs against its backend, and the NotYetImplementedAdapter exit 5 path is removed for verbs the paper engine now serves.
- R65 (carry-over from Phase 3, user-approved assumption): the bonding-curve layout in curve_layout.py is ASSUMED. Before any paper entry depends on an RPC-derived price, run a live probe against the pump.fun bonding-curve accounts, record the decoded fields as a fixture, mark the fixture VERIFIED, and fail the entry gate with data_unavailable while the fixture is ASSUMED.
