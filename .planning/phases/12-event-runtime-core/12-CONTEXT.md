# Phase 12 CONTEXT: Event runtime core

Milestone v4, Phase 12. Goal per ROADMAP: a typed, bounded, deterministic event runtime exists as a LIBRARY: frozen event models with derived ids, an EventBus with per-entity FIFO lanes, a never-dropping P0 lane, dedup, coalescing, seeded retry, a persisted DLQ, graceful shutdown, a deterministic drain for replay, and a SourceSupervisor with reconnect backoff, staleness, resync and cursors. The v4 settings skeleton lands here once. Nothing is wired into the supervisor yet and the replay path is untouched.

Depends on: Phase 11 (settings split 11-04 and the pins 11-01). Reuses without re-implementing: core/ids.py, core/idempotency (derive_idempotency_key), core/datasource (Freshness, Health), replay/clock.py FixtureClock, harness FaultInjector in tests/harness/faults.py, ledger Escalation (Escalation.kind is a plain str).

## Locked decisions (NON-NEGOTIABLE)

- D-01: Money integer lamports, Decimal only for ratios.
- D-02: time only through the injected Clock; no datetime.now, time.time or time.sleep under src/pumpgrok/events (`! grep -rnE 'datetime\.(now|utcnow)|time\.(time|sleep)\(' src/pumpgrok/events`).
- D-03: Live stays refused (exit 3); this phase adds no live code.
- D-04: hashes are identity only, never a score or verdict.
- D-05: mypy --strict, ruff, no dead code, no swallowed errors, no placeholders, ASCII-only docs.
- D-06: SET0 (plan 12-01) is the ONE settings skeleton: a module per area under config/sections (events, grok_gateway, datafeed, recorder, strategies, backtest_v2, risk_strategy, promotion, live, signer, paper_fees), one import and one field line each in settings.py; defaults leave every behavior off (events.wake_mode cadence, strategies.runtime_enabled false, live.enabled false, execution.fees.version v1). Later units add NO field or section file. Reason: settings.py was a seven-unit contention chain (N6 item 21).
- D-07: SET0 owns the keys the designs forgot: datafeed.watch_max, datafeed.mtm_refresh_s (45), backtest.gap_haircut_bps, promotion thresholds path, live.arm_max_expiry_hours (default 72, hard ceiling 168), live.notional_cap_sol (validator 0 < x <= 1.0, ConfigError above), live.wallet_allowlist (base58 shape), live.drift_tolerance_lamports (5_000_000), signer.socket_path, socket_group, fee_cap_lamports, confirm_timeout_s, nonce_window_s. No setting name contains seed, span or an _at suffix (canonical_request_hash drops them); use rng_stream, never seed.
- D-08: events/models.py is the ONE catalog (plan 12-02): Design A kinds plus every Design B and C kind (NewTokenSeen as an alias view of TokenLaunched, CurveTick, FeedGap, FeedResynced, MintEvicted, DatasetSealed, LlmCallCompleted, BacktestCompleted, StrategyVersionRegistered, ParamsProposed). One publisher interface `EventPublisher`; priority is a pure function of kind (PRIORITY[kind]), never a payload field.
- D-09: Bus state lives in a SIDECAR sqlite var/events/events.sqlite (dead letters, dedup, cursors, pending events); it never touches the ledger. Ledger writes reuse existing types only: Escalation with free-string kinds event_dead_letter, event_backlog, source_stale, grok_budget_exhausted. No contract surface changes (`test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0`).
- D-10: P0 is never dropped (producer awaits space at the soft bound, one Escalation per outage); P1 overflow rejects newest to the DLQ with reason overflow; P2 overflow drops oldest and counts. Per-entity order is FIFO. Handlers are idempotent: ledger writes pass the idempotency key and a UNIQUE IntegrityError counts as success.
- D-11: DeterministicBus orders by (ts, priority_rank, source_seq) with source_seq from the source (fixture line), never publish order; drain yields until quiescent (coalescing futures, retry timers, FixtureClock FIFO continuation order) before advancing virtual time; coalescing OFF by default; a DLQ entry in replay fails the run. Parity runs on the trading `smoke` fixture against the pinned rows, not only smoke-10m (which has no trades).
- D-12: SourceSupervisor owns staleness for the whole desk through a SourceStateBook and SourceStatus events. DegradedState.ws_data_stale (written by the 14-03 bridge), FeedHealth (17-02) and LivePriceSource (13-02) READ it; none keeps its own timer or calls a separate note_tick.
- D-13: Reconnect backoff min(cap, base*2**n)*(0.5+rng.random()), seeded per source; the attempt counter resets only after stable_s of healthy frames, not on connect. One PumpPortal connection only.

## Grey-area defaults

