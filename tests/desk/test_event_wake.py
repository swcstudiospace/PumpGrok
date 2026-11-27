"""Event mode wakes per SEAT_WAKES; cadence unchanged; unknown timer refuses."""

import pathlib

import pytest

from pumpgrok.events.models import Event, EventKind
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.scheduler.wake import (
    SEAT_WAKES,
    UnknownTimerError,
    assert_allowed_timers,
    dispatch,
    wakes_for,
)


def _event(kind: EventKind, entity: str = "e1") -> Event:
    return Event(
        kind=kind,
        entity_id=entity,
        payload={"v": 1},
        occurred_at="2026-01-01T00:00:00.000000Z",
    )


def test_seat_wakes_covers_every_kind() -> None:
    assert set(SEAT_WAKES) == set(EventKind)
    for seats in SEAT_WAKES.values():
        assert seats


def test_dispatch_wakes_exact_seats() -> None:
    wakes = dispatch([_event(EventKind.token_created)], clock=FixtureClock())
    assert [w.seat for w in wakes] == ["bot-01-scout", "bot-08-signal"]


def test_dispatch_is_deterministic() -> None:
    events = [_event(EventKind.trade, "a"), _event(EventKind.trade, "b")]
    first = dispatch(events, clock=FixtureClock())
    second = dispatch(events, clock=FixtureClock())
    assert [w.seat for w in first] == [w.seat for w in second]
    assert len(first) == 4


def test_wakes_for_known_kind() -> None:
    assert wakes_for(EventKind.gap) == ("bot-02-risk",)


def test_allowed_timers_pass_and_unknown_refuses() -> None:
    assert_allowed_timers(frozenset({"wake"}))
    with pytest.raises(UnknownTimerError):
        assert_allowed_timers(frozenset({"wake", "poll"}))


def test_cadence_path_does_not_import_wake() -> None:

    for name in ["supervisor.py", "serve.py", "replay_cycles.py"]:
        source = pathlib.Path(f"src/pumpgrok/supervisor/scheduler/{name}").read_text(
            encoding="utf-8"
        )
        assert "scheduler.wake" not in source
