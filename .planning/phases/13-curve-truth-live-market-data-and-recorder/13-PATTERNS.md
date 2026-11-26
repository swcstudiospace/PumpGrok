# Phase 13: Curve truth, live market data and recorder - Pattern Map

**Mapped:** 2026-11-10  
**Scope:** 22 named source/document targets and 7 grouped test targets below. New datafeed filenames are the roadmap's module names made explicit, not evidence that implementations already exist.  
**Upstream:** `13-CONTEXT.md`, Phase 13 roadmap and MKT/REC requirements. `13-RESEARCH.md` was not present when mapped; reconcile any additional targets it names before planning. Phase 12 historical verification remains stale; this map makes no refreshed-verification claim.

## File Classification

Quality: **exact** = existing file is the same role/data flow and is the modification target or closest established pattern; **partial** = useful seam but missing required new behavior; **none** = no close implementation established. Test rows list the acceptance-test filenames as grouped targets, not existing files.

| New/Modified File | Role | Data Flow | Closest tracked analog | Match |
|---|---|---|---|---|
| `src/pumpgrok/tools/onchain/curve_layout.py` | model/utility | transform | same file | exact |
| `src/pumpgrok/tools/onchain/pump_events.py` | utility | transform | same file | exact |
| `src/pumpgrok/datafeed/events.py` | model | event-driven | `src/pumpgrok/events/models.py` | partial |
| `src/pumpgrok/datafeed/mintbook.py` | store | event-driven | `src/pumpgrok/replay/sources.py` | partial |
| `src/pumpgrok/datafeed/watchset.py` | store | event-driven | `src/pumpgrok/events/sources.py` | partial |
| `src/pumpgrok/datafeed/readonly.py` | service | request-response | `src/pumpgrok/tools/onchain/rpc.py` | partial |
| `src/pumpgrok/datafeed/bridge.py` | service | event-driven | `src/pumpgrok/events/bus.py` and `src/pumpgrok/events/models.py` | partial |
| `src/pumpgrok/datafeed/portal.py` | service | streaming | none; see source supervisor and RPC seams | none |
| `src/pumpgrok/datafeed/logs.py` | service | streaming | none; see event decoder and source supervisor | none |
| `src/pumpgrok/datafeed/resync.py` | service | event-driven | `src/pumpgrok/events/sources.py` | partial |
| `src/pumpgrok/datafeed/fallback.py` | service | request-response | `src/pumpgrok/tools/onchain/rpc.py` | partial |
| `src/pumpgrok/datafeed/price.py` | provider | request-response | `src/pumpgrok/replay/sources.py` | partial |
| `src/pumpgrok/datafeed/graduation.py` | service | event-driven | `src/pumpgrok/execution/paper_adapter/marks.py` | partial |
| `src/pumpgrok/datafeed/marks.py` | service | event-driven | `src/pumpgrok/execution/paper_adapter/marks.py` | partial |
| `src/pumpgrok/replay/live_recorder.py` | service | streaming/file-I/O | `src/pumpgrok/replay/fixtures.py` | partial |
| `src/pumpgrok/replay/import_data.py` | utility | file-I/O/transform | `src/pumpgrok/replay/fixtures.py` | partial |
| `src/pumpgrok/replay/trim.py` | utility | file-I/O/transform | `src/pumpgrok/replay/fixtures.py` | partial |
| `src/pumpgrok/execution/fees.py` | model | transform | same file | exact |
| `src/pumpgrok/execution/paper_factory.py` | provider | request-response | `src/pumpgrok/execution/paper_adapter/adapter.py` | partial |
| `src/pumpgrok/execution/entry_hook.py` | service | request-response | `src/pumpgrok/execution/paper_adapter/adapter.py`, `src/pumpgrok/tools/onchain/curve_layout.py` | partial |
| `docs/CURVE_LAYOUT_PROBE.md` and probe artifacts | config/evidence | file-I/O | `docs/CURVE_LAYOUT_PROBE.md`, `scripts/probe_curve_layout.py` | partial |
| `CHANGELOG.md` | config/documentation | file-I/O | same file | exact |
| `tests/tools/onchain/test_curve_layout.py`, `test_pump_events.py`, `test_price_gate.py`, `test_event_decode_status.py`, `test_probe_record.py`; `tests/desk/test_probe_pump_accounts.py` | test | transform/request-response | `tests/tools/onchain/test_pump_events.py`, `tests/execution/test_curve_source_gate.py` | partial |
| `tests/datafeed/test_watchset.py`, `test_mintbook.py`, `test_bridge.py`, `test_feed.py`, `test_readonly.py` | test | event-driven/streaming | `tests/events/test_sources.py`, `tests/degradation/test_event_source_faults.py` | partial |
| `tests/datafeed/test_price_source.py`, `test_graduation.py`, `test_marks.py` | test | event-driven/request-response | `tests/execution/test_curve_source_gate.py`, `tests/replay/test_clock.py` | partial |
| `tests/replay/test_live_recorder.py`, `test_live_recorder_manifest_strings.py` | test | streaming/file-I/O | `tests/replay/test_fixture_manifest.py` | partial |
| `tests/execution/test_fee_model_v2.py`, `test_paper_factory.py`, `test_entry_gate_hook.py` | test | request-response/transform | `tests/execution/test_curve_source_gate.py` | partial |
| `tests/events/test_models_v4_kinds.py` | test | event-driven | same file | exact |
| `tests/safety/test_import_graph_no_live.py`, existing replay pins and execution characterization tests | test | file-I/O/transform | same existing tests | exact |

