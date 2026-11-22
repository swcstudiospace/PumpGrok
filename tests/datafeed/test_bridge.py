"""Bridge maps datafeed events onto the single EventKind catalog (MKT-05)."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.datafeed.bridge import publish, to_bus_event
from pumpgrok.datafeed.events import CurveTick, GapEvent
from pumpgrok.events.models import Event, EventKind

TS = "2026-11-21T00:00:00.000000Z"


def _tick() -> CurveTick:
    return CurveTick.model_validate(
        {
            "mint": "m1",
            "ts_utc": TS,
            "virtual_sol_reserves_lamports": 42_000_000_000,
            "virtual_token_reserves_units": 766_428_571,  # pragma: allowlist secret
            "real_sol_reserves_lamports": 12_000_000_000,
            "real_token_reserves_units": 500_000_000_000,
            "total_supply_units": 1_000_000_000_000,
            "complete": False,
        }
    )


def test_tick_maps_to_curve_tick_kind() -> None:
    event = to_bus_event(_tick())
    assert event.kind is EventKind.curve_tick
    assert event.entity_id == "m1"
    assert event.occurred_at == TS
    assert event.event_id  # derived


def test_gap_maps_to_gap_kind() -> None:
    gap = GapEvent.model_validate(
        {"mint": "m1", "ts_utc": TS, "reason": "timeout", "from_ts_utc": TS, "to_ts_utc": TS}
    )
    assert to_bus_event(gap).kind is EventKind.gap


def test_publish_uses_injected_publisher() -> None:
    seen: list[Event] = []
    event = publish(_tick(), seen.append)
    assert seen == [event]


def test_one_catalog() -> None:
    src = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"
    hits = [
        path for path in src.rglob("*.py") if "class EventKind" in path.read_text(encoding="utf-8")
    ]
    assert hits == [src / "events" / "models.py"]
