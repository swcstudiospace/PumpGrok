# DESIGN A - Event runtime and Grok gateway (milestone v4)

Scope: replace cadence polling with typed events; make every Grok call a consequence of an event and pass one gateway. Evidence: `supervisor/scheduler/supervisor.py` (SEAT_CADENCES, `_start_due`, `tick_once`, `serve_forever`), `seat_task.py` (`is_due`, `RestartPolicy`), `degraded.py`, `core/llm.py` (GrokOps), `core/budget.py`, `engine/agents/base.py`, `replay/recorder.py`, `replay/clock.py`, `hermes/cron/jobs.yaml`, scouts A/B. Not present in this checkout: any non-replay composition root that instantiates GrokAgent or GrokOps (grep: `GrokOps(`/`CallBudget(` appear only in tests), so the gateway owns that wiring.

## 0. Invariants that shape everything
- Bus state lives in a SIDECAR sqlite `var/events/events.sqlite` (dead letters, dedup, cursors, pending events, Grok cache, Grok budget, Grok call rows). It never touches the ledger, so replay hashes cannot move. Ledger writes reuse existing types only: `Escalation` with new free-string kinds `event_dead_letter`, `event_backlog`, `source_stale`, `grok_budget_exhausted` (`Escalation.kind` is a plain `str`; schema untouched, no contract change; `seat_task._ESCALATION_SEVERITY` gets the severities).
- Event ids are derived, never random: `sha256(kind|entity|dedup_key)` first 32 hex. Time via injected Clock only. Money int lamports; ratios Decimal.
- Legacy replay path (`run_once_replay`, `tick_once`, `FIXTURE_SEAT_CADENCES`) is NOT edited. Hash safety is by construction (section 4.4).

## 1. Typed event model (`src/pumpgrok/events/models.py`, owner bot-02-risk)
Pydantic v2 frozen `Event`: `event_id`, `kind: EventKind` (StrEnum), `entity: str` (lane key), `ts: float` (occurrence time from data, else Clock), `source_seq: int` (assigned by the source adapter in input order; fixture line number in replay), `dedup_key: str`, `source: str`, plus a typed payload per kind. `priority` is a pure function of kind (`PRIORITY[kind]`), never a payload field, so a handler cannot escalate.

| Class | Kinds (entity) | Payload reuse |
|---|---|---|
| P0 critical, never dropped | `ExitTrigger(mint)`, `PositionTick(mint)` (price tick of a HELD mint), `OrderOutcome(mint)`, `PositionChange(mint; opened/closed, ticket_id)`, `RiskEdge(desk; halt/breaker/kill/resume)`, `SourceStatus(source)`, `Timer(desk)`, `Heartbeat(seat)`, `Shutdown(desk)` | `CurveSnapshot` as is; `Freshness` in SourceStatus |
| P1 standard | `TokenLaunched(mint)`, `Migration(mint)`, `CandidateReady(mint)`, `StrategySignal(mint, strategy_id)`, `LeadCreated(mint)`, `HolderShift(mint)`, `GrokVerdict(mint)` | engine `Token` unchanged (`unique_buyers None` stays fail-closed) |
| P2 bulk | `PriceTick(mint)` (unheld), `TradeObserved(mint)`, `LargeTransfer(wallet)`, `SocialMention(mint)` | `CurveSnapshot`, engine `Trade`, `Quote` not used |

Held-mint promotion: the source adapter holds a `HeldMints` view (folded from ledger `PositionView`) and emits a tick for a held mint as `PositionTick` (P0, coalesce latest), otherwise `PriceTick` (P2). `SourceStatus.state` in `up|stale|down|resyncing|resynced`, carries `Freshness | None` and `gap_s`. `GrokVerdict` carries agent, request hash, `fallback_level`, never the model text.

## 2. EventBus (`events/bus.py`, `dlq.py`, `store.py`)
Interface `EventPublisher.publish(event) -> PublishResult(accepted|deduped|coalesced|rejected_closed|spilled)`; two implementations, `AsyncEventBus` (live) and `DeterministicBus` (section 2.3).

