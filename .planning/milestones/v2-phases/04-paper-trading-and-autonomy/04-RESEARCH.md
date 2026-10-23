# Phase 4: Paper Trading and Autonomy - Research

**Researched:** 2026-10-21
**Domain:** Python 3.12 paper-trading engine: curve-faithful fills, hash-chained sqlite ledger, deterministic replay under virtual time, risk engine with halts/breakers/kill switch, supervised ten-seat asyncio loop, daily/weekly reports, fail-closed live gate, vendor retirement
**Confidence:** HIGH for repo facts (file:line cited, discrete values quoted verbatim); MEDIUM for design-derived plans (docs/design/paper-engine.md is binding but partly unimplemented); LOW for pump.fun chain facts (ASSUMED, R65)

**Scope of this research:** read-only. No product code was edited. The test suite and lint were NOT run. Test counts below are `def test_` greps, not `pytest --collect-only`. No network was used; the R65 live RPC probe was NOT executed and remains open.

**Project constraints:** No `CLAUDE.md` exists in the repo. `AGENTS.md` exists (owner bot-02-risk) and was not re-read in full for this research. Directives applied: markdown is ASCII-only, no emoji (task prompt). Workflow flags from `.planning/config.json`: `nyquist_validation: true` (Validation Architecture section included), `security_enforcement: true` (Security Domain included), `tdd_mode: true`.

## User Constraints (from CONTEXT.md)

Copied verbatim from `.planning/phases/04-paper-trading-and-autonomy/04-CONTEXT.md`.

### Locked Decisions
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

### Deferred Ideas (OUT OF SCOPE)
- RISK-007, AUTO-007/008, OBS-003..005, GOLIVE-003, SEC-005: Phase 5. Later: soak-3d, CPMM, PumpPortal trade key (R49).

### Orchestrator resolutions (binding, from Phase 2 review)
- R62 (degraded reputation book, fail-closed): the Phase 2 port of reputation.py quarantines a corrupt file and returns a degraded (empty) book (CR-03 fix, commit baa4a47). In the paper engine, a degraded reputation book refuses NEW entries (buys) until the book is restored or rebuilt from the ledger; it never silently treats every creator as clean. Exits, kill-flatten and read-only views still run. RiskEngine reports the degraded state as a breaker-style reason (reputation_degraded) and writes an Escalation event. Add tests in tests/safety/ that corrupt the reputation file and assert that a buy is refused while exits still execute.
- R64 (carry-over from Phase 3, user-approved partials): deliver the TOOL-004 atomic consume-and-order transaction (approval consumption in the same ledger transaction as the order; a repeated decision returns the first Fill; a new read-by-idempotency-key path in the ledger store). Also deliver TOOL-011 full verb coverage: every wired CLI verb runs against its backend, and the NotYetImplementedAdapter exit 5 path is removed for verbs the paper engine now serves.
- R65 (carry-over from Phase 3, user-approved assumption): the bonding-curve layout in curve_layout.py is ASSUMED. Before any paper entry depends on an RPC-derived price, run a live probe against the pump.fun bonding-curve accounts, record the decoded fields as a fixture, mark the fixture VERIFIED, and fail the entry gate with data_unavailable while the fixture is ASSUMED.

## Phase Requirements

Required by the orchestrator (24 IDs, equal to ROADMAP Phase 4). Status is as observed in this research, not a claim that the requirement is met.

| ID | Requirement (short) | Research support / current state |
|----|---------------------|----------------------------------|
| STRUCT-004 | Port vendor executor, risk, ops, state, log; 13 characterization files, >=164 1:1 tests | Partial. Ported engine pieces exist (engine/exits.py, engine/watcher.py). Characterization dir has 13 files but a different set (see 4.2). Section 4.1, 4.2 |
| STRUCT-006 | Delete vendor tree after six checks | Not met. Vendor tree present; census hits in src/, skills/, rules/, hermes/, scripts/, ci/. Section 11 |
| PAPER-001 | PaperAdapter curve-faithful fills, fees, partials, liquidity floor, slippage, tx_dropped | Missing. Only design (paper-engine.md 2.x) and tool contract (tools/exec/place.py). Section 5 |
| PAPER-002 | WAL ledger, 18 types, hash chain, snapshots, reducer, restart, tamper detection | Partial. store.py has schema, append, verify, by_key, snapshots table. reducer/views/reconcile missing. Section 6 |
| PAPER-003 | JSONL export resumes from meta.export_seq; atomic markdown writes | Missing (ledger/export.py, desk_bus.py absent). Section 6.5 |
| PAPER-004 | FixtureClock replay, recorder, canonical_request_hash, determinism over smoke-10m | Partial. clock.py/fixtures.py/rng.py present; sources/recorder/runner, smoke-10m, LLM hashing missing. Section 7 |
| PAPER-005 | Graduation close, post-graduation reject, blind flatten, MTM every 60 s | Missing. Section 5.4, 5.5 |
| PAPER-006 | daily/weekly reports, str.format, ASCII, snapshot-tested | Partial. tools/journal/render_report.py exists; reporting/ absent; CLI report routes to exit 5. Section 9 |
| PAPER-007 | SOL-YYYYMMDD-NNN tickets, ApprovalRecorded kinds, approval consumption | Partial. approvals.py kinds present; ticket allocation and consumption missing. Section 9 |
| RISK-001 | RiskEngine.check, 19 ordered steps, R20 budget from [risk] | Missing (no risk/ package). Section 8.1 |
| RISK-002 | Daily loss / drawdown HaltSet, FLOOR_HALTED constant, human-only clear | Missing. FLOOR constant absent from src. Section 8.2 |
| RISK-003 | Breakers DataStale/LossVelocity/ExecErrors with half-open, ledger-rebuilt state | Missing (risk/breakers.py absent; vendor CircuitBreaker at vendor ops.py:131). Section 8.3 |
| RISK-004 | Kill switch env/file/alert sources, flatten, CLI-only clear | Partial. tools/risk/kill_switch.py and halt_status.py exist; semantics differ (Section 8.4) |
| RISK-005 | KILL token block for session; seat_may_trade | Missing. Section 8.1 step 8 |
| RISK-006 | Observe-only latches; sniper/risk/exit semantics | Missing. Section 10 |
| AUTO-001 | Ten seats as asyncio tasks, roster order, cadences, autonomy levels | Missing (no supervisor/, no seat bodies). Section 10 |
| AUTO-002 | Heartbeats, restart budget 5/h with backoff+jitter, latch, resume | Missing. `state resume` absent from CLI. Section 10.2 |
| AUTO-003 | SIGTERM/SIGINT drain 30 s, snapshot, health.json stopped, exit 0 | Missing. Vendor helpers drain/install_signal_handlers at vendor ops.py:406,420 |
| AUTO-004 | /healthz, /readyz, var/health.json every 10 s | Missing. Vendor HealthServer at vendor ops.py:299 |
| AUTO-005 | Degraded modes: LLM, RPC, WS, unwritable ledger, clock skew | Missing. Section 10.4 |
| AUTO-006 | `run --mode paper --once --replay tests/fixtures/replay/smoke` = one full ten-seat cycle | Not met. Current `_skip_cycle` is skip-only (cli.py:500-560). Section 10.5 |
| SEC-004 | Live refusal: nine preconditions, exit 3, sends nothing | Largely present in code (live_gate.py, cli.py:484-488). Gaps: refusal lines and stub construction (Section 12) |
| GOLIVE-001 | `live confirm` HMAC record bound to config hash | Missing (cli.py:742-744 returns exit 5). Section 12.3 |
| GOLIVE-002 | LiveGate metrics on source=paper only, notional cap, allowlist | Partial: preconditions 3-9 reported unmet by design; no metrics reader. Section 12.2 |

## Summary

Phase 4 is mostly greenfield. The Phase 1-3 base gives a usable skeleton: a hash-chained sqlite `LedgerStore` with the R32 table schema and append-only triggers (`src/pumpgrok/ledger/store.py:36-60`), the 18 R32 event models (`ledger/events.py:52-72`), a virtual-time `FixtureClock` with a timer heap (`replay/clock.py:79-158`), a manifest-verified fixture loader (`replay/fixtures.py:155-176`), approval and idempotency primitives (`core/approvals.py:30-38`, `core/idempotency.py:68-79`), a fail-closed `LiveGate` (`execution/live/live_gate.py:19-101`), and a `LiveAdapterStub` that appends `LiveWriteAttempted` and raises `LiveGateError` (`execution/live/live_adapter.py:49-75`). Everything else the phase needs is absent: there is no `risk/`, `supervisor/`, or `reporting/` package, no PaperAdapter (only `NotYetImplementedAdapter`, `execution/not_yet_implemented.py:28-73`), no ledger reducer/views/reconcile, no replay sources/recorder/runner, and no seat `Bot` implementation at all (`core/bot.py:97-104` is a Protocol only). The current replay "engine" is evidence-less and always returns `skip reason=data_unavailable` (`engine/pipeline.py:88-108`).

Several defects are not design gaps but present blockers. (1) `PUMPGROK_KILLSWITCH` is not in `NON_SETTING_ENV_NAMES` (`config/settings.py:346-348`), and `_dispatch` runs `load_settings` before any verb (`cli.py:791`), so `PUMPGROK_KILLSWITCH=1 uv run pumpgrok run ...` exits 1 before the kill switch is read, which breaks ROADMAP success criterion 3. (2) The wired verbs open `var/desk/ledger.sqlite` (`cli.py:223`, `:651`) while the live gate checks `var/ledger.sqlite` (`live_gate.py:49`) and the design fixes the paper ledger at `var/ledger.sqlite`. (3) `market.price`, `market.liquidity` and `onchain.lp_status` consume the ASSUMED curve layout with no status guard (`tools/onchain/curve_layout.py:26,60,110`, `tools/market/price.py`), so R65's fail-closed gate has no hook yet.

Primary recommendation: sequence the work so the ledger extensions, settings fixes and replay clock primitives land first; then PaperAdapter with `RiskEngine.check` called in-process; then supervisor and seats; then reports and live confirm; and delete the vendor tree last, only after the characterization ports are green and the STRUCT-006 census is clean. Several requirement conflicts must be decided before planning (Section 14), most importantly the scope of the vendor census (ROADMAP criterion 5 vs MIGRATION_MAP 3.4 check 1) and where the seat cycle bodies live.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Market/curve data ingest (PumpPortal WS, pump.fun REST, Solana RPC) | External feed adapters (`tools/market`, `tools/onchain`) | Replay fixtures (`replay/fixtures.py`) | Only tier that touches network; replay substitutes fixture events |
| Virtual time, timers, seeded RNG | `replay/clock.py`, `replay/rng.py` | - | Single allowlisted module for time and sleep (`tests/safety/test_static_guards.py:21`) |
| Ledger of record (events, snapshots, approvals, tickets) | `ledger/store.py` (sqlite WAL) | `ledger/reducer.py`, `views.py` (pure fold) | Single writer via BEGIN IMMEDIATE (`store.py:135`) |
| Fill computation (curve math, fees, latency) | `execution/curve_math.py`, `fees.py`, `latency.py` (pure) | `execution/paper_adapter.py` (I/O: ledger, clock, price source) | Pure integer math testable without I/O |
| Risk decisions (RiskEngine.check, halts, breakers, kill switch) | `risk/engine.py` (library, called in-process by PaperAdapter) | `risk/breakers.py`, `risk/killswitch.py` | RISK seat is not in the decision path (R24) |
| Seat decisions (signal, safety, entry/exit proposals) | Seat bodies (NOT YET DESIGNED; see Section 14 D-h) | `engine/*` pure ports (scoring, monitor, exits, watcher, reputation) | Ten seats as asyncio tasks under supervisor |
| Scheduling, heartbeats, restarts, shutdown, health | `supervisor/{scheduler,seat_task,health,lifecycle}.py` | `replay/clock.py` for every sleep and timeout | Owner bot-00-chief (ownership.yaml:284) |
| Reports (daily/weekly markdown) | `reporting/{daily,weekly,render}.py` (pure render) | `ledger/views.py` for data | Owner bot-09-journal (ownership.yaml:326) |
| Operator CLI (verbs, exit codes) | `cli.py` | `tools/*` through `ToolRegistry.find` | Human-only verbs (R22, R21) |
| Live refusal | `execution/live/live_gate.py`, `live_adapter.py` | cli.py startup | Exit 3 before any other work (cli.py:484-488) |

## Standard Stack

### Core (already declared; no new packages)

| Library | Version constraint in repo | Purpose | Why this one |
|---------|---------------------------|---------|--------------|
| pydantic | `>=2.14.1,<3` (pyproject.toml:10) | Event, tool, settings models; `extra="forbid"` | Already the project model layer |
| pydantic-settings | `>=2.16.1,<3` (pyproject.toml:11) | Layered TOML + env settings (`config/settings.py:253-260`) | R30 precedence already implemented |
| sqlite3 (stdlib) | Python 3.12.3 present | Ledger WAL store | Single-file, transactional; `store.py` already uses it |
| httpx | `>=0.28.1,<0.29` (pyproject.toml:12) | Outbound HTTP, `MockTransport` in tests | Existing RPC client uses it (`tools/onchain/rpc.py:85`) |
| websockets | `>=17.3,<18` (pyproject.toml:13) | PumpPortal stream (live-paper only) | Declared; replay does not use it |
| tenacity | `>=9.2.1,<10` (pyproject.toml:15) | Retries with `sleep=clock.sleep` | Declared; must receive injected sleep (R27) |
| pyyaml | `>=6.0.3,<7` (pyproject.toml:14) | ownership.yaml, roster YAML | Existing |
| hmac, hashlib (stdlib) | - | GOLIVE-001 HMAC-SHA256; ledger chain sha256 | No external crypto package needed |
| asyncio (stdlib) | - | Seat tasks, supervisor loop | Virtual-time wrappers required (see Pitfalls) |
| pytest / pytest-asyncio | pytest 9.x, pytest-asyncio 1.4.x (pyproject.toml:36-41) | Tests; `asyncio_mode = "auto"` (pyproject.toml:87) | Existing config |
| mypy | strict (pyproject.toml:72-74) | Typed src | Existing gate |

### Not required in Phase 4

| Candidate | Why not |
|-----------|---------|
| prometheus_client | Phase 5 (OBS-003). Design 6.6 names it but metrics are Phase 5 |
| jinja2 | Forbidden by R9; use str.format |
| solders, solana, base58 package, nacl | Forbidden by MIGRATION_MAP 2.4 gate (`--forbid-imports solders,solana,base58,nacl`). The PDA and base58 code for the R65 probe must be pure Python |
| aiohttp / web framework | Not needed; `/healthz` and `/readyz` can use `asyncio.start_server` (vendor HealthServer pattern at vendor ops.py:299) |

### Package Legitimacy Audit