- G-01: Bounds events.max_concurrency 4, priority_workers 2, per-lane 256, P1+P2 total 4096, P0 soft 10000. Reason: Design A section 2.2 defaults.
- G-02: Dedup TTLs 1 h, 10 min, 24 h, 24 h, 24 h by kind; P0/P1 keys persisted, P2 in memory. Reason: restart plus resync overlap must not reprocess.
- G-03: Handler retry only for transient errors (DataStale, ToolTimeout, ToolRateLimited, LedgerUnavailable); anything else is poison to the DLQ; P0 handlers retry until deadline_s (exit 60 s). CancelledError always propagates.
- G-04: OD-02, OD-03, OD-07 defaults recorded as REVIEW values (desk caps 6 and 40 are applied by the 15-02 overlay, holder 0.30, strategy loss 0.25, 4 losses, drift 5_000_000).

## Phase boundary

In scope: src/pumpgrok/config/{settings.py,sections/*.py}, src/pumpgrok/events/, core/errors.py typed errors (EventBusSaturated, GrokBudgetDenied), tests/harness FaultyEventSource and FaultyGrokTransport, cli/events.py with `pumpgrok events dlq list|replay|purge`, docs/design/events-grok.md. Out of scope: wiring into supervisor, any datafeed, Grok gateway, strategies, replay entry edits.

## Canonical references

src/pumpgrok/config/settings.py and config/sections/, src/pumpgrok/supervisor/scheduler/{supervisor,degraded,serve}.py, src/pumpgrok/replay/{clock,runner}.py, tests/harness/faults.py, src/pumpgrok/core/errors.py, cli/{parsing,dispatch}.py (a new verb needs a _VERB_HANDLERS entry), research/A-events-grok.md sections 1 to 3, research/changes-applied.md items 11, 12, 21, 26.

## Existing code insights

- `ledger_events_hash` is the hash column chain (replay runner.py:135); new JournalNote text in replay would move it, so the bus writes nothing to the ledger in replay.
- degraded.py has signal_scoring_mode values llm, rule_fallback, observe_only_buys, replay (lines 89-97) and NO bus_backlog attribute; assert_no_skew is at degraded.py:52.
- tests/conftest.py blocks websocket connect; new websocket modules need their own patch (Phase 13, plan 13-02 is its only editor).

## Specifics

- `EventPublisher.publish(event) -> PublishResult` with states accepted, deduped, coalesced, rejected_closed, spilled. Event fields: event_id, kind, entity, ts, source_seq, dedup_key, source, typed payload; event_id = first 32 hex of sha256(kind|entity|dedup_key).
- `HandlerSpec(name, seat, kinds, fn, idempotent=True, max_attempts, base_s, cap_s, deadline_s)`; retry jitter rng = make_rng(run_seed + crc32(handler.name)).
- `SourceSpec(name, open(cursor), resync(cursor), stale_after_s, backoff_base_s=1, backoff_cap_s=60, stable_s=30)`; staleness uses clock.timeout(stale_after_s) (WS 120 s), emits SourceStatus(stale); resync emits resyncing then seeds one PositionTick per held mint; cursors table written every 50 events or 5 s and at close.
- `bus.close(grace_s)` refuses new P1/P2, drains P0 then P1 until the timeout, persists leftovers to pending_events; `recover()` re-injects at boot.
- Held-mint mapping CurveTick(held) -> PositionTick, CurveTick(other) -> PriceTick, FeedGap -> SourceStatus(stale)+FeedGap, FeedResynced -> SourceStatus(resynced) is a tested constant (used in 13-01).
- Hash rule this phase: both pairs EQUAL (smoke-10m and trading smoke); `pumpgrok verify --fixture smoke-10m` and tests/replay/test_trading_smoke_pin.py stay green; 12-04 records the lines.

## Deferred ideas

Spill-to-disk for P2; per-handler priority overrides; a bus metrics exporter (Phase 14, 14-04); event-mode as default (OD-20).

## Ownership, receipt and hash rules (every plan of this phase)

- Branch `bot-0N-seat/v4-pPHASE-slug`, one PR per (phase, seat) (PR table below). Receipt `.receipts/bot-0N-seat/v4-pPHASE-slug.json` (task_id = slug, branch = the branch), tracked through the glob `!.receipts/bot-0*/v4-p*.json` from plan 11-01; no other seat edits .gitignore.
- `approved_by` is NEVER self-written and a seat never approves its own work. An agent reviewer (chief for risk-authored work, risk for other seats) reads the diff; human-gated receipts are committed WITHOUT approved_by and the owner adds `human:SomeRandmGuyy` in a batch at the ship checkpoint (after phases 12, 14, 17, 19).
- Seat purity: every path resolves to the plan seat via `resolve_owner(path, load_manifest(DEFAULT_MANIFEST))`; tests/** is risk except tests/desk/** (chief) and tests/engine/** (signal); execution/** sniper; cli/** risk; supervisor/** chief. A foreign-test failure gets a one-file companion plan by the owning seat, merged first.
- Replay hashes: smoke-10m `events.hash` is `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` (seq=2 events=41, verdict and rollover rows only). Trading `smoke` (5 events, seq 11) gave `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54` at HEAD 641927c; plan 11-01 pins it at v4-base; it moves only in plan 15-01. Run receipts in a fresh worktree without var/ledger.sqlite.
- Live stays refused: `uv run pumpgrok run --mode live --once; test $? -eq 3`; nothing arms it.
- Acceptance lines are real commands; exit 0 means success. The G-2 bypass family (collect-only, `--co`, `|| true`, stderr to /dev/null, `--force`, `--dry-run`, inline PUMPGROK_LIVE_ENABLE) never appears; `! cmd -rs | grep -q SKIPPED` proves no skips. Plans touching src also run make lint and make typecheck.


## Plans (5 planned; research/plans.json is the source)

Pull requests in merge order (numbers from research/pr-plan.md):

| PR | Branch | Plans | Approver | Checkpoint |
|----|--------|-------|----------|------------|
| PR-09 | `bot-02-risk/v4-p12-settings-events-core` | 12-01, 12-02, 12-03 | human:SomeRandmGuyy (batch); agent review first | CP12 |
| PR-10 | `bot-09-journal/v4-p12-changelog` | 12-04 | bot-02-risk (agent) | CP12 |
| PR-11 | `bot-00-chief/v4-p12-close` | 12-05 | bot-02-risk (agent) | CP12 |

### 12-01: Settings skeleton: every v4 section, config-gated off, in one unit

- seat bot-02-risk; wave 1; PR-09; depends_on: 11-01, 11-04; requirements: EVT-01, PRC-11, LIV-04; owner decisions: OD-02, OD-03, OD-07.
- files: src/pumpgrok/config/settings.py, src/pumpgrok/config/sections/events.py, src/pumpgrok/config/sections/grok_gateway.py, src/pumpgrok/config/sections/datafeed.py, src/pumpgrok/config/sections/recorder.py, src/pumpgrok/config/sections/strategies.py, src/pumpgrok/config/sections/backtest_v2.py, src/pumpgrok/config/sections/risk_strategy.py, src/pumpgrok/config/sections/promotion.py, src/pumpgrok/config/sections/live.py, src/pumpgrok/config/sections/signer.py, src/pumpgrok/config/sections/paper_fees.py, tests/config/test_v4_settings_skeleton.py, tests/config/test_events_settings.py, tests/config/test_live_settings_caps.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/config
uv run ruff check src/pumpgrok/config
uv run mypy src/pumpgrok/config
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/replay/test_trading_smoke_pin.py
make lint
make typecheck
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 12-02: Typed errors, harness fakes, the single event catalog, EventBus, store, DLQ and events CLI

- seat bot-02-risk; wave 2; PR-09; depends_on: 11-04, 12-01; requirements: EVT-01, EVT-02, EVT-03, EVT-04, EVT-05, EVT-06, EVT-07, EVT-14.
- files: src/pumpgrok/core/errors.py, tests/harness/faults.py, tests/harness/test_faults.py, src/pumpgrok/events/__init__.py, src/pumpgrok/events/models.py, src/pumpgrok/events/bus.py, src/pumpgrok/events/store.py, src/pumpgrok/events/dlq.py, src/pumpgrok/cli/events.py, src/pumpgrok/cli/parsing.py, src/pumpgrok/cli/dispatch.py, docs/design/events-grok.md, tests/events/test_models.py, tests/events/test_bus_lanes.py, tests/events/test_bus_backpressure.py, tests/events/test_bus_dedup_coalesce.py, tests/events/test_bus_retry_dlq.py, tests/events/test_handler_idempotency.py, tests/events/test_bus_shutdown.py, tests/cli/test_events_cli.py, tests/events/test_models_v4_kinds.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/harness tests/config
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/events tests/cli/test_events_cli.py
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 12-03: Deterministic drain with quiescence loop and trading-smoke parity; SourceSupervisor with the single SourceStateBook

- seat bot-02-risk; wave 3; PR-09; depends_on: 11-01, 12-02; requirements: EVT-08, EVT-09, EVT-14.
- files: src/pumpgrok/events/drain.py, tests/replay/test_event_drain_parity.py, src/pumpgrok/events/sources.py, tests/events/test_sources.py, tests/degradation/test_event_source_faults.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/replay/test_event_drain_parity.py -k determinism
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/replay/test_event_drain_parity.py -k smoke_trading
! uv run pytest tests/replay/test_event_drain_parity.py -rs | grep -q SKIPPED
uv run pytest -q tests/events/test_sources.py tests/degradation/test_event_source_faults.py
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 12-04: CHANGELOG entry for Phase 12 with both hash pairs

- seat bot-09-journal; wave 4; PR-10; depends_on: 12-01, 12-02, 12-03; order_after 11-10; requirements: PRC-03, PRC-06.
- files: CHANGELOG.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -qF 'Phase 12: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
grep -qF 'Phase 12: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 12: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 12: trading-smoke events.hash after: $p" CHANGELOG.md
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 12-05: Phase 12 close: STATE, verification record, progress table

- seat bot-00-chief; wave 5; PR-11; depends_on: 12-01, 12-02, 12-03, 12-04; order_after 11-09, 11-11; requirements: PRC-06.
- files: .planning/STATE.md, .planning/ROADMAP.md, .planning/phases/12-event-runtime-core/12-VERIFICATION.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -q 'Phase 12' .planning/STATE.md
./scripts/check.sh
test -f .planning/phases/12-event-runtime-core/12-VERIFICATION.md
python3 ci/gates/check_ownership.py --validate-manifest
```
