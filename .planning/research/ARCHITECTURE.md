# Architecture Research

**Domain:** Autonomous, paper-only Solana memecoin trading desk (ten LLM-backed seats, typed tool layer, paper execution engine, event-sourced sqlite ledger, deterministic replay, risk engine with breakers and kill switch, asyncio supervisor, per-seat MCP gateway)
**Researched:** 2026-10-20
**Confidence:** MEDIUM overall. Repository design facts (`docs/design/paper-engine.md`, `docs/design/interfaces.md`, `docs/MIGRATION_MAP.md` section 7, `.planning/PROJECT.md`) were read directly and are HIGH. Library and platform facts were verified on 2026-10-20 directly against official documentation, upstream source and PyPI (URLs cited inline, tagged `[webfetch]`); the `classify-confidence` seam rates the `webfetch` provider LOW because no curated docs provider (context7) is mounted in this session, so treat every `[webfetch]` claim as "primary source, not independently cross-checked by a second provider". Recommendations that go beyond the design docs are tagged `[INFERENCE]`.

This file does not re-research the existing desk (eight prompts, 23 skills, read-only CLIs, vendored dry-run engine). It assesses the structure the project must ADD, confirms or refines the design docs, and names the build order and the seams between phases.

## Standard Architecture

### System Overview

The shape that autonomous multi-agent paper-trading systems converge on, and that the two design docs already specify, is a single asyncio process with four rings: seats (LLM-backed decision makers) that can only reach the world through a least-privilege tool registry; a thin execution adapter that owns every write to the paper venue and embeds the risk engine; one append-only event ledger that is the only system of record; and record/replay gateways around every external system so the whole process can be re-run from fixtures with virtual time.

```
+------------------------------------------------------------------------------------+
| Operators / Hermes cron / external LLM clients                                     |
|   pumpgrok CLI (run, doctor, verify, report, paper buy|sell, killswitch, state)     |
|   services/desk-gateway  (/mcp/<seat>, MCPServer, one roster per seat)             |
+------------------------------------------------------------------------------------+
        | tool calls (dotted ids, typed pydantic payloads, SideEffect <= grant)
        v
+------------------------------------------------------------------------------------+
| SUPERVISOR  src/pumpgrok/supervisor/  (one asyncio loop, task-per-seat)            |
|  +-------+ +-------+ +------+ +-------+ +--------+ +-----+ +------+ +-------+ ...   |
|  | chief | | scout | | risk | | whale | | sniper | | rug | | exit | | shill |       |
|  +---+---+ +---+---+ +--+---+ +---+---+ +---+----+ +--+--+ +--+---+ +---+---+       |
|      |         |        |         |         |         |       |         |           |
|  SeatTask: heartbeat, RestartPolicy (5/h token bucket), observe-only latch, Escalation|
|  roster-order ticks; health.py (/healthz /readyz /metrics, var/health.json)        |
+------------------------------------------------------------------------------------+
        | ToolRegistry.find(capability, max_side_effect, bot)  (core/registry.py)
        v
+------------------------------------------------------------------------------------+
| TOOL LAYER  src/pumpgrok/tools/{market,onchain,safety,exec,portfolio,risk,         |
|             journal,notify,desk}/   READ tools fail open; PAPER_WRITE fail closed   |
+--------------------+-----------------------------+---------------------------------+
                     | exec.quote / exec.place     | market.* onchain.* (DataSource)
                     v                             v
+-------------------------------+   +--------------------------------------------+
| EXECUTION  execution/         |   | ENGINE  engine/ (ported vendor)            |
|  PaperAdapter (curve_math,    |   |  monitor, analyzer, scoring, agents,       |
|  fees, latency, quote)        |   |  exits (ExitSignal), watcher               |
|  RiskEngine.check inside      |   +--------------------------------------------+
|  place(): NEW and CONFIRMING  |
|  in-flight barrier            |   +--------------------------------------------+
|  live/: LiveAdapterStub       |   | RISK  risk/ engine, limits, sizing,        |
|         (raises LiveGateError)|   |  breakers (DataStale, LossVelocity,        |
+---------------+---------------+   |  ExecErrors), killswitch (env/file/alert)  |
                |                   +--------------------------------------------+
                v  LedgerStore.append(event) -> seq   (BEGIN IMMEDIATE, hash chain)
+------------------------------------------------------------------------------------+
| LEDGER  ledger/  sqlite3 WAL  var/ledger.sqlite | var/replay/<dataset>/ledger.sqlite|
|  events(seq, ts_utc, source, correlation_id, idempotency_key, type, payload_json,   |
|         prev_hash, hash)  +  snapshots  +  meta ;  reducer -> LedgerState -> views  |
|  export: var/journal/*.jsonl, trades.jsonl, $PUMPGROK_DESK/*.md (atomic_write)     |
+------------------------------------------------------------------------------------+
        ^ ts_utc, ids, latency draws, retry waits
+------------------------------------------------------------------------------------+
| REPLAY  replay/  Clock (WallClock | FixtureClock heap), make_rng(seed), IdFactory,  |
|  FixtureReader, Fixture{HttpTransport,WebSocket,PriceSource,Llm}, Recorder, runner  |
+------------------------------------------------------------------------------------+
        | recorded or live transports (httpx, websockets, x.ai)
        v
+------------------------------------------------------------------------------------+
| EXTERNAL (exactly five): pump.fun frontend REST | PumpPortal WS | Jupiter lite-api  |
|                          quote | Solana JSON-RPC (failover list) | x.ai Grok        |
+------------------------------------------------------------------------------------+
```

