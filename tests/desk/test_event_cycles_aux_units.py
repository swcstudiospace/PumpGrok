"""Unit checks for whale, signal and journal event bodies (EVT-10, 14-04)."""

from __future__ import annotations

import asyncio
import random
from types import SimpleNamespace
from typing import Any

from pumpgrok.events.models import Event, EventKind
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.scheduler import event_cycles_aux
from pumpgrok.supervisor.scheduler.degraded import DegradedState
from pumpgrok.supervisor.scheduler.supervisor import TRIGGER_EVENT
from pumpgrok.supervisor.seat_task import SeatContext
from pumpgrok.tools.onchain.rpc import RpcError

MINT = "So11111111111111111111111111111111111111112"


def _ctx() -> SeatContext:
    return SeatContext(
        seat_id="bot-03-whale",
        clock=FixtureClock(),
        rng=random.Random(7),
        store=SimpleNamespace(read=lambda *a, **k: []),  # type: ignore[arg-type]
    )


def _event(kind: EventKind) -> Event:
    return Event(
        kind=kind,
        entity_id=MINT,
        payload={},
        occurred_at="2026-01-01T00:00:00Z",
    )


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class _FailingRpc:
    async def call(self, method: str, params: list[Any]) -> Any:
        raise RpcError("endpoint down")


def test_whale_skips_non_candidate_events() -> None:
    TOKEN = TRIGGER_EVENT.set(_event(EventKind.trade))
    try:
        result = _run(event_cycles_aux._whale(_ctx(), degraded=DegradedState(), rpc=None))
    finally:
        TRIGGER_EVENT.reset(TOKEN)
    assert result == {
        "verdict": "SKIP",
        "reason": "not_a_candidate",
        "mint": None,
        "trigger": "trade",
    }


def test_whale_blinds_without_transport_or_rpc() -> None:
    TOKEN = TRIGGER_EVENT.set(_event(EventKind.token_created))
    try:
        blind = _run(
            event_cycles_aux._whale(
                _ctx(),
                degraded=DegradedState(rpc_endpoints=[False]),
                rpc=_FailingRpc(),  # type: ignore[arg-type]
            )
        )
        no_rpc = _run(event_cycles_aux._whale(_ctx(), degraded=DegradedState(), rpc=None))
    finally:
        TRIGGER_EVENT.reset(TOKEN)
    assert blind["verdict"] == "BLIND"
    assert blind["reason"] == "rpc_down"
    assert no_rpc["verdict"] == "BLIND"
    assert no_rpc["reason"] == "no_rpc"


def test_whale_reports_unread_when_rpc_fails() -> None:
    TOKEN = TRIGGER_EVENT.set(_event(EventKind.token_created))
    try:
        result = _run(
            event_cycles_aux._whale(_ctx(), degraded=DegradedState(), rpc=_FailingRpc())  # type: ignore[arg-type]
        )
    finally:
        TRIGGER_EVENT.reset(TOKEN)
    assert result["verdict"] == "UNREAD"
    assert result["mint"] == MINT


def test_synthetic_signal_score_terms() -> None:
    full = {
        "unique_buyers": 20,
        "S": 10**15,
        "created_ts_utc": "2026-01-01T00:00:00Z",
        "ts_utc": "2026-01-01T00:30:00Z",
    }
    score = event_cycles_aux.synthetic_signal_score(full)
    assert 0.5 < score <= 1.0
    assert score == event_cycles_aux.synthetic_signal_score(dict(full))
    assert event_cycles_aux.synthetic_signal_score({}) == 0.0
    assert event_cycles_aux.synthetic_signal_score({"unique_buyers": True}) == 0.0
    assert event_cycles_aux.synthetic_signal_score({"unique_buyers": -1}) == 0.0
    assert event_cycles_aux.synthetic_signal_score({"S": True}) == 0.0
    assert event_cycles_aux.synthetic_signal_score({"S": -5}) == 0.0
    ancient = {
        "created_ts_utc": "2026-01-01T00:00:00Z",
        "ts_utc": "2026-01-03T00:00:00Z",
    }
    assert event_cycles_aux.synthetic_signal_score(ancient) == 0.0
    garbled = {"created_ts_utc": "not-a-time", "ts_utc": "2026-01-01T00:00:00Z"}
    assert event_cycles_aux.synthetic_signal_score(garbled) == 0.0
    future = {
        "created_ts_utc": "2026-01-02T00:00:00Z",
        "ts_utc": "2026-01-01T00:00:00Z",
    }
    assert event_cycles_aux.synthetic_signal_score(future) == 0.0


