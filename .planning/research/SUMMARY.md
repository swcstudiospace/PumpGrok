# Project Research Summary

**Project:** PumpGrok Desk v2 (branch feat/grokbot-desk-merge)
**Domain:** Autonomous, paper-only Solana memecoin (pump.fun) trading desk: ten LLM-backed seats, typed tool layer, curve-faithful paper engine, hash-chained sqlite ledger, deterministic replay, risk engine with breakers and kill switch, asyncio supervisor
**Researched:** 2026-10-21
**Confidence:** MEDIUM overall (STACK MEDIUM-HIGH; FEATURES, ARCHITECTURE and PITFALLS MEDIUM). Binding decisions R44-R49 in `.planning/PROJECT.md` override any conflicting research claim; each conflict is listed under "Conflicts resolved by binding decisions".

## Executive Summary

PumpGrok Desk v2 is a paper-trading desk, not a trading bot. It discovers new pump.fun launches, scores token safety with fail-closed checks, forms signals with coverage-capped confidence, and records every decision in an append-only ledger that can be replayed byte-for-byte from fixtures. Experts building this class of system converge on one asyncio process, a single-writer event ledger as the only system of record, injected virtual time and seeded randomness, and record/replay gateways around every external source. The existing repository already has the seats, skills, read-only tools and a vendored dry-run engine; the milestone adds the paper engine, ledger, replay, risk, supervision and reporting on top of them. The stack research confirms the chosen libraries (pydantic v2, httpx, websockets 17 asyncio API, stdlib sqlite3 in WAL mode, tenacity, prometheus-client, uv, ruff, mypy, pytest) and requires twelve corrections, most of them small pin and tooling changes.

The recommended approach is to build the foundation first and keep every checkpoint runnable from there. The ledger, clock, RNG and tool registry sit at the bottom of the graph; the paper engine, risk checks and supervisor are added above a working skip-only replay cycle; the autonomous paper run only starts once the realism and risk layers exist. Data sources must be treated as unreliable by design. Two of them are already degraded on the observation date: pump.fun REST returns HTTP 530 with error 1016 on every tested path, and the public Solana RPC cannot serve holder enumeration (HTTP 429). PumpPortal's per-token trade streams are refused without a funded key, which the binding decisions rule out (R45). Trade-derived data therefore comes from Solana JSON-RPC log subscriptions on bonding-curve accounts (R46), bounded by a watch-list cap. Every unavailable input must surface as `blind`, `n/a` or `data_unavailable` with a reason, never as a pass or a zero.

The main risks are paper results that cannot be realised (fills that ignore curve impact, fees, latency and dropped transactions), replay that silently diverges (wall clock, uuid, float money, asyncio ordering), ledger races across processes, and safety checks that give false passes (Token-2022 extensions, bundling, holder tricks). Prompt injection through token metadata and confusable tickers is a fourth risk, and it is especially relevant because seats are LLMs. Each of these maps to a named phase below, with a test that proves the mitigation. Three open decisions remain for the user: the PumpPortal trade key, the paid RPC provider, and whether a BLIND holder check counts as KILL. Defaults applied for each are stated in "Open decisions for the user".

## Key Findings

### Recommended Stack

The stack holds with corrections. Pin the versions below, and apply the corrections V-1 to V-12 (all accepted by R49 or superseded by R44-R48 where noted). Python stays on 3.12 with `.python-version` committed, because uv 0.13 defaults to 3.15.

**Core technologies:**
- **Python 3.12 (`>=3.12,<3.13`), pinned by `.python-version`:** every pinned package supports it; uv 0.13's default of 3.15 would otherwise apply (V-3).
- **pydantic 2.14.1 + pydantic-settings 2.16.1 (floor `>=2.16.1,<3`):** contracts, upstream parsing and layered config; 2.16.1 fixes two CLI regressions in 2.16.0 (V-1). Money fields parse via `Decimal(str(value))`, never float (R28).
- **httpx 0.28.1:** the only HTTP client; isolate behind our own transport wrapper because the project has had no release since 2024-12-06 (V-6, maintenance risk). Use `proxy=`, never `proxies=` (removed in 0.28).
- **websockets 17.3 via `websockets.asyncio.client.connect`:** the legacy implementation is not used. Pass `proxy=None` (the default `proxy=True` silently uses environment proxies) and an explicit `max_queue` (default 16) (V-7). Reconnect loop is owned by the desk (see conflicts).
- **sqlite3 (stdlib, Python 3.12):** `autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL` with explicit `BEGIN IMMEDIATE` / `COMMIT`; `PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL` for `ledger.sqlite` (NORMAL can lose the most recent commits on power loss).
- **tenacity 9.2.1:** predicate composition only. Jitter comes from a first-party seeded wait, not `wait_random_exponential` (see conflicts).
- **prometheus-client 0.26.0:** `pumpgrok_*` metrics served from the asyncio health server (phase 5). Ships `py.typed`.
- **Tooling:** uv 0.13.4 with `uv_build>=0.13.4,<0.14.0` (V-2); ruff 0.17.1 with `target-version = "py312"`; mypy 2.4 `--strict` with the `pydantic.mypy` plugin and no `ignore_missing_imports` overrides for prometheus_client or respx (V-5); pytest 9.1.1 with pytest-asyncio 1.4.0 (`asyncio_default_fixture_loop_scope` set explicitly, V-9); respx 0.23.1 for httpx mocks only; pip-audit over `uv export --frozen --no-dev --no-emit-project` (V-4).
- **Model IDs (binding, R48):** `grok-4.3` for the strong seat and `grok-4.20-0309-non-reasoning` for the fast path. `grok-4` and `grok-4-fast` were retired 2026-05-15. Resolve IDs at start-up against `GET /v1/models`, and record the resolved ID in the ledger for replay.