Direction of authority is top-down for commands and bottom-up for facts: seats propose, the tool registry filters by grant, the adapter decides (with the risk engine), the ledger records, views and reports derive. Nothing above the ledger holds state that the ledger cannot rebuild.

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `core/` (interfaces, registry, ids, approvals) | Protocols (`Tool`, `DataSource`, `ExecutionAdapter`, `LiveGate`, `Skill`, `Bot`), `SideEffect` ordering READ < PAPER_WRITE < LIVE_WRITE, `canonical_json`, idempotency keys, ULIDs from `Clock + rng`, `ToolRegistry.find(capability, max_side_effect, bot)` with `GrantAudit` | pydantic v2 frozen models, `typing.Protocol`, one registry instance built from `contracts/tool-rosters/*.yaml`; `docs/design/interfaces.md` section 1 |
| `config/` | pydantic-settings with precedence CLI `--mode` > env `PUMPGROK_*` > in-package TOML overlay selected by `PUMPGROK_PROFILE` (R30); `[risk]` keys (R20); `live.*` validation (R21) | `BaseSettings` + TOML sources; one effective mode object passed by constructor injection |
| `ledger/` | The only system of record: append-only `events` with hash chain, `snapshots`, `meta`; pure `reducer`; `views`; restart `reconcile` (snapshot + tail + verify); JSONL and markdown `export`; `desk_bus` halt mirror | sqlite3 WAL, `BEGIN IMMEDIATE` per append, append-only triggers, `atomic_write` (tmp + fsync + `os.replace`) |
| `replay/` | `Clock` protocol (`WallClock`, `FixtureClock`), `make_rng(seed)`, fixture reader/merger, fixture transports, `Recorder`, `run_replay` | Virtual-time heap keyed `(wake_time, enqueue_seq)`; `httpx.MockTransport`; fake WebSocket; LLM lookup by canonical request hash; `ReplayMissingRecord` on a miss |
| `execution/` | `PaperAdapter` (`quote`, `simulate`, `place`, `cancel`, `positions`), constant-product curve math on integer reserves, fee model, seeded lognormal latency, order state machine NEW -> ACCEPTED -> CONFIRMING -> FILLED/PARTIAL/REJECTED, in-flight barrier; `live/` disabled stubs and the nine-precondition `LiveGate` | Library code; every transition is one ledger event; `RiskEngine.check` called at NEW and re-run at CONFIRMING |
| `risk/` | `RiskEngine.check(order) -> RiskDecision`, halts (daily loss, drawdown; human-cleared only), breakers (vendor `CircuitBreaker` port + `DataStale`, `LossVelocity`, `ExecErrors`), `KillSwitch` sources (env at start, `var/KILLSWITCH` file, allowlisted alert command) and flatten request, daily rollover | Library code called from inside the adapter and from the risk seat's cadence; appends `HaltSet`, `BreakerTripped`, `KillSwitchSet` itself (R24) |
| `engine/` | Ported vendor screening loop: monitor (PumpPortal create/trade frames), analyzer, scoring, reputation, LLM agents, exits, watcher | Characterization-tested port, English strings, `clock` injected everywhere the vendor read time |
| `tools/` | The `<ns>.<verb>` catalog: `market.*`, `onchain.*` (shared RPC client with failover), `safety.*`, `exec.*`, `portfolio.*`, `risk.*`, `journal.*`, `notify.*`, `desk.*` core eight | Thin typed wrappers over engine/execution/ledger/risk; the only surface seats and the gateway see |
| `supervisor/` | `Supervisor` (task-per-seat, cadence, roster-order ticks, signal handlers, drain, bounded restart, kill-switch flatten executor), `SeatTask`, `HealthServer`, `metrics` (phase 5) | asyncio single loop; `prometheus_client` text exposition; `var/health.json` atomic writer |
| `reporting/` | Pure `ReportModel` from ledger views; daily/weekly markdown renderers | No I/O in the renderer; snapshot-tested |
| `services/desk-gateway/` | One Streamable-HTTP MCP endpoint per seat serving that seat's roster; derives the transport name `<ns>_<verb>` at exposure time; validates input schema; audits every call | `mcp` SDK `MCPServer` subclass + seat router (programming-desk precedent) over the in-process `ToolRegistry` |
| `cli.py` | `run --mode paper [--once] [--replay <dir> | --record <dataset>]`, `doctor`, `verify`, `report`, `paper buy|sell`, `killswitch *`, `state *`, `live confirm` | Builds the object graph once (`make_rng` called exactly once), then delegates |

## Recommended Project Structure

The structure is fixed by R31 and `docs/MIGRATION_MAP.md` section 7.1 (every design-named module has exactly one home batch). Research confirms the layout; it is the conventional "ports and adapters around a single event store" layout and needs no change.

```
src/pumpgrok/
+-- core/           # interfaces.py, registry.py, ids.py, approvals.py, atomic_write.py, llm.py, budget.py, ratelimit.py
+-- config/         # settings.py, overlays/{dev,paper,live}.toml
+-- logging/        # json.py (JsonFormatter + RedactionFilter), spans.py (phase 5)
+-- ledger/         # store.py, events.py, reducer.py, views.py, reconcile.py, export.py, desk_bus.py
+-- replay/         # clock.py, rng.py, fixtures.py, sources.py, recorder.py, runner.py
+-- engine/         # pipeline.py, monitor.py, analyzer.py, scoring.py, reputation.py, tune.py, models.py, exits.py, watcher.py, agents/
+-- execution/      # paper_adapter.py, curve_math.py, fees.py, latency.py, quote.py, live/{live_adapter,live_gate}.py
+-- risk/           # engine.py, limits.py, sizing.py, breakers.py, killswitch.py
+-- tools/          # market/ onchain/ safety/ exec/ portfolio/ risk/ journal/ notify/ desk/
+-- supervisor/     # scheduler.py, seat_task.py, lifecycle.py, health.py, metrics.py
+-- reporting/      # daily.py, weekly.py, render.py
+-- cli.py
services/desk-gateway/   # separate package: server.py (SeatServer(MCPServer), SeatRouter), config.py, tools/
contracts/               # tool-rosters/*.yaml, events/*.schema.json
tests/                   # core/ config/ ledger/ replay/ risk/ desk/ safety/ characterization/ fixtures/replay/<dataset>/
```

### Structure Rationale

- **`ledger/` has no dependency on `execution/`, `risk/` or `engine/`:** it is the bottom of the dependency graph (only `core/` and `replay/clock` below it) so that `pumpgrok verify`, `report` and `doctor` can read a ledger without importing the engine. This is what makes the batch-1 skip-only cycle (`JournalNote decision: skip`) buildable before any engine exists (`docs/MIGRATION_MAP.md` section 7).
- **`replay/clock.py` is the only module allowed to import `time`, `asyncio.sleep`, `asyncio.timeout`:** every other module receives a `Clock`. The static test `tests/safety/test_virtual_time_only.py` enforces the boundary; this is the single most important structural rule for determinism (`docs/design/paper-engine.md` section 4.2).
- **`risk/` is library code, not a seat:** `RiskEngine.check` runs inside `PaperAdapter.place` (at NEW and again at CONFIRMING). The risk seat only monitors cadence and sets the kill switch; it cannot be bypassed by a seat that never calls `risk.*` tools (R24, section 2.8).
- **`tools/` is the only surface above the adapter:** seats and the gateway never import `execution/` or `ledger/` directly, which is what makes "least privilege" testable (`ToolRegistry.find` with `max_side_effect` per grant) and what keeps the gateway thin.
- **`services/desk-gateway/` is a separate package with its own `pyproject.toml`** (programming-desk precedent `services/desk-gateway/pyproject.toml`): the `mcp` SDK dependency stays out of the core package; the gateway imports `pumpgrok` (see Integration Points for the process-placement question).