Phase 4 installs no external packages. No `pip`/`uv add` is required, so the legitimacy seam (`gsd_run query package-legitimacy check`) is not applicable. If the planner adds any dependency, it must be run through that gate first.

## Architecture Patterns

### System data flow (target)

```
fixture events (replay) or live feeds
        |
        v
FixtureClock.advance_to(ts) ----> due timers fire (seat wakeups, deadlines)
        |
        v
supervisor tick (1 s) -> roster-order due seats (bot-00 .. bot-09)
        |
        v  each seat: Bot.cycle(registry, trigger) under clock.timeout
ToolRegistry.find(capability, bot=manifest)   (least-privilege, I1-I5)
        |
        v  exec.place (PAPER_WRITE)
PaperAdapter.place(order)
   1. RiskEngine.check(order)  -- 19 ordered steps; order_hash bound
   2. consume approval + OrderPlaced in ONE BEGIN IMMEDIATE transaction
   3. latency sleep (clock.sleep), re-read curve, re-run stop checks (CONFIRMING)
   4. curve_math fill / reject; FillRecorded or OrderRejected
        |
        v
LedgerStore.append(...)  -- seq, prev_hash, hash inside the transaction
        |
        +--> views / reducer (snapshot + tail) --> reports, health.json, desk.md mirror
```

### Recommended file layout (target; R31 names)

```
src/pumpgrok/
  execution/   __init__, paper_adapter, curve_math, fees, latency   (NEW; not_yet_implemented.py retired)
  execution/live/  live_adapter, live_gate                          (EXISTS; extend)
  risk/        __init__, engine, limits, sizing, breakers, killswitch  (NEW package)
  ledger/      store, events (EXIST); reducer, views, reconcile, export, desk_bus, tickets (NEW)
  replay/      clock, rng, fixtures (EXIST); sources, recorder, runner (NEW)
  supervisor/  __init__, scheduler, seat_task, health, lifecycle     (NEW package; lifecycle per CONTEXT)
  reporting/   __init__, daily, weekly, render                        (NEW package)
  engine/      LICENSE-grokbot-pumpfun (NEW, copied from vendor LICENSE; MIGRATION row 84)
tests/
  execution/ (NEW), risk/ (NEW; note tests/tools/risk/ exists), supervisor/ (NEW), reporting/ (NEW),
  engine/ (NEW), replay/ (EXISTS), ledger/ (EXISTS), safety/ (EXISTS), characterization/ (EXISTS, extend)
tests/fixtures/replay/smoke-10m/ (NEW, generator + manifest + events)
tests/fixtures/rpc/bonding_curve/ (NEW, R65 probe records)
```

Ownership (ownership.yaml) already has rules for `src/pumpgrok/risk/**` (bot-02-risk), `supervisor/**` (bot-00-chief), `execution/**` (bot-04-sniper), `execution/live/**` (bot-02-risk, placed after), `reporting/**` (bot-09-journal), `tests/execution/**`, `tests/reporting/**`, and `tests/characterization/execution/**` (ownership.yaml:266-391). No ownership gap was found for the new packages.

### Pattern: check-and-append inside one BEGIN IMMEDIATE transaction

The current `LedgerStore.append` opens its own `BEGIN IMMEDIATE` per call (`ledger/store.py:135`). TOOL-004 (R64) and PAPER-002 need several rows (ApprovalRecorded consumed, OrderPlaced, FillRecorded, PositionOpened) committed atomically, and a read-by-key check inside the same write lock. A new batch API is required; calling `append` inside another open transaction fails (Pitfall P6).

```python
# Target shape (not yet in code). Uses the existing hash rule in store.py:78-101.
def append_batch(self, rows: Sequence[EventDraft]) -> list[dict[str, Any]]:
    db = self._db
    db.execute("BEGIN IMMEDIATE;")
    try:
        # repeat-check inside the write lock (R64)
        # seq/prev_hash from head; compute each row hash exactly as append() does
        ...
        db.execute("COMMIT;")
    except Exception:
        with contextlib.suppress(sqlite3.Error):
            db.execute("ROLLBACK;")
        raise
```

### Pattern: virtual time for every wait

`FixtureClock` only moves when `advance_to(ts)` is called and fires timers due on the way (`replay/clock.py:101-112`). Tasks waiting on `clock.sleep` resume only when the event loop runs. The replay runner therefore needs one sanctioned "yield to loop" primitive inside `replay/clock.py` (the only allowlisted module for `asyncio.sleep`, `tests/safety/test_static_guards.py:21,25-37`). Without it, seats cannot run between fixture events. This primitive does not exist (Pitfall P11).

### Pattern: integer money, Decimal ratios

`events.py` enforces `MoneyInt = Annotated[int, Field(strict=True)]` and rejects float leaves before Decimal parsing (`events.py:34-43`). `core/idempotency.canonical_json` refuses float leaves (`idempotency.py:17-37`). Keep this for every new payload.

### Anti-patterns to avoid

- Calling `asyncio.sleep`, `asyncio.wait_for`, `asyncio.timeout`, `time.time`, `time.monotonic`, `datetime.now` or module-level `random.*` anywhere in `src/pumpgrok` outside `replay/clock.py` and `replay/rng.py` (`test_static_guards.py:25-45`).
- Deriving the same idempotency key for two rows: `idempotency_key` is UNIQUE per row (`store.py:41`). OrderPlaced can own `exec_place_key(...)`; FillRecorded, PositionOpened and ApprovalRecorded need distinct derived keys (scope on order_id).
- Writing a DB or file from the CLI's read-only verbs (`report`, `state status`) through `LedgerStore(...)`: the constructor creates the file (`store.py:107-114`).

## 4. Existing code to port (STRUCT-004 / STRUCT-006)

### 4.1 Vendor-to-target map with current state

| Vendor symbol (file:line, tree at 409e74c) | Target (R31 / MIGRATION_MAP) | State in repo today |
|---|---|---|
| `TOTAL_SUPPLY = 1_000_000_000.0` (executor.py:28), `DRY_RUN_TX = "dry_run"` (:30) | `execution/curve_math.py`, `paper_adapter.py` | Missing. Note `Fill.venue_tx_ref` pattern requires `dry_run:<ULID>` (`core/adapter.py:99`) |
| `price_from_reserves` (executor.py:85-97) float; fallback `market_cap / TOTAL_SUPPLY` | `curve_math.py` `CurveQuote.spot()` (design 2.2) | Missing. Equivalent exists only as `curve_price_sol_per_token` (`tools/onchain/curve_layout.py:120-132`) |
| `DryRunExecutor.buy/sell` (executor.py:100-134); fee-less, no slippage | Replaced by `PaperAdapter` (design 1, row 45-46) | Missing |
| `LiveExecutor` (executor.py:137-172) with 6-step TODO | `execution/live/live_adapter.py` raising LiveGateError | Present in different form (`LiveAdapterStub`, live_adapter.py:35-92). Vendor TODO correctly not carried |
| `build_executor` (executor.py:175-180) | `execution/__init__.py` `build_adapter(settings)` (MIGRATION 2.1 row 272) | Missing. `tools/__init__.py:224` builds `NotYetImplementedAdapter()` instead |
| `new_position` (executor.py:183-195) | `ledger/views.py` Position view | Missing. Core `Position` model exists (`core/adapter.py:112-131`) |
| `RiskManager` state, `restore`, `persist`, `roll_day_if_needed` (risk.py:39-118) | Ledger-derived state; `DailyRollover` event (design 5.5) | Missing. Auto-clear is NOT ported (R5) |
| `halted` (risk.py:131-135) calls `roll_day_if_needed` then `daily_loss >= daily_loss_limit_sol` | `risk/engine.py` halts, fractions not absolute SOL (design 11.2) | Missing. Vendor limit is absolute 2.0 SOL (models.py:320) |
| `position_size` (risk.py:143-147), `MAX_SHARE_OF_REMAINING_BUDGET = 0.30` (:33), `MIN_TRADE_SOL = 0.01` (:36) | `risk/sizing.py`, `[limits] min_trade_lamports = 10000000` | Missing |
| `evaluate` reasons (risk.py:149-178): `daily_loss_limit_hit`, `max_trades_per_day`, `max_open_positions`, `already_open`, `size_too_small` | RiskEngine steps 3, 9, 10, 11, 18 (R34 ids) | Missing. Map to R34 vocabulary, not vendor text |
| `exit_signal` (risk.py:238-280); `EXIT_REASONS` (:216) | `engine/exits.py` | Present (`engine/exits.py:29,53`) |
| `PositionWatcher` (risk.py:283-382) | `engine/watcher.py` | Present (`engine/watcher.py:49`) |
| `CircuitBreaker` (ops.py:131-182) | `risk/breakers.py` base (design 5.3) | Missing |
| `CallBudget` (ops.py:187-229) | `core/budget.py` | Present (`core/budget.py:21`) |
| `RateLimiter` (ops.py:90-128) | `core/ratelimit.py` | Present (`core/ratelimit.py:17`) |
| `GrokOps` precheck (ops.py:235-297) | `core/llm.py` | Present (`core/llm.py:21`) |
| `Metrics` (ops.py:41-86) | `supervisor/metrics.py` (Phase 5) | Not Phase 4 |
| `HealthServer` (ops.py:299-370) | `supervisor/health.py` | Missing |
| `Heartbeat` (ops.py:372-404), `drain` (:406-417), `install_signal_handlers` (:420-431), `cancel_and_wait` (:434-440) | `supervisor/lifecycle.py` | Missing |
| `PipelineState` (state.py:32-41), `StateStore` (state.py:48-91) | `ledger/snapshots` role; sqlite `snapshots` table (`store.py:51-55`) | Partial: table and `write_snapshot`/`latest_snapshot` exist (`store.py:334-352`); reducer missing |
| `TradeLog` (log.py:40-186), `read_log` (log.py:197) | `ledger/export.py` (vendor-shape JSONL, design 3.6) | Missing |
| `models.py` config classes (`:271-624`) | `config/settings.py` | Present in new form; `JitoConfig` and `wallet_private_key` absent (STRUCT-008 satisfied) |
| `monitor.py` `CURVE_COMPLETION_SOL = 85.0` (monitor.py:30) | Graduation threshold | Present in `engine/monitor.py:44` (vendor reference monitor.py:30) |
| `reputation.py` | `engine/reputation.py` (degraded flag at `engine/reputation.py:73`) | Present |

### 4.2 Characterization test set (STRUCT-004)

Current `tests/characterization/` (13 files, `def test_` counts from grep): test_agents 20, test_analyzer 19, test_authority_check 5, test_exits 14, test_holder_check 2, test_jupiter_quote 4, test_monitor 26, test_pipeline 6, test_priority_fee 2, test_reputation 20, test_scoring 13, test_tune 10, test_watcher 10. Total 151 (no parametrize decorators in these files, so collected count should equal 151; not run).

Vendor oracle test counts (verified with `grep -c 'def test_'` in `vendor/grokbot-pumpfun/tests/`): test_agents 21, test_alerts 19, test_analyzer 16, test_config 20, test_filter 21 (ports to test_monitor), test_log 8, test_ops 24, test_pipeline 37, test_reputation 18, test_risk 36, test_scoring 13, test_state 16, test_tune 15. Total 264. The 1:1 subset named by MIGRATION_MAP 3.1 is agents 21 + analyzer 16 + monitor 21 + ops 24 + reputation 18 + risk 36 + scoring 13 + tune 15 = 164.

Mismatch: MIGRATION_MAP 3.1 expects characterization modules for the 13 vendor modules (agents, alerts, analyzer, config, monitor, log, ops, pipeline, reputation, risk, scoring, state, tune). The current directory covers agents, analyzer, monitor, pipeline, reputation, scoring, tune (7) plus exits and watcher (the risk split) and four Phase-2 tool pins. It does NOT cover alerts, config, log, ops, risk (full), or state. Required additions: `test_risk` (36 vendor tests, with the auto-clear case marked), `test_ops` (24), `test_state` (16), `test_log` (8), `test_alerts` (19), `test_config` (20). Adding these at vendor counts gives roughly 151 + 123 = 274 defs, well above 164. The collected count, not the vendor count, is what SC1 checks.

**Basename collision (Pitfall P36):** `tests/tools/risk/test_risk.py` already exists (`find tests -name test_risk.py` returns only that path), and no `__init__.py` exists under `tests/` except `tests/harness/__init__.py`. A new `tests/characterization/test_risk.py` would collide under pytest's default import mode. Use distinct names (for example `test_vendor_risk.py`) or add packages.

**Intentional non-port:** vendor `test_new_day_resets_counters_and_unhalts` (vendor tests/test_risk.py:151) and `test_day_roll_keeps_open_positions` (:166) cover the auto-clear path. STRUCT-004 says the auto-clear test is "marked as such". No marker is declared for that purpose; `pyproject.toml:91-94` declares only `replay` and `characterization`, and `--strict-markers` is on (`pyproject.toml:90`). Use `pytest.mark.skip(reason=...)` or add a marker to pyproject.

### 4.3 Test-count gap (SC1)

SC1 requires `uv run pytest --collect-only -q tests/characterization` to report at least 164. Current directory gives roughly 151 by grep. Adding the six vendor ports at vendor counts clears it with margin, but the 1:1 ports must be real ports (not re-written tests) so the count is defensible under the MIGRATION_MAP rule.

## 5. PaperAdapter and curve math (PAPER-001)

### 5.1 Verified current state

- `ExecutionAdapter` Protocol with five methods: quote, simulate, place, cancel, positions (`core/adapter.py:141-159`).
- `OrderRequest` fields: ticket_id, mint, side, decision_id, size_lamports or token_units, max_slippage_bps, approval_id, quote_id, correlation_id (`core/adapter.py:25-51`).
- `Quote` fields include `source: Literal["jupiter", "curve"]`, `other_amount_threshold`, `price_impact_pct` (`core/adapter.py:54-69`).
- `Fill` fields: order_id, decision_id, status, venue_tx_ref (pattern `^dry_run:[0-9A-HJKMNP-TV-Z]{26}$`, `core/adapter.py:99`), filled_lamports, filled_units, filled_fraction, price_avg, realised_slippage_bps, venue_fee_lamports, network_cost_lamports, route, ledger_seq (`core/adapter.py:93-109`).
- `Position` fields include `price_entry`, `price_peak`, `cost_basis_lamports`, `token_units`, `mtm_source`, `mtm_frozen` (`core/adapter.py:112-131`).
- `NotYetImplementedAdapter` raises on every method (`execution/not_yet_implemented.py:28-73`) and is bound into every exec tool by `build_operator_registry` (`tools/__init__.py:224`, `:140-153`).
- `exec.place` input model PlaceIn requires `approval_id` and `decision_id` and derives the idempotency key with `exec_place_key(ticket_id, side, decision_id)` (`tools/exec/place.py`, `core/idempotency.py:68-79`). The module docstring states the atomic consume-and-order transaction "must NOT be implemented here" (`place.py:1-7`), so it is Phase 4 work (R64).
- `run_place` rejects a BUY when `RiskBudget.may_open_exposure` is false, with reason `seat_may_trade` (`place.py`, `core/risk_budget.py:46-48`).