**Upstream surfaces (binding, R44-R47):**
- Jupiter: quote-only through `GET https://api.jup.ag/swap/v2/order` with optional `JUPITER_API_KEY`, no `taker` (R44). Map `priceImpact` (percentage points) to a ratio by dividing by 100. Keyless is 0.5 RPS; Free key 1 RPS; Developer 10 RPS. Jupiter is informational only; fills use the bonding curve (R38).
- PumpPortal: free methods only, `subscribeNewToken` and `subscribeMigration` (R45). Migration payload shape is unverified.
- pump.fun REST: degradable only; no entry may depend on it alone (R47).
- x.ai: Chat Completions is acceptable for probes; new seat code should use the Responses API, with `response_format` / `json_schema` after confirming the exact key on the page (MEDIUM-HIGH). Use `max_completion_tokens`, not `max_tokens`. Generate schemas from pydantic models and re-validate every reply.

### Expected Features

Feature groups carry the IDs used in `docs/upgrade-plan-desk-v2.md` section 5 (DISC, SAFE, SIG, EXEC, LEDG, REPL, RISK, SUPV, RPT, HITL, GOLV). Every feature that touches an external source carries one status: `[CLEAR]`, `[DEGRADABLE: reason]` or `[BLOCKED: reason]`.

**Must have (table stakes, launch with the milestone):**
- **Discovery and source health (DISC-1, 2, 4, 5, 6):** `subscribeNewToken` intake, source health, and the discovery path. Nothing else runs without it.
- **Cheap, clearly sourced safety checks plus explained verdict (SAFE-1, 2, 3, 9, 10, 11):** fail-closed; the verdict names every check and its status. SAFE-5 (LP status) is `n/a` before graduation, never `BLIND` and never a pass.
- **Signals (SIG-1, 2, 4, 6):** price ticks by polling curve reserves (SIG-1 is the hinge: MTM, momentum, blind protection and graduation depend on it), reserve momentum, coverage-capped confidence, signal record.
- **Curve-faithful paper execution (EXEC-1 to 9):** fills from the constant-product curve at decision time, re-quote after seeded lognormal latency, fees as data (tiered, not constants), dropped-transaction handling, partial fills, graduation, mark-to-market at liquidation value, blind protection, data-age gate.
- **Ledger and attribution (LEDG-1 to 4):** hash-chained events, PnL, equity and drawdown, source tags so live-gate evidence is computed only from `source=paper`.
- **Replay (REPL-1, 2, 3):** deterministic replay, LLM response recording, live-feed recording into self-recorded datasets.
- **Risk (RISK-1 to 7):** caps, daily and drawdown halts (human-clear only), breakers, kill switch with flatten, re-check at CONFIRMING, absolute risk veto, exit rules.
- **Supervision (SUPV-1 to 6):** task-per-seat supervisor, bounded restarts, health, shutdown, degraded modes, redacted logs.
- **Reporting (RPT-1 to 5):** daily and weekly reports with an explicit unverified section and rejected-signal table.
- **Human-in-the-loop (HITL-1 to 5):** ticket and exact-phrase approval, exit-rule approval, autonomy switch, escalation, safe inbound commands.
- **Go-live gate (GOLV-1, 2, 3, 5):** refuses to start; disabled in this milestone.

**Should have (differentiators, add after validation):**
- SAFE-6 with an RPC `simulateTransaction` sell check, once a probe shows it works and the structural check shows false passes in the paper run.
- SAFE-7 bundler flags and SAFE-8 deployer history, once a paid provider exists.
- Lookahead and fixture-sensitivity diffs (DIFF-3 to 6) that report n/a below sample-size thresholds rather than hiding it.