## Architectural Patterns

### Pattern 1: Single-writer, hash-chained, append-only event ledger with snapshots (event sourcing on sqlite WAL)

**What:** Every state change is one immutable event row; state is `reduce(snapshot, tail)`; each row's `hash` covers `prev_hash` so tampering or a fork is detectable; snapshots bound restart time. This is Fowler's Event Sourcing with the two hard parts he names, external updates and external queries, handled by replay gateways (Pattern 4) `[webfetch]` https://martinfowler.com/eaaDev/EventSourcing.html.

**When to use:** Whenever the ledger must be the audit trail and the replay oracle at once (paper trading for 2-4 weeks, honest reports, live-gate evidence computed only from `source=paper` events).

**Trade-offs:** sqlite gives one host, one file, zero ops; WAL gives concurrent readers (`report`, `status`, Hermes cron) while the supervisor writes `[webfetch]` https://sqlite.org/wal.html. Costs: (a) the design's `synchronous = FULL` fsyncs the WAL on every append; at the designed cadence (500 events / 300 s snapshot cadence, MTM every 60 s) this is milliseconds per event on local SSD and negligible, but it runs on the event-loop thread, so appends must stay small and never be batched behind a network await; (b) WAL does not work on a network filesystem, so `var/` must be a local disk or a local Docker volume `[webfetch]` https://sqlite.org/wal.html section 1; (c) `synchronous=NORMAL` would be faster but can lose the last commit on power loss, which for a ledger that is the system of record is the wrong trade `[webfetch]` https://sqlite.org/pragma.html#pragma_synchronous.

**Refinement the implementation must carry (HIGH impact):** Python's `sqlite3` module issues its implicit `BEGIN` only before `INSERT/UPDATE/DELETE/REPLACE`, never before a `SELECT`, under the default `LEGACY_TRANSACTION_CONTROL` `[webfetch]` https://docs.python.org/3.12/library/sqlite3.html (Transaction control via the isolation_level attribute). A naive `append()` that does `SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1` and then `INSERT` therefore reads the chain head OUTSIDE the write lock, even with `isolation_level="IMMEDIATE"`; two processes (supervisor and `pumpgrok paper buy`) can both read head N and one of them fails with `IntegrityError` on `seq`/`hash` or, worse, computes a `prev_hash` for a row that is no longer the head. The fix is to open the connection with `autocommit=True` (3.12+) or `isolation_level=None` and issue `BEGIN IMMEDIATE` explicitly before the head read, so the read and the insert are one write transaction. Also note `sqlite3.connect(timeout=5.0)` already installs the busy handler; `PRAGMA busy_timeout = 5000` in the schema is redundant with it (pick one, keep the value in config). In WAL mode a DEFERRED transaction that has already read and then tries to write gets `SQLITE_BUSY` immediately without consulting the busy handler, whereas `BEGIN IMMEDIATE` waits on it `[webfetch]` https://sqlite.org/lang_transaction.html section 2.2; this is exactly why R26 is right to mandate IMMEDIATE.

**Example:**
```python
# ledger/store.py (sketch; Python 3.12 sqlite3, autocommit=True so BEGIN is ours)
con = sqlite3.connect(path, timeout=cfg.busy_timeout_s, autocommit=True, uri=True)
con.execute("PRAGMA journal_mode=WAL")
con.execute("PRAGMA synchronous=FULL")

def append(self, event: Event) -> int:
    con.execute("BEGIN IMMEDIATE")              # write lock first, then read the head
    try:
        row = con.execute("SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        seq, prev = (row[0] + 1, row[1]) if row else (1, "0" * 64)
        body = {"prev_hash": prev, "seq": seq, "ts_utc": event.ts_utc, "source": event.source,
                "correlation_id": event.correlation_id, "type": event.type,
                "payload_json": canonical_json(event.payload)}
        h = hashlib.sha256(canonical_json(body).encode()).hexdigest()
        con.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
                    (seq, event.ts_utc, event.source, event.correlation_id,
                     event.idempotency_key, event.type, body["payload_json"], prev, h))
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK"); raise
    return seq
```

### Pattern 2: Virtual-time discipline (injected Clock, seeded RNG, no library-owned timers)

**What:** One `Clock` protocol (`now`, `monotonic`, `utc_iso`, `sleep`, `timeout`) injected everywhere; `FixtureClock` advances only when the runner delivers the next fixture event or when the earliest pending `sleep`/`timeout` deadline is reached, waking sleepers in `(wake_time, enqueue_seq)` order; one `random.Random(seed)` created once in `cli.py` and passed down (`docs/design/paper-engine.md` section 4.2).

**When to use:** Any system that must replay a recorded day byte-for-byte (identical hash chain, identical ULIDs) and whose tests must not depend on host speed.

**Trade-offs:** The discipline is cheap to follow in first-party code and enforced by a static test, but third-party libraries own timers the static test cannot see. Research found three concrete leaks the design must route around:

1. **tenacity jitter uses the module-global `random`.** `wait_random` calls `random.random()` and `wait_random_exponential` calls `random.uniform()` `[webfetch]` https://raw.githubusercontent.com/jd/tenacity/main/tenacity/wait.py. `AsyncRetrying(sleep=clock.sleep)` is supported (the `sleep` parameter accepts any async callable; the default is a portable `asyncio.sleep`) `[webfetch]` https://raw.githubusercontent.com/jd/tenacity/main/tenacity/asyncio/__init__.py, but the wait amount itself is not seedable through tenacity. The `RetryPolicy.jitter` field in `docs/design/interfaces.md` must therefore be realised by a first-party wait callable `(retry_state) -> float` that draws from the injected rng (full-jitter formula from the AWS post tenacity cites), and `tests/safety/test_no_ambient_randomness.py` should also ban `tenacity.wait_random` / `wait_random_exponential` / `wait_exponential_jitter` imports. `[INFERENCE]` on the test extension.
2. **websockets' reconnect iterator sleeps on the real loop.** `websockets.asyncio.client.connect.__aiter__` awaits `asyncio.sleep(delay)` with `reconnect_delays=backoff` between attempts and wraps the handshake in `asyncio.timeout(open_timeout)` `[webfetch]` https://raw.githubusercontent.com/python-websockets/websockets/main/src/websockets/asyncio/client.py (version 17.3 on PyPI, 2026-10-19). The port of the vendor stream loop (`monitor.py`, reconnect 1 -> 60 s) must own its reconnect loop with `clock.sleep` and call `connect(...)` once per attempt, never `async for ws in connect(...)`. Under `WallClock` the library's internal `open_timeout` and keepalive pings are fine; under replay `FixtureWebSocket` replaces `connect` entirely, so library timers never run.
3. **asyncio task ordering.** The event loop documents that `call_soon` callbacks run in registration order `[webfetch]` https://docs.python.org/3.12/library/asyncio-eventloop.html, which is what makes the FixtureClock heap sufficient for determinism. Two things break it: `asyncio.eager_task_factory` (3.12) which the docs say "is likely to change the application's task execution order" `[webfetch]` https://docs.python.org/3.12/library/asyncio-task.html, and running seats concurrently with `gather` instead of in roster order within a tick. Do not set a task factory; keep the design's roster-order ticks; use `TaskGroup` only for structured shutdown, not for per-tick fan-out.