### 2.1 Lanes and priority
- P1/P2: one deque per entity (`lane_key = entity`), handled serially per lane, so per-entity order is FIFO. Different lanes run concurrently up to `events.max_concurrency` (default 4).
- P0: one global FIFO lane with its own `events.priority_workers` (default 2) that no P1/P2 handler can occupy. P0 may overtake P1/P2 of the same entity (an exit must not wait behind a Grok-bound handler); handlers read latest state and are idempotent, and each P0 event carries its own snapshot. Documented guarantee: order is total within (entity, class).
- Handlers register `HandlerSpec(name, seat, kinds, fn, idempotent=True, max_attempts, base_s, cap_s, deadline_s)`. Grok awaits happen only in P1 handlers.

### 2.2 Bounds, backpressure, dedup, coalescing, retry, DLQ, shutdown
- Bounds (settings `EventsSettings`, defaults): per-lane 256, P1+P2 total 4096, P0 soft 10000.
- Backpressure: P0 NEVER dropped. At soft bound the producer `await`s space (internal producers only), one `Escalation(event_backlog)` per outage and `degraded.bus_backlog=True`. P1 full: reject newest, persist to DLQ with reason `overflow` (older events keep order; nothing silent). P2 full: drop oldest entity entry, count `events_dropped_total{reason=overflow}`; P2 is mostly coalesced so depth is bounded by entity count.
- Dedup: `dedup_key` per kind (TokenLaunched: mint; TradeObserved: signature; OrderOutcome: order id; RiskEdge: ledger seq; PositionChange: ticket+change). TTL per kind (1 h, 10 min, 24 h, 24 h, 24 h) measured on Clock. P0/P1 keys persisted in sqlite `seen(key, expires_at)` so restart plus resync overlap cannot reprocess; P2 keys in memory.
- Coalescing per kind: `latest` (replace pending event with same `(kind, entity)`: PositionTick, PriceTick), `debounce(window_s, max_wait_s)` (SocialMention 30 s, HolderShift 5 s), `none`. Debounce uses `clock.sleep` tasks; replay uses virtual timers.
- Handler retry: only for transient errors (`DataStale`, `ToolTimeout`, `ToolRateLimited`, `LedgerUnavailable`); any other exception is poison, straight to DLQ. Backoff `min(cap, base*2**(n-1)) * (0.5 + rng.random())`, slept on `clock.sleep`, rng = `make_rng(run_seed + crc32(handler.name))` (seeded jitter, same shape as `GrokAgent._backoff`). P0 handlers retry until `deadline_s` (exit: 60 s) then DLQ plus `Escalation(event_dead_letter)`; an unsold exit is critical. `CancelledError` always propagates.
- DLQ: table `dead_letters(id, ts_utc, kind, entity, dedup_key, handler, attempts, error_code, error_text_redacted, event_json)` (canonical_json). CLI `pumpgrok events dlq list|replay|purge` (`cli/events.py`). `replay` clears the dedup key and republishes.
- Idempotent handlers: `HandlerContext.idempotency_key = derive_idempotency_key(handler, seat, {"event_id": ...})`; ledger writes pass it, and the store's UNIQUE constraint (IntegrityError) is treated as success. Registry test double-delivers every event to every handler and asserts ledger rows unchanged.
- Graceful shutdown `bus.close(grace_s)`: refuse new P1/P2, keep accepting P0, drain P0, drain P1 until `clock.timeout(grace_s)`, persist leftovers (P0/P1) to `pending_events`, await in-flight handlers. `recover()` re-injects them at boot (dedup protects). Called from `lifecycle.shutdown` drain.

### 2.3 Deterministic drain (replay and backtest)
`DeterministicBus` has the same interface, no tasks, no wall time. Total order `(ts, priority_rank, source_seq)`; `source_seq` comes from the source (fixture line), never from publish order. `drain(until_ts)` pops in key order and awaits each handler inline, handlers in roster order. Retries/debounce/timers run as heap timers on `FixtureClock.advance_to` (the same mechanism as `_settle_on_virtual_time`). Coalescing is OFF by default in drain so every recorded tick is processed (opt-in per backtest, recorded in the run manifest). No sidecar sqlite (in-memory seen/DLQ); a DLQ entry in a replay fails the run. Same events plus same seed gives byte-identical ledger and `events.hash`; test runs twice and compares.

