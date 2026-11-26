"""Journal rollup runs on journal wakes only."""

from pumpgrok.events.models import Event, EventKind
from pumpgrok.supervisor.scheduler.journal_rollup import rollup
from pumpgrok.supervisor.scheduler.wake import Wake


def test_rollup_counts_journal_wakes() -> None:
    event = Event(
        kind=EventKind.position_closed,
        entity_id="pos-1",
        payload={"v": 1},
        occurred_at="2026-01-01T00:00:00.000000Z",
    )
    wakes = [Wake(seat="bot-09-journal", event=event), Wake(seat="bot-01-scout", event=event)]
    result = rollup(wakes)
    assert result.journal_wakes == 1
    assert result.kinds == {"position_closed": 1}