**Defer (v2+ or never in this milestone):**
- Live adapter and any real send path (stays disabled; needs its own change document and a re-run of the paper window).
- Hyperparameter search on the live window (AF-9 forbids it; GOLV-3 restarts the window on any tuning).
- Any external historical data (AF-10; replay uses self-recorded datasets only).
- Trade-stream features through a funded PumpPortal key (blocked by R45 unless the user opts in).

**Anti-features (must not build):** coordinated buying (AF-1), wash trading (AF-2), volume generation (AF-3), shilling and social posting (AF-4), any signing or sending path, and treating missing data as a pass or a zero (AF-8). Sentiment ingestion must not drift into posting (Pitfall 15).

### Architecture Approach

The architecture is a single asyncio process with four rings: seats reach the world only through a least-privilege `ToolRegistry` (`find(capability, max_side_effect, bot)`); a thin execution adapter (`PaperAdapter.place`) is the only write path to the paper venue and embeds the risk engine; one append-only ledger is the only system of record; and record/replay gateways wrap every external system so the process can be re-run from fixtures with virtual time. The design docs are confirmed; the build order in `docs/MIGRATION_MAP.md` section 7 is kept.

**Major components:**
1. **`ledger/`** - single writer, `BEGIN IMMEDIATE` with the hash chain computed inside the transaction, `prev_hash` enforced by trigger, snapshots bound restart time, markdown exports via tmp plus `os.replace`. Check-and-append at CONFIRMING prevents two adapters deciding against stale state.
2. **`core/` and `replay/`** - `Clock` protocol (`now`, `monotonic`, `utc_iso`, `sleep`, `timeout`) injected everywhere; one `random.Random(seed)` created once in `cli.py`; `FixtureClock` advances only on delivered events or deadlines; `FixtureWebSocket` replaces `connect` in replay.
3. **`execution/` and `risk/`** - `PaperAdapter` state machine NEW -> ACCEPTED -> CONFIRMING -> FILLED/PARTIAL/REJECTED with an in-flight barrier; `curve_math`, `fees`, `latency`, `quote`; `RiskEngine.check` at NEW and again at CONFIRMING; `live/` disabled stubs behind the nine-precondition `LiveGate` (exit code 3).
4. **`engine/` and `tools/`** - the ported screening loop (monitor, analyzer, scoring, LLM agents, exits, watcher) and the `<ns>.<verb>` catalog (`market`, `onchain` with shared RPC failover, `safety`, `exec`, `portfolio`, `risk`, `journal`, `notify`, `desk`). Thin typed wrappers; the only surface seats and the gateway see.
5. **`supervisor/` and `services/desk-gateway/`** - task-per-seat with roster-order ticks, `RestartPolicy` (5 per hour token bucket), observe-only latch, `var/health.json`; one Streamable-HTTP MCP endpoint per seat (`/mcp/<seat>`) with transport names derived at exposure time, read-only until phase 4 adds `exec.*` in-process.

**Key patterns (adopted):** single-writer hash-chained ledger with snapshots; virtual-time discipline; risk as library code inside the adapter; record/replay gateways; supervisor as task-per-seat; least-privilege registry with gateway as projection.

**Anti-patterns to ban by static test:** reading the chain head outside the write lock; `async for ws in websockets.connect(...)` (its backoff uses real `asyncio.sleep`); `tenacity.wait_random*`; two live `PaperAdapter` instances; hashing the rendered prompt as the LLM replay key (the replay key is decided in phase 2); `asyncio.gather` or an eager task factory for the per-tick seat fan-out; read-only ledger access from a different Unix user or a read-only mount.

### Critical Pitfalls

1. **Paper fills that ignore impact, fees, latency and drops** (Pitfall 1). On a curve with 30 SOL virtual liquidity a 0.2 SOL buy already costs about 0.47 percent impact, and the round trip loses about 2 percent before price moves. Fill from the curve on `(S0, T0)`, recompute on `(S1, T1)` after lognormal latency, reject when `out_at_confirmation < other_amount_threshold`, recompute the threshold for partials, charge network cost on slippage rejections, mark to liquidation value. Fee constants are stale: pump.fun switched to market-cap-tiered fees on 2025-09-01; keep the fee table as data.
2. **Stale 2024 venue model** (Pitfall 2). Hosts, model names, Raydium and Jito references must be removed from `src/` and profiles. Check the current fee program and bonding-curve layout with a fresh primary-source read before implementing EXEC-2.
3. **Look-ahead and survivorship bias in replay** (Pitfall 3). Monotone per-stream cursors, masking of outcome fields, `subscribeNewToken` in every manifest, the `graduation-1h` dataset forces close and freezes MTM.
4. **Non-deterministic replay and ledger races** (Pitfalls 4, 5). Ban wall clock, uuid, ambient randomness, float money, asyncio ordering and non-canonical JSON in static tests; file-backed two-process WAL test; `BEGIN IMMEDIATE` grep; trigger-enforced `prev_hash`.
5. **Rug and honeypot false negatives** (Pitfall 8). Token-2022 extensions (transfer hook, permanent delegate, freeze authority), bundlers, and holder-count tricks. SAFE-6 is structural only and must be labelled that way; "honeypot-free" wording must not appear.
6. **Upstream instability and prompt injection** (Pitfalls 9, 12). Parsers use `extra="ignore"` returning `Result`; circuit breakers per source; metadata is NFKC-normalised, capped at 64 KB, delimited, never placed in the system prompt; TR39 confusable skeletons for tickers; injection corpus test.