## 3. SourceSupervisor (`events/sources.py`, bot-02-risk)
`SourceSpec(name, open(cursor) -> AsyncIterator[Event], resync(cursor) -> AsyncIterator[Event], stale_after_s, backoff_base_s=1, backoff_cap_s=60, stable_s=30)`. One task per source; wraps a `core.datasource.DataSource` (Freshness, Health) where the source already is one.
- Reconnect: `min(cap, base*2**n)*(0.5+rng.random())`, rng seeded per source. The attempt counter resets only after `stable_s` of healthy frames, not on connect (today `monitor.py` resets at connect, which hammers a flapping endpoint). One PumpPortal connection only (research2: single connection, ban risk).
- Staleness: each recv runs under `clock.timeout(stale_after_s)` (WS 120 s = `WS_STALE_S`; RPC poll sources use `Freshness.stale`). Timeout publishes P0 `SourceStatus(stale)`; the `DegradedBridge` handler (chief unit) maps it to `degraded.note_ws_frame` withheld (`ws_data_stale`), `note_rpc_result(i, False)` and `llm_available`. Recovery is the same setter.
- Resync after reconnect: emit `resyncing`, then `resync(cursor)`: RPC log source uses `getSignaturesForAddress(until=last_sig)` then `getTransaction` for gaps (research2 section 3); for every HELD mint it seeds one `PositionTick` from a curve read, so exit rules never wait for the next trade. PumpPortal has no replay: the gap is recorded (`gap_s`) and missed launches are not chased (fail closed, no catch-up buys). Replayed events are marked and deduped by signature. Then `resynced`.
- Cursor: table `cursors(source, cursor_json, updated_at)`, written every 50 events or 5 s and at close, atomic. At-least-once; dedup absorbs overlap.

## 4. Supervisor: cadence polling to event wakes
### 4.1 Mechanism (bot-00-chief)
`SeatTask` gains a bounded wake set (dedup on `(kind, entity)`), `wake(event)`, and `SeatContext.wakes: tuple[Event, ...] = ()`. `Supervisor(wake_mode="cadence"|"event")`, default `"cadence"`. Event mode: `is_due` = pending wakes or heartbeat due; `serve_forever` waits on `asyncio.Event` plus the nearest timer via `clock.sleep`, no 1 s `TICK_S` loop; `_start_due` keeps the single-flight "busy" rule; wakes arriving during a cycle are merged into the next one. A new `WakeRouter` (`supervisor/scheduler/wake.py`) subscribes seat handlers on the bus per `SEAT_WAKES`. `SEAT_CADENCES` stays as the fixture/legacy table.
### 4.2 Timers that legitimately remain (all Grok-free, cheap)
`Heartbeat` per seat every 30 s (cycle gets `wakes=(Heartbeat,)`, liveness only; stale after 3 missed = 90 s, replacing cadence-derived staleness so an idle seat is never "stale"); health.json every 10 s (`HEALTH_FILE_INTERVAL_S`); `Timer(daily_rollover)` at next UTC midnight plus once at start (`rollover_key` keeps it idempotent); reconciliation every 300 s (`store.verify()`, position/ledger fold); kill-source poll every 2 s (`risk.poll_kill_sources`, RISK-004: env/file have no push event); relay tail every 2 s (ledger has no notifier); per-position `ExitDeadline(mint)` timer at open (max_hold, replaces 15 s polling); position watchdog: only while positions are open, a held mint with no tick for `exits.max_silence_s` (30 s) triggers a direct curve read and a `PositionTick`; dedup/DLQ TTL sweep every 60 s.
### 4.3 Wake table replacing SEAT_CADENCES (event mode)
| Seat (old cadence s) | Wake events |
|---|---|
| chief (60) | RiskEdge, SourceStatus change, escalation/ticket rows (relay), Heartbeat |
| scout (10) | TokenLaunched, Migration, SourceStatus(pumpportal resynced) |
| risk (5) | CandidateReady, PositionTick (coalesced to 1/s), OrderOutcome, RiskEdge(halt/breaker) |
| whale (120) | LargeTransfer, CandidateReady (whale-eligible), SourceStatus(rpc) |
| sniper (1) | StrategySignal / CandidateReady with BUY verdict, OrderOutcome(partial/retry) |
| rug (30) | PositionTick (held), HolderShift, Migration (held), SourceStatus(blind) |
| exit (15) | PositionTick, ExitDeadline, OrderOutcome(sell), RiskEdge(halt) |
| shill (300) | SocialMention (no source exists; heartbeat only) |
| signal (1) | TokenLaunched that passed `passes_filter` (CandidateReady), GrokVerdict, SourceStatus(llm) |
| journal (300) | OrderOutcome, PositionChange(closed), Timer(daily_rollover); flush only when dirty |
Promotion/strategy consumers (design C) subscribe to PositionChange(closed), Timer(daily_rollover), RiskEdge(breaker), StrategySignal; no timers.
### 4.4 Replay hash plan
`run_replay`, `run_once_replay`, `tick_once`, `FIXTURE_SEAT_CADENCES`, `llm_request_for` and the ledger writers are untouched; `wake_mode` defaults to cadence; the bus writes nothing to the ledger. Therefore smoke-10m `events.hash` stays `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` and no CHANGELOG pair is needed. Proof: (a) existing `tests/replay/test_replay_determinism.py` and `test_replay_hash_pin` (new, pins the value); (b) a parity test drives `DeterministicBus` with one `FixtureStep` event per distinct stamp and `WakePolicy.fixture_compat` (wake exactly the seats where `SeatTask.is_due(now)` is true, roster order) and asserts the same hash. Event-native wake tables get their own golden hashes (`events-smoke-10m`, `events-soak-3d`) recorded as NEW entries in CHANGELOG. If the default of `run --replay` is later flipped to event mode, CHANGELOG records before and after (expected equal under compat).

