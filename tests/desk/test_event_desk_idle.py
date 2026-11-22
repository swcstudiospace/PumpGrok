"""RT-03: an idle desk stays silent — zero Grok calls, zero trade writes.

24 virtual hours with zero source events: no gateway calls and no
OrderPlaced/FillRecorded rows (health-only writes aside).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import ExecutionMode
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.event_desk import build_event_desk

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()


def test_idle_desk_is_silent_after_24_virtual_hours(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", "10000000000")
    store.set_meta("source", "paper")
    desk = build_event_desk(
        mode=ExecutionMode.PAPER,
        store=store,
        clock=clock,
        place=lambda intent: None,
        sidecar_path=tmp_path / "sidecar.sqlite",
        params={"momentum_breakout": {"breakout_bps": 100}},
    )
    clock.jump(24 * 3600.0)
    assert desk.gateway.transport_calls == 0
    trades = store.read(types=["OrderPlaced", "FillRecorded"], limit=None)
    # store.read takes one type at a time; count both kinds explicitly.
    placed = store.read(types=["OrderPlaced"], limit=None)
    fills = store.read(types=["FillRecorded"], limit=None)
    assert placed == []
    assert fills == []
    assert trades == []
