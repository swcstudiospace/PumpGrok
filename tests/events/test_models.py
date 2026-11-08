"""Frozen event catalog, derived ids, and integer money."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from typing import Any

import pytest
from pydantic import ValidationError

from pumpgrok.events.bus import EventBus
from pumpgrok.events.constants import (
    BACKOFF_FACTOR,
    BACKOFF_INITIAL_S,
    BACKOFF_JITTER_S,
    BACKOFF_MAX_S,
    EVENTS_SIDECAR_PATH,
    P0_DEDUP_TTL_S,
    P0_LANE_CAP,
    P1_DEDUP_TTL_S,
    P1_LANE_CAP,
    P2_COALESCE_CAP,
    P2_DEBOUNCE_S,
    RETRY_ATTEMPTS,
    STABLE_S,
    STALE_AFTER_S,
)
from pumpgrok.events.models import PRIORITY_BY_KIND, Event, EventKind, priority_of
from pumpgrok.replay.clock import FixtureClock


def _event(**overrides: object) -> Event:
    body: dict[str, object] = {
        "kind": EventKind.kill_switch,
        "entity_id": "desk",
        "payload": {"reason": "daily_loss"},
        "occurred_at": "2026-01-01T00:00:00Z",
    }
    body.update(overrides)
    return Event(**body)  # type: ignore[arg-type]


def test_event_id_is_stable_32_hex_and_ignores_correlation_id() -> None:
    left = _event(correlation_id="corr-a")
    right = _event(
        correlation_id="corr-b",
        payload={"reason": "daily_loss", "correlation_id": "inner"},
    )
    assert left.event_id == right.event_id
    assert len(left.event_id) == 32
    assert all(ch in "0123456789abcdef" for ch in left.event_id)


def test_occurred_at_is_required_and_changes_the_id() -> None:
    with pytest.raises(ValidationError):
        Event(kind=EventKind.kill_switch, entity_id="desk", payload={"reason": "daily_loss"})
    early = _event(occurred_at="2026-01-01T00:00:00Z")
    later = _event(occurred_at="2026-01-01T00:00:01Z")
    assert early.event_id != later.event_id


def test_caller_mutation_after_construction_does_not_change_event_or_id() -> None:
    original: dict[str, Any] = {
        "reason": "daily_loss",
        "legs": [{"qty": 1}],
        "meta": {"tags": ["a"]},
    }
    event = _event(payload=original)
    before = event.event_id
    original["reason"] = "changed"
    original["extra"] = 1
    original["meta"]["tags"].append("b")
    original["legs"][0]["qty"] = 9
    expected = {"reason": "daily_loss", "legs": [{"qty": 1}], "meta": {"tags": ["a"]}}
    assert event.payload == expected
    assert event.event_id == before
    assert _event(payload=expected).event_id == before


def test_correlation_id_inside_a_list_does_not_change_the_id() -> None:
    left = _event(payload={"legs": [{"correlation_id": "corr-a", "qty": 1}]})
    right = _event(payload={"legs": [{"correlation_id": "corr-b", "qty": 1}]})
    assert left.event_id == right.event_id
    assert left.event_id != _event(payload={"legs": [{"qty": 2}]}).event_id


def test_equal_nested_payloads_with_different_insertion_order_share_an_id() -> None:
    left = _event(payload={"outer": {"a": 1, "b": {"x": 1, "y": 2}}, "z": [{"p": 1, "q": 2}]})
    right = _event(payload={"z": [{"q": 2, "p": 1}], "outer": {"b": {"y": 2, "x": 1}, "a": 1}})
    assert left.event_id == right.event_id


def test_float_payload_raises_type_error_and_float_lamports_is_rejected() -> None:
    with pytest.raises(TypeError):
        _event(payload={"fee": 1.5})
    with pytest.raises(ValidationError):
        _event(lamports=1.5)


def test_priority_is_total_and_not_a_caller_field() -> None:
    assert set(PRIORITY_BY_KIND) == set(EventKind)
    assert "tick" not in EventKind.__members__
    assert [priority_of(kind) for kind in EventKind if priority_of(kind) == 2] == [
        priority_of(EventKind.curve_tick),
        priority_of(EventKind.mark),
    ]
    assert priority_of(EventKind.kill_switch) == 0
    assert priority_of(EventKind.trade) == 1
    with pytest.raises(ValidationError):
        _event(priority=0)  # type: ignore[call-arg]


def test_model_is_frozen() -> None:
    event = _event(lamports=1)
    with pytest.raises(ValidationError):
        event.entity_id = "other"  # type: ignore[misc]


def test_named_lane_constants() -> None:
    assert P0_LANE_CAP is None
    assert P1_LANE_CAP == 1000
    assert P2_COALESCE_CAP == 1
    assert STALE_AFTER_S == 120.0
    assert STABLE_S == 30.0
    assert RETRY_ATTEMPTS == 5
    assert P0_DEDUP_TTL_S == 86400
    assert P1_DEDUP_TTL_S == 300
    assert P2_DEBOUNCE_S == 1.0
    assert BACKOFF_INITIAL_S == 1.0
    assert BACKOFF_FACTOR == 2
    assert BACKOFF_MAX_S == 16.0
    assert BACKOFF_JITTER_S == 1.0
    assert EVENTS_SIDECAR_PATH.as_posix() == "var/desk/events.sqlite"


def test_import_does_not_open_sqlite_or_a_socket() -> None:
    probe = (
        "import socket, sqlite3\n"
        "opened = []\n"
        "_connect = sqlite3.connect\n"
        "def _wrap_connect(*args, **kwargs):\n"
        "    opened.append('sqlite')\n"
        "    return _connect(*args, **kwargs)\n"
        "sqlite3.connect = _wrap_connect\n"
        "_socket = socket.socket\n"
        "class _Wrap(_socket):\n"
        "    def __init__(self, *args, **kwargs):\n"
        "        opened.append('socket')\n"
        "        super().__init__(*args, **kwargs)\n"
        "socket.socket = _Wrap\n"
        "import pumpgrok.events\n"
        "import pumpgrok.events.bus\n"
        "import pumpgrok.events.constants\n"
        "assert opened == [], opened\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


async def test_two_kill_switch_events_with_different_occurred_at_both_deliver() -> None:
    early = _event(occurred_at="2026-01-01T00:00:00Z")
    later = _event(occurred_at="2026-01-01T00:00:01Z")
    assert early.event_id != later.event_id
    delivered: list[str] = []

    async def handler(event: Event) -> None:
        delivered.append(event.event_id)

    bus = EventBus(clock=FixtureClock(0.0), handler=handler, dlq=lambda _event: None)
    await bus.publish(early)
    await bus.publish(later)
    await bus.start()
    await _yield()
    assert delivered == [early.event_id, later.event_id]


async def _yield() -> None:
    await asyncio.sleep(0)
    await asyncio.sleep(0)
