"""Deterministic drain parity. Does not rewrite fixtures or call verify."""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.events.drain import drain
from pumpgrok.events.models import Event, EventKind
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng

_SEED = 20260101
_SMOKE = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke" / "events.jsonl"


def _event(kind: EventKind, entity_id: str, n: int, occurred_at: str) -> Event:
    return Event(
        kind=kind,
        entity_id=entity_id,
        payload={"n": n},
        occurred_at=occurred_at,
    )


def _smoke_events() -> list[Event]:
    events: list[Event] = []
    for line in _SMOKE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        kind = EventKind.curve_tick if row["kind"] == "tick" else EventKind(row["kind"])
        payload = {
            key: value for key, value in row.items() if key not in {"kind", "mint", "ts_utc"}
        }
        events.append(
            Event(
                kind=kind,
                entity_id=str(row["mint"]),
                payload=payload,
                occurred_at=str(row["ts_utc"]),
            )
        )
    return events


def test_determinism() -> None:
    events = [
        _event(EventKind.trade, "mint-a", 1, "2026-01-01T00:00:00.000Z"),
        _event(EventKind.curve_tick, "mint-a", 2, "2026-01-01T00:00:01.000Z"),
        _event(EventKind.kill_switch, "desk", 3, "2026-01-01T00:00:02.000Z"),
    ]
    first = drain(events, FixtureClock(0.0), make_rng(_SEED))
    second = drain(events, FixtureClock(0.0), make_rng(_SEED))
    assert first == second
    assert bytes(first) == bytes(second)
    assert first.pending == 0
    assert second.pending == 0
    delivered = [row["event_id"] for row in json.loads(bytes(first))["deliveries"]]
    assert delivered == [event.event_id for event in events]
    again = drain(events + events, FixtureClock(0.0), make_rng(_SEED))
    assert again == first
    assert again.pending == 0


def test_smoke_trading() -> None:
    events = _smoke_events()
    assert len(events) == 5
    assert all(event.kind is EventKind.curve_tick for event in events)
    first = drain(events, FixtureClock(0.0), make_rng(_SEED))
    second = drain(events, FixtureClock(0.0), make_rng(_SEED))
    assert first == second
    assert first.pending == 0
    assert second.pending == 0
    delivered = [row["event_id"] for row in json.loads(bytes(first))["deliveries"]]
    assert delivered == list(dict.fromkeys(event.event_id for event in events))
    repeated = drain(events, FixtureClock(0.0), make_rng(_SEED))
    assert repeated == first
    assert len(repeated) == len(first)


def test_mark_flushes_after_debounce_and_superseded_mark_does_not_deliver() -> None:
    first_mark = _event(EventKind.mark, "mint-a", 1, "2026-01-01T00:00:00.000Z")
    second_mark = _event(EventKind.mark, "mint-a", 2, "2026-01-01T00:00:00.500Z")
    result = drain([first_mark, second_mark], FixtureClock(0.0), make_rng(_SEED))
    delivered = [row["event_id"] for row in json.loads(bytes(result))["deliveries"]]
    assert delivered == [second_mark.event_id]
    assert result.pending == 0
