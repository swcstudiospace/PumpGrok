# Events and Grok

This library is not wired into the supervisor. No gateway is built in this phase.
There is no mainnet router, no devnet client, and no book size in this document.

## Kind table

`class EventKind` lives only in `src/pumpgrok/events/models.py`. There is no `tick` member.

| Kind | Priority | Lane rule |
| --- | --- | --- |
| kill_switch | 0 | never drop |
| halt | 0 | never drop |
| exit_signal | 0 | never drop |
| risk_veto | 0 | never drop |
| token_created | 1 | overflow to DLQ |
| migration | 1 | overflow to DLQ |
| trade | 1 | overflow to DLQ |
| position_opened | 1 | overflow to DLQ |
| position_closed | 1 | overflow to DLQ |
| strategy_intent | 1 | overflow to DLQ |
| curve_tick | 2 | latest-wins coalesce |
| mark | 2 | debounce coalesce |

## Priority function

`priority_of(kind)` returns 0, 1, or 2 from the table above. It is a total function of `EventKind`. The event model has no priority field a caller can set. A kind missing from the table raises `KeyError`.

P0 is unbounded (`P0_LANE_CAP` is `None`). P1 overflow calls an injected sink. Each P0 and P1 lane is FIFO per `(priority, entity_id)`, and lanes run concurrently, so a slow P1 handler does not block P0. P2 keeps one coalesced event per key.

## Derived id

`occurred_at` is a required `str`. It is not optional and it is not defaulted. A missing `occurred_at` raises `ValidationError`.

`event_id` is the first 32 hex characters of sha256 over `canonical_json` of `kind`, `entity_id`, `payload`, and `occurred_at`. Before hashing, `correlation_id` is removed from the payload at every depth, including inside lists. The id is not a ULID. Hashing kind, entity_id, and payload alone is forbidden: two kill_switch events with payload `{"reason":"daily_loss"}` and different `occurred_at` values are different ids, and both deliver. A second delivery of the same id is the only dedup.

Money fields are strict `int`. A float payload raises `TypeError`. A float lamports field is rejected by the model.

## Frozen payload

- After construction, `event.payload` is a `FrozenPayload`, a read-only `Mapping`. It has no mutator methods and no item assignment. A write raises `TypeError`.
- Nested dicts become `FrozenPayload`. Nested lists become tuples. This applies recursively.
- `Event(...)` accepts a dict or any `Mapping` and freezes its own copy. Later changes to the caller's objects do not reach the event or its id.
- `model_dump()` and `model_dump(mode="json")` return plain dicts and lists. The sidecar stores the JSON form. Loading a row rebuilds a frozen payload.
- `derive_event_id` output is unchanged for identical logical payloads.

## Bus lifecycle

Accept (P0 and P1, with a store):

- One transaction writes the dedup row and the pending row when the event is queued. A full P1 lane (`P1_LANE_CAP`) takes a different path: one transaction writes the dedup row and a DLQ row with reason `overflow`. P0 has no cap, so P0 never overflows.
- If that transaction raises, `publish` raises the same error. The event is not remembered, not queued, and not saved, so a retried publish is not suppressed.
- Without a store, the same dedup and overflow rules apply in memory only.

Completion (P0 and P1):

- Success is one transaction: the applied row is written and the pending row is deleted.
- Failure is one transaction: a poison failure, or a transient failure on the RETRY_ATTEMPTS-th attempt, writes the DLQ row and deletes the pending row.
- A DLQ replay moves the row to pending. The next `recover()` runs it once, then marks it applied.
- A P0 or P1 event that is queued or in flight keeps its pending row until one of these transactions commits.

P2 (with a store):

- Accept writes nothing to the sidecar. There is no dedup row and no pending row. P2 dedup ids are kept in memory only, from acceptance until delivery or replacement.
- Success deletes any pending row for the id and writes no applied row.
- Failure writes a DLQ row and deletes the pending row.
- A P2 pending row exists only after shutdown (see below).

Retries:

- A transient failure waits on the injected clock before the next attempt. The wait is `min(BACKOFF_INITIAL_S * BACKOFF_FACTOR**step, BACKOFF_MAX_S)` plus a draw from the seeded rng times `BACKOFF_JITTER_S`. The handler runs at most RETRY_ATTEMPTS times.
- The rng draw is recorded in `bus.jitters` before the wait starts.

P2 latest-wins:

- Each key holds at most one queued event (`P2_COALESCE_CAP`). A newer event replaces it, and the replaced event is dropped, not sent to the DLQ.
- Handler calls for one key are serialized by a key lock. The lock is held only around handler calls. Retry backoff holds no lock, so a newer publish for the same key is never delayed by a retry sleep.
- When a retrying P2 event wakes and the key's generation has changed, the bus stops retrying. The stale event is sent to the DLQ with reason `transient`. A newer value runs as soon as the lock is free, so it can run while the stale event is still in its backoff wait.
- `mark` waits `P2_DEBOUNCE_S` on the clock before delivery. `curve_tick` does not wait.
- A delivered P2 id leaves the in-memory dedup set, so it can publish again. The design sets no P2 TTL.