Roadmap also names existing tests under `tests/docs`, `tests/execution`, `tests/characterization/execution`, and `tests/cli/test_review_trade_prices.py`: retain them as acceptance/regression surfaces, rather than presuming every one must be edited. Path ownership follows the last matching rule of `ownership.yaml`; in particular onchain belongs to bot-05-rug, execution to its applicable seat rules, replay and generic new `datafeed` under source default to bot-02-risk, planning to bot-00-chief, and CHANGELOG to bot-09-journal. Resolve exact path ownership, independent receipts and cross-seat handoffs before edits.

## Pattern Assignments

### Curve decode, event decode, and price gate

**Targets:** `curve_layout.py`, `pump_events.py`, curve/decoder/probe/gate tests. **Analogs:** the same tracked decoder files and `tests/tools/onchain/test_pump_events.py`.

`curve_layout.py:57-80` currently unpacks a fixed account size and rejects malformed flags and zero pricing reserves:

```python
if len(data) != CURVE_ACCOUNT_SIZE:
    raise CurveDecodeError(f"curve account size {len(data)} != ASSUMED {CURVE_ACCOUNT_SIZE}")
try:
    (_, vsol, vtok, rsol, rtok, supply, complete) = _CURVE_STRUCT.unpack(data)
except struct.error as exc:
    raise CurveDecodeError(f"curve account unpack failed: {type(exc).__name__}") from exc
if complete not in (0, 1):
    raise CurveDecodeError(f"curve completion flag not boolean: {complete!r}")
```

**Do not copy its field order or its current permissive source predicate:** `curve_layout.py:153-162` currently allows anything except unverified `rpc`. Replace with the specified token-first 49/166-byte decode, discriminator validation and explicit allowed/verified source decision. Preserve integer reserve types, typed decode failures, and ASSUMED until human review. `pump_events.py:1-16,50-73` documents five typed event layouts, integer chain amounts and explicit malformed/unknown errors. Existing tests `test_pump_events.py:214-233` parameterize all five, trailing bytes and every truncation. `tests/execution/test_curve_source_gate.py:116-145,165-168` distinguishes accepted and confirming entry snapshots and the buy-only gate; keep protective exits possible. `docs/CURVE_LAYOUT_PROBE.md:1-8` presently records ASSUMED and the exact no-account/no-RPC error; a successful probe alone is not human verification.

### Feed, recovery, and watchset

**Targets:** `datafeed/{events,mintbook,watchset,readonly,portal,logs,resync,fallback}.py`. **Analogs:** `events/sources.py:63-140`, `core/ratelimit.py:17-48`, `tools/onchain/rpc.py:88-188`, `tools/onchain/pump_events.py:1-16`.

Supervisor already separates source state from socket code; preserve explicit failure and resync transitions:

```python
# src/pumpgrok/events/sources.py:103-138
self._last_frame_at = ts
if self._healthy_since is None:
    self._healthy_since = ts
if self._status is not SourceStatus.live:
    self._status = SourceStatus.live
# On failure:
self._status = SourceStatus.disconnected
# On resync:
self._held_mints = tuple(held_mints)
self._status = SourceStatus.resyncing
```

Use `note_frame`, `note_failure`, `next_delay_s` and `resync`, not a second supervisor. It deliberately treats a never-framed source as live (`sources.py:91-101`), so a price provider **must additionally fail closed** until it has a fresh usable price; do not mistake that initial state for proof of connectivity. Watchset pinning, overflow policy, signature dedupe, gap emission, and actual WebSocket subscriptions have no equivalent implementation in these analogs.