## 5. Grok gateway (`src/pumpgrok/grok/`, bot-02-risk)
`GrokGateway.call(GrokRequest) -> GrokOutcome`. `GrokRequest(agent, schema, tier, prompt_sha, payload, entity, cause_event_id, priority=normal|reserve, ttl_s)`. `AgentPort` protocol (name, prompt_sha, build_request, run_network, parse, fallback) keeps `grok/` free of engine imports; `engine/agents` adapt (signal seat).
Pipeline, in order:
1. Deterministic prefilter (pure, no I/O). Auditor/narrative: candidate already passed `passes_filter`, age within window, `unique_buyers` present, no open position or cooldown for the mint, reputation not blocked, rule pre-score (`compute_scores` with LLM parts neutral) at least `grok.min_prerank`. Checker only after all earlier verdicts and when `RiskEngine` would not refuse for non-LLM reasons (halt, autonomy, budget): no paying to check a vetoed trade. Timing only on a market-window event. Result `Skip(reason)` is accounting, not failure.
2. Sanitize (`sanitize.py`, `SANITIZER_VERSION`): NFKC, strip control/zero-width/bidi, collapse whitespace, truncate (name 32, symbol 12, description 280, URLs host only). Untrusted text goes only inside `payload.untrusted` JSON under an explicit envelope, and the system prompt states it is data. Pattern heuristics (role markers, "ignore previous", fences, `<|`) set `injection_flagged`; a flagged token sends NO text (`untrusted=null`) and the narrative fallback applies. The checker input is built from structured Analysis values and sanitized flags, never raw names.
3. Cache key `canonical_request_hash({"kind":"grok_call","agent","model","prompt_sha","schema","sanitizer":V,"input":payload})` (volatile keys such as `asked_at`, `created_timestamp` are already stripped by `_VOLATILE_RE`). TTL: narrative 24 h (key on text digest, so copy-paste names share a verdict), auditor 300 s, timing 900 s (`ScoringSettings.timing_cache_seconds`), checker 60 s. Sidecar sqlite, LRU 5000 rows, in-memory in replay. Pessimistic fallbacks are never cached; transport errors negative-cached 30 s to stop retry storms.
4. In-flight coalescing: `dict[key, Future]`; identical concurrent requests await one HTTP call (`coalesced` counter).
5. Layered persisted budget (`budget.py`): `LayeredBudget` with minute/hour/day windows (defaults 6/60/400, settings `GrokGatewaySettings`), atomic all-or-nothing `try_spend` across layers, window starts from `clock.now()`, persisted so restart does not reset, fail closed if unreadable. It implements the `CallBudget` surface so `GrokOps(limiter, budget)` takes it; `GrokOps.precheck` is changed to report `budget.denial_reason()`. The existing per-attempt precheck in `GrokAgent._call` therefore charges every real HTTP attempt. `reserve` priority (checker) may use the top 20 percent of each layer; background work cannot.
6. Execute through the existing `GrokAgent._call` (retries, limiter, semaphore), then STRICT parse: the whole reply must be one JSON object (`json.loads(strip)`, no first-balanced-object scavenging, which lets injected prose win); `result_model` stays `extra=forbid`, ranges validated, `flags` items match `^[a-z_]{1,32}$` max 8, `reasoning` max 400 chars and never fed into any later prompt or decision. Any violation yields the agent's pessimistic fallback.
Fallback ladder, tied to `DegradedState.signal_scoring_mode`: `fresh` / `cache_hit` / `coalesced` (also served in rule_fallback) then `prefilter_skip`, then `rule_fallback` (gateway sets `llm_available=False` on 3 consecutive failures via breaker with 60 s Clock cooldown and one half-open probe, or when a budget layer is exhausted until its window rolls), then `observe_only_buys` if `require_llm`, then `pessimistic`. Each outcome carries `fallback_level`; a transition emits one `Escalation(grok_budget_exhausted)` for budget cases.
Never blocking exits or risk: `exit_rules`, `risk/**`, `execution/**`, `engine/watcher` must not import `pumpgrok.grok` (static import-graph test); the gateway runs only in P1 handlers, total call deadline 20 s on `clock.timeout`; a test hangs the transport forever and asserts an `ExitTrigger` still sells within bounded virtual time.
Replay compatibility: `ReplayBackend` wraps `ReplayLlm`: request dict -> `canonical_request_hash` -> record, miss raises `ReplayMissingRecord`, never the network. The legacy dataset-level request from `llm_request_for` (used by the signal seat for smoke) is unchanged, so existing `llm.jsonl` hashes still resolve; new per-call records use the `grok_call` shape above. The live recorder (design B) writes `llm.jsonl` rows at the gateway boundary with the same hash. In replay, cache and budget run on virtual time and in memory, so results are deterministic.
Four agents: `engine/agents/gateway_agents.py` builds `AgentPort`s from `AuditorAgent`, `NarrativeAgent`, `TimingAgent`, `CheckerAgent` (class attrs `name`, `prompt`, `result_model`, `use_checker_model`, `build_user_message`, `fallback`). Trigger map: auditor and narrative on `CandidateReady` after prefilter; timing on market-window event; checker last, `reserve` priority, immediately before the sniper buy. Signal seat calls gateway, never `GrokAgent.run` directly.

