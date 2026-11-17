# 14-03 Summary: event wake path (EVT-08 second half, EVT-10)

## Done
- `SEAT_WAKES` (owner-confirmed matrix) and `EVENT_TIMERS` (risk 5 s, exit 15 s, journal 300 s) in `src/pumpgrok/supervisor/scheduler/wake.py`.
- `Supervisor(wake_mode="cadence"|"event")`; `on_event` is the EventBus handler. Cadence mode is unchanged; `SEAT_CADENCES` is untouched.
- Per-seat locks serialize one seat across event and timer paths.
- Drain parity (RISK): `tests/replay/test_event_drain_parity.py` 3 passed, 0 skipped, no edits needed.

## Verified (phase end)
- `tests/desk/test_event_wake.py` 34 passed; `tests/desk/test_event_mode_run_once.py` 3 passed.
- `tests/supervisor/test_scheduler.py` 7 passed (unchanged); `tests/replay/test_trading_smoke_pin.py` 5 passed (pins unchanged).
- `ruff check`, `ruff format --check`, `mypy` clean on the four changed source/test files.
- Full repo gates NOT run yet; they run at Phase 14 close.

## Deviations (planned scope, not closed here)
- The triggering event does not reach seat cycles; `SeatContext` carries only the seat id. Closed by 14-04 (event-cycle services).
- `settings.events.wake_mode` is still `Literal["cadence"]`, so `serve` and the CLI cannot select event mode yet. Closed by 14-07 (wake flag and doctor refusal).
- `run_once()` in event mode runs only the timed seats that are due; cadence still runs all ten.
- Event-only seats have `stale_cadence = inf`; staleness applies only to timed seats in event mode.

## Owner input recorded, not acted on
- Product direction (autonomous self-improvement, autonomous upgrade to live, $200 top-up in $20 increments) conflicts with D-11 and the live refusal; not applied. Sizing is a later-phase input.

## Owner decisions applied
- Wake matrix confirmed as drafted.
- Provenance: wake reads only verified replay provenance (proceed-verified-only).
- Breaker: queued-slot timeouts do not count as breaker failures (commit d625ef2). Also skips `cache.put_error` for queued timeouts; flagged for review.