The existing rate limiter serializes callers and injects its clock (`core/ratelimit.py:23-48`):

```python
async with self._lock:
    while True:
        delay = self.delay_for_next()
        if delay <= 0:
            self.tokens -= 1.0
            return waited
        waited += delay
        await self._clock.sleep(delay)
```

A token bucket with bursts is **not automatically proof** of the required 30 calls in every rolling 10 seconds; select or implement semantics that satisfy the stated provider limit and test the boundary. `RpcClient.call` retries via `sleep=self._clock.sleep` and strips endpoint/header/exception details from final errors (`rpc.py:151-188`), but accepts an arbitrary method: it is **not a read-only allowlist**. Enforce the phase's read-only RPC and PumpPortal method boundary before transport and assert sent frames/methods in tests. No signing or transaction send path.

### Bus bridge

**Target:** `datafeed/bridge.py`; **analogs:** `events/models.py:20-53,137-171`, `events/bus.py:144-151`.

```python
# src/pumpgrok/events/models.py:36-53
PRIORITY_BY_KIND = {
    EventKind.kill_switch: 0,
    EventKind.halt: 0,
    # ... other existing kinds ...
    EventKind.token_created: 1,
    EventKind.migration: 1,
    EventKind.trade: 1,
    EventKind.curve_tick: 2,
    EventKind.mark: 2,
}


# src/pumpgrok/events/bus.py:144-151
async def publish(self, event: Event) -> None:
    if self._closing.is_set():
        raise EventBusClosed()
    priority = priority_of(event.kind)
    if priority == 2:
        self._publish_p2(event)
        return
    await self._publish_durable(event, priority)
```

The mapping above is an excerpt, not a replacement for the total catalog. Construct the frozen `Event` with existing `kind`, `entity_id`, `payload`, `occurred_at`; its ID is derived from canonical data and timestamp (`models.py:137-161`), not the chain signature. Thus use a separate signature-deduplication mechanism where required. P2 coalesces; P0/P1 are routed through durable publishing; do not equate event-bus ID dedupe with exactly-once feed recovery. No contract surface changes in this phase.

### Live price, marks, and paper adapter

**Targets:** `datafeed/{price,graduation,marks}.py`, `execution/{fees,paper_factory,entry_hook}.py`, existing paper mixins as required. **Analogs:** `replay/sources.py:46-85`, `execution/paper_adapter/models.py:20-35`, `execution/paper_adapter/adapter.py:41-75`, `execution/paper_adapter/marks.py:102-195`, `execution/fees.py:29-62`.

```python
# src/pumpgrok/execution/paper_adapter/models.py:20-35
mint: str
s_lamports: int
t_units: int
complete: bool = False
source: str = "fixture"
slot: int | None = None
ts: float | None = None


class PriceSource(Protocol):
    async def curve(self, mint: str) -> CurveSnapshot | None: ...
```

`FixtureCurveSource` returns `None` without a tick at/before injected `clock.now()` and otherwise returns a timestamped integer `CurveSnapshot` (`replay/sources.py:51-80`). Follow the same seam for live, additionally requiring connection and freshness. A completed curve refuses entry; gap holds and timeout zero-marks must follow the phase criteria, not be conflated. `mark_open_positions` reads all held prices before appending a combined mark and returns immediately if flat (`marks.py:158-187`); reuse that accounting path and schedule via injected Clock, with no timer while flat and every held mint marked within 60 seconds.

`PaperAdapter.__init__` already injects `clock`, `rng`, `fees`, and `price_source`, defaulting `fees` to `FeeModel()` (`adapter.py:44-68`). Keep v1 default and preserve the existing methods' integer floor arithmetic (`fees.py:37-62`); v2 must be explicitly selected. Factory and hook stay on paper-only imports. Existing entry source checking must cover both accepted and confirming reads; do not add a live-execution dependency or wallet requirement.

### Recorder, manifests, import and trim

**Targets:** `replay/{live_recorder,import_data,trim}.py`, recorder tests. **Analog:** `replay/fixtures.py:26-55,83-147,168-185`; tests `tests/replay/test_fixture_manifest.py:28-88`. Note `replay/recorder.py` records LLM outcomes, not market streams; it is not a complete live-recorder implementation.

```python
# src/pumpgrok/replay/fixtures.py:110-129
manifest = _load_manifest(dataset_dir)
contents: dict[str, bytes] = {}
for name, expected in sorted(manifest.sha256.items()):
    target = dataset_dir / name
    if target.is_symlink():
        raise CorruptFixture("listed file is a symlink", file=name)
    if not target.is_file():
        raise CorruptFixture("listed file is missing", file=name)
    data = target.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise CorruptFixture("sha256 does not match manifest", file=name)
    contents[name] = data
```