## 6. Hermes cron
| Job | Action |
|---|---|
| scout-discover (60m) | disable: TokenLaunched/Migration events |
| scout-pipeline (60m) | disable: reads archived retired-engine JSONL, no event source; keep on-demand verb |
| risk-audit-open-leads (15m) | disable: CandidateReady/LeadCreated wake risk seat |
| chief-pickup (15m) | disable: relay of Escalation/HaltSet/BreakerTripped already notifies (`relay_tail`) |
| rug-watch-paper (30m) | disable: PositionTick/HolderShift wake rug seat |
| chief-journal-rollup (daily) | keep, add `require_activity: true` (prompt exits `[SILENT]` on zero trades), at most 1 session/day, 0 when idle |
Add `superseded_by: events` field; `desk doctor` refuses event mode with a superseded job still enabled. Baseline today is about 12 Hermes sessions/hour (scout A, inference). Owner bot-00-chief; `jobs.yaml` is not a contract surface.

## 7. Metrics and measurement
`GrokCallLedger` (`grok/ledger.py`, plain dataclass, no prometheus import): counts by `(agent, outcome)`, outcome in `call_ok|call_error|cache_hit|coalesced|prefilter_skip|budget_denied|breaker_open|rule_fallback|replay_hit`; tokens in/out; latency sum/count on Clock; `by_event_kind`. Every real call appends a row to sidecar `grok_calls(ts, agent, model, request_hash, cause_event_id, latency_s, tokens, outcome)`.
Prometheus, in a NEW extension `supervisor/metrics_events.py` registered on the same registry only when event mode is on, so `NINE_FAMILIES` and `test_exposition_carries_exactly_the_nine_names` stay valid: `pumpgrok_grok_calls_total{agent,outcome}`, `pumpgrok_grok_tokens_total{agent,direction}`, `pumpgrok_grok_call_seconds{agent}`, `pumpgrok_grok_budget_remaining{window}`, `pumpgrok_grok_fallback_mode`, `pumpgrok_events_published_total{kind,priority}`, `pumpgrok_events_dropped_total{kind,reason}`, `pumpgrok_events_dead_letters_total{kind}`, `pumpgrok_event_queue_depth{lane}`, `pumpgrok_event_handler_seconds{handler}`, `pumpgrok_event_handler_retries_total{handler}`, `pumpgrok_source_state{source}`, `pumpgrok_source_reconnects_total{source}`, `pumpgrok_seat_wakes_total{seat,kind}`.
Before/after method (`scripts/measure_grok_calls.py`, bot-00-chief): replay recorded datasets (smoke-10m, soak-3d, later live-recorded sets) twice through a counting fake transport at the `GrokAgent._call` boundary. BEFORE = counterfactual cadence policy: every signal-seat 1 s wake re-analyzes pending candidates with all four agents, timing uncached. AFTER = gateway policy. Output JSON `{dataset, candidates, calls_before, calls_after, cache_hits, skips}`; report states these are modeled counts (no wired live baseline exists) and the live truth is the `grok_calls` table over 24 h of live-paper. Idle test: event-mode desk on FixtureClock, zero source events, 24 virtual hours, fake transport that fails on any call: `calls == 0`, ledger `GrokCallLedger.total == 0`, only Heartbeat/health/reconcile timers ran.