`FixtureClock.timeout()` must reproduce `asyncio.timeout` semantics (cancel the current task at the deadline, then `uncancel()` so a `TaskGroup` above it is not torn down) `[webfetch]` https://docs.python.org/3.12/library/asyncio-task.html (Task Cancellation / Timeouts). Budget this as a unit-tested primitive in phase 1, not an afterthought.

**Example:**
```python
# first-party jittered wait, seeded; passes mypy --strict
def full_jitter(rng: random.Random, base_s: float, max_s: float) -> Callable[[RetryCallState], float]:
    def wait(state: RetryCallState) -> float:
        high = min(max_s, base_s * (2 ** (state.attempt_number - 1)))
        return rng.uniform(0.0, high)
    return wait

retrier = AsyncRetrying(sleep=clock.sleep, wait=full_jitter(rng, 0.5, 5.0),
                        stop=stop_after_attempt(policy.attempts), reraise=True)
```

### Pattern 3: Risk engine as library code inside the execution adapter (check at NEW, re-check at CONFIRMING, in-flight barrier)

**What:** `PaperAdapter.place` is the single chokepoint for paper writes. It calls `RiskEngine.check` before accepting an order and again immediately before computing the fill, after the simulated confirmation latency; orders in ACCEPTED/CONFIRMING form an in-flight set the supervisor's kill-switch flatten waits on (`docs/design/paper-engine.md` sections 2.8, 5.4).

**When to use:** Whenever a seat (an LLM) is the caller: the policy must sit below the lowest layer the caller can reach, so a prompt that forgets to call `risk.check_limits` changes nothing.

**Trade-offs:** The adapter becomes the one stateful component (in-flight set, idempotency cache) that two processes cannot share. `pumpgrok paper buy|sell` runs `exec.simulate + exec.place` in the CLI process (`docs/TOOL_CATALOG.md` CLI table) and `tests/ledger/test_single_writer_concurrent_appends.py` deliberately runs the supervisor and the CLI side by side. The ledger protects itself (UNIQUE `idempotency_key`, chain computed under the write lock), but `RiskEngine.check` in each process evaluates `max_open_positions`, `daily_loss`, cash against a `LedgerState` reconstructed when that process opened the ledger. Two processes can each see 2 of 3 open positions and both open a third. `[INFERENCE]` Mitigation to settle in phase 4 planning: perform the CONFIRMING re-check inside the same `BEGIN IMMEDIATE` transaction that appends `FillRecorded`, re-reading the tail since the process's last known `seq` and folding it through the reducer before deciding (cheap: the tail is a handful of rows). This turns "check then append" into "check-and-append" and makes the risk caps hold across processes without supervisor IPC, which is the property R26 wants. The in-flight barrier remains per process; document that flatten only waits on the supervisor's own in-flight orders and that CLI orders are refused while `var/KILLSWITCH` exists (the file source is already cross-process truth).

### Pattern 4: Record/replay gateways around every external system