### 5.2 Curve math (design 2.2, integer form)

Pre-graduation pump.fun is constant-product on virtual reserves (`CITED: docs/design/paper-engine.md:103-115`):

```
spot(S,T)        = Decimal(S) / Decimal(T)            lamports per token base unit
buy_out(S,T,x)   = T * x // (S + x)                    token units for x lamports (x is net of venue fee)
impact_buy(S,x)  = Decimal(x) / Decimal(S)
sell_out(S,T,t)  = S * t // (T + t)                    lamports for t token units (gross of venue fee)
impact_sell(T,t) = Decimal(t) / Decimal(T + t)
post_buy(S,T,x)  = (S + x, T - buy_out(S,T,x))
```

Gate and fee formulas (design 2.3, 2.6):

```
venue_fee_lamports    = size_lamports * venue_fee_bps // 10_000        (100 bps, REVIEW)
base_fee_lamports     = 5_000                                           (REVIEW)
priority_fee_lamports = micro_lamports_per_cu * compute_units // 1_000_000   (CU 200_000, REVIEW)
x_net                 = size_lamports - venue_fee_lamports
cash_debit            = size_lamports + network_cost_lamports
liquidity floor:  S0 < liquidity_floor_multiple * size  -> reject below_liquidity_floor
fill_cap          = S0 * partial_fill_fraction_num // 100  (2 %; design writes S0 * 0.02, floored)
if size > fill_cap: fill fill_cap, threshold recomputed for filled size, remainder cancelled
```

Worked example from design 2.9 (self-consistent on my recomputation: `766428571428571 * 198000000 // 42198000000` is about 3.59621e12 units, i.e. 3,596,210 whole tokens). Use this as a golden-vector source, but compute the golden integers from the formulas in code, not from the rounded prose (see Section 5.2 and Pitfall P30).

### 5.3 Quote source and slippage (design 2.4)

Fill basis is ALWAYS the curve quote synthesised from `(S0,T0)` (R38). Jupiter `exec.quote` is informational and stored on OrderPlaced as `source="curve"` with the Jupiter quote id in detail when fetched. Threshold: `other_amount_threshold = out_amount * (10_000 - slippage_bps) // 10_000`; sell side applies venue fee first. At CONFIRMING: if `out_at_confirmation < threshold` reject `slippage_exceeded`; for a partial fill, recompute threshold for executed size before comparing.

### 5.4 Graduation and blind (design 2.2, 5.3)

- BUY where `CurveState.complete` is true at decision or CONFIRMING -> `OrderRejected reason=post_graduation_no_reserves`.
- Open position whose curve turns complete (or `S >= CURVE_COMPLETION_SOL` when `complete` is absent) -> adapter closes at last pre-graduation sell_out, `PositionClosed reason=graduated`, `mtm_frozen=true`, `Escalation kind=graduated`. No order and no approval.
- Blind: no price for `blind_max_s = 300` virtual seconds -> `PositionClosed reason=blind_flatten` at `last_good`, `mtm_frozen=true`, `Escalation kind=blind_flatten`. Design 5.3 also says sells are not blocked by this path.

### 5.5 Latency and drop

`latency_s = clip(lognormal(mu=ln(1.2), sigma=0.5), 0.4, 20.0)`; `dropped = rng.random() < 0.02` (design 2.5, REVIEW). Use the injected `random.Random` instance (allowed by `test_static_guards.py:40-42`: only module-level `random.*` is banned). `tx_dropped` means no cash and no retry; `slippage_exceeded` charges network cost; `tx_dropped` does not (design unverified item 8, REVIEW).

### 5.6 State machine and in-flight barrier (design 2.8)

NEW -> ACCEPTED (after RiskEngine pass) -> CONFIRMING (after latency) -> FILLED | PARTIAL | REJECTED. The adapter keeps an in-flight set of ACCEPTED/CONFIRMING orders; kill-flatten waits on it (design 5.4). `cancel` succeeds only in ACCEPTED (design 2.8 and `tests/execution/test_paper_fill_model.py` description).

### 5.7 Event-model gaps (PAPER-001, PAPER-002)

Compare design 3.3 with `ledger/events.py`:

- `FillRecorded` (events.py:118-134) lacks `curve_before{S,T}`, `curve_after{S,T}`. Design requires them.
- `OrderRejected` (events.py:106-115) lacks `quote_out`, `threshold`, `confirm_out`. Design requires them for slippage explainability.
- `OrderPlaced` (events.py:89-103) carries `quote_json` (free string) rather than typed `quote{out_amount, other_amount_threshold, price_impact_pct, source}`. Acceptable if the planner keeps the JSON string, but then tests must parse it.
- `PositionClosed.reason` is a free `str` with a description (events.py:160-163), not an enum. Enforce the nine values in code.

Changing these models requires regenerating `contracts/events/*.schema.json` (18 files exist) and passing `tests/ledger/test_events.py`, which checks schema equality and money types (`test_events.py:61`).

## 6. Ledger and WAL (PAPER-002, PAPER-003, R26, R28, R32, R41, R64)

### 6.1 Verified current state (`src/pumpgrok/ledger/store.py`)

- Schema (`store.py:32-60`): `events(seq INTEGER PRIMARY KEY, ts_utc, source, correlation_id, idempotency_key UNIQUE, type, payload_json, prev_hash, hash UNIQUE)`, append-only triggers on UPDATE and DELETE for `events` and `snapshots`, `snapshots(seq, ts_utc, state_json)`, `meta(key, value)`.
- Pragmas (`store.py:111-113`): `journal_mode = WAL`, `synchronous = FULL`, `busy_timeout = 5000`.
- Hash rule (`store.py:78-101`): sha256 over canonical JSON of `prev_hash, seq, ts_utc, source, correlation_id, idempotency_key, type, payload_json`, matching design 3.2 (R28, locked Q3).
- `append` (`store.py:116-183`): validates source in `SOURCES = frozenset({"paper","replay","manual"})` (`store.py:30`), validates payload with the event model, opens `BEGIN IMMEDIATE` (`store.py:135`), reads head, inserts, commits; rolls back and re-raises on error.
- `verify` (`store.py:185-221`): recomputes every row hash in seq order; raises `LedgerInconsistent` (code `ledger_inconsistent`, `store.py:64-67`) on prev-hash or hash mismatch. It does NOT run design 3.5 integrity checks 6a-6f (cash, positions, full-replay equality, snapshot chain hash, source equality).
- `by_key(idempotency_key)` (`store.py:291-322`) gives the read-by-key path R64 needs.
- Snapshots: `write_snapshot`, `read_snapshots`, `latest_snapshot` (`store.py:324-352`); no cadence logic.
- `recreate_ledger_db` (`store.py:70-75`) deletes sqlite and -wal/-shm for replay runs.

### 6.2 Gaps

1. No reducer, views, reconcile, desk_bus, tickets modules (none exist).
2. No batch append; see the batch pattern under Architecture Patterns.
3. Duplicate key surfaces as a raw `sqlite3.IntegrityError` (UNIQUE on `idempotency_key`, `store.py:41`). Map it to a domain refusal (`ledger_duplicate` or first-fill return) in the adapter (Pitfall P7).
4. `append` does not enforce `payload.source == row.source` (design 3.5 check 6f).
5. No clock-skew check and no `LedgerUnavailable` buffering (AUTO-005; `core/errors.py:39` defines the class only).
6. Snapshot cadence (`ledger.snapshot_every_events = 500`, `snapshot_every_s = 300`, design 3.2) not implemented.
7. `meta` keys (`schema_version`, `ledger_id`, `initial_equity_lamports`, `created_ts_utc`, `source`, `autonomy_level`, `export_seq`) are not written by any code (grep finds no writer).

### 6.3 Restart procedure (design 3.5) to implement

snapshot + tail replay + verify; then checks 6a-6f; status CONSISTENT or INCONSISTENT; INCONSISTENT appends `HaltSet(reason=ledger_inconsistent)` and runs observe-only. Design says the full-replay state must equal the snapshot-tail state "field-for-field" (check d) and this is cheap at paper scale.

### 6.4 Idempotency (R23, R64): exact rule

- OrderPlaced idempotency key: `exec_place_key(ticket_id, side, decision_id)` (`core/idempotency.py:68-79`, 32 hex chars).
- Other rows of the same order need different keys (UNIQUE per row). Derive them with `derive_idempotency_key(tool, bot, payload, scope=order_id)` (`idempotency.py:49-65`) or a fixed prefix convention. Choose one convention and test it (D-p).
- Repeat decision (same key): look up OrderPlaced by key with `by_key`; return the first FillRecorded (or OrderRejected) for that order_id. Do this inside the same BEGIN IMMEDIATE as any write (R64).

### 6.5 JSONL export and desk markdown (PAPER-003)

- `export_seq` lives in `meta` (design 3.6). JSONL line shape: `{seq, ts_utc, source, correlation_id, type, payload}`.
- Vendor-compatible `trades.jsonl` keys come from `vendor/grokbot-pumpfun/src/log.py:98-183`; `tx_hash` bare `dry_run`, ULID in `venue_tx_ref`.
- `core/atomic_write.py` provides `atomic_write_json` only (`atomic_write.py`, function near line 15). Markdown and text exports (`desk.md`, `paper-YYYY-MM-DD.md`, reports) need a text variant with the same tmp + fsync + `os.replace` ordering. Do not use json for markdown.

### 6.6 Single writer across processes

Design 3.1 says the supervisor and CLI writers share one file via BEGIN IMMEDIATE. The CLI and the supervisor are separate processes. The test `tests/ledger/test_single_writer_concurrent_appends.py` (design 9) must use two real processes. `busy_timeout=5000` (`store.py:113`) is the only wait; a timed-out CLI append must be reported (design 16).

## 7. Replay, FixtureClock, determinism (PAPER-004, AUTO-006)

### 7.1 Verified current state

- `Clock` protocol: now, monotonic, utc_iso, sleep, timeout (`replay/clock.py:22-33`). `WallClock` (`clock.py:50-68`) is the only place that reads host time. `FixtureClock` (`clock.py:79-158`).
- `FixtureClock` has NO `utc_day()` method (design 4.2 and 5.5 use `clock.utc_day()`); only `utc_iso` (`clock.py:98-99`). Add it.
- `FixtureClock` has NO sanctioned yield primitive; `advance_to` fires timers synchronously (`clock.py:101-112`) and tasks resume only when the loop runs.
- `FixtureClock.timeout` cancels the current task on virtual deadline and raises `TimeoutError` (`clock.py:132-158`).
- `make_rng(seed)` returns `random.Random(seed)` (`replay/rng.py:15-16`), default seed `20260101` (`rng.py:12`). Only allowlisted constructor (`test_static_guards.py:23`).
- Fixture format today (`tests/fixtures/replay/smoke/events.jsonl`): four lines, each with `ts_utc` ISO string, `kind: tick`, `mint`, integer `S`, integer `T`, `complete`, `source` (`rest` or `pumpportal`). Manifest `sha256` lists only `events.jsonl`.
- `load_dataset` verifies manifest, digests and stray files (`fixtures.py:96-120`), then requires `events.jsonl` in the sha256 map (`fixtures.py:157-158`); `event_epoch` parses `ts_utc` (`fixtures.py:69-71`). `FixtureManifest` is `extra="forbid"` (`fixtures.py:39-40`).

### 7.2 Gaps and conflicts

- Design 4.3 uses multiple files (`pumpportal.jsonl`, `pumpfun_rest.jsonl`, `jupiter.jsonl`, `rpc.jsonl`, `ticks.jsonl`, `llm.jsonl`) with a leading `ts` epoch float, merged by `(ts, file_order, line_no)`. The current loader reads one file and rejects stray files. Either the loader changes (sources, merge) or the dataset stays single-file. D-d.
- LLM replay: `canonical_request_hash` appears only in docs (grep of src, tests, ci, contracts). Recording (`core/llm.py`) and replay lookup (`ReplayMissingRecord`) do not exist. The smoke checkpoint runs the full ten-seat cycle, so either bot-08-signal runs rule-based only in replay, or `llm.jsonl` must hold a record for every LLM request the cycle makes. D-c.
- Recorder hook on RPC: none (`grep recorder src/pumpgrok` is empty). Design 4.4 needs it in `tools/onchain/rpc.py`.
- `pumpgrok run --record` and `replay trim|rebuild-ticks` are `_not_implemented` today (`cli.py:489-490`, `:747-748`).

### 7.3 Smoke dataset and smoke-10m (design 4.6; CONTEXT specifics c)

- `smoke` (checkpoint): hand-authored, 4 ticks, 2 mints. Replay produces one skip. The MIGRATION_MAP batch-2 line that says "recorded smoke replaces the hand-written one" requires network and conflicts with the no-network constraint (D-c). Keep it hand-authored.
- `smoke-10m` (SC2, SC3): must be generated by a committed generator, manifest sha256 per file, under 1 MB, and must contain: at least one full fill, one partial fill, one `slippage_exceeded`, one `below_liquidity_floor`, one 180 s DataStale hole, one LLM `timeout` outcome, one exit by `stop_loss` or `take_profit` (design 4.6). The generator must be deterministic (seeded) so the committed bytes are reproducible.
- Determinism: `events.hash` = sha256 over concatenated row hashes in seq order (design 4.5 item 1). `verify --fixture` runs twice, compares events.hash, JSONL bytes and final state (SC2; design 9).

### 7.4 Design of the replay runner (to implement)

```
run_replay(dataset_dir, settings):
  ds = load_dataset(dataset_dir)            # verify digests before any ledger file (fixtures.py:155-176)
  clock = FixtureClock(start=epoch(ds.events[0]))
  ids = IdFactory(clock, make_rng(settings.replay.seed))
  ledger = LedgerStore(recreate_ledger_db(LEDGER_ROOT / name / "ledger.sqlite"))
  for event in ds.events:
      clock.advance_to(epoch(event))        # fires due timers
      await clock.yield_now()               # NEW primitive in replay/clock.py (allowlisted)
      deliver event to PriceSource / feeds
  final: verify(), snapshot, export
```

## 8. Risk engine, breakers, kill switch (RISK-001..006)

### 8.1 The 19 failure steps and the pass step

Verbatim from `CONTEXT.md:23` (matches `docs/design/paper-engine.md:556-575`). Steps 13 and 14 cap rather than reject (`decision.capped = true`), per design 5.2 lines 568-569.

