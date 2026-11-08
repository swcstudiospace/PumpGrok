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

`event_id` is the first 32 hex characters of sha256 over `canonical_json` of `kind`, `entity_id`, `payload`, and `occurred_at`. `correlation_id` is excluded before hashing. The id is not a ULID. Hashing kind, entity_id, and payload alone is forbidden: two kill_switch events with payload `{"reason":"daily_loss"}` and different `occurred_at` values are different ids, and both deliver. A second delivery of the same id is the only dedup.

Money fields are strict `int`. A float payload raises `TypeError`. A float lamports field is rejected by the model.

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

`PAPER_LEDGER_PATH` is imported so a later store can refuse it. This package does not open that path, does not open sqlite, and does not open a socket.
