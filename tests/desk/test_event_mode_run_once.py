"""Event-mode run-once consumes bus events and wakes seats; cadence is default."""

from pumpgrok.cli.parsing import build_parser
from pumpgrok.events.models import Event, EventKind
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.scheduler.wake import dispatch


def test_wake_mode_defaults_to_cadence() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "--mode", "paper", "--once"])
    assert args.wake_mode is None


def test_wake_mode_event_selects_event() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "--mode", "paper", "--once", "--wake-mode", "event"])
    assert args.wake_mode == "event"


def test_run_once_dispatch_wakes_expected_seats() -> None:
    clock = FixtureClock()
    events = [
        Event(
            kind=EventKind.exit_signal,
            entity_id="pos-1",
            payload={"v": 1},
            occurred_at="2026-01-01T00:00:00.000000Z",
        )
    ]
    wakes = dispatch(events, clock=clock)
    assert [w.seat for w in wakes] == ["bot-06-exit"]