Recovery:

- `recover()` runs pending rows in seq order. Call it on a fresh bus before publishing.
- For a P0 or P1 row that has an applied mark, the handler is skipped and the row is completed.
- For any other P0 or P1 row, and for every P2 row, the handler runs under the retry rules above. Success and failure then follow the completion rules for that priority.

## Shutdown

`shutdown()` is bounded by `SHUTDOWN_TIMEOUT_S`, measured on the injected clock. It runs in this order:

1. The bus closes. From then on `publish()` and `start()` raise `EventBusClosed`. Drain loops stop taking new events from their lanes.
2. Every wait that is not inside a handler call is cancelled. These are P2 debounce sleeps and retry-backoff sleeps for P0, P1, and P2. Their events stay queued or pending. Nothing is applied and nothing goes to the DLQ.
3. The bus waits up to `SHUTDOWN_TIMEOUT_S` for running handler calls to return. A call that returns completes normally: applied on success, DLQ on failure.
4. Handler calls still running at the bound are cancelled. Their events stay pending. Cancellation is not a handler failure and writes no DLQ row. A handler that catches the cancellation and returns normally counts as completed.
5. The bus waits up to `SHUTDOWN_TIMEOUT_S` more for its worker tasks to finish. A task still running after that keeps running, and its event stays unsettled. Then every unsettled P2 event (claimed and retrying or in flight, or still queued) is written to pending in one transaction. P0 and P1 need no write at this step, because their pending rows were written at accept.
6. `shutdown()` is idempotent. A second call returns after the first has finished. `start()` after shutdown raises `EventBusClosed`.

Without a store, shutdown writes nothing. Queued events are lost.

## Crash path

A crash is a process exit with no `shutdown()` call. Nothing is saved at the crash, and nothing is sent to the DLQ.

- A P0 or P1 event accepted before the crash has a pending row. `recover()` on a new bus on the same sidecar runs it once. A second `recover()` does not run it again.
- A P0 or P1 event whose handler finished but whose completion transaction did not commit is still pending. It runs again. A handler must be idempotent for that window.
- P2 values queued or in flight at a crash are lost, along with the in-memory P2 dedup set. P2 persists only at shutdown, so a crash drops the latest-wins P2 ticks that were not yet settled. Consumers of `curve_tick` and `mark` must accept that gap.

## Dedup and applied semantics

- A P0 or P1 republish after its dedup TTL is accepted as a new event. Pending rows are keyed by event id, so a second accept while the first is still pending shares one row.
- The applied mark is keyed by event id. If a republish after the TTL is pending at a crash and an applied row already exists for its id, recovery completes it without running the handler.

## Source reconnect

- Each failed connection advances the backoff step. The delay is `min(BACKOFF_INITIAL_S * BACKOFF_FACTOR**exponent, BACKOFF_MAX_S)` plus jitter in [0, BACKOFF_JITTER_S). The exponent is capped where the uncapped delay first reaches BACKOFF_MAX_S, so a long outage never raises and the delay stays at BACKOFF_MAX_S plus jitter.
- A healthy span starts at the first good frame after a failure. If a failure arrives STABLE_S or more after that span started, the failure resets the step to zero instead of advancing it, so the next delay is BACKOFF_INITIAL_S plus jitter.

## Constants

Defined in `src/pumpgrok/events/constants.py`. The bus reads these names. It does not inline the numbers.

| Name | Value |
| --- | --- |
| P0_LANE_CAP | None |
| P1_LANE_CAP | 1000 |
| P2_COALESCE_CAP | 1 |
| STALE_AFTER_S | 120.0 |
| STABLE_S | 30.0 |
| RETRY_ATTEMPTS | 5 |
| P0_DEDUP_TTL_S | 86400 |
| P1_DEDUP_TTL_S | 300 |
| P2_DEBOUNCE_S | 1.0 |
| BACKOFF_INITIAL_S | 1.0 |
| BACKOFF_FACTOR | 2 |
| BACKOFF_MAX_S | 16.0 |
| BACKOFF_JITTER_S | 1.0 |
| SHUTDOWN_TIMEOUT_S | 5.0 |
| EVENTS_SIDECAR_PATH | var/desk/events.sqlite |

`PAPER_LEDGER_PATH` is never opened. `EventStore` compares its path with `PAPER_LEDGER_PATH` and raises `SidecarRefusal` before it connects. The package opens one sqlite file, the sidecar store at `EVENTS_SIDECAR_PATH`, which is the default for `events.sidecar_path`. The store holds pending rows, applied marks, P0 and P1 dedup records with their TTLs, DLQ rows, and the source cursor. The package opens no socket.