def test_signal_withholds_skips_and_scores() -> None:
    row = {
        "unique_buyers": 20,
        "S": 10**15,
        "created_ts_utc": "2026-01-01T00:00:00Z",
        "ts_utc": "2026-01-01T00:30:00Z",
    }
    TOKEN = TRIGGER_EVENT.set(_event(EventKind.halt))
    try:
        withheld = _run(event_cycles_aux._signal(_ctx(), first_rows={MINT: row}))
        TRIGGER_EVENT.set(_event(EventKind.token_created))
        missing_row = _run(event_cycles_aux._signal(_ctx(), first_rows={}))
        scored = _run(event_cycles_aux._signal(_ctx(), first_rows={MINT: row}))
        TRIGGER_EVENT.set(_event(EventKind.trade))
        skipped = _run(event_cycles_aux._signal(_ctx(), first_rows={MINT: row}))
    finally:
        TRIGGER_EVENT.reset(TOKEN)
    assert withheld["scoring"] == "withheld"
    assert missing_row["reason"] == "no_fixture_row"
    assert scored["scoring"] == "synthetic"
    assert scored["score"] == event_cycles_aux.synthetic_signal_score(row)
    assert skipped["reason"] == "not_a_candidate"


def test_deterministic_bus_drains_deterministically() -> None:
    clock = FixtureClock()
    bus = event_cycles_aux.DeterministicBus(clock=clock, rng=random.Random(7))
    events = [_event(EventKind.token_created)]
    first = bus.deliver(events)
    assert first.pending == 0
    assert b"token_created" in bytes(first)
    bus2 = event_cycles_aux.DeterministicBus(clock=FixtureClock(), rng=random.Random(7))
    assert bytes(bus2.deliver(events)) == bytes(first)
    try:
        bus.deliver(events, fixture_compat=False)
    except ValueError as exc:
        assert "fixture_compat" in str(exc)
    else:
        raise AssertionError("non-fixture drain accepted")


def test_first_rows_by_mint_keeps_the_first_row() -> None:
    events = [{"mint": "A", "v": 1}, {"mint": "A", "v": 2}, {"mint": "B", "v": 3}]
    rows = event_cycles_aux._first_rows_by_mint(events)
    assert rows["A"]["v"] == 1
    assert rows["B"]["v"] == 3


def test_journal_notes_trades_and_rolls_up_on_timer(tmp_path: Any) -> None:

    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    journal_dir = tmp_path / "journal"
    reports_dir = tmp_path / "reports"
    kwargs: dict[str, Any] = {
        "store": store,
        "trading": None,
        "journal_dir": journal_dir,
        "reports_dir": reports_dir,
    }
    TOKEN = TRIGGER_EVENT.set(_event(EventKind.trade))
    try:
        noted = _run(event_cycles_aux._journal(_ctx(), **kwargs))
        TRIGGER_EVENT.set(_event(EventKind.position_closed))
        closed = _run(event_cycles_aux._journal(_ctx(), **kwargs))
        TRIGGER_EVENT.set(None)
        timer = _run(event_cycles_aux._journal(_ctx(), **kwargs))
    finally:
        TRIGGER_EVENT.reset(TOKEN)
    assert noted["noted"] is True
    assert noted["rollup"] is None
    assert closed["noted"] is True
    assert closed["rollup"] is not None
    assert timer["noted"] is False
    assert timer["rollup"] is not None
