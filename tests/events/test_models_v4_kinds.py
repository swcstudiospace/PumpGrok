"""One EventKind catalog. SourceStatus is not a second kind."""

from __future__ import annotations

from pathlib import Path

import pumpgrok.ledger.events as ledger_events
from pumpgrok.events.models import PRIORITY_BY_KIND, EventKind

_SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"


def test_event_kind_module_is_the_catalog() -> None:
    assert EventKind.__module__ == "pumpgrok.events.models"
    assert not hasattr(ledger_events, "EventKind")


def test_class_event_kind_appears_once() -> None:
    hits = [
        path for path in _SRC.rglob("*.py") if "class EventKind" in path.read_text(encoding="utf-8")
    ]
    assert hits == [_SRC / "events" / "models.py"]


def test_priority_map_matches_members() -> None:
    assert set(PRIORITY_BY_KIND) == set(EventKind)
    for kind in EventKind:
        assert PRIORITY_BY_KIND[kind] in (0, 1, 2)