| # | Step id (R34) | Rule (design 5.2) | Rejects or caps |
|---|---|---|---|
| 1 | ledger_inconsistent | ledger status CONSISTENT (3.5) | rejects |
| 2 | kill_switch | no active kill switch (file and alert re-polled now; env read at start) | rejects buys (sells allowed) |
| 3 | halted | no active halt; detail carries reason | rejects |
| 4 | breaker_open | no breaker open; detail carries breaker name | rejects buys |
| 5 | live_gate | order.adapter == "paper" or LiveGate.check() empty | rejects |
| 6 | approval_missing | manual-ticket: unconsumed ApprovalRecorded for ticket; autonomous-paper: mint ApprovalRecord(autonomous_paper) | rejects |
| 7 | approval_mismatch | approval matches ticket, mint, size, slippage token for token (ApprovalRecord.matches) | rejects |
| 8 | seat_may_trade | buys only from bot-04-sniper, sells only from bot-06-exit; not observe-only; bot-02-risk not latched for buys | rejects |
| 9 | max_trades_per_day | counters.trades_today < max_trades_per_day | rejects |
| 10 | max_open_positions | open count < max_open_positions (buy only) | rejects |
| 11 | already_open | mint not already open (buy only) | rejects |
| 12 | creator_already_open | creator has no open position if one_position_per_creator (buy only) | rejects |
| 13 | max_trade_fraction | size <= max_trade_fraction * equity | CAPS |
| 14 | max_token_fraction | cost_basis(mint) + size <= max_token_fraction * equity | caps; rejects if cap < min_trade_lamports |
| 15 | daily_loss_halt | evaluate_halts: daily loss < 0.05 of day-start equity; else HaltSet daily_loss + reject | rejects |
| 16 | drawdown_halt | evaluate_halts: drawdown < 0.15 of peak; else HaltSet drawdown + reject | rejects |
| 17 | data_stale | equity from MarkToMarket younger than mtm_interval_s (60 s); else refresh or reject | rejects |
| 18 | size_too_small | size >= min_trade_lamports after caps | rejects |
| 19 | below_liquidity_floor | S0 >= liquidity_floor_multiple * size (adapter re-checks at fill) | rejects |
| 20 | pass | RiskDecision(passed=True, size_lamports, caps, order_hash, approval_id) | - |

Sells with reason in exit rules, rug_alert, kill_flatten, blind_flatten or graduated skip steps 2-4 and 9-19 (design 5.2 line 578). `graduated` and `blind_flatten` closes carry no order and still append PositionClosed.

Re-check at CONFIRMING (design 2.8, RISK-003): kill switch, halts, breakers, limits, i.e. steps 2-4 and 13-19. Reject with the same reason; no fill; no fee.

### 8.2 Halts and FLOOR constant

- `evaluate_halts` runs at steps 15-16, at the start of every risk-seat cycle, and after every PositionClosed or MarkToMarket (design 5.2 lines 580-591).
- Idempotent HaltSet per `(reason, utc_day)` through the ledger UNIQUE key; RiskEngine must catch the IntegrityError and treat it as already set (Pitfall P7).
- Constant: `FLOOR_HALTED_DAILY` in `risk/engine.py` must be the constitution's bytes: `FLOOR HALTED <U+2013> DAILY LOSS LIMIT` with U+2013 (`rules/pumpgrok-team.mdc:34`; that line contains an en dash, verified by byte grep: 2 matching lines). `grep` of `src/` and `tests/` for `FLOOR HALTED` finds nothing today. The research document is ASCII-only, so the code must carry the U+2013 bytes and this document writes the escape.
- `desk.md` mirror: `HaltSet` writes `Halt: true` plus `FLOOR HALTED - <reason> @ <ts>` via tmp and `os.replace` (design 3.6 row 412; `tools/desk_state.py:195-210` for the vendor-shape reference).

### 8.3 Breakers (design 5.3)

| Breaker | Trip (REVIEW) | Cooldown | Reset | While open |
|---|---|---|---|---|
| DataStale | no PumpPortal frame AND no REST curve read for 120 s, OR 3 consecutive missing prices on an open position | 60 s after first fresh tick | 3 consecutive fresh ticks within 30 s | no buys; EXIT evaluates on last_good up to blind_max_s |
| LossVelocity | equity fell >= 0.02 over rolling 15 min of MTM points | 30 min | window loss < 0.5 % for 5 min | no buys; exits allowed |
| ExecErrors | 3 OrderRejected with reason in {tx_dropped, slippage_exceeded, quote_unavailable, rpc_error} in 10 min | 15 min | one probe fills | no buys; exits allowed |

Hysteresis: `closed -> open -> half_open -> closed | open`; half-open admits exactly one probe; `reset_after_ok` successes before closed. Base class: vendor `CircuitBreaker` (vendor ops.py:131-182: consecutive failures, `opened_at`, cooldown, `is_open`, `state`, `record_success`). Breaker state is rebuilt from the last BreakerTripped without a later BreakerReset (design 5.3 last paragraph); the cooldown deadline uses the injected clock.

### 8.4 Kill switch (design 5.4) and current tool drift

- Sources: env (`PUMPGROK_KILLSWITCH` set and not in {"", "0", "false"}, read once at start); file `var/KILLSWITCH`; alert command `KILL <reason>` from an allowlisted chat id (design unverified item 9).
- Current tools: `tools/risk/kill_switch.py:111` and `tools/risk/halt_status.py:75` both test `os.environ.get("PUMPGROK_KILLSWITCH", "").strip() == "1"` at call time. This differs from the design (exact `"1"` versus `set and not in {"","0","false"}`; read at call versus read at start). Decide one rule (D-m) and make the CLI and tools agree.
- `risk.kill_switch` writes `KillSwitchSet` via `LedgerStore.append` idempotent per minute (`tools/risk/kill_switch.py:70-104`). Design wants the per-minute key to become `(reason, utc_day)`-style or `(source, flatten)`; decide.
- Clear is CLI-only (`killswitch clear --by human:<name> --reason`), appends KillSwitchCleared plus ApprovalRecorded killswitch_clear, refused while any source is still set (design 5.4). `cli.py:611-614` returns exit 5 today.
- `flatten` (design 5.4): waits on the in-flight barrier, then one sell per open position with reason `kill_flatten`, minted by RiskEngine `autonomous_paper` approval. EXIT seat not in the path.

### 8.5 Daily rollover (design 5.5)

At the first risk cycle after 00:00:00Z: force MTM; append DailyRollover; reset counters; open positions untouched; HaltSet NOT cleared (R5). Vendor auto-clear (vendor risk.py:106-118 and `halted` at :131-135) is intentionally not ported; its test is at vendor tests/test_risk.py:151.

## 9. Reports, tickets, approvals (PAPER-006, PAPER-007)

### 9.1 Reports

- `report --daily|--weekly` (cli.py:353-356) routes to the find-only path (`cli.py:759`, `_FIND_ONLY_ROUTES["report"] = ("journal", ("journal.render_report",))`), which returns exit 5 (`_skip_use`, `cli.py:292-298`).
- `tools/journal/render_report.py` already exists (`_REPORT_TEMPLATE` at line 37, `report_path_for` at 78, `_write_report` at 83, `run_render_report` at 97). Decide whether `reporting/render.py` reuses or replaces it (D-q). Either way the output must be ASCII and use str.format (R9).
- Design 8.3 sections, in order: Summary; Trades; Open positions; Rejected signals (by R34 reason); Safety outcomes (RUG verdicts from JournalNote note_kind=verdict); Risk events; Bot health; Data freshness; Live gate (weekly only, all nine ids); Unverified. Lamports rendered as SOL with 9 decimals only at render time.
- Empty-ledger problem: `LedgerStore(path)` creates the database on construction (`store.py:107-110`). `report --daily` on a machine with no ledger must still exit 0 (SC4). Use a read-only connection (`file:...?mode=ro`, design 3.1) or treat a missing ledger as an empty view. Do not create a ledger file from a read-only verb.
- Schedule (R40): daily 00:05Z, weekly Monday 00:15Z; scheduler in bot-09-journal (design 6.2). These are scheduled supervisor jobs, not cron.

### 9.2 Tickets and approvals

- Ticket regex `^SOL-\d{8}-\d{3}$` (`cli.py:77`, `tools/exec/place.py` PlaceIn). Ticket allocation: NNN = 1 + count of that day's tickets, computed in the same BEGIN IMMEDIATE transaction (CONTEXT discretion); store as JournalNote note_kind=ticket. `ledger/tickets.py` is missing.
- `ApprovalRecord` (core/approvals.py:20-96): kinds Literal exactly `"human_buy","human_sell","exit_rule","autonomous_paper","killswitch_clear","halt_clear","live_gate"` (approvals.py:30-38), matches R33. HUMAN_KINDS (approvals.py:50-59) excludes autonomous_paper. ORDER_SIDES maps human_buy->buy, human_sell->sell, exit_rule->sell (approvals.py:62-66).
- Consumption: ApprovalRecorded row with `consumed=true` written inside the order's transaction (R23, R33; design 3.3).
- `cli._paper` currently refuses every paper trade with R63 (`cli.py:573-590`) because no approval-issue path exists. Phase 4 must implement issuance (human phrase `approve <ticket> <mint> <size> <slippage>` matched token for token, design 7.5) and consumption.

## 10. Supervisor and autonomy (AUTO-001..006, RISK-006)

### 10.1 Cadence and roster order (design 6.2)

| Seat | Trigger | Cadence (REVIEW) | Write tools |
|---|---|---|---|
| bot-00-chief | timer | 60 s | none (JournalNote, ticket files) |
| bot-01-scout | event + sweep | sweep 10 s | none |
| bot-02-risk | timer | 5 s | risk.kill_switch set/flatten_request; desk.event_emit escalation |
| bot-03-whale | timer, per candidate | 120 s | none |
| bot-04-sniper | queue, serialised | immediate | exec.place buy |
| bot-05-rug | timer | 30 s | desk.event_emit escalation |
| bot-06-exit | timer | 15 s | exec.place sell |
| bot-07-shill | timer | 300 s | none |
| bot-08-signal | queue | immediate | none |
| bot-09-journal | timer + daily | 300 s; 00:05Z; Monday 00:15Z | MarkToMarket every 60 s; JournalNote; reports |

Tick: `supervisor.tick_s = 1`; due seats started in roster order 00..09 (design 6.2). Each cycle under `clock.timeout(seat.cycle_timeout_s)` with default 4 x cadence, min 30 s; timed-out cycle counts as crash. `asyncio.timeout` and `asyncio.wait_for` are banned in src (test_static_guards.py:28-29).

### 10.2 Heartbeats and restarts (design 6.3-6.4)

- Heartbeats are recorded by the task wrapper (`seat_task.py`), not by the bot: `(started_at, finished_at, ok, duration_s)`.
- Stale: `clock.now() - finished_at > 3 * cadence` -> edge-triggered `Escalation(heartbeat_stale)`.
- Restart: token bucket capacity 5, refill 1 per 12 min (5/h); backoff `min(16, 2 ** attempt) + rng.uniform(0, 1)`; attempt resets after 1 h clean.
- Latch observe-only with `Escalation(bot_restart_exhausted)`; per-seat effects: sniper -> no buys desk-wide; exit -> `HaltSet(manual, "exit seat observe-only")`; risk -> buys off, exits continue, RiskEngine still runs inside PaperAdapter.place.
- `pumpgrok state resume --seat <seat> --by human:<name>` clears the latch. Currently absent: `_add_state` defines only `status`, `halt`, `autonomy` (`cli.py:398-413`).
- Escalation relay: the supervisor watches the ledger tail and relays each new Escalation, HaltSet, KillSwitchSet, BreakerTripped and LiveWriteAttempted to `notify.alert` with alert kind equal to the escalation kind (design 6.4 last paragraph). Notifier today is `HttpxNotifier` (`tools/notify/notifier.py:80-184`); design needs stdout and file sinks (MIGRATION row 105 and batch 2 names `tools/notify/{base,stdout,file}.py`, none exist).

### 10.3 Shutdown and signals (design 6.5, AUTO-003)

SIGTERM/SIGINT -> stop event -> stop scheduling -> `drain(tasks, 30)` (vendor ops.py:406-417) -> snapshot -> flush JSONL -> `var/health.json status=stopped` -> exit 0. Second signal logs and does not force (vendor pipeline semantics). Use `loop.add_signal_handler` (vendor `install_signal_handlers`, ops.py:420-431). The grace wait uses `clock.sleep`.

### 10.4 Health and degraded modes (design 6.6-6.7)

- `/healthz`: 200 only when status ok, else 503 (vendor ops.py:349-355 contract). Keys: vendor `status()` keys (`pipeline.py:392-419` in vendor) plus `autonomy_level, ledger_status, ledger_source, kill_switch, breakers{...}, seats{...}, equity_lamports, drawdown_pct, data_age_s`.
- `/readyz`: 200 only after CONSISTENT ledger and one cycle per seat.
- `var/health.json`: `/healthz` body written atomically every 10 s.
- Degraded rows (design 6.7): LLM down -> rule-based scoring live-paper; replay -> ReplayMissingRecord; RPC down -> failover then BLIND (missing data = KILL per agents/risk.md); WS down -> reconnect 1->60 s, DataStale after 120 s; REST down -> last PumpPortal tick, blind_flatten at blind_max_s; ledger unwritable -> refuse orders, bounded buffer 1000 (`ledger.buffer_max_events`), Escalation(persistence_down); clock skew > 5 s -> refuse appends, Escalation(clock_skew).

### 10.5 Ten-seat checkpoint (AUTO-006)

Current `_skip_cycle` (`cli.py:500-560`) runs one `decide_replay` and appends one JournalNote. The Phase 4 checkpoint requires one full ten-seat cycle through engine, RiskEngine and PaperAdapter. No seat bodies exist (`core/bot.py:97-104` is a Protocol only; `grep "def cycle"` finds nothing in src). Seat-level behaviour must be designed (D-h) before the checkpoint is achievable. `tests/test_skip_cycle.py` pins the skip-only behaviour and must be rewritten, not silently broken (Section 13 P5).

## 11. Vendor retirement (STRUCT-006)

### 11.1 Census (run this session; read-only)

Census run with `grep -rln -F` (ripgrep was not invoked); results:

Under ROADMAP criterion 5 scope (`src skills agents rules hermes scripts ci contracts prompts`), today:
- `src/pumpgrok/tools/onchain/curve_layout.py` (docstring provenance)
- `src/pumpgrok/engine/*.py` and `engine/agents/*.py`: exits, tune, reputation, analyzer, monitor, scoring, models, `__init__`, watcher, agents/base, agents/auditor, agents/timing, agents/narrative, agents/checker, agents/__init__ (all single docstring/provenance references)
- `skills/grokbot-pipeline/SKILL.md` (lines 21, 25, 33, 44, 58)
- `rules/pumpgrok-team.mdc:42` (rule 9: "Vendored engine is dry-run evidence only. The grokbot-pumpfun engine under `vendor/grokbot-pumpfun/` ...")
- `hermes/README.md:93`
- `scripts/README.md:36`
- `ci/tests/test_gates.py:112-113` (ownership fixture paths)