## 8. Failure-injection tests (extend `tests/harness/faults.py`: `FaultyEventSource`, `FaultyGrokTransport`, same `fired` counters as existing fakes)
1. Handler poison exception -> DLQ, other lanes continue. 2. Transient handler error retries with seeded backoff, then succeeds; same seed same delays. 3. Exit handler failing past deadline -> DLQ plus Escalation. 4. P0 flood beyond soft bound -> producer blocks, zero P0 dropped. 5. P1 overflow -> DLQ `overflow`, order of survivors kept. 6. Duplicate delivery (same dedup key twice, and restart overlap) -> one ledger effect. 7. Crash mid-drain then `recover()` -> pending events processed once. 8. Source disconnect storm -> backoff grows, resets only after `stable_s`. 9. Source silent 121 s -> `SourceStatus(stale)`, `ws_data_stale`, recovery clears. 10. Reconnect with gap -> held mints get seeded ticks, replayed signatures deduped. 11. Cursor corrupt -> start from head, `Escalation`, no crash. 12. Grok 429/5xx/timeout x3 -> breaker opens, `rule_fallback`, exits unaffected; half-open recovery. 13. Budget minute/hour/day exhaustion each denies, window roll restores, restart keeps spent. 14. Prompt-injection corpus in name/description -> no raw text in payload, reply with extra keys/prose/out-of-range -> pessimistic fallback, no tool call. 15. Transport hangs forever -> `ExitTrigger` sells in bounded virtual time. 16. 100 identical concurrent requests -> 1 HTTP call. 17. Replay: gateway with missing record raises `ReplayMissingRecord`. 18. Ledger unwritable during handler -> buffer path (existing) plus retry.