## Implications for Roadmap

Five phases, fixed by R37, in this order. Each checkpoint is buildable from Phase 1. The vendor suite (264 pytest cases) is the characterization oracle through Phase 4.

### Phase 1: Foundation
**Rationale:** Every later phase depends on the ledger, the clock, the RNG, the ID factory and the tool registry. Determinism and the explicit-transaction ledger are cross-phase invariants that are cheap to enforce now and very expensive to retrofit. The toolchain corrections belong here too, so every later phase runs on the corrected pins.

**Delivers:** packaging with `.python-version` 3.12, uv 0.13.4 and `uv_build`; pydantic-settings floor 2.16.1; `make audit` with `--no-emit-project`; mypy overrides removed; config precedence CLI `--mode` > env `PUMPGROK_MODE` > TOML with in-package overlays and no root `config/` (R30); `core/*` (interfaces, registry, ids, approvals, `atomic_write`); `logging/json.py` with redaction; `ledger/{store,events}.py` (schema, `BEGIN IMMEDIATE`, hash chain, the 18 CamelCase event types, R32); `replay/{clock,rng,fixtures}.py`; `cli.py` skeleton; gates G-1..G-7 and `ownership.yaml`; network-blocked test harness with hostile route fixtures (429, 530, truncated bodies) present from the first test; the skip-only `pumpgrok run --once --replay smoke` cycle that lands `JournalNote(decision: skip, reason: engine_not_yet_implemented)` in `var/replay/smoke/ledger.sqlite`.

**Addresses:** FOUND-001..013; the foundations for every feature group (especially LEDG and REPL).

**Avoids:** Pitfall 4 (static determinism bans, canonical JSON digest test), Pitfall 5 (two-process WAL test, `BEGIN IMMEDIATE` grep, trigger-enforced `prev_hash`), Pitfall 14 (redaction formatter test, fixture grep test, `SecretStr` on every credential including the PumpPortal key if ever used), Pitfall 18 harness part (network-blocked conftest with hostile fixtures).

**Research flag:** standard patterns, skip research-phase. Two items need a unit test rather than research: pydantic-settings multi-file TOML layering (U-2, LOW confidence on the list form; keep the 15-line custom settings source as fallback) and `uv_build` `module-root` (U-1).

### Phase 2: Restructure
**Rationale:** Source adapters and the engine port need the Phase 1 clock, RNG, ledger and registry, and must be characterization-tested against the vendor engine while it is still the oracle. Retiring stale hosts and models happens here so no new code inherits them. Replay recording must start here, because it cannot be retrofitted onto live-only clients.

**Delivers:** `tools/onchain/rpc.py` (shared RPC client with failover list, `RpcPool` buckets); `tools/market/{pumpfun,pumpportal,jupiter}.py` as `DataSource` implementations behind fixture transports (Jupiter quote-only V2 per R44; PumpPortal free methods only per R45; pump.fun REST degradable per R47); `tools/notify/*`; `replay/{recorder,sources}.py` and the recorded `smoke` dataset; engine port (`engine/*`, `core/{ratelimit,budget,llm}.py`, `risk/breakers.py` base, `engine/{exits,watcher}.py`) with `clock` injected everywhere the vendor read time; owned reconnect loop with `clock.sleep` and first-party seeded jitter; prompts, skills and docs rewritten to the new tool names; vendor characterization tests with "intentionally not ported" markers. The engine produces `buy|skip` from fixtures; `buy` is recorded as `skip execution_not_yet_implemented`.

**Uses:** websockets 17.3 with `proxy=None` and explicit `max_queue`; httpx behind the transport wrapper; respx for upstream mocks; first-party `FixtureWebSocket` for PumpPortal; Solana JSON-RPC `getRecentPrioritizationFees`, `getAccountInfo` (`jsonParsed` with base64 fallback), and `logsSubscribe` for bonding-curve PDA trade events (R46).

