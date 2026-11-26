"""All ten seat cycle bodies run on wakes with golden hashes."""

import hashlib
import json
from pathlib import Path

import pytest

from pumpgrok.core.idempotency import canonical_json
from pumpgrok.events.models import Event, EventKind
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.scheduler.event_cycles import (
    SEAT_BODIES,
    TEN_SEATS,
    event_typed_fields,
    run_cycle,
    run_wake,
)
from pumpgrok.supervisor.scheduler.wake import Wake, dispatch

SMOKE_GOLDEN_HASH = "e31e667ce4209036edac5f3f03f260ea317fa44d218e831babf494d661043f5e"


def _smoke_events() -> list[Event]:
    rows = [
        json.loads(line)
        for line in Path("tests/fixtures/replay/smoke/events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    events: list[Event] = []
    for row in rows:
        kind = EventKind.curve_tick if row["kind"] == "tick" else EventKind(row["kind"])
        payload = {k: v for k, v in row.items() if k not in {"kind", "mint", "ts_utc"}}
        events.append(
            Event(
                kind=kind,
                entity_id=str(row["mint"]),
                payload=payload,
                occurred_at=str(row["ts_utc"]),
            )
        )
    return events


def test_ten_bodies_present() -> None:
    assert len(TEN_SEATS) == 10
    assert set(SEAT_BODIES) == set(TEN_SEATS)


def test_unknown_seat_fails_loudly() -> None:
    event = Event(
        kind=EventKind.mark,
        entity_id="x",
        payload={"v": 1},
        occurred_at="2026-01-01T00:00:00.000000Z",
    )
    with pytest.raises(KeyError):
        run_cycle("bot-99-nope", Wake(seat="bot-99-nope", event=event), clock=FixtureClock())


def test_golden_hash_on_smoke() -> None:
    wakes = dispatch(_smoke_events(), clock=FixtureClock(0.0))
    results = run_wake(wakes, clock=FixtureClock(0.0))
    body = [{"seat": r.seat, "kind": r.kind, "entity_id": r.entity_id} for r in results]
    digest = hashlib.sha256(canonical_json({"results": body}).encode()).hexdigest()
    assert digest == SMOKE_GOLDEN_HASH


def test_one_wake_invokes_at_most_one_cycle_per_seat() -> None:
    event = Event(
        kind=EventKind.kill_switch,
        entity_id="desk",
        payload={"v": 1},
        occurred_at="2026-01-01T00:00:00.000000Z",
    )
    wakes = dispatch([event], clock=FixtureClock())
    assert len(wakes) == 1
    assert wakes[0].seat == "bot-06-exit"


def test_typed_fields_have_no_payload_passthrough() -> None:
    event = Event(
        kind=EventKind.trade,
        entity_id="mint-a",
        payload={"secret": "nope"},
        occurred_at="2026-01-01T00:00:00.000000Z",
    )
    fields = event_typed_fields(event)
    assert set(fields) == {"kind", "entity_id"}
    assert "secret" not in str(fields.values())