**What:** Every outbound transport (pump.fun REST, Jupiter, RPC via `httpx`; PumpPortal via `websockets`; x.ai via `core/llm.py`) is wrapped once: in `--record` mode the wrapper writes the dataset format; in `--replay` mode `FixtureHttpTransport` (an `httpx.MockTransport` `[webfetch]` https://www.python-httpx.org/advanced/transports/), `FixtureWebSocket` and `FixtureLlm` answer from the dataset keyed by `(method, url-or-params_hash)` and `canonical_request_hash`; a miss returns a synthetic 503 for HTTP/RPC (exercises breakers) but FAILS the replay for LLM (`ReplayMissingRecord`) (`docs/design/paper-engine.md` section 4.3). This is Fowler's "External Queries" rule (record the answer with the event) and "External Updates" rule (the gateway knows it is in replay) `[webfetch]` https://martinfowler.com/eaaDev/EventSourcing.html.

**When to use:** Always; it is what makes `pumpgrok verify --fixture <dataset>` (two runs, identical chain) a CI gate rather than a hope.

**Trade-offs and refinement:** The LLM key is "the prompt with timestamps, correlation ids and ULIDs stripped before hashing". Prompts are assembled from `prompts/` + skills (L1/L2/L3), so any wording change in a skill or role prompt changes every recorded request hash and turns every committed dataset into `ReplayMissingRecord`. `[INFERENCE]` Key the LLM record by a structured request instead: `(model, prompt_template_id, prompt_template_version, canonical_json(variables))` where the template version is the sha256 of the assembled prompt stored once in the dataset manifest. Replay then fails loudly only when the variables or the model change (which should fail), while a prompt edit produces one explicit manifest mismatch (`prompt_template_version`) that `pumpgrok replay rebuild-ticks`-style tooling can report, not thousands of silent misses. Decide this in phase 2 when `replay/recorder.py` and `core/llm.py` land; changing the key later invalidates recorded datasets.

### Pattern 5: Supervisor as task-per-seat with bounded restart and roster-order ticks

**What:** One asyncio loop owns a `SeatTask` per seat (heartbeat, `RestartPolicy` token bucket 5/h with jittered exponential backoff, observe-only latch after exhaustion, edge-triggered `Escalation` events to ledger + Notifier), timer or stream-driven cadence per seat, roster-order execution within a tick, `install_signal_handlers / drain / cancel_and_wait` ported from the vendor into `supervisor/lifecycle.py` (R43), `/healthz`, `/readyz`, `/metrics` and `var/health.json` (`docs/design/paper-engine.md` section 6).

**When to use:** Single-host autonomous desks where the failure domain is one process and the cheapest supervisor is the loop itself; a process supervisor (programming-desk `process_supervisor.py`) buys nothing here because every seat shares the ledger connection, the adapter and the clock.

**Trade-offs:** `asyncio.TaskGroup` cancels every sibling when one task raises, which is the opposite of bounded per-seat restart; use `TaskGroup` for shutdown (drain then cancel) and plain `create_task` with strong references (the loop keeps only weak references `[webfetch]` https://docs.python.org/3.12/library/asyncio-task.html) plus a per-seat restart loop for the seats. Because sqlite calls are synchronous, an append blocks the loop for the fsync; that is acceptable and in replay actually desirable (deterministic ordering); do not move ledger I/O to `asyncio.to_thread`, which would reintroduce thread scheduling into the replay ordering.

### Pattern 6: Least-privilege tool registry with the gateway as a thin per-seat projection

**What:** Tools are registered once with a `ToolSpec` (dotted id, `SideEffect`, timeout, retry policy, input/output models); each seat's roster (`contracts/tool-rosters/<seat>.yaml`, 8-15 tools, `_core.yaml` eight for every seat) is a grant; `ToolRegistry.find(capability, max_side_effect, bot)` is the only lookup and refuses anything above the grant; `LIVE_WRITE` exists in the enum and in no roster. The gateway serves `/mcp/<seat>` from the same rosters and derives the transport name `<ns>_<verb>` at exposure time (R19), validates input with `additionalProperties: false`, refuses credential-shaped arguments, deadlines every call and audits it (programming-desk `services/desk-gateway/README.md`).

**When to use:** Always; this is the mechanism that makes "no private keys, no live writes" a property of the registry rather than of prompt wording.

**Trade-offs:** The `mcp` SDK v2 (`from mcp.server import MCPServer`, Streamable HTTP is the deployable transport, SSE superseded; `Client(mcp)` gives an in-memory client for tests with no port) `[webfetch]` https://py.sdk.modelcontextprotocol.io/run/ and https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md; PyPI `mcp` 2.3.0 released 2026-10-02 (checked 2026-10-20), matching the precedent pin `mcp[cli]>=2.2.0,<3`. The precedent's OAuth AS is deferred for pumpgrok (PROJECT.md Out of Scope); keep the `x-connector-key` header mode and one passphrase per seat. The open question is process placement; see Integration Points.

## Data Flow

### Request Flow

The one flow everything else is a variation of: signal -> decision -> order -> fill -> ledger -> report.

```
PumpPortal WS frame / pump.fun REST poll / RPC lookups      (DataSource, Freshness)
    |
    v
engine.monitor -> engine.analyzer -> engine.scoring (+ core/llm.py for bot-08-signal)
    |  JournalNote(note_kind=signal, refs=[stage, reason]) with a root correlation_id ULID
    v
seat cycle (scout -> whale -> rug -> shill -> signal -> sniper, roster order within a tick)
    |  ToolRegistry.find("exec.place", PAPER_WRITE, bot-04-sniper)   (grant check, GrantAudit)
    v
exec.place -> PaperAdapter.place(OrderRequest, approval)
    |  idempotency_scope = f"{ticket_id}:{side}:{decision_id}"  (R23, derived, never caller-supplied)
    |  RiskEngine.check  -> OrderRejected(reason) | OrderPlaced(quote source=curve, risk_check)
    |  clock.sleep(latency)  (seeded lognormal)          [ACCEPTED]
    |  RiskEngine re-check  -> OrderRejected(kill_switch|halted|breaker_open) | continue   [CONFIRMING]
    |  curve_math on (S0, T0): FillRecorded (filled_fraction, price_avg, fees) | OrderRejected(slippage_exceeded|tx_dropped)
    |  PositionOpened (first buy fill) / PositionClosed (last sell fill)
    v
LedgerStore.append  (BEGIN IMMEDIATE; ts_utc from Clock; hash chain)  -> seq
    |
    +--> reducer.reduce(state, event) -> LedgerState  (positions, cash, counters, halts, breakers)
    +--> export: var/journal/YYYY-MM-DD.jsonl, trades.jsonl, $PUMPGROK_DESK/journal/paper-*.md, desk.md halt mirror
    +--> views: positions(), cash(), pnl(), equity_curve(), drawdown(), fees()
    v
reporting.daily / weekly (pure ReportModel -> markdown) ; supervisor.health (/healthz, var/health.json) ; live_gate evidence (source=paper only)
```

Exits run the same path from the other side: `engine.watcher` marks to market every 60 s (`MarkToMarket`), `engine.exits` emits `ExitSignal`, `bot-06-exit` calls `exec.place(side=sell)`, same adapter, same ledger.

### State Management

```
events (sqlite, append-only, hash chain)
    | reduce in seq order (pure)             | snapshot every 500 events / 300 s / DailyRollover / HaltSet / shutdown
    v                                        v
LedgerState (positions, cash, day_utc, counters, halt, breakers, kill_switch, autonomy_level)
    | read by                                 | read-only connections (?mode=ro, WAL permits concurrently)
    v                                        v
RiskEngine.check, PaperAdapter MTM, views  CLI status/report/verify, Hermes cron (via health.json / desk.md, not sqlite)
```

Restart is `snapshot + tail replay + verify chain`; any mismatch sets `INCONSISTENT`, appends `HaltSet(ledger_inconsistent)` and `RiskEngine.check` rejects every buy until a human clears it (`docs/design/paper-engine.md` section 3.5). There is no in-memory state that is not either in the ledger or derivable from it, except the per-process in-flight set (Pattern 3) and `CallBudget` counters in `var/budget.json`.

### Key Data Flows

1. **Entry (paper buy):** as drawn above; one root ULID correlation id from the PumpPortal `create` frame to `PositionOpened`; every event carries it so `pumpgrok report` and the journal can thread a trade end-to-end.
2. **Exit:** `MarkToMarket` (60 s cadence, liquidation value not spot) -> `ExitSignal` (stop_loss, take_profit, trailing, time) -> `exec.place(sell)` -> `FillRecorded` -> `PositionClosed(realized_pnl_lamports, reason)`; day attribution by fill timestamp (section 5.5).
3. **Kill switch:** env (start-time) | `var/KILLSWITCH` file | allowlisted alert command -> `KillSwitchSet` -> every buy rejected `kill_switch`; in-flight orders rejected at CONFIRMING; optional flatten: supervisor waits on the in-flight barrier, then calls `PaperAdapter.place(sell)` per position in-process with `ApprovalRecord(kind=autonomous_paper)` minted by `RiskEngine`; clear only via CLI `--by human:<name>` appending `KillSwitchCleared + ApprovalRecorded(kind=killswitch_clear)` (section 5.4).
4. **Daily rollover (UTC):** forced MTM -> `DailyRollover(day_start_equity_lamports)` -> counters reset -> halts NOT cleared (human only; vendor auto-clear intentionally not ported).
5. **Replay / verify:** `FixtureReader` merges streams by `(ts, file_order, line_no)`; `FixtureClock` advances; fixture transports answer; the run writes `var/replay/<dataset>/ledger.sqlite` with `source=replay`; `verify` runs twice and compares `events.hash` chains and JSONL bytes.
6. **Manual CLI write (`paper buy|sell`, `killswitch clear`, `state halt --clear`, `live confirm`):** a second process appends through the same `LedgerStore.append`; sqlite's write lock serialises it with the supervisor (Pattern 1); `source=manual`.
7. **Live gate (never passes in this milestone):** `pumpgrok run --mode live` evaluates nine preconditions from config + `source=paper` events only, prints every unmet one, exits 3; `LiveAdapterStub` raises `LiveGateError` on any call.

## Scaling Considerations

"Scale" here is events per day, seats, and replay dataset size, not users; the desk is one process on one host by design.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| One desk, ten seats, a few hundred to a few thousand ledger events/day (MTM every 60 s per open position dominates; 3 positions max) | The designed shape is correct as is: one sqlite file, WAL, `synchronous=FULL`, snapshot every 500 events / 300 s, auto-checkpoint at the sqlite default of 1000 WAL pages `[webfetch]` https://sqlite.org/wal.html section 3.1. Nothing to tune. |
| Recorded datasets: `smoke-10m` under 1 MB committed; `soak-3d` about 50 MB from an artifact store | `FixtureReader` must stream the JSONL merge (heap over per-file iterators), not load files into lists; `ticks.jsonl` is derived once at record time so `FixturePriceSource.curve()` is a dict lookup. Replay of three virtual days must finish in CI minutes: the FixtureClock jumps between wake times, so wall time is bounded by event count, not virtual duration. |
| Weeks of live-paper history in one ledger (tens of thousands of events) | Restart stays O(tail) thanks to snapshots; `pumpgrok verify` and chain verification stay O(n) and run offline. If `report --weekly` gets slow, add covering indexes on `(type, ts_utc)` to `events`; do not denormalise into a second store. |

### Scaling Priorities

1. **First bottleneck: event-loop stalls, not sqlite throughput.** Synchronous `fsync` per append and synchronous JSONL/markdown exports run on the loop. Keep exports batched "after every event batch and on shutdown" as designed, write with `atomic_write`, and measure `pumpgrok_cycle_seconds{seat}` once metrics exist (phase 5). Only if a histogram shows export time competing with the 5 s risk cadence should export move to a worker thread, and never in replay mode.
2. **Second bottleneck: WAL growth under long-lived readers.** A reader that holds a transaction open (a long `report` query) prevents the checkpoint from resetting the WAL (`[webfetch]` https://sqlite.org/wal.html section 6). Reports open read-only connections and iterate to completion; `pumpgrok doctor` should report WAL file size next to the ledger status so starvation is visible.

## Anti-Patterns

### Anti-Pattern 1: Reading the chain head outside the write lock

**What people do:** Rely on Python's implicit transaction (`isolation_level="IMMEDIATE"`) and write `SELECT head; INSERT row; commit()`.
**Why it's wrong:** The implicit `BEGIN` is issued before the `INSERT`, not before the `SELECT` `[webfetch]` https://docs.python.org/3.12/library/sqlite3.html; the head read is unprotected and the second writer computes a stale `prev_hash`. The UNIQUE constraints turn the fork into an `IntegrityError` that the CLI then reports as "ledger unavailable" at exactly the moment a human is trying to clear a halt.
**Do this instead:** `connect(..., autocommit=True)` and explicit `BEGIN IMMEDIATE ... COMMIT` (Pattern 1); `tests/ledger/test_single_writer_concurrent_appends.py` already expects this property, make it also assert that `prev_hash` of every row equals `hash` of `seq-1` under contention.

### Anti-Pattern 2: `async for ws in websockets.connect(...)` for the PumpPortal stream

**What people do:** Use the library's reconnect iterator because it is one line.
**Why it's wrong:** Its backoff is `await asyncio.sleep(delay)` on the real loop `[webfetch]` https://raw.githubusercontent.com/python-websockets/websockets/main/src/websockets/asyncio/client.py; the virtual-time static test cannot see it, the DataStale breaker's 120 s window then measures wall time in replay, and the recorded reconnect timing cannot be reproduced.
**Do this instead:** Own the reconnect loop in `engine/monitor.py` with `clock.sleep(backoff)` and a single `connect(...)` per attempt; in replay `FixtureWebSocket` replaces `connect`.

### Anti-Pattern 3: tenacity's built-in jitter

**What people do:** `AsyncRetrying(sleep=clock.sleep, wait=wait_random_exponential(...))` and believe the retry is deterministic because the sleep is virtual.
**Why it's wrong:** The wait amount comes from the global `random` module `[webfetch]` https://raw.githubusercontent.com/jd/tenacity/main/tenacity/wait.py; two replays schedule retries at different virtual times and the hash chains differ.
**Do this instead:** First-party `full_jitter(rng, base_s, max_s)` wait callable (Pattern 2); ban `tenacity.wait_random*` in the static test.

### Anti-Pattern 4: Two live `PaperAdapter` instances deciding against stale state

**What people do:** Let the gateway process or the CLI build its own adapter and call `exec.place` directly, trusting the ledger's idempotency key.
**Why it's wrong:** Idempotency prevents the same order twice; it does not prevent two different orders that each individually pass `max_open_positions` or `daily_loss_halt_fraction` against a state that is one event behind.
**Do this instead:** Check-and-append inside the `BEGIN IMMEDIATE` transaction at CONFIRMING (Pattern 3); in-process gateway or read-only gateway (Integration Points).

### Anti-Pattern 5: Hashing the rendered prompt as the LLM replay key

**What people do:** `sha256(prompt_text_with_ids_stripped)`.
**Why it's wrong:** Every skill or role-prompt edit invalidates every recorded dataset at once, with the failure surfacing as thousands of `ReplayMissingRecord`s instead of one "template version changed".
**Do this instead:** Structured key `(model, template_id, template_version, variables)` with the template version pinned in the dataset manifest (Pattern 4).

### Anti-Pattern 6: Using `asyncio.gather` or an eager task factory for the per-tick seat fan-out

**What people do:** Run all seats concurrently per tick for speed.
**Why it's wrong:** Completion order then depends on I/O timing; with `eager_task_factory` even start order changes `[webfetch]` https://docs.python.org/3.12/library/asyncio-task.html. The ledger `seq` order, and therefore the hash chain, becomes non-reproducible.
**Do this instead:** Roster-order ticks as designed; concurrency only inside a seat's own I/O (bounded by the vendor's `_guarded` semaphore port) where results are merged deterministically (sorted by mint/ULID) before any ledger append.

### Anti-Pattern 7: Read-only ledger access from a different Unix user or a read-only mount

**What people do:** Mount `var/` read-only into a reporting container, or run Hermes cron under another user, and open `file:ledger.sqlite?mode=ro`.
**Why it's wrong:** A WAL database can be opened read-only only if the `-shm` and `-wal` files exist or can be created by the opener `[webfetch]` https://sqlite.org/wal.html section 5; otherwise the open fails or falls back to behaviour that ignores the WAL content.
**Do this instead:** Same user, same host, local disk; Hermes cron reads `var/health.json` and `$PUMPGROK_DESK/*.md` (the design already routes it that way), never sqlite.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| PumpPortal WS | `websockets.asyncio.client.connect` (17.3, new asyncio API; legacy deprecated), first-party reconnect loop with `clock.sleep`, raw frames recorded to `pumpportal.jsonl` and derived `ticks.jsonl` | `vTokensInBondingCurve` presence is an unverified item (paper-engine Unverified 4); the recorder keeps the raw frame so the derivation can be rebuilt |
| pump.fun frontend REST | `httpx.AsyncClient(transport=...)` with explicit `httpx.Timeout`, tenacity on timeout/5xx/429 only, `extra="ignore"` models | Fixture key `(method, url)`; a miss is a synthetic 503 |
| Jupiter lite-api quote | Same httpx pattern; quote is informational only (R38), never the fill price | Keeps the fill model single-sourced on the curve |
| Solana JSON-RPC | Shared client `tools/onchain/rpc.py`: failover list, tenacity with `sleep=clock.sleep`, `getAccountInfo`, `getTokenLargestAccounts`, `getRecentPrioritizationFees` | Fixture key `(method, params_hash)`; `BLIND` result = KILL for that token |
| x.ai Grok | `core/llm.py`: precheck + breaker port, call budget, recorder; replay by structured key (Pattern 4) | Missing record fails replay; rule-based fallback only in live-paper degradation |
| Telegram / webhook (notify, kill command inbound) | `tools/notify/*` allowlisted destinations (R39); inbound `KILL` command only when `alerts.telegram.allowed_chat_ids` is non-empty; the adapter writes `var/KILLSWITCH` so the file is the durable source | Not a Solana integration; existing Hermes profile gives only chief a token |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| seat <-> tool layer | `ToolRegistry.find(capability, max_side_effect, bot)` returning a bound `Tool`; typed pydantic in/out; `GrantAudit` row per call | The only way a seat reaches anything; `LIVE_WRITE` unreachable |
| tool layer <-> execution | `exec.quote/simulate/place/cancel/positions` -> `ExecutionAdapter` protocol (five methods) | `PaperAdapter` only; `LiveAdapterStub` raises `LiveGateError` |
| execution <-> risk | Direct call `RiskEngine.check(order)` at NEW and CONFIRMING; `RiskEngine` appends `HaltSet`/`BreakerTripped` itself | Library, not IPC; no seat in the path |
| execution/risk/engine <-> ledger | `LedgerStore.append(event) -> seq`; reads via `views`/`reducer` | Events defined once in `ledger/events.py` (18 types, R32); JSON Schemas generated from them |
| everything <-> replay | Constructor-injected `Clock`, `rng`, `IdFactory`; transports swapped at the composition root (`cli.py`) | `tests/safety/test_virtual_time_only.py`, `test_no_ambient_randomness.py`, `test_no_uuid.py` |
| supervisor <-> seats | `Bot.cycle(ctx)` per cadence; `SeatTask` restart policy; `Escalation` events | Seats never touch the loop directly |
| supervisor <-> CLI processes | Shared sqlite file (write lock) + `var/KILLSWITCH` file + `var/health.json`; no sockets | Deliberate: no supervisor IPC (R26) |
| gateway <-> registry | Same `ToolRegistry` and rosters; transport name derived `<ns>_<verb>` | Process placement below |

**Gateway process placement (decision needed in phase 3 planning).** D2 says "thin per-seat MCP/HTTP wrapper over the in-process registry". The precedent gateway is a standalone uvicorn service. If the pumpgrok gateway is a separate process it has its own `ToolRegistry`, its own `PaperAdapter` (Anti-Pattern 4) and its own `Clock`, and a `exec.place` from an external LLM client would fill in a process the supervisor cannot see in flight. `[INFERENCE]` Recommended split: (a) in the supervisor process, mount the `MCPServer` ASGI app as one more loop task next to `HealthServer` (the `mcp` SDK documents mounting into an existing ASGI app `[webfetch]` https://py.sdk.modelcontextprotocol.io/run/), so the gateway serves the live registry, the live adapter and the live clock; (b) when `services/desk-gateway` runs standalone (operator convenience, tests), it serves READ tools only and answers `PAPER_WRITE` calls with `not_in_process` (fail closed), the same way the precedent answers unconfigured upstreams with `not_configured`. Either way the gateway is phase 3 for READ tools and only gains `exec.*` in phase 4 when the adapter exists.

### Build Order (phase seams)

The five batches of `docs/MIGRATION_MAP.md` section 7 are the right order and research found no reason to re-cut them; each checkpoint is runnable because the ledger sits at the bottom of the graph and the engine/adapter are added above an already-working `run --once --replay` cycle. The seams below are where one phase's output is the next phase's input, named by module and symbol so the roadmap can pin them.

| Phase | Builds | Seam it exposes to the next phase | Proves |
|---|---|---|---|
| 1 Foundation | `core/*` (interfaces, registry, ids, approvals, atomic_write), `config/`, `logging/json.py`, `ledger/{store,events}.py` (schema, explicit `BEGIN IMMEDIATE`, hash chain, 18 types), `replay/{clock,rng,fixtures}.py` incl. `FixtureClock.timeout`, `cli.py` skeleton, gates G-1..G-7 + `ownership.yaml`, static safety tests | `Clock`, `make_rng`, `IdFactory`, `LedgerStore.append`, `ToolRegistry`, the skip-only `run --once --replay smoke` cycle, `doctor` with `not-yet-implemented` map | `JournalNote(decision: skip, reason: engine_not_yet_implemented)` lands in `var/replay/smoke/ledger.sqlite`; concurrent-append test green |
| 2 Restructure | `tools/onchain/rpc.py`, `tools/market/{pumpfun,pumpportal,jupiter}.py`, `tools/notify/*`, `replay/{recorder,sources}.py` + recorded `smoke`, engine port (`engine/*`, `core/{ratelimit,budget,llm}.py`, `risk/breakers.py` base, `engine/{exits,watcher}.py`), prompts/skills/docs rewrite, characterization tests | `DataSource` implementations behind fixture transports; `Recorder` dataset format; LLM replay key (decide Pattern 4 here); first-party WS reconnect loop and jitter wait | Engine produces `buy|skip` from fixtures; `buy` recorded as `skip execution_not_yet_implemented`; vendor suite still green as oracle |
| 3 Tools and Skills | Catalog tools under `tools/*` (dotted ids), rosters 8-15 per seat, `contracts/events/*.schema.json` generated from `ledger/events.py`, skills frontmatter + 12 new skills, `services/desk-gateway/` READ-only surface, G-7 against real rosters | `ToolRegistry` grants per seat; `exec.*` registered but backed by a `not_yet_implemented` refusal; gateway `/mcp/<seat>` with `tools/list` | Least-privilege tests (`find` refuses above-grant); gateway in-memory `Client(mcp)` tests per seat |
| 4 Paper and Autonomy | `execution/*` (PaperAdapter, curve_math, fees, latency, quote), `execution/live/*` (nine preconditions, exit 3), `risk/{engine,limits,sizing,killswitch}.py` + risk breakers, `ledger/{reducer,views,reconcile,export,desk_bus}.py`, `replay/runner.py`, `supervisor/{scheduler,seat_task,lifecycle,health}.py`, reporting, CLI verbs | `ExecutionAdapter.place` wired to `exec.place`; check-and-append at CONFIRMING; flatten executor; `verify --fixture` determinism; gateway gains `exec.*` in-process | `OrderPlaced + FillRecorded + PositionOpened` from `smoke`; two replays identical chain; `run --mode live --once` exits 3; kill-switch one-cycle and in-flight tests |
| 5 Hardening | `supervisor/metrics.py` (`prometheus_client` 0.26), `logging/spans.py`, fault-injection and soak tests, security CI, Dockerfile/compose, delete `tools/` and `vendor/` at zero census | `/metrics` families named in section 6.6; `soak-3d` nightly | `doctor` has no `not-yet-implemented`; three virtual days under 20 MB growth (REVIEW) |

Cross-phase invariants that must be tested from phase 1 and never relaxed: the three static safety tests (virtual time only, no ambient randomness, no uuid), the explicit-transaction ledger append, and the `CHECKPOINT_RULE` (`run --once --replay smoke` exits 0 after every batch).

## Sources

- `docs/design/paper-engine.md` sections 0-6, 9-12 (PaperAdapter state machine, ledger schema and single-writer rule, replay clock/RNG/fixtures, risk and kill switch, supervisor, test list) - HIGH, read directly
- `docs/design/interfaces.md` sections 1-2 (module map, `SideEffect`, `canonical_json`, `derive_idempotency_key`, `RetryPolicy`, `Tool`, registry) - HIGH, read directly
- `docs/MIGRATION_MAP.md` section 7 and 7.1 (five batches, checkpoint rule, module-to-batch coverage) - HIGH, read directly
- `docs/TOOL_CATALOG.md` CLI table (`pumpgrok paper buy|sell` runs `exec.simulate + exec.place`), `docs/FOUNDATION_STACK.md` section 2 (pins) and M-1 (websockets) - HIGH, read directly
- `/root/src/repos/programming-desk/services/desk-gateway/README.md`, `pyproject.toml` (`mcp[cli]>=2.2.0,<3`), `server.py` (`SeatServer(MCPServer)`, `SeatRouter`) - HIGH, read directly
- Python 3.12 `sqlite3` transaction control (`autocommit`, `isolation_level`, implicit BEGIN only before DML, `timeout` busy handler): https://docs.python.org/3.12/library/sqlite3.html - `[webfetch]`
- SQLite WAL (readers vs writers, no network FS, read-only needs `-shm`, auto-checkpoint 1000 pages, long readers block checkpoint): https://sqlite.org/wal.html - `[webfetch]`
- SQLite `synchronous` in WAL (NORMAL may lose last commit on power loss; FULL fsyncs WAL per commit): https://sqlite.org/pragma.html#pragma_synchronous - `[webfetch]`
- SQLite `BEGIN IMMEDIATE` vs DEFERRED upgrade `SQLITE_BUSY`; EXCLUSIVE == IMMEDIATE in WAL: https://sqlite.org/lang_transaction.html - `[webfetch]`
- tenacity `AsyncRetrying(sleep=...)` and global-`random` jitter: https://raw.githubusercontent.com/jd/tenacity/main/tenacity/asyncio/__init__.py , https://raw.githubusercontent.com/jd/tenacity/main/tenacity/wait.py - `[webfetch]`; PyPI tenacity 9.2.1 (2026-10-07)
- websockets asyncio client reconnect loop (`reconnect_delays`, `asyncio.sleep`, `asyncio.timeout(open_timeout)`): https://raw.githubusercontent.com/python-websockets/websockets/main/src/websockets/asyncio/client.py - `[webfetch]`; PyPI websockets 17.3 (2026-10-19)
- asyncio tasks (`TaskGroup`, `eager_task_factory` changes execution order, weak task references, timeout/uncancel): https://docs.python.org/3.12/library/asyncio-task.html ; `call_soon` registration order: https://docs.python.org/3.12/library/asyncio-eventloop.html - `[webfetch]`
- MCP Python SDK v2 (`MCPServer`, Streamable HTTP, ASGI mount, in-memory `Client(mcp)`): https://py.sdk.modelcontextprotocol.io/run/ , https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md - `[webfetch]`; PyPI mcp 2.3.0 (2026-10-02)
- httpx transports and `MockTransport`: https://www.python-httpx.org/advanced/transports/ - `[webfetch]`; PyPI httpx 0.28.1
- Martin Fowler, Event Sourcing (replay, snapshots, external updates via gateways, external queries recorded): https://martinfowler.com/eaaDev/EventSourcing.html - `[webfetch]`
- PyPI version checks run 2026-10-20 (`curl https://pypi.org/pypi/<pkg>/json`): mcp 2.3.0, websockets 17.3, tenacity 9.2.1, httpx 0.28.1, prometheus_client 0.26.0, pydantic 2.14.1 - matches `docs/FOUNDATION_STACK.md` section 2

---
*Architecture research for: autonomous paper-only Solana memecoin trading desk (PumpGrok Desk v2)*
*Researched: 2026-10-20*