## 9. Requirements (command plus expected exit; `uv run pytest` abbreviated `pt`)
| Id | Requirement | Acceptance command | Exit |
|---|---|---|---|
| EVT-01 | Typed frozen event models, derived ids, priority by kind table, no float money | `pt tests/events/test_models.py -q` | 0 |
| EVT-02 | P0 lane never drops; P1 overflow goes to DLQ; P2 coalesces | `pt tests/events/test_bus_backpressure.py -q` | 0 |
| EVT-03 | Per-entity FIFO and P0 isolation from slow P1 handlers | `pt tests/events/test_bus_lanes.py -q` | 0 |
| EVT-04 | Dedup with TTL (persisted for P0/P1), debounce and latest-wins coalescing on Clock | `pt tests/events/test_bus_dedup_coalesce.py -q` | 0 |
| EVT-05 | Handler retry: transient only, seeded jitter on Clock, poison to persisted DLQ, `pumpgrok events dlq replay` works | `pt tests/events/test_bus_retry_dlq.py -q` | 0 |
| EVT-06 | Handlers idempotent under double delivery | `pt tests/events/test_handler_idempotency.py -q` | 0 |
| EVT-07 | Graceful shutdown persists pending, recover resumes once | `pt tests/events/test_bus_shutdown.py -q` | 0 |
| EVT-08 | Deterministic drain gives byte-identical ledger across two runs and equals legacy smoke-10m hash under fixture_compat | `pt tests/replay/test_event_drain_parity.py -q` | 0 |
| EVT-09 | SourceSupervisor backoff, staleness to DegradedState, resync, cursor | `pt tests/events/test_sources.py tests/degradation/test_event_source_faults.py -q` | 0 |
| EVT-10 | Event-mode supervisor wakes seats per `SEAT_WAKES`; cadence mode unchanged; remaining timers are exactly the allowed set | `pt tests/supervisor/test_event_wake.py tests/supervisor/test_scheduler.py -q` | 0 |
| EVT-11 | smoke-10m events.hash unchanged | `pt tests/replay/test_replay_hash_pin.py -q` | 0 |
| EVT-12 | Idle desk: 24 virtual hours, zero source events, zero Grok calls | `pt tests/events/test_idle_zero_grok.py -q` | 0 |
| EVT-13 | Hermes superseded jobs disabled, doctor refuses double-trigger | `pt tests/test_hermes_jobs_superseded.py -q` | 0 |
| GRK-01 | Prefilter skips before any budget spend | `pt tests/grok/test_prefilter.py -q` | 0 |
| GRK-02 | Cache key via `canonical_request_hash`, TTLs, no caching of fallbacks | `pt tests/grok/test_cache.py -q` | 0 |
| GRK-03 | In-flight coalescing: N identical requests, 1 call | `pt tests/grok/test_coalesce.py -q` | 0 |
| GRK-04 | Layered persisted budget, atomic, reserve, restart-safe | `pt tests/grok/test_budget.py -q` | 0 |
| GRK-05 | Sanitizer and strict parse defeat the injection corpus | `pt tests/grok/test_sanitize_injection.py tests/engine/test_gateway_agents.py -q` | 0 |
| GRK-06 | Fallback ladder follows `signal_scoring_mode`; breaker and half-open | `pt tests/grok/test_fallback_ladder.py -q` | 0 |
| GRK-07 | Exits and risk never import or wait on gateway | `pt tests/safety/test_no_grok_in_exit_risk.py tests/degradation/test_grok_hang_exit.py -q` | 0 |
| GRK-08 | Replay backend honors recorded hash, miss raises | `pt tests/grok/test_replay_backend.py tests/replay/test_replay_determinism.py -q` | 0 |
| GRK-09 | Four agents behind gateway; signal seat never calls `GrokAgent.run` directly | `pt tests/engine/test_gateway_agents.py -q` | 0 |
| GRK-10 | Metrics families exposed in event mode; nine families unchanged | `pt tests/supervisor/test_metrics.py tests/supervisor/test_metrics_events.py -q` | 0 |
| GRK-11 | Measurement script outputs before/after JSON and calls_after is at most 20 percent of calls_before on soak-3d | `uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/soak-3d --max-ratio 0.2` | 0 |

## 10. Units
Seat-pure: a PR touches one seat's paths. Chief units contain no tests (tests under `tests/**` resolve to risk, except `tests/engine/**` to bot-08-signal); their tests ship in test-first risk units that use `pytest.importorskip` on the target module, and the chief unit's acceptance asserts zero skips (`! uv run pytest <file> -rs | grep -q SKIPPED`). Note `cli/**` resolves to bot-02-risk here, not chief.