**Implements:** `DataSource` seam for the signal path; recorder dataset format; LLM replay-key decision (Pattern 4; decide here, and record the resolved model ID).

**Avoids:** Pitfall 2 (no `frontend-api.pump.fun`, `grok-4`, `grok-4-fast`, Raydium or Jito keys in `src/` or profiles; static grep test), Pitfall 7 (daily-halt auto-reset: characterization test marked as an intentional non-port with a `vendor_bug` marker referenced from design section 11), Pitfall 11 (RPC bucket tests begin here so the public endpoint's 100 requests per 10 seconds and 40 per call are respected in every recording).

**Research flag:** needs research. Probe before requirements freeze: `logsSubscribe` on bonding-curve PDAs (per-token RPC cost, which endpoints allow it, frame shape), bonding-curve account layout (LOW confidence), PumpPortal migration payload shape (UNVERIFIED), and whether the trade-event path fits the 20-trade budget per watched mint. These feed SIG-1.

### Phase 3: Tools and Skills
**Rationale:** Least-privilege tool rosters and the gateway need the Phase 2 data sources to exist as fixtures. Safety checks and the sanitiser are pure functions over those sources, so they are the right place to close the rug, injection and sentiment pitfalls before any paper write exists. `exec.*` is registered here but refused, so least-privilege can be tested before execution exists.

**Delivers:** catalog tools under `tools/*` with dotted ids (R19); rosters of 8-15 tools per seat (R20 nine-key risk budget); `contracts/events/*.schema.json` generated from `ledger/events.py`; skills frontmatter and 12 new skills; `services/desk-gateway/` read-only surface (`/mcp/<seat>`, `tools/list`); G-7 against real rosters; `safety.*` checks (SAFE-1, 2, 3, 9, 10, 11 required or advisory per open decision 2); `Quote.source` literal that rejects non-curve quotes; TR39 skeleton tool and sanitiser; injection corpus; roster capability filter (no posting capability for any seat); outbound host allow-list.

**Uses:** pydantic `extra="forbid"` for our events and `extra="ignore"` for upstream payloads; `Decimal` parsing; x.ai structured outputs from pydantic schemas (`max_completion_tokens`); `ToolRegistry` grants per seat.

**Implements:** `ToolRegistry.find(capability, max_side_effect, bot)` enforcement; `exec.*` backed by a `not_yet_implemented` refusal; gateway in-memory `Client(mcp)` tests per seat.

**Avoids:** Pitfall 8 (extension verdict table, rug corpus, curve ATA excluded), Pitfall 9 (`extra="ignore"` parsers returning `Result`, one-connection PumpPortal client with spend counter, nightly liveness probe), Pitfall 10 (Jupiter quote never used as fill; adapter rejects non-curve quotes), Pitfall 11 (per-candidate RPC call counts), Pitfall 12 (sanitiser, skeleton check, injection corpus, no raw interpolation static test), Pitfall 13 (LLM budget and breaker tests, dated model probe, replay-no-network test), Pitfall 15 (roster capability filter, outbound allow-list), and Pitfall 2 clients.

**Research flag:** needs research on two items: the exact x.ai `response_format` key for the Responses API (confirm on the page with a live call under a key), and SAFE-6 depth (structural only, labelled; RPC `simulateTransaction` sell check needs a probe). Token-2022 extension list should be re-read from the current spec at implementation time.

### Phase 4: Paper Trading and Autonomy
**Rationale:** This is where the paper run becomes meaningful, so it depends on everything beneath: curve-faithful fills need reserves from Phase 2, the risk engine needs the ledger from Phase 1, and the exposure rules need the roster from Phase 3. It is the largest phase and has the most pitfalls. Autonomy is only switched on after the kill switch, in-flight barrier and UTC-rollover behaviour are tested.

**Delivers:** `execution/*` (`PaperAdapter`, `curve_math`, `fees` as tiered data, `latency`, `quote`); `execution/live/*` disabled stubs with the nine-precondition `LiveGate` (exit 3); `risk/{engine,limits,sizing,killswitch}.py` and breakers (`DataStale`, `LossVelocity`, `ExecErrors`); `ledger/{reducer,views,reconcile,export,desk_bus}.py`; `replay/runner.py`; `supervisor/{scheduler,seat_task,lifecycle,health}.py`; reporting (daily and weekly, pure `ReportModel`); CLI verbs (`run --mode paper`, `paper buy|sell`, `killswitch *`, `state *`, `verify`, `report`); signal and graduation logic (SIG-1 to 6 with the probe results); EXEC-1..9; HITL-1..5; GOLV-1..3 and 5 with the gate disabled.

**Addresses:** EXEC, RISK, LEDG, RPT, HITL, SUPV, GOLV feature groups; SIG-1 hinge.

**Avoids:** Pitfall 1 (worked example 2.9 as a golden test; fee-sensitivity test; MTM at liquidation value), Pitfall 3 (monotone per-stream cursor test; outcome-field masking), Pitfall 4 runtime part (two-subprocess `ledger_hash` equality on `smoke`), Pitfall 6 barrier (`test_in_flight_order_rejected_at_confirming`; one flatten per mint under concurrent sources), Pitfall 7 (`tests/risk/test_halts.py` rollover cases; cross-midnight fill attribution), Pitfall 16 (ledger-derived counters survive restart; fee-drag guard; creator exposure in report), Pitfall 17 (graduation: `graduation-1h` dataset forces close and freezes MTM; `subscribeMigration` shape fallback to `S >= 85 SOL`), Pitfall 10 execution side (`exec.place` consumes only curve quotes).

**Research flag:** partly standard. Re-read the current pump.fun fee-tier program and bonding-curve constants from primary sources before writing `fees` (Pitfall 2 warns the design's `venue_fee_bps = 100` is stale). Position sizing and the `EXEC-9` data-age bound are REVIEW values, not research.

### Phase 5: Hardening
**Rationale:** Fault injection and soak tests only mean something once the paper engine, risk and supervision exist, and once the replay datasets are complete. Metrics and security CI come last so they instrument the final shape. Deleting `tools/` and `vendor/` happens only at zero retirement census, which is the proof the port is complete.

**Delivers:** `supervisor/metrics.py` (`prometheus_client` 0.26, families named in design section 6.6); `logging/spans.py`; `tests/fault_injection.py` with one owning test per failure row; security CI (secrets scan, dependency audit, redaction); Dockerfile and compose with the corrected uv pin; `soak-3d` nightly soak with 20 MB growth budget (REVIEW); deletion of `tools/` and `vendor/` at zero census; `doctor` with no `not-yet-implemented` entries; weekly report lines for fee drag, parse-error rate, LLM USD per trade, trades per day and creator concentration.

**Addresses:** SUPV-5 completion, observability of every differentiator, the hardening gate for go-live review (GOLV stays disabled).

**Avoids:** Pitfall 6 fault injection (`test_*` per row of kill-switch and halt race table), Pitfall 18 (mocked-away risks: fault injection file with one owning test per failure row; nightly soak fails when its dataset is absent), observability checks for Pitfalls 1, 2, 9, 13 and 16, and the WAL growth watch for long `report` readers (`doctor` reports WAL size).

**Research flag:** standard patterns, skip research-phase. The soak budget and report thresholds are REVIEW values set by the user, not research.

### Phase Ordering Rationale

- **Ledger, clock and RNG first (Phase 1):** every other module writes events or reads time through them. Static determinism bans are only useful if they exist before the code they forbid.
- **Sources before rules (Phase 2 before 3):** safety checks and signals consume source outputs; the recorder must capture the same frames the engine consumes, so recording starts with the clients.
- **Rules before writes (Phase 3 before 4):** least-privilege rosters and the sanitiser are proven on read-only tools before the paper adapter gives any seat a write.
- **Writes before autonomy (Phase 4 before 5):** the in-flight barrier and kill switch must exist before fault injection can exercise them.
- **Hardening last (Phase 5):** fault injection, metrics and deletion of the vendor tree only make sense for the final shape. The vendor suite is the oracle until then.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** logsSubscribe per-token cost and frame shape on the chosen RPC provider; bonding-curve account layout; PumpPortal migration payload. These gate SIG-1 and the requirements freeze.
- **Phase 3:** x.ai Responses `response_format` key (live confirmation); SAFE-6 depth; Token-2022 extension list at implementation time.
- **Phase 4:** current pump.fun fee tiers and curve constants from primary sources (fees are stale in the design); EXEC-2 priority-fee source.

Phases with standard patterns (skip research-phase):
- **Phase 1:** packaging, ledger schema, gates and test harness follow the programming-desk precedent and the design docs.
- **Phase 5:** metrics, fault injection, Docker and soak are well documented.

## Conflicts resolved by binding decisions

| Topic | Research said | Resolution (binding source) |
|---|---|---|
| Trade-derived data | FEATURES marks SIG-3 and SAFE-7 trade parts BLOCKED because PumpPortal trade streams need a funded key | R46 wins: trade events come from Solana JSON-RPC `logsSubscribe` on bonding-curve PDAs, bounded by `signal.max_watched_mints`. PumpPortal is used only for free methods (R45). The RPC path is UNVERIFIED and needs the Phase 2 probe |
| x.ai flagship | STACK suggests `grok-4.7` as flagship and `grok-4.3` as lower cost | R48 wins: `grok-4.3` (strong, low effort) and `grok-4.20-0309-non-reasoning` (fast) in config |
| Jupiter fallback | STACK keeps `lite-api` v1 behind a config flag with a removal date | R44 wins: quote-only `api.jup.ag/swap/v2/order`; no lite-api path |
| Reconnect loop | STACK uses the library `reconnect_delays` option | Architecture wins (R27): the desk owns the reconnect loop with `clock.sleep`, because the library sleeps on the real loop and breaks replay |
| Retry jitter | STACK uses tenacity `wait_random_exponential` | Architecture wins (R27, R28): tenacity for predicates only; first-party seeded `full_jitter(rng, base_s, max_s)`; ban `tenacity.wait_random*` by static test |
| PumpPortal trade frames | FEATURES assumes trade frame fields exist for SIG-3 | Moot under R45/R46; PumpPortal trade frames are not used. Trade-frame shape stays UNVERIFIED |

Binding-decision coverage of STACK corrections: R49 accepts V-1 to V-7 and V-9; V-8 (Jupiter) is implemented by R44; V-10 (x.ai IDs) by R48; V-11 (PumpPortal key secret and budget) by R45; V-12 (pump.fun REST) by R47.

## Open decisions for the user

Each decision has a default already applied in this research and in the planned roadmap. The user can change any default; the consequence of changing it is stated.

1. **Enable a funded PumpPortal trade-stream key?** Default applied: **no** (R45, R49). Effect: PumpPortal is used only for `subscribeNewToken` and `subscribeMigration`; trade-derived data comes from Solana RPC `logsSubscribe` (R46). If the user answers yes, a wallet with at least 0.02 SOL must be linked to the key, the key becomes a `SecretStr` that is never a Solana keypair, and the metered fee of 0.01 SOL per 10,000 events must be budgeted. This would also move SIG-3 and the trade parts of SAFE-7 from `[BLOCKED]` to `[CLEAR]`. This is a new financial dependency under D4 and needs explicit approval.

2. **Paid Solana RPC provider and plan.** Default applied: **none approved; no spend committed.** The desk is built against a configured `rpc.endpoints[]` failover list with the public endpoint as lowest priority and `solana.rpc_api_key` as a `SecretStr` (FOUNDATION M-7). Effect: `getTokenLargestAccounts` (public endpoint returned HTTP 429 on 2026-10-21) cannot run, so SAFE-4 (holder concentration) and SAFE-8 (deployer history) report `blind` with reason, and SAFE-7 bundler flags stay in v1.x. LogsSubscribe trade events (R46) also need a provider with adequate limits; the public endpoint's documented limits are 100 requests per 10 seconds per IP and 40 per single RPC, and it is "not intended for production". Decide the provider, plan and monthly budget before the Phase 2 probe.

3. **Does a BLIND holder check count as KILL?** Default applied: **no, while no paid provider is approved.** Following the FEATURES proposal, SAFE-4 is required only if decision 2 is yes; until then it is advisory, and its `blind` result is recorded in the verdict with its reason. The fail-closed reading of the constitution (AF-8) would instead make every token KILL while SAFE-4 is blind, which means no buy can ever be proposed in v1. Choose one of: (a) BLIND is KILL for required checks, which requires a paid provider to be useful; (b) BLIND is advisory and recorded (default); (c) a different required set. Whichever is chosen must be written into the safety verdict table, not left implicit.

Further decisions from FEATURES that block requirements freeze (defaults applied):
- **SIG-1 poll cadence and watch-list cap:** default to the probe result in Phase 2; `signal.max_watched_mints` is a REVIEW value in the TOML block.
- **SAFE-6 depth:** default structural simulation only, labelled as structural; never called honeypot.
- **Historical data policy:** default self-recorded datasets only (AF-10); no external history is considered.
- **EXEC-9 data-age bound:** default is a REVIEW value in config; no value is fixed by research.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Versions and APIs verified on PyPI, upstream changelogs and live probes on 2026-10-21. Downgraded for httpx maintenance cadence, pydantic-settings multi-file TOML (U-2), x.ai structured-output key (confirm live), and the RPC trade path (not in the stack probes) |
| Features | MEDIUM | Desk requirements read directly from the project brief and design docs (HIGH). PumpPortal free and metered split and refusal observed live (HIGH). Migration payload, trade-frame shape, bonding-curve layout and RPC per-token cost are LOW and marked wherever they matter. Competitor comparison is MEDIUM (Freqtrade docs read; Hummingbot paper page returned 404) |
| Architecture | MEDIUM | Repository design facts read directly (HIGH). Library and platform facts from primary sources, not cross-checked by a second provider. Recommendations beyond the design docs are marked as inference |
| Pitfalls | MEDIUM | External facts read from official pages or live endpoints on 2026-10-20 to 21. Pump.fun fee and venue facts are from the vendor's own docs and may already be stale (Pitfall 2). Several claims are community wisdom and marked LOW |

**Overall confidence:** MEDIUM

### Gaps to Address

- **Trade path without a key (SIG-3, EXEC-6 input):** logsSubscribe frame shape, per-token RPC cost and endpoint acceptance are unverified. Probe in Phase 2 before the requirements freeze; if the cost is too high, reduce `signal.max_watched_mints` rather than adding a key (R45).
- **Bonding-curve account layout:** LOW confidence; needed for curve reserves on the RPC path and for EXEC-1 fills. Verify against the current program source before implementing `curve_math`.
- **PumpPortal migration payload:** UNVERIFIED; graduation falls back to `S >= 85 SOL` from reserves (DISC-3, EXEC-6). Add a fixture once a live frame is captured.
- **pump.fun fee tiers:** the design's flat 1 percent is stale (switched 2025-09-01 to market-cap tiers). Re-read the current fee program before Phase 4 `fees`.
- **Paid RPC provider:** unresolved (open decision 2). Holder and deployer checks cannot be `pass` until resolved.
- **x.ai Responses structured-output key:** confirm the exact `format` key with a live call under a key; Chat Completions remains the fallback.
- **pydantic-settings multi-file TOML (U-2):** list-of-files override order undocumented; keep the 15-line custom settings source and decide by a unit test in Phase 1.
- **FOUNDATION open items:** U-1 (`uv_build` `module-root`), U-4 (`setup-uv` SHA), U-7 (Helius and QuickNode URL shapes for G-3 regexes). Resolve in Phase 1.
- **Jupiter routing:** quote-only without `taker` lets every router compete; the quote is informational, so this is acceptable under R38 and R44, but record the `router` value in each quote for audit.
- **httpx maintenance:** no release since 0.28.1; keep the transport wrapper so a swap is local. Re-check at each milestone.

## Sources

### Primary (HIGH confidence)
- PyPI JSON for every pinned package, fetched 2026-10-21 (pydantic, pydantic-settings, httpx, websockets, tenacity, prometheus-client, ruff, mypy, pytest, pytest-asyncio, pip-audit, uv, uv-build, respx, PyYAML) - versions and `requires_python`
- websockets changelog and 17.3 source defaults (`proxy=True`, `max_queue=16`) - https://websockets.readthedocs.io/en/stable/project/changelog.html
- httpx CHANGELOG (0.28.0 removals) - https://github.com/encode/httpx/blob/master/CHANGELOG.md
- Jupiter Metis V1 deprecation and Swap V2 order API - https://developers.jup.ag/docs/swap/v1/get-quote and https://developers.jup.ag/docs/api-reference/swap/order.md; rate limits - https://developers.jup.ag/docs/portal/rate-limits.md
- PumpPortal real-time data docs and FAQ - https://pumpportal.fun/data-api/real-time/ and https://pumpportal.fun/FAQ; live probes 2026-10-21
- x.ai model table and structured outputs - https://docs.x.ai/developers/models and https://docs.x.ai/developers/model-capabilities/text/structured-outputs
- Solana RPC methods and public-endpoint limits - https://solana.com/docs/rpc/http/gettokenlargestaccounts, https://solana.com/docs/rpc/http/getaccountinfo, https://solana.com/docs/references/clusters
- Python 3.12 sqlite3 and SQLite WAL - https://docs.python.org/3.12/library/sqlite3.html and https://sqlite.org/wal.html
- Project binding decisions - `.planning/PROJECT.md` (D1-D9, R16-R49); `docs/upgrade-plan-desk-v2.md` sections 4 and 5; `docs/design/paper-engine.md`; `docs/RISK_POLICY.md`
- Repository facts - `vendor/grokbot-pumpfun/src/monitor.py:133`, `src/analyzer.py:134`, `tools/priority_fee.py:45`

### Secondary (MEDIUM confidence)
- Freqtrade bot-usage, backtesting and lookahead-analysis docs (competitor comparison and replay bias)
- Solana Token Extensions overview and Transfer Hook docs (Token-2022 extension list)
- Unicode TR39 confusables data and section 4 guidance (ticker skeletons)
- OWASP LLM01:2025 (prompt injection through metadata)
- Cloudflare 1xxx error reference (meaning of error 1016)

### Tertiary (LOW confidence, needs validation)
- PumpPortal trade-frame field names (not observed live without a key)
- Bonding-curve account layout over RPC and per-token RPC cost for logsSubscribe
- PumpPortal migration payload shape
- Current pump.fun fee-tier program constants (Pitfall 2 secondary source)
- Lite-api rate ceiling (no longer used under R44)

---
*Research completed: 2026-10-21*
*Ready for roadmap: yes*