Beyond the ROADMAP scope but included by MIGRATION_MAP 3.4 check 1 (`rg ... . --glob '!vendor/**'`): `tests/characterization/test_{watcher,reputation,agents,scoring,tune,exits,analyzer,monitor}.py` (oracle citations in docstrings), `tests/core/test_analyzer_request_timeout.py:9`, `tools/pipeline_evidence.py` (DEFAULT_LOG), `README.md`, `AGENTS.md`, `ARCHITECTURE.md`, `SETUP.md`, `scripts/check.sh` (lines 105, 131, 164 mention `vendor` but not the path string; the 409e74c pin check at 105 stays valid against docs/VENDOR_PIN.md), and many docs/.planning files (historical).

`409e74c` (pin commit) outside vendor: scripts/check.sh:105 (pin check, keep and retarget to docs/VENDOR_PIN.md), docs/*, SETUP.md, README.md, ARCHITECTURE.md, skills/grokbot-pipeline/SKILL.md, .planning/* (history). MIGRATION 3.4 check 3 allows only docs/VENDOR_PIN.md after the move, which conflicts with the planning history (D-b).

`src.pipeline` outside vendor: docs/FOUNDATION_STACK.md, docs/MIGRATION_MAP.md, docs/DISCOVERY.md, skills/grokbot-pipeline/SKILL.md, .planning history.

### 11.2 Decisions and checks

- D-b: MIGRATION_MAP 3.4 check 1 is repo-wide (`. --glob '!vendor/**'`), while ROADMAP criterion 5 is narrow. A repo-wide zero is impossible without rewriting historical .planning and docs/MIGRATION_MAP text. Recommend: enforce the ROADMAP list (criterion 5) plus MIGRATION check 4-6, and record the historical references as an explicit exception in docs/VENDOR_PIN.md.
- `rules/pumpgrok-team.mdc:42` is inside the constitution, which D2/R7 keep verbatim. The R7 byte rule covers the FLOOR and UNKNOWN strings, not rule 9's path. Recommend retargeting only the path in rule 9 to `src/pumpgrok/engine/`, and noting it in the closing report. Needs user sign-off (D-b2).
- LICENSE: copy `vendor/grokbot-pumpfun/LICENSE` to `src/pumpgrok/engine/LICENSE-grokbot-pumpfun` (MIGRATION row 84). Not present today (`ls src/pumpgrok/engine/ | grep -i license` empty).
- Delete order: copy LICENSE, retarget references, port characterization, then `git rm -r vendor/grokbot-pumpfun`. Vendor tests are the oracle until then (`cd vendor/grokbot-pumpfun && python3 -m pytest -q` must still pass; ROADMAP STRUCT-003 SC2).
- Vendor pyproject declares `solders>=0.21` and `solana>=0.34` (vendor pyproject.toml:17-18) but nothing imports them; root pyproject does not declare them (verified: root dependencies lines 10-15 contain no solders or solana). Deleting vendor removes the declarations.

## 12. Live gate and go-live (SEC-004, GOLIVE-001, GOLIVE-002)

### 12.1 Verified current behaviour

- `run --mode live --once` exits 3 before any other work (`cli.py:484-488`), and `refusal_lines` prints unmet items only (`live_gate.py:92-101`). SC4 (`run --mode live --once` exit 3, sends nothing) is met by this path.
- `PRECONDITION_IDS` verbatim (`live_gate.py:19-29`): `"mode_live","live_enable_env","min_paper_days","performance_thresholds","wallet_allowlist","notional_cap","confirmation_record","adapter_registered","no_active_stop"`.
- `LiveGate.evaluate` reads `var/ledger.sqlite` and `var/live_confirmation.json` relative to `Path.cwd()` (`live_gate.py:49-50`, cli.py:483).
- `LiveAdapterStub._refuse` appends `LiveWriteAttempted` with `source="manual"` then raises `LiveGateError` (`live_adapter.py:49-75`). Construction does NOT raise (design 7.4 says it must raise `unmet=["adapter_registered"]` at construction). Method-level refusal is test-covered (`tests/test_live_gate.py:51-76`).
- `live confirm` returns exit 5 (`cli.py:742-744`).
- `LiveSettings` has only `enabled: bool = False` (`config/settings.py:245-250`); `[live]` keys `min_paper_days`, `wallet_allowlist`, `notional_cap_sol`, `confirmation_record`, `adapter`, `thresholds` are absent, and Settings is `extra="forbid"` (`settings.py:256-260`), so overlays cannot carry them until models are extended.

### 12.2 GOLIVE-002 requires the ledger metrics reader

`closed_trades >= 50`, `profit_factor >= 1.2`, `max_drawdown <= drawdown_halt_fraction` over `source=paper` events only; refuse ledgers with `source=replay` for metrics (design 7.2 ids 3, 4). Depends on `ledger/views.py` and `reducer.py`. Until then, preconditions 3-4 report unmet with reason (current behaviour, `live_gate.py:53-57,67-68`).

### 12.3 GOLIVE-001 confirmation record

HMAC-SHA256 over canonical JSON of the fields in design 7.3 (ledger_id, config_hash, confirmed_by, confirmed_at, expires_at, notional_cap_lamports, wallet_allowlist_sha256, statement), keyed by `PUMPGROK_CONFIRMATION_KEY`. Verify with `hmac.compare_digest` (stdlib). The key must be env-only and must not appear in logs (redaction exists at `logging/redaction.py`). Caution: `PUMPGROK_CONFIRMATION_KEY` is NOT in `NON_SETTING_ENV_NAMES` (`settings.py:346-348`), so `find_unknown_env` would reject it (Pitfall P19). Whitelist it or read it outside the settings loader.

## 13. Pitfalls (each with evidence)

**P1 (blocking, SC3): `PUMPGROK_KILLSWITCH` is an unknown setting.** `NON_SETTING_ENV_NAMES` contains only `PUMPGROK_PROFILE`, `PUMPGROK_CONFIG`, `PUMPGROK_LOG_JSON`, `PUMPGROK_LIVE_ENABLE` (`config/settings.py:346-348`). `find_unknown_env` reports any unlisted `PUMPGROK_*` name (`settings.py:378-388`) and `collect_startup_problems` includes it (`settings.py:446`). `_dispatch` calls `load_settings` before routing (`cli.py:791`). Therefore `PUMPGROK_KILLSWITCH=1 uv run pumpgrok run ...` fails with ConfigError (exit 1). Tests missed it because `tests/tools/risk/test_kill_switch_source.py:72` calls the tool directly, never the CLI. Fix: add the name (and any other env-only names) to `NON_SETTING_ENV_NAMES`, and add a CLI-level test that sets the env and runs `main([...])`. [INFERENCE from code path, not executed; confirm with the planned CLI test.]

**P2 (blocking): two ledger locations.** Wired verbs use `Path("var") / "desk"` (`cli.py:223`, `cli.py:651`), so `LedgerStore(data_dir / "ledger.sqlite")` is `var/desk/ledger.sqlite` (`tools/__init__.py:223`). `LiveGate` checks `var/ledger.sqlite` (`live_gate.py:49`); design 3.1 and 7.2 fix the paper ledger at `var/ledger.sqlite`; replay uses `var/replay/<dataset>/ledger.sqlite` (`cli.py:72,510`). Decide one paper ledger path and migrate every caller (D-r).

**P3 (blocking, R65): no entry gate on the ASSUMED layout.** `market.price` decodes with `decode_curve_account_base64` and returns `source="curve"` plus `graduated=state.complete` with no status check (`tools/market/price.py`, `run_price`). `market.liquidity` (`liquidity.py:74`) and `onchain.lp_status` (`lp_status.py:72`) do the same. `CurveDecodeError` maps to `DataStale` (`price.py`), not to `data_unavailable`. See Section 15 for the gate design.

**P4 (blocking, AUTO-006/SC checkpoint): no seat bodies.** No class implements `Bot.cycle` (`core/bot.py:97-104`; grep of `src` for `def cycle` returns none). Design names no module for seat behaviour (MIGRATION row 111 and batch 4 list `supervisor/{scheduler,seat_task,health,lifecycle,escalation}.py` only). See D-h.

**P5 (test conflict): existing tests pin skip-only and unmet-only behaviour.** `tests/test_skip_cycle.py:55-80` asserts exactly one JournalNote, `note_kind == "verdict"`, text containing `engine decision=skip reason=data_unavailable`, and `events_read == 4`. `tests/test_live_gate.py:44-48` asserts the header `"8 of 9"` and unmet-only lines. Both must be rewritten deliberately with the new behaviour. Do not relax the assertions to make them pass.

**P6: LedgerStore.append opens its own transaction.** Calling `append` while another `BEGIN IMMEDIATE` is open would start a nested transaction, which SQLite rejects (standard behaviour [ASSUMED]). Any multi-row atomic path (R64, PAPER-002) needs a batch API that owns one BEGIN IMMEDIATE (`store.py:135`).

**P7: duplicate keys raise a raw sqlite3 error.** `idempotency_key` UNIQUE (`store.py:41`); `append` re-raises `sqlite3.IntegrityError` after ROLLBACK (`store.py:169-172`). The adapter must convert this into the R64 first-fill return (checked inside the same transaction via `by_key`) and RiskEngine must treat a duplicate HaltSet/BreakerTripped as already recorded.

**P8: payload models are closed.** `_ClosedModel` has `extra="forbid"` (`events.py:46-49`), and `append` validates payloads (`store.py:132-133`). Any new field must be added to the model, then `contracts/events/*.schema.json` regenerated (18 files) and `tests/ledger/test_events.py` kept green.

**P9: FillRecorded and OrderRejected lack design fields** (Section 5.7): `curve_before`/`curve_after`, `quote_out`/`threshold`/`confirm_out`.

**P10: verify() is chain-only.** `store.py:185-221` does not check design 3.5 items 6a-6f. A forger who rewrites rows and recomputes the chain forward passes `verify`. Mitigation: periodic snapshot records `events.hash` at seq (design 3.5 item e) and reconcile checks. Document as residual risk.

**P11 (blocking for replay): no yield-to-loop primitive.** `asyncio.sleep(0)` is banned outside `replay/clock.py` (`test_static_guards.py:27,20-21`). Add `async def yield_now()` to `replay/clock.py` (allowlisted) and to the `Clock` protocol (`clock.py:22-33`) or as a module function.

**P12: FixtureClock lacks utc_day.** Design 4.2 and 5.5 use `clock.utc_day()`. Only `utc_iso` exists (`clock.py:98-99`). Add it; RiskEngine day rollover and budget resets depend on it.

**P13: stray-file check blocks multi-file fixtures.** `_verify` rejects stray data files (`fixtures.py:96-120`). Design 4.3 multi-file datasets need the loader changed in the same commit.

**P14: manifest model is closed.** `FixtureManifest` is `extra="forbid"` (`fixtures.py:39-40`). Adding manifest keys for per-file digests or `layout_status` requires updating the model.

**P15: Settings and overlays are closed.** `Settings` is `extra="forbid"` (`settings.py:256-260`). Design 5.2 TOML sections `[limits]`, `[supervisor]`, `[ledger]`, `[health]`, `[breakers]`, `[kill_switch]`, extended `[live]` and the `risk.kill_switch` knobs do not exist in any model. Any overlay key added without a model field fails startup.

**P16: overlays carry 8 of 9 R20 keys.** `[risk]` in `paper.toml`, `dev.toml` and `live.toml` lists max_trade_fraction, max_token_fraction, daily_loss_halt_fraction, drawdown_halt_fraction, max_open_positions, max_trades_per_day, liquidity_floor_multiple, partial_fill_fraction. `paper_equity_sol` is absent; the model default (`core/risk_budget.py:33`) fills it, but R20 says the TOML block carries all nine.

**P17: refusal lines.** `refusal_lines` prints only unmet items (`live_gate.py:92-101`); design 7.2 sample and CONTEXT line 39 require one `[x]`/`[ ]` line per id. Changing this breaks `tests/test_live_gate.py:44-48` (must update together).

**P18: LiveAdapterStub construction.** Design 7.4 requires construction to raise `LiveGateError(unmet=["adapter_registered"])` even when the gate is open. Current code raises per method (`live_adapter.py:49-92`). Tests in `tests/safety/test_live_adapter_raises.py` (interfaces.md section 4) expect construction-time refusal. Decide (D-j).

**P19: GOLIVE env name.** See Section 12.3. `PUMPGROK_CONFIRMATION_KEY` would hit P1.

**P20: reason vocabulary drift.** R34 vocabulary has 19 failure ids (CONTEXT:23). `data_unavailable` (`engine/pipeline.py:39`, DATA_UNAVAILABLE) and `reputation_degraded` (R62) are outside it. `tools/risk/check_limits.py` and tools use `data_stale`. Adding a 20th failure step contradicts "19 steps". D-a and D-k.

**P21: vendor auto-clear.** `RiskManager.halted` calls `roll_day_if_needed` (vendor risk.py:131-135), and `roll_day_if_needed` resets `realized_pnl_sol` (risk.py:106-118). Do not port this; the characterization case must be skipped with a reason, not converted into a passing test that asserts the vendor behaviour.

**P22: vendor limit is absolute SOL.** `daily_loss_limit_sol = 2.0` (vendor models.py:320). Design uses fractions (R20). Do not port the absolute knob.

**P23: exec tools bind NotYetImplementedAdapter in two places.** `tools/exec/place.py:84` (backend string), `tools/exec/positions.py:55`, `tools/exec/quote.py:65`, and the wiring `tools/__init__.py:224`. The desk gateway uses the same factory (`tools/__init__.py:210-211` docstring). Replace in one factory, then confirm `services/desk-gateway` tests still pass (their own suite).

**P24: kill-switch tools read env at call time.** See Section 8.4 and D-m. CLI `_killswitch` (`cli.py:609-631`) and `_state` (`cli.py:595-606`) differ from the design verbs (`--flatten` flag; `state resume` absent). Decide shapes first (D-e).

**P25: report and verify route to exit 5.** `_FIND_ONLY_ROUTES` (`cli.py:750-762`) sends `audit`, `verify`, `report`, `journal`, `ticket`, `rug`, `scout`, `risk`, `chief` through `_skip_use`. `verify` lacks `--ledger` (`cli.py:351-352`).

**P26: read-only verbs create files.** `LedgerStore(path)` creates parent dirs and the sqlite file (`store.py:107-114`). `report --daily` and `state status` must not create or migrate `var/ledger.sqlite` when absent.

**P27: FixtureClock timers need the loop.** `sleep` creates a future resolved from `advance_to` (`clock.py:121-130`). A runner that never yields will not progress seats. Pair `advance_to` with `yield_now` (P11).

**P28: `Clock.timeout` cancellation semantics.** `FixtureClock.timeout` cancels the task (`clock.py:141-144`). A seat that catches `CancelledError` broadly would swallow the virtual timeout; supervisor must classify it as a crash (design 6.2).

**P29: SC1 test count.** 151 defs by grep; need >=164 collected. See Section 4.3. Do not inflate by parametrizing trivial cases; the MIGRATION rule requires 1:1 ports.

**P30: decimal-to-int rounding.** `_size_sol` and `size_sol_to_lamports` use ROUND_HALF_UP (`cli.py:110-140`). Design 2.3 uses floor (`//`) for fees and fill caps. Use the same rounding rule everywhere money is derived from SOL, and document it. Vendor `position_size` rounds to 6 decimals via `round(..., 6)` (vendor risk.py:147).

**P31: FLOOR constant bytes.** The constitution's U+2013 must be used in code (R7). Writing a hyphen in code would break byte-level checks. `FLOOR HALTED - DAILY LOSS LIMIT` (hyphen) is the ASCII form only in this document.

**P32: `tests/risk/` naming.** `tests/tools/risk/` holds Phase-3 tool tests; design 9 names `tests/risk/` for new tests. Keep names unique (P36).

**P33: CLI verb exit semantics.** `_not_implemented` exits 5 with a JSON envelope (`cli.py:143-154`); SC4 expects `report --daily` exit 0, not 5. Ensure every served verb returns through its own handler, not `_skip_use`.

**P34: smoke fixture size and determinism.** `events.hash` must not depend on dict ordering or wall time; use canonical JSON (`idempotency.py:40-47`) and `FixtureClock` only.

**P35: JSON float leaks.** `canonical_json` raises on float (`idempotency.py:17-37`). Any float in a payload breaks the ledger write. Convert ratios to Decimal strings before append.

**P36: pytest basename collision.** `tests/tools/risk/test_risk.py` exists; `tests/characterization/test_risk.py` would collide under default import mode with no `__init__.py` (Section 4.2). Choose unique basenames.

**P37: markers.** `--strict-markers` (`pyproject.toml:90`) and only `replay`, `characterization` declared (`pyproject.toml:91-94`). A new marker (for example `slow` for nightly soak, Phase 5) must be declared first.

## 14. Decisions required before planning (conflicts found)

| ID | Conflict | Options | Recommended default |
|----|----------|---------|---------------------|
| D-a | R65 gate reason `data_unavailable` is not in the R34 19-step vocabulary | (1) Engine pre-order skip reason, like existing `DATA_UNAVAILABLE` (`engine/pipeline.py:39`); no OrderRejected. (2) Map to `data_stale` in step 17 with detail `layout_assumed`. (3) Add a step (breaks "19") | (1): it matches the current skip vocabulary and keeps 19 steps |
| D-b | STRUCT-006 scope: ROADMAP criterion 5 (narrow) vs MIGRATION_MAP 3.4 check 1 (repo-wide) | Enforce narrow; or rewrite history | Enforce narrow list; list historical references as exceptions in docs/VENDOR_PIN.md |
| D-b2 | `rules/pumpgrok-team.mdc:42` names the vendor path; D2/R7 keep the constitution verbatim | Retarget the path only; or keep and fail criterion 5 | Retarget path only; user sign-off required |
| D-c | Smoke checkpoint: bot-08-signal LLM in replay vs recorded llm.jsonl; MIGRATION batch 2 wants a recorded smoke | Rule-based signal in replay; or hand-authored llm.jsonl with records | Rule-based signal in replay for smoke; keep smoke hand-authored (no network) |
| D-d | Fixture time key: design `ts` (epoch float) vs code and smoke `ts_utc` (ISO string) | Keep `ts_utc`; or rewrite loader and smoke | Keep `ts_utc`; amend design 4.3 |
| D-e | Killswitch CLI shape: design `killswitch set --reason <text> [--flatten]` vs code `set` and `flatten` subcommands | Keep subcommands and document; or change to flag | Change to design flag (user-facing contract in design 8.2) |
| D-f | Supervisor module names: design 6.1 (`scheduler, seat_task, health, metrics`) vs MIGRATION row 111 and CONTEXT (`lifecycle`, `escalation`) | Use CONTEXT list (`scheduler, seat_task, health, lifecycle`) | CONTEXT list; metrics stays Phase 5 |
| D-g | `reporting/` owner: ownership.yaml bot-09 (line 326) vs design 8.1 | Already consistent (bot-09-journal) | No action |
| D-h | Where the ten seat cycle bodies live; no R31 module owns them | (1) `supervisor/seats/` (owner bot-00). (2) Per-owner module (`engine/`, `tools/`) | (1) with one file per seat, delegating to engine and tools, so ownership rules stay satisfied |
| D-i | Live refusal output: unmet-only (code) vs all nine `[x]/[ ]` lines (design, CONTEXT:39) | Change code and test | All nine lines (matches CONTEXT) |
| D-j | LiveAdapterStub: method-time refusal (code) vs construction-time refusal (design 7.4) | Construction raises when gate unmet; plus method refusal | Construction raises; keep method refusal as defense |
| D-k | `reputation_degraded` (R62) outside R34 vocabulary | Fold into step 4 `breaker_open` with detail; or add id | Fold into step 4 detail, emit Escalation once; keep 19 |
| D-l | How to mark the intentionally unported vendor auto-clear tests | `pytest.mark.skip(reason=...)`; or new declared marker | skip with reason; no new marker |
| D-m | Kill-switch env truthiness: `== "1"` in tools (`tools/risk/kill_switch.py:111`, `halt_status.py:75`) vs design `set and not in {"", "0", "false"}` read once at start | Unify on design rule read at process start | Design rule; read once in settings/RiskEngine; tools consume the RiskEngine view |
| D-p | Idempotency key convention for non-OrderPlaced rows of one order (UNIQUE per row) | Derived keys with prefix per type, scope=order_id | Derived keys: `derive_idempotency_key("<type>", seat, payload, scope=order_id)` |
| D-q | Reports: reuse `tools/journal/render_report.py` or replace with `reporting/` | Reuse template and writer, or replace | Replace with `reporting/render.py` (design 8.1) and remove the tool path once CLI is wired; avoid two renderers |
| D-r | Paper ledger path: `var/desk/ledger.sqlite` (tools) vs `var/ledger.sqlite` (design, LiveGate) | Single path `var/ledger.sqlite` | Single path `var/ledger.sqlite`; migrate `cli.py:223,651` and `tools/__init__.py` callers |

## 15. R65: live probe and the fail-closed entry gate

### 15.1 Current state (verified)

- Layout constants: `_CURVE_STRUCT = struct.Struct("<8sQQQQQB")` (`tools/onchain/curve_layout.py:26`); size 49 bytes; `COMPLETION_SOL_LAMPORTS = 85 * LAMPORTS_PER_SOL` marked `[ASSUMED]` (`curve_layout.py:30-31`).
- Field order in decode: `(_, vsol, vtok, rsol, rtok, supply, complete)` (`curve_layout.py:60`). The discriminator (first 8 bytes) is discarded (`_`), so decode accepts any 8-byte prefix (see Section 15.1).
- `decode_curve_account` checks length and the completion byte only (`curve_layout.py:57-58` size check; `:62-65` complete in {0,1}; `:66-72` zero reserves). Zero reserves raise.
- The module docstring says the layout is "NOT verified against a mainnet account" (`curve_layout.py:3-6`), and `encode_curve_fixture` writes `b"ASSUMED\x00"` as the discriminator (`curve_layout.py:110`). The ASSUMED marker lives only in test-fixture bytes, not in a status field.
- Consumers: `market.price` (price.py), `market.liquidity` (`liquidity.py:74`), `onchain.lp_status` (`lp_status.py:72`).
- Phase 3 verification and UAT record the probe as carried to Phase 4 (`.planning/phases/03-tools-and-skills/03-VERIFICATION.md:127-134`; `03-UAT.md:20-23`). No live check was run.

### 15.2 External facts (ASSUMED; must be confirmed by the probe)

- Program id `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` for pump.fun (ASSUMED, training knowledge).
- Bonding-curve PDA seeds `["bonding-curve", mint_pubkey]` under that program (ASSUMED).
- Anchor-style discriminator for the `BondingCurve` account, computed locally this session as `sha256(b"account:BondingCurve")[:8] = 17b7f83760d8ac60` (computed, not observed on chain). Applicability is ASSUMED.
- Field order commonly described for the account (ASSUMED): virtual_token_reserves, virtual_sol_reserves, real_token_reserves, real_sol_reserves, token_total_supply (five u64), then complete (bool). This differs from the repo order (`vsol, vtok, rsol, rtok, supply`). Both candidates must be tested by the probe.
- Account size: 8 + 5*8 + 1 = 49 bytes under the repo layout; newer account versions may append a creator pubkey (32 bytes), giving 81 (ASSUMED). A size that matches neither must fail closed (current code does: `curve_layout.py:57-58`).

### 15.3 Probe procedure (to implement as an operator script; not run in CI)

Location: `scripts/probe_curve_layout.py` (operator-only; outside `src/` so the `--forbid-imports` gate over `src/`, `services/`, `tests/` does not apply; still must avoid `solders`, `solana`, `base58`, `nacl` imports). Steps:

1. Pick N mints from a recorded PumpPortal create frame or an operator-supplied list (pump.fun REST returned HTTP 530 / error 1016 on all tested paths, STATE.md and R47; do not depend on REST).
2. Derive the bonding-curve PDA in pure Python: base58-decode the mint (pure Python alphabet table), then `find_program_address([b"bonding-curve", mint], program_id)` using sha256 and the ed25519 off-curve test (pure Python, about 40 lines, no dependency).
3. Fetch with `RpcClient.call("getAccountInfo", [pda, {"encoding": "base64", "commitment": "confirmed"}])` (`tools/onchain/rpc.py:149`), which already supports failover over `rpc.endpoints`. Record `context.slot`. Never write the API key (`rpc.api_key` header only, `settings.py:55-65`).
4. Check length against the candidate sizes (49 or 81). Compute the discriminator and compare to the expected 8 bytes; record the observed bytes even on mismatch.
5. Decode with both candidate orders (repo order and the ASSUMED IDL order). Accept a layout only if the decoded pair `(virtual_sol, virtual_token)` equals the reserves in a same-slot or same-second PumpPortal trade frame (`vSolInBondingCurve` and `vTokensInBondingCurve`; design unverified item 4 says the second field may be absent, in which case the probe is inconclusive and the layout stays ASSUMED). Conversion from SOL float to lamports uses Decimal at the boundary (R28).
6. Write one fixture per mint to `tests/fixtures/rpc/bonding_curve/<mint>.json` (schema in 15.4) and a `manifest.json` with sha256 per file.
7. A human reviews the records and changes the code constant (single source of truth, Section 15.5) in a separate reviewed commit (H2 in 03-VERIFICATION).

### 15.4 Fixture record (proposed schema; ASCII JSON)

```json
{
  "fixture": "bonding_curve_layout",
  "mint": "<base58 mint>",
  "pda": "<base58 pda>",
  "program_id": "<base58 program id, ASSUMED until confirmed>",
  "rpc_endpoint_host": "<host only, no key>",
  "context_slot": 0,
  "commitment": "confirmed",
  "account_b64": "<base64 raw account data>",
  "account_len": 49,
  "account_sha256": "<hex>",
  "discriminator_hex": "<16 hex chars observed>",
  "candidate_layouts": {
    "repo_order": ["vsol", "vtok", "rsol", "rtok", "supply", "complete"],
    "idl_order": ["vtok", "vsol", "rtok", "rsol", "supply", "complete"]
  },
  "decoded_under": "repo_order | idl_order | none",
  "cross_check": {"source": "pumpportal", "slot_or_ts": "...", "vSolInBondingCurve": "...", "vTokensInBondingCurve": "..."},
  "layout_id": "<id>",
  "layout_status": "ASSUMED",
  "probed_at": "2026-10-21T00:00:00Z",
  "probed_by": "human:<name>"
}
```

`layout_status` becomes `VERIFIED` only after a human reviews the record and the code constant changes in the same reviewed commit. Until then the fixture stays `ASSUMED`.

### 15.5 Fail-closed entry gate (design)

- Single source of truth: `LAYOUT_STATUS: Final = "ASSUMED"` in `tools/onchain/curve_layout.py`. A test loads every probe fixture and asserts that the constant equals the status of the committed `layout_id`; a mismatch fails the suite.
- Provenance: `PriceSource` returns `source` in `{rest, pumpportal, rpc}` (design 2.1). A curve read whose source is `rpc` while `LAYOUT_STATUS != "VERIFIED"` is not a usable price.
- Gate point (D-a option 1): the engine pre-order stage returns skip reason `data_unavailable` for a candidate whose only price is RPC-derived and layout is ASSUMED; no OrderRejected, no order, no fill. Sells are not blocked by this gate (reducing risk is always allowed, design 5.2 line 578), but MTM uses last_good or non-RPC ticks.
- Replay ticks (`source` rest or pumpportal, integer S and T) do not pass through `curve_layout`, so SC2/SC3 and the checkpoint are not blocked by R65. Say so explicitly in the plan.
- Tests (tests/execution/test_curve_gate.py, new): ASSUMED layout -> `data_unavailable` skip and zero OrderPlaced; VERIFIED fixture -> gate open; mismatched constant vs fixture -> failure; decode of an 81-byte or unknown-size account -> `CurveDecodeError` (fail closed).

## 16. Fixture generation and smoke-10m

Design 4.6 and CONTEXT:47. Requirements for the generator:

- Committed script (for example `tests/fixtures/replay/smoke-10m/generate.py`, owner bot-02-risk via `**/*.py`) that writes `events.jsonl` and `manifest.json` deterministically (seeded `random.Random(20260101)` or a fixed hand-authored list; no wall time).
- `manifest.json` keys must match `FixtureManifest` (`fixtures.py:39-60`, extra forbid): dataset, recorded_from_utc, recorded_to_utc, seed_hint, sources, sha256 (one entry per file), notes. Add any new key by changing the model first (P14).
- Size under 1 MB (design 4.6). A 10-minute stream of ticks at 1-2 per second for 2-3 mints is well under 1 MB.
- Required scenarios (each must be verified by a test that reads the ledger, not by reading the generator): full fill; partial fill (size in (S/50, S/10]); `slippage_exceeded`; `below_liquidity_floor`; one 180 s gap that trips DataStale; one LLM timeout (only if D-c keeps LLM in replay); one exit by `stop_loss` or `take_profit` (needs a position opened and a price move).
- Determinism test: run `verify --fixture smoke-10m` twice in fresh temp dirs (or sequentially with `recreate_ledger_db`), compare `events.hash`, JSONL bytes and final state (design 4.5).
- Different seed must produce a different events.hash (design 4.5/9) so seed wiring is proven.

## 17. Don't Hand-Roll

| Problem | Do not build | Use instead | Why |
|---------|-------------|-------------|-----|
| Chain hashing | custom digest format | `hashlib.sha256` over `canonical_json` (`store.py:78-101`, `core/idempotency.py:40-47`) | Already the R28 rule |
| Canonical JSON | ad-hoc `json.dumps` | `core/idempotency.canonical_json` | Refuses floats, stable key order |
| Atomic file write | tmp+rename by hand | `core/atomic_write.py` pattern (extend with a text variant) | fsync and replace ordering already correct |
| ULIDs | `uuid` (banned) or time-based ids | `core/ids.IdFactory(clock, rng)` (`ids.py:34-54`) | Banned by static guard; virtual-time deterministic |
| Retries and backoff | custom loops with sleep | tenacity with `sleep=clock.sleep` and seeded jitter (`core/registry.py:49-64` pattern) | R27 |
| Token bucket rate limit | new limiter | `core/ratelimit.RateLimiter` (`ratelimit.py:17`) | Exists |
| Daily call budget | new counter | `core/budget.CallBudget` (`budget.py:21`) | Exists |
| Circuit breaker | new state machine | vendor `CircuitBreaker` (vendor ops.py:131-182) as base for `risk/breakers.py` | Behaviour pinned by vendor tests |
| HMAC verification | string compare | `hmac.compare_digest` | Constant-time |
| Money parsing | float | `Decimal` at the CLI boundary, `size_sol_to_lamports` (`cli.py:138-140`) | R28 |
| Templates | jinja2 | `str.format` (R9) | No new dependency |
| Signal handling | custom signal threads | `loop.add_signal_handler` (vendor ops.py:420-431 pattern) | Loop-safe |
| HTTP health server | web framework | `asyncio.start_server` (vendor HealthServer pattern) | No dependency |
| Base58 / PDA for probe | solders/solana/base58 packages | Pure-Python base58 and ed25519 off-curve check in `scripts/probe_curve_layout.py` | MIGRATION 2.4 forbids the packages in src/tests |
| Schema generation | hand-written JSON schemas | `ledger/events.event_json_schemas()` (`events.py:342-347`) | One source of truth (FOUND-008) |

**Key insight:** the ledger, fills, risk and supervisor should each have one place that decides, and every other path must call that place. Re-implementing a check in a tool or seat is how the existing kill-switch and live-gate drift (P1, P24, D-m) happened.

## 18. State of the Art (in this repo)

| Old approach (vendor) | Current/target approach | Impact |
|---|---|---|
| JSON state file, atomic write (vendor state.py:76-89) | sqlite WAL, hash chain, snapshots (`store.py`) | Tamper detection; single writer |
| Day counters auto-reset and auto-clear halt (vendor risk.py:106-135) | Human-only halt clear; DailyRollover event; no auto-clear (R5) | Constitution compliance |
| Absolute SOL daily limit (models.py:320) | Fractions of equity (R20) | Scales with equity |
| Dry-run fill with no fee or impact (executor.py:103-134) | Curve fills with fees, latency, partials (design 2) | Honest paper results |
| Raw asyncio HealthServer (ops.py:299) | Keep vendor contract, add `/readyz` (design 6.6) | Same route contract |
| Hand-rolled Prometheus text (ops.py:67-80) | prometheus_client in Phase 5 (D5) | Deferred |
| Vendor `LiveExecutor` with TODO (executor.py:137-172) | LiveAdapterStub that refuses and records attempts | No signing path |
| Jupiter as price (`tools/jupiter_quote.py`) | Jupiter informational only; curve is the fill basis (R38) | Matches fill model |

Deprecated in this phase: `NotYetImplementedAdapter` (after PaperAdapter lands), `_not_implemented` for served verbs, `tools/` root scripts (Batch 5 per MIGRATION 7), `_skip_cycle` skip-only replay.

## 19. Runtime State Inventory (vendor retirement and skip-only removal)

| Category | Items found | Action required |
|----------|-------------|-----------------|
| Stored data | `var/replay/smoke/ledger.sqlite` (28 KB, from Phase 1 skip cycle); `var/desk/` directory (from operator registry); no `var/ledger.sqlite`, no `var/reputation.json`, no `var/KILLSWITCH` observed in the listing | Replay ledgers are recreated each run (`recreate_ledger_db`, `store.py:70-75`): safe. `var/desk/ledger.sqlite` (if created) must be migrated or ignored per D-r; document the cutover |
| Live service config | None in repo (no systemd, no pm2, no launchd, no external dashboards) | None |
| OS-registered state | None found in repo. Hermes cron pack (`hermes/cron/jobs.yaml`, 6 jobs) calls CLI verbs; job prompts wrap `pumpgrok` verbs per MIGRATION 4.3 | Rewrite prompt wrappers to served verbs; no OS registration to re-register |
| Secrets and env vars | `PUMPGROK_KILLSWITCH` (read by two tools, not whitelisted, P1); `PUMPGROK_LIVE_ENABLE` (whitelisted); `PUMPGROK_CONFIRMATION_KEY` (planned, must not be an unknown setting, P19). Host environment variables NOT inspected | Whitelist names; confirm host env is clean before running gates |
| Build artifacts | `__pycache__/*.pyc` under `src/pumpgrok/engine`, `tests/characterization`, vendor tree, containing vendor path strings (ignored by `.gitignore`: `__pycache__/`, `*.pyc`). `.pytest_cache/v/cache/nodeids` contains a vendor path (ignored: `.pytest_cache/`) | Delete `__pycache__` and `.pytest_cache` with the vendor tree; no tracked artifacts affected |
| Documentation state | `CHANGELOG.md` must record each phase (ROADMAP Phase 5 SC3 and OBS-005); runbooks under docs/ mention `micro-live` or vendor paths (Phase 5 OBS-004) | Add CHANGELOG entry in Phase 4 close-out; runbooks Phase 5 |

## 20. Common Pitfalls summary

See Section 13 (P1-P37) for evidence. The top blockers for planning:
1. P1 kill-switch env whitelist (SC3).
2. P2 ledger path split (SC2, SC3, SC4, LiveGate).
3. P3 R65 gate absent on curve reads.
4. P4 no seat bodies (checkpoint).
5. P11 no yield primitive for replay.
6. P6/P7 transaction API and duplicate-key mapping (R64).
7. STRUCT-006 census hits and D-b/D-b2.
8. P5 existing tests that must be rewritten deliberately.

## 21. Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | pump.fun bonding-curve field order (vtok, vsol, rtok, rsol, supply, complete) and account size 49 or 81 bytes | 15.2 | Wrong decode prices; fail-closed gate holds until probe |
| A2 | Program id `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` and PDA seeds `["bonding-curve", mint]` | 15.2 | Probe derives wrong PDA; no data |
| A3 | Anchor discriminator applies to pump.fun BondingCurve (sha256 prefix 17b7f83760d8ac60) | 15.2 | Discriminator check fails; probe must record bytes, not assume |
| A4 | sqlite behaviour: nested BEGIN fails; BEGIN IMMEDIATE takes write lock; WAL concurrency | 6, 13 P6 | Transaction design changes |
| A5 | venue fee 100 bps; base fee 5000 lamports; CU 200000; latency lognormal(1.2, 0.5) clip [0.4, 20]; p_drop 0.02 | 5.2, 5.5 | Fill economics differ from reality (REVIEW in design) |
| A6 | Graduation threshold 85 SOL (vendor monitor.py:30) and REST `complete` field | 5.4, 15.2 | Graduation detected late or early |
| A7 | PumpPortal frames carry `vTokensInBondingCurve` (design unverified item 4) | 15.3 | Cross-check unavailable; probe inconclusive |
| A8 | `daily_loss_basis = total` (realized + unrealized) (design unverified 14) | 8.2 | Halt timing differs |
| A9 | Telegram inbound kill command availability (design unverified 9) | 8.4 | Alert-source kill switch unavailable; env and file sources still work |
| A10 | `paper_equity_sol = 10` and the nine R20 values (REVIEW) | 8.1 | Sizing differs |
| A11 | Soak memory bound 20 MB (design unverified 15) | Phase 5 only | None in Phase 4 |
| A12 | Constitution rule 9 path edit is acceptable under R7 | 11.2 | Criterion 5 fails if kept |
| A13 | Test counts by grep equal collected counts (no parametrize in char files) | 4.2 | SC1 count may differ; re-check by collect-only when allowed |
| A14 | `FixtureClock` virtual time plus `yield_now` is sufficient for deterministic seat scheduling | 7, P11 | Non-deterministic ordering; need explicit queue |

## 22. Open Questions (all RESOLVED; orchestrator runs non-interactively, so the recommended option is recorded in each case)

1. How should seat cycles be structured (D-h)? RESOLVED: no dedicated `supervisor/seats/` files in Phase 4; the supervisor drives the existing engine ports (exits, watcher, monitor, reputation) through the seat_task wrapper, and seat-specific logic stays in `engine/*` plus tool rosters. Covered by plan 04-07.
2. Which LLM behaviour does the smoke checkpoint use (D-c)? RESOLVED: rule-based signal in replay; a missing LLM record fails the run with ReplayMissingRecord. Covered by plans 04-02 (recorder) and 04-07 (AUTO-005 degraded row).
3. Is the fixture time key `ts_utc` (D-d)? RESOLVED: keep `ts_utc`. Covered by plan 04-02.
4. What is the exact `killswitch` surface (D-e)? RESOLVED: design flag `--flatten` via the kill_switch tool flatten_request; clear is CLI-only. Covered by plans 04-05 (tool backend) and 04-06 (CLI verb).
5. Should the vendor census follow ROADMAP scope (D-b)? RESOLVED: yes, with documented exceptions; the repo-wide MIGRATION_MAP 3.4 check 1 beyond the nine scoped paths is recorded as a deferral, not a gap. Covered by plan 04-08.
6. What is the rebuild path for a degraded reputation book (R62 "rebuilt from the ledger")? RESOLVED with the recommended option (no user confirm available): rebuild scans ledger PositionOpened rows for creator plus PositionClosed rows for realized_pnl_lamports to reconstruct per-creator losses and restores the book; a quarantined-but-unrestorable book stays degraded and keeps refusing. Covered by the R62 task in plan 04-05 with a rebuild test.
7. Snapshot cadence and `snapshots.state_json` contents (design 3.2)? RESOLVED: snapshot at shutdown (lifecycle) and on demand before export flush; state_json holds the LedgerState canonical JSON plus chain_hash. Covered by plans 04-01 (reconcile) and 04-07 (shutdown snapshot).
8. Persist `FillRecorded.curve_before`/`curve_after` (D-p interplay)? RESOLVED: yes, required by design 3.3; the Fill event carries the (S,T) reserve pairs at decision and at CONFIRMING with schema regeneration. Covered by the tracer task in plan 04-04.
9. Does `report` need the live-gate section on daily reports? RESOLVED: no; design 8.3 puts the live-gate section in the weekly report only. Covered by plan 04-08.
10. Seat restart jitter source? RESOLVED: a separate seeded instance via replay/rng (determinism only needs seeding, not a shared stream); jitter flows through clock.sleep. Covered by plan 04-07.

## 23. Environment Availability

| Dependency | Required by | Available (this session) | Version | Fallback |
|------------|-------------|--------------------------|---------|----------|
| Python 3.12 | all src and tests (pyproject `requires-python = ">=3.12,<3.13"`) | Yes (`python3 --version` -> Python 3.12.3) | 3.12.3 | - |
| uv | `uv run pumpgrok`, `uv sync --frozen` | Not probed (read-only research) | - | Use `python -m pytest` in a prepared env |
| sqlite3 (stdlib, WAL) | ledger | Assumed present with Python; `var/replay/smoke/ledger.sqlite` exists from Phase 1 | - | - |
| Solana RPC (`api.mainnet-beta.solana.com`) | R65 probe, live reads | NOT used; not probed | - | Fixture-only; fail closed |
| PumpPortal WS, pump.fun REST | live-paper feeds, R65 cross-check | NOT used; REST known to return HTTP 530 / error 1016 (STATE.md, R47) | - | Recorded fixtures only |
| x.ai LLM | bot-08-signal live-paper | NOT used | - | Rule-based fallback live-paper; recorded outcomes in replay |
| Network in tests | forbidden | Blocked by `tests/conftest.py` (httpx and websockets patched) | - | `httpx.MockTransport` |
| git | ownership G-1 self-test walks `git ls-files` | Repo present; clean-ish (untracked `.planning/state.json`, `01-REVIEW.iter2.md`) | - | - |

**Missing dependencies with no fallback:** none for planning. The R65 live probe cannot run without network access; that is a human checkpoint (H2), not a blocker for the fail-closed gate.

## 24. Validation Architecture

### Test framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x with pytest-asyncio 1.4.x, `asyncio_mode = "auto"` (pyproject.toml:87) |
| Config | pyproject.toml `[tool.pytest.ini_options]` (lines 86-96); `--strict-markers` (line 90) |
| Markers declared | `replay`, `characterization` (lines 91-94). Declare any new marker first |
| Quick run | `uv run pytest -q tests/<area>` |
| Full suite | `uv run pytest -q` (includes `ci/tests`, testpaths line 89) |
| Collect check (SC1) | `uv run pytest --collect-only -q tests/characterization` |

Not run in this research. Commands are for the planner and the verifier.

### Success criteria status (observed by reading code; not executed)

| SC | Command (ROADMAP) | Status now | Blocker |
|----|-------------------|------------|---------|
| SC1 | `--collect-only tests/characterization` >= 164; `pytest -q` exit 0 | Not met (about 151 by grep) | Add vendor ports (4.2); P36 |
| SC2 | `verify --fixture smoke-10m` exit 0; identical events.hash | Not met | verify routes to exit 5 (`cli.py:761`, `:351-352`); smoke-10m absent |
| SC3 | `PUMPGROK_KILLSWITCH=1 ... --replay smoke-10m` exit 0; zero OrderPlaced | Not met | P1 (exit 1); dataset absent; `_run` is skip-only |
| SC4a | `run --mode live --once` exit 3, sends nothing | Met by code path (`cli.py:484-488`) | Keep; re-verify after refusal-line change (D-i) |
| SC4b | `report --daily` / `--weekly` exit 0, ASCII | Not met (exit 5) | `report` route (`cli.py:759`); empty-ledger handling (P26) |
| SC5 | vendor removed; LICENSE present; rg clean under src skills agents rules hermes scripts ci contracts prompts | Not met | Section 11 census; LICENSE absent |
| Checkpoint | `run --mode paper --once --replay smoke` completes one ten-seat cycle, no network | Not met | P4 (no seats); skip-only cycle |

### Requirement-to-test map (design section 9, with Wave 0 status)

| Req | Test file (proposed) | Status | Notes |
|-----|----------------------|--------|-------|
| PAPER-001 | `tests/execution/test_paper_fill_model.py` | Wave 0 (new) | curve_math invariants; worked example as integer golden vectors (5.2) |
| PAPER-001 | `tests/execution/test_curve_gate.py` | Wave 0 (new) | R65 gate (15.5) |
| PAPER-002 | `tests/ledger/test_ledger_restart_reconcile.py` | Wave 0 (new) | snapshot+tail, tamper INCONSISTENT |
| PAPER-002 | `tests/ledger/test_single_writer_concurrent_appends.py` | Wave 0 (new) | two processes |
| PAPER-002 | `tests/ledger/test_store.py`, `test_events.py` | Exists | extend for batch API and new fields |
| PAPER-003 | `tests/ledger/test_export_resume.py` | Wave 0 (new) | export_seq resume |
| PAPER-004 | `tests/replay/test_replay_determinism.py` | Wave 0 (new) | events.hash twice; seed differs; 180 s hole; missing LLM record fails |
| PAPER-004 | `tests/replay/test_clock.py`, `test_fixtures.py` | Exists | extend for `utc_day`, `yield_now` |
| PAPER-005 | `tests/engine/test_blind_flatten.py`, `tests/execution/test_graduation.py` | Wave 0 (new) | |
| PAPER-006 | `tests/reporting/test_reporting_render.py` | Wave 0 (new) | snapshot; ASCII; nine live-gate ids |
| PAPER-007 | `tests/execution/test_approvals_tickets.py` | Wave 0 (new) | phrase token match; consumption |
| RISK-001 | `tests/risk/test_check_order.py` | Wave 0 (new) | 19-step order; first failure wins |
| RISK-002 | `tests/risk/test_daily_rollover.py`, `test_halts.py` | Wave 0 (new) | no auto-clear; idempotent HaltSet |
| RISK-003 | `tests/risk/test_breaker_trip_and_cooldown.py` | Wave 0 (new) | half-open single probe; restart rebuild |
| RISK-004 | `tests/risk/test_kill_switch_one_cycle.py`, `test_kill_switch_in_flight.py` | Wave 0 (new) | CLI-level env test (P1) |
| RISK-005 | `tests/risk/test_seat_may_trade.py` | Wave 0 (new) | KILL block |
| RISK-006 | `tests/supervisor/test_observe_only_latch.py` | Wave 0 (new) | |
| AUTO-001..002 | `tests/supervisor/test_supervisor_bounded_restart.py` | Wave 0 (new) | 5 restarts/h; backoff 1,2,4,8,16 + jitter |
| AUTO-003 | `tests/supervisor/test_shutdown.py` | Wave 0 (new) | drain, snapshot, health.json stopped |
| AUTO-004 | `tests/supervisor/test_health.py` | Wave 0 (new) | /healthz 503 when stale; /readyz |
| AUTO-005 | `tests/degradation/` (Phase 5 for full), Phase 4 subset in `tests/safety/` | Wave 0 (new) | persistence_down, clock_skew subset |
| AUTO-006 | `tests/test_skip_cycle.py` (rewrite) | Exists, must change | P5 |
| SEC-004 | `tests/execution/test_live_gate_fails_fast.py` | Wave 0 (new) | nine preconditions one at a time |
| SEC-004 | `tests/test_live_gate.py` | Exists, must change | P17 |
| SEC-004 | `tests/safety/test_no_signing_outside_live_stub.py` | Exists | keep green |
| GOLIVE-001 | `tests/execution/test_live_confirm.py` | Wave 0 (new) | HMAC; env-only key; never changes mode |
| GOLIVE-002 | `tests/safety/test_live_gate_rejects_replay_ledger.py` | Wave 0 (new) | source=paper only |
| R62 | `tests/safety/test_reputation_degraded.py` | Wave 0 (new) | corrupt file -> buy refused; exit executes |
| R64 | `tests/ledger/test_consume_and_order.py` | Wave 0 (new) | repeat returns first fill; approval consumed in same tx |
| R65 | `tests/execution/test_curve_gate.py`, `tests/tools/onchain/test_curve_layout_fixture.py` | Wave 0 (new) | constant matches fixture |
| STRUCT-004 | `tests/characterization/test_vendor_risk.py` (name avoids P36), `test_ops.py`, `test_state.py`, `test_log.py`, `test_alerts.py`, `test_config.py` | Wave 0 (new) | vendor oracle counts |
| STRUCT-006 | `tests/safety/test_vendor_retired.py` (new) | Wave 0 (new) | grep census under the agreed scope |
| TOOL-011 | `tests/test_tools_cli.py` (exists) | Exists, extend | every served verb returns non-5 |

### Sampling rate

- Per task: the file(s) changed plus `tests/ledger` and `tests/replay` (fast).
- Per wave: `uv run pytest -q tests/execution tests/risk tests/supervisor tests/reporting tests/replay tests/ledger tests/safety tests/characterization`.
- Phase gate: full `uv run pytest -q` plus SC1-SC5 commands and the checkpoint.

### Wave 0 gaps

- Create `tests/execution/`, `tests/risk/` (unique basenames), `tests/supervisor/`, `tests/reporting/`, `tests/engine/`.
- Add `replay/clock.py` `utc_day` and `yield_now` before any replay test.
- Add smoke-10m generator and fixture (Section 16) before SC2/SC3.
- Add CLI-level env test harness (for P1).
- Declare any new pytest marker in pyproject.toml before use.

## 25. Security Domain

`security_enforcement: true`, `security_asvs_level: 1`, `security_block_on: high` (`.planning/config.json`).

### Applicable ASVS categories

| ASVS category | Applies | Standard control in this repo |
|---------------|---------|-------------------------------|
| V2 Authentication | Limited: human phrase approvals and `human:<name>` identity | ApprovalRecord human-kind validator (`core/approvals.py:69-85`) |
| V4 Access control | Yes: least-privilege rosters, human-only verbs | ToolRegistry.find I1-I5 (`core/registry.py:137`), `_refuse_forbidden_seat` (`cli.py:157-162`), `FORBIDDEN_OWNERS` (`cli.py:76`) |
| V5 Input validation | Yes | pydantic models with `extra="forbid"` (events.py:46-49; settings.py:256-260; fixtures.py:39-40) |
| V6 Cryptography | Yes (GOLIVE-001 HMAC; ledger hash) | stdlib `hmac`, `hashlib`; never hand-roll (Section 17) |
| V7 Error handling and logging | Yes | `logging/redaction.py` (`RedactionFilter`, `redact_value`) |
| V8 Data protection | Yes: no keys in repo or logs | `forbidden_env` substrings (`settings.py:192-200`), `KEY_BEARING_VALUE_RE` (`settings.py:212`), SecretStr for api keys (`settings.py:65,77`) |
| V9 Communications | Yes: no network in tests; notify allowlist | conftest network block; `NotifySettings.allowlist` (`settings.py:171-181`) |
| V10 Malicious input | Yes: untrusted RPC, feeds, fixtures | `extra="ignore"`/closed models; `CurveDecodeError` (`curve_layout.py:34`); manifest digests (`fixtures.py:96-120`) |

### Threat patterns

| Pattern | STRIDE | Mitigation |
|---------|--------|------------|
| Ledger row tamper with forged chain | Tampering | Hash chain + triggers; verify; snapshot chain hash; external anchor is a residual risk (P10) |
| Approval replay (second order on one approval) | Tampering/Elevation | `consumed` row inside the order transaction (R23); `ApprovalRecord.matches` checks `consumed` (`approvals.py:89`) |
| Duplicate order through retry | Tampering | `exec_place_key` + UNIQUE + first-fill return (R23, R64) |
| Kill switch bypass by env or file | Tampering | Env read once; file polled; clear CLI-only; RISK seat cannot clear (R22) |
| Live path activation | Elevation | Nine preconditions; LiveAdapterStub refuses; no signer imports (`tests/safety/test_no_signing_outside_live_stub.py`) |
| Fixture poisoning (edited events) | Tampering | Manifest sha256 per file (`fixtures.py:96-120`); stray-file rejection |
| RPC response spoofing / malformed curve | Spoofing/Tampering | Length and completion-flag checks; add discriminator check (see Section 15.1); fail closed to `data_unavailable` (R65) |
| LLM prompt injection via feeds | Elevation | Model output is untrusted; LLM-backed decisions need the same RiskEngine checks; no tool grants from LLM output |
| Secret leakage in logs or ledger payloads | Information disclosure | Redaction; no key values in payloads (design 3.3); `mask()` (`settings.py:226-230`) |
| Clock skew manipulating halts or rollover | Tampering | Clock skew refuses appends (AUTO-005); virtual time only in replay |
| Seat escalation through tools | Elevation | `seat_may_trade`, roster grants, `exec.live*` forbidden in rosters (MIGRATION 2.3) |

## 26. Sources

### Primary (in-repo, read this session)

- `.planning/phases/04-paper-trading-and-autonomy/04-CONTEXT.md` (lines 1-76, all sections)
- `.planning/REQUIREMENTS.md` (Phase 4 requirements and traceability)
- `.planning/ROADMAP.md` (Phase 4 success criteria lines 118-129)
- `.planning/STATE.md` (decisions, open blockers, R47 REST degradation)
- `.planning/phases/03-tools-and-skills/03-VERIFICATION.md` (lines 96-150), `03-UAT.md` (lines 19-28), `03-CONTEXT.md` (decisions lines 81-132)
- `.planning/config.json` (workflow flags)
- `docs/design/paper-engine.md` (lines 1-987; binding design)
- `docs/MIGRATION_MAP.md` (lines 1-622; sections 1.8, 2, 3, 4.3, 4.5, 7, 7.1, Unverified)
- `ownership.yaml` (lines 266-391: src, tests, reporting, supervisor, execution rules)
- `pyproject.toml` (lines 9-15 dependencies, 36-41 dev, 72-74 mypy, 86-96 pytest)
- `src/pumpgrok/ledger/store.py` (lines 27-360), `ledger/events.py` (lines 31-352)
- `src/pumpgrok/core/adapter.py` (25-159), `core/approvals.py` (20-96), `core/idempotency.py` (17-85), `core/ids.py` (31-111), `core/risk_budget.py` (15-48), `core/bot.py` (46-104), `core/errors.py` (8-39)
- `src/pumpgrok/replay/clock.py` (22-158), `replay/fixtures.py` (27-176), `replay/rng.py` (12-16)
- `src/pumpgrok/cli.py` (65-812; key ranges cited), `doctor.py` (32-52)
- `src/pumpgrok/config/settings.py` (55-65, 163-168, 171-181, 192-212, 226-290, 346-364, 378-389, 431-509)
- `src/pumpgrok/config/overlays/paper.toml`, `dev.toml`, `live.toml` (`[risk]`, `[live]`, `[replay]` blocks)
- `src/pumpgrok/execution/live/live_gate.py` (19-101), `live_adapter.py` (30-92), `execution/not_yet_implemented.py` (28-73)
- `src/pumpgrok/tools/__init__.py` (114-241), `tools/exec/place.py` (1-7, 84), `tools/risk/kill_switch.py` (70-160 range), `tools/risk/halt_status.py:75`
- `src/pumpgrok/tools/onchain/curve_layout.py` (3-6, 26-31, 34-145), `tools/market/price.py` (run_price), `tools/market/liquidity.py:74`, `tools/onchain/lp_status.py:72`, `tools/onchain/rpc.py` (36-149)
- `src/pumpgrok/tools/journal/render_report.py` (37-166 range)
- `src/pumpgrok/engine/pipeline.py` (34-111), `engine/reputation.py` (43-119), `engine/exits.py` (29-98), `engine/watcher.py` (34-49), `engine/monitor.py:44` (CURVE_COMPLETION_SOL; vendor reference monitor.py:30)
- `tests/conftest.py` (1-35), `tests/harness/faults.py` (42-96), `tests/safety/test_static_guards.py` (17-45), `tests/test_skip_cycle.py` (55-138), `tests/test_live_gate.py` (22-76), `tests/config/test_settings.py:107`, `tests/tools/risk/test_kill_switch_source.py:25,72`
- `tests/fixtures/replay/smoke/manifest.json`, `events.jsonl`; `tests/fixtures/http/*` (7 files)
- `vendor/grokbot-pumpfun/src/executor.py` (28-195), `risk.py` (33-382), `ops.py` (32-440 defs), `state.py` (29-91 defs), `log.py` (30-197 defs), `models.py` (243-390 range), `monitor.py:30`, `pipeline.py` (references only)
- `vendor/grokbot-pumpfun/tests/*.py` (counts by `grep -c 'def test_'`: 21, 19, 16, 20, 21, 8, 24, 37, 18, 36, 13, 16, 15)
- `contracts/events/*.schema.json` (18 files); `tests/ledger/test_events.py` (schema and money checks)
- `rules/pumpgrok-team.mdc:34` (FLOOR line, 2 lines contain U+2013) and `:42` (vendor path)
- Repo census commands run this session: `grep -rln -F` for `vendor/grokbot-pumpfun`, `409e74c`, `src.pipeline`; `find tests ci/tests -name test_*.py` duplicate check (none); `find tests -name __init__.py` (only harness)

### Secondary (design-cited, binding but partly unimplemented)

- `[CITED: docs/design/paper-engine.md]` sections 2-9, 10, 11, unverified items 1-16
- `[CITED: docs/upgrade-plan-desk-v2.md]` R-items (R20 at line 186, others per CONTEXT)

### Tertiary (ASSUMED; training knowledge; to be verified)

- pump.fun program id, PDA seeds, account layout order and size, Anchor discriminator applicability (Section 15.2)
- sqlite transaction behaviour details (A4)
- Solana getAccountInfo commitment options (standard RPC)

## 27. Metadata

**Confidence breakdown:**
- Standard stack: HIGH (declared in pyproject.toml, lines verified)
- Architecture and module placement: HIGH for existing modules (read), MEDIUM for planned modules (design only)
- Ledger design and gaps: HIGH (code read; gaps enumerated)
- PaperAdapter math: HIGH for formulas (design, internally consistent); MEDIUM for numeric REVIEW values
- Risk engine order and breakers: HIGH (design and CONTEXT agree on 19 steps)
- Supervisor design: MEDIUM (no code exists; seat bodies undefined)
- Reports: HIGH for requirements, MEDIUM for reuse decision
- Live gate: HIGH (code read), MEDIUM for construction-time semantics (D-j)
- R65 external chain facts: LOW (ASSUMED, unverified)
- Vendor census: HIGH for grep results; MEDIUM for scope interpretation (D-b)
- Test counts: MEDIUM (grep, not collect-only)

**Research date:** 2026-10-21
**Valid until:** 7 days (the tree is changing in this phase; re-check file:line citations before planning)

**Not executed in this research (by assignment):** the test suite, lint, type checks, the R65 live probe, network access to any feed or RPC, and any CLI verb that writes var/ state.