| Unit | Title | Owner | Files | depends_on | Acceptance |
|---|---|---|---|---|---|
| A0 | Settings, errors, harness fakes | bot-02-risk | `config/settings.py` (EventsSettings, GrokGatewaySettings), `core/errors.py` (EventBusSaturated, GrokBudgetDenied), `tests/harness/faults.py` (FaultyEventSource, FaultyGrokTransport), `tests/harness/test_faults.py` | none | `pt tests/harness tests/config -q` |
| A1 | Event models, bus, store, DLQ, CLI | bot-02-risk | `events/{__init__,models,bus,store,dlq}.py`, `cli/events.py`, `cli/parsing.py`, `docs/design/events-grok.md`, `tests/events/test_{models,bus_lanes,bus_backpressure,bus_dedup_coalesce,bus_retry_dlq,handler_idempotency,bus_shutdown}.py` | A0 | EVT-01..07 commands |
| A2 | Deterministic drain and parity tests | bot-02-risk | `events/drain.py`, `tests/replay/{test_event_drain_parity,test_replay_hash_pin}.py` (parity part importorskips wake until A4) | A1 | EVT-08, EVT-11 |
| A3 | SourceSupervisor | bot-02-risk | `events/sources.py`, `tests/events/test_sources.py`, `tests/degradation/test_event_source_faults.py` | A1 | EVT-09 |
| A5 | Grok gateway core | bot-02-risk | `grok/{__init__,gateway,prefilter,cache,budget,sanitize,ledger,replay_backend}.py`, `core/llm.py`, `tests/grok/*.py`, `tests/safety/test_no_grok_in_exit_risk.py` | A0 | GRK-01..04, 06, 08 |
| T4 | Wake and idle tests (test-first) | bot-02-risk | `tests/supervisor/test_event_wake.py`, `tests/events/test_idle_zero_grok.py`, `tests/degradation/test_grok_hang_exit.py`, `tests/test_hermes_jobs_superseded.py`, `tests/supervisor/test_metrics_events.py` (all importorskip) | A1, A5 | collect-only exit 0 |
| A4 | Supervisor wake queues, Heartbeat/timers, DegradedBridge, shutdown hook | bot-00-chief | `supervisor/scheduler/{wake,supervisor,degraded,serve}.py`, `supervisor/{seat_task,lifecycle}.py` | A1, T4 | EVT-10, EVT-12 (no skips), `pt tests/supervisor -q` |
| A6 | Agents behind gateway, strict parse | bot-08-signal | `engine/agents/{base,narrative,auditor,timing,checker,gateway_agents}.py`, `tests/engine/test_gateway_agents.py` | A5 | GRK-05, GRK-09 |
| A7 | Event and Grok metrics extension | bot-00-chief | `supervisor/metrics_events.py`, `supervisor/metrics.py` (hook only) | A1, A5, T4 | GRK-10 |
| A8 | Hermes cron cutover | bot-00-chief | `hermes/cron/jobs.yaml`, `hermes/cron/prompts/chief-journal.md`, `hermes/README.md`, `skills/hermes-cron-desk/SKILL.md`, `docs/runbooks/events.md` | A4, T4 | EVT-13 |
| A9 | Measurement script | bot-00-chief | `scripts/measure_grok_calls.py` | A5, A6 | GRK-11 |
| A10 | Cross-cutting failure suite and CI gate | bot-02-risk | `tests/degradation/test_event_*.py`, `ci/gates/check_idle_grok.py`, `Makefile` | A3, A4, A6, A7 | all section 8 tests, `uv run python ci/gates/check_idle_grok.py` |
| A11 | CHANGELOG: new golden hashes, smoke-10m unchanged note | bot-09-journal | `CHANGELOG.md` | A2, A10 | `grep -c "events-smoke-10m events.hash" CHANGELOG.md` is 1 |

Parallel waves: W1 {A0}. W2 {A1, A5}. W3 {A2, A3, T4, A6} (T4 needs A1 and A5, A6 needs A5). W4 {A4, A7}. W5 {A8, A9, A10}. W6 {A11}. A2/A3 and A6 are independent of each other; A4 and A7 touch different chief files (`metrics.py` only gets a registration hook) so they run in parallel.