Keep the verifier's exact manifest schema (`dataset`, string UTC bounds, integer `seed_hint`, `sources: dict[str, str]`, `sha256`, `notes`), list **every** JSONL including `gaps.jsonl`, digest the exact final bytes and parse the verified bytes rather than rereading. `load_dataset` requires `events.jsonl`, UTC `ts_utc`, and non-decreasing timestamps; replay ticks use `kind: "tick"`, mint, integer `S`/`T`, complete and source (`test_fixture_manifest.py:49-64`). Seal a ticks-only event stream, preserve gap records separately, and distinguish a recoverable torn final line from non-tail or otherwise real corruption; the loader currently rejects any malformed line. Existing loader is an integrity analog, **not** a ready-made append/recovery/sealing implementation.

### Tests and deterministic clock

Use fixtures and fault injection, not real network. `tests/degradation/test_event_source_faults.py:21-46` combines `FaultyEventSource(FaultMode.TIMEOUT)`, `FixtureClock`, seeded `make_rng`, and source-state assertions; extend the behavior at the feed seam to prove reconnect, gaps and no duplicate signature. `tests/replay/test_clock.py:51-64` schedules sleep, yields to the loop, and advances the fixture clock: assert mark deadline, staleness boundaries, and absence of flat timers without wall-clock sleeps. The only allowed production time source is `replay/clock.py`; its `Clock` protocol at lines 24-33 offers `now`, `monotonic`, `utc_iso`, `sleep`, and `timeout`, and `FixtureClock.advance_to` fires due timers in order (lines 87-110).

`tests/replay/test_fixture_manifest.py:68-88` synthesizes a real manifest, tampers the bytes, and verifies both digest mismatch and malformed-but-correctly-digested JSONL fail before ledger creation. Extend this approach for sealing, string fields, sorted ticks, listed gap files, final torn tail and non-tail corruption. `tests/execution/test_curve_source_gate.py:116-145,165-168` scripts source changes across buy stages and preserves sells. Characterize existing fee v1 and both pinned datasets before adding behavior; Phase 13 CHANGELOG records both before/after hashes, without altering pins.

## Shared Patterns

- **Clock and retries:** inject `Clock` everywhere; never use direct time or production `asyncio.sleep` outside `replay/clock.py`. SourceSupervisor is lifecycle state only and does not open sockets.
- **Money:** reserve quantities, fees, and ledger amounts use integer base units; preserve `FeeModel` floors and use Decimal only where existing ratios require it.
- **Fail closed:** decoder validates bytes, read-only boundary allowlists methods, stale/disconnected/never-framed live prices return `None`, unverified/unknown source entries refuse. Do not block protective exits by blindly applying an entry gate to sells.
- **Event handling:** use the single existing `EventKind`/`Event` catalog and bus priority routing; feed signatures need their own dedupe and reconnect gap evidence.
- **Replay integrity:** reject unlisted JSONL and digest mismatch, prohibit symlinked listed data, and consume bytes already verified; maintain chronological tick order.
- **Safety and ownership:** no live adapter imports in paper composition, no keys/signing/sends, no contract surface edits. TDD RED/GREEN and independent seat receipts are implementation work, not claims made by this map.

## No Analog Found

| File or behavior | Role | Data Flow | Reason |
|---|---|---|---|
| `datafeed/portal.py`, `datafeed/logs.py` | service | streaming | No existing matching PumpPortal/logsSubscribe transport identified; source supervisor does not open sockets. |
| Bounded held-pinned watchset, reconnect signature dedupe and gap tracking | store/service | event-driven | Existing supervisor tracks held mints and cursor but does not implement bounded subscription policy or feed dedupe. |
| `replay/live_recorder.py` sealing and torn-tail recovery | service | streaming/file-I/O | Existing verifier is read-only; LLM recorder is a different data flow. |
| `replay/import_data.py`, `replay/trim.py` | utility | file-I/O | Fixture verifier is only a partial analogy; no equivalent complete import/trim found in examined sources. |

## Metadata

**Analog search scope:** `src/pumpgrok/events`, `replay`, `execution`, `core/ratelimit.py`, `tools/onchain`, `tests/events`, `tests/degradation`, `tests/execution`, `tests/replay`, `tests/tools/onchain`, and roadmap/requirements/ownership. Analog paths were checked against `git ls-files`; all named existing source/test/doc analogs are tracked. No implementation tests, builds, formatting, or verification were run. **Pattern extraction date:** 2026-11-10.
