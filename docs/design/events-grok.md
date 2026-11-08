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

P0 is unbounded (`P0_LANE_CAP` is `None`) and is dispatched on its own task so a slow P1 handler cannot block it. P1 overflow calls an injected sink. P2 keeps one coalesced event per key.

## Derived id

`occurred_at` is a required `str`. It is not optional and it is not defaulted. A missing `occurred_at` raises `ValidationError`.

`event_id` is the first 32 hex characters of sha256 over `canonical_json` of `kind`, `entity_id`, `payload`, and `occurred_at`. Before hashing, `correlation_id` is removed from the payload at every depth, including inside lists. The id is not a ULID. Hashing kind, entity_id, and payload alone is forbidden: two kill_switch events with payload `{"reason":"daily_loss"}` and different `occurred_at` values are different ids, and both deliver. A second delivery of the same id is the only dedup.

The payload is deep-copied when the event is constructed. Later changes to the caller's objects do not change the event or its id.

Money fields are strict `int`. A float payload raises `TypeError`. A float lamports field is rejected by the model.

## Bus lifecycle

- An event whose handler is running stays in an in-flight slot until the handler returns. `shutdown()` saves in-flight and queued events to pending. `recover()` runs each saved event that is not marked applied.
- An event is marked applied only after its handler returns normally.
- A poison failure, or a transient failure on the RETRY_ATTEMPTS-th attempt, sends the event to the DLQ unapplied. A DLQ replay moves the row to pending. The next `recover()` runs it once, and it is marked applied after that.
- A transient failure waits on the injected clock before the next attempt. The wait is `min(BACKOFF_INITIAL_S * BACKOFF_FACTOR**step, BACKOFF_MAX_S)` plus a draw from the seeded rng times `BACKOFF_JITTER_S`. The handler runs at most RETRY_ATTEMPTS times.
- A P0 or P1 event is recorded in the sidecar dedup table when it is accepted, with a TTL of P0_DEDUP_TTL_S or P1_DEDUP_TTL_S. A duplicate publish is suppressed until that TTL expires. A P1 event that overflows its lane (P1_LANE_CAP) is recorded the same way and sent to the DLQ with reason `overflow`, so a DLQ replay runs it exactly once. P0 has no cap, so P0 never overflows.
- P2 is latest-wins. Each key holds at most one queued event (P2_COALESCE_CAP). A newer event replaces it, and the replaced event is dropped, not sent to the DLQ. A running handler is never cancelled. A newer P2 event waits for the running one, then delivers the newest queued value once. `mark` waits P2_DEBOUNCE_S on the clock before delivery; `curve_tick` does not.
- P2 ids are kept in memory only, from acceptance until delivery or replacement. The design sets no P2 TTL, so a delivered P2 id leaves the dedup set and can publish again.

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
| EVENTS_SIDECAR_PATH | var/desk/events.sqlite |

`PAPER_LEDGER_PATH` is never opened. `EventStore` compares its path with `PAPER_LEDGER_PATH` and raises `SidecarRefusal` before it connects. The package opens one sqlite file, the sidecar store at `EVENTS_SIDECAR_PATH`, which is the default for `events.sidecar_path`. The store holds pending rows, applied marks, P0 and P1 dedup records with their TTLs, DLQ rows, and the source cursor. The package opens no socket.
