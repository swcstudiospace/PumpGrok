"""Fault harness modes, protocol fakes, clock jump, and the rollover emitter.

Task 1 proof: a three-virtual-day supervisor run yields exactly three
DailyRollover events (one per UTC day including the first, D6), and every
protocol fake fires through the InjectedFault marker.
"""

from __future__ import annotations

import errno
from pathlib import Path
from typing import Any

import pytest

from harness.faults import (
    FaultInjector,
    FaultMode,
    FaultyDataSource,
    FaultyExecutionAdapter,
    FaultyLedgerStore,
    FaultyLLMClient,
    FaultyPriceSource,
    FaultyRpcClient,
    InjectedFault,
    InjectedRateLimit,
    InjectedUnknown,
)
from pumpgrok.core.errors import DataStale
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, parse_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor, rollover_key
from pumpgrok.supervisor.seat_task import SeatContext
from pumpgrok.tools.onchain.rpc import RpcError

BASE = 1767225600.0


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


def test_unknown_mode_raises_marker() -> None:
    injector = FaultInjector(FaultMode.UNKNOWN, at_index=1)
    events = [{"ts_utc": "2026-01-01T00:00:00.000Z"}, {"ts_utc": "2026-01-01T00:01:00.000Z"}]
    with pytest.raises(InjectedUnknown):
        list(injector.apply(events))


def test_malformed_mode_yields_unparsable_event() -> None:
    injector = FaultInjector(FaultMode.MALFORMED, at_index=0)
    events = [{"ts_utc": "2026-01-01T00:00:00.000Z"}]
    (corrupt,) = list(injector.apply(events))
    assert corrupt["fault"] == "malformed"
    with pytest.raises(ValueError):
        parse_ts_utc(str(corrupt["ts_utc"]))


def test_existing_modes_unchanged() -> None:
    events = [{"ts_utc": "2026-01-01T00:00:00.000Z"}, {"ts_utc": "2026-01-01T00:01:00.000Z"}]
    with pytest.raises(TimeoutError):
        list(FaultInjector(FaultMode.TIMEOUT, at_index=0).apply(events))
    with pytest.raises(InjectedRateLimit):
        list(FaultInjector(FaultMode.RATE_LIMIT, at_index=0).apply(events))
    with pytest.raises(InjectedFault):
        list(FaultInjector(FaultMode.RAISE, at_index=0).apply(events))


async def test_faulty_llm_client_modes() -> None:
    clock = FixtureClock(start=BASE)
    request = {"dataset": "smoke", "events": 4}
    for mode, expected in [
        (FaultMode.TIMEOUT, TimeoutError),
        (FaultMode.RATE_LIMIT, InjectedRateLimit),
        (FaultMode.RAISE, InjectedFault),
        (FaultMode.UNKNOWN, InjectedUnknown),
    ]:
        fake = FaultyLLMClient(mode)
        with pytest.raises(expected):
            await fake.complete(request, clock)
        assert fake.fired == 1
    malformed = FaultyLLMClient(FaultMode.MALFORMED)
    outcome = await malformed.complete(request, clock)
    assert outcome["outcome"] == "malformed"
    assert malformed.fired == 1
    healthy = FaultyLLMClient(FaultMode.TIMEOUT, at_call=5)
    outcome = await healthy.complete(request, clock)
    assert outcome["outcome"] == "ok"
    assert healthy.fired == 0


async def test_faulty_rpc_client_failover_order_then_product_error() -> None:
    fake = FaultyRpcClient([FaultMode.RATE_LIMIT, FaultMode.RAISE])
    with pytest.raises(RpcError):
        await fake.call("getAccountInfo", ["mint"])
    assert fake.attempts == [0, 1]
    assert fake.fired == 2


async def test_faulty_rpc_client_all_malformed_is_data_stale() -> None:
    fake = FaultyRpcClient([FaultMode.MALFORMED, FaultMode.MALFORMED])
    with pytest.raises(DataStale):
        await fake.call("getAccountInfo", ["mint"])
    assert fake.attempts == [0, 1]


async def test_faulty_rpc_client_unknown_never_fails_over() -> None:
    fake = FaultyRpcClient([FaultMode.UNKNOWN, None])
    with pytest.raises(InjectedUnknown):
        await fake.call("getAccountInfo", ["mint"])
    assert fake.attempts == [0]


async def test_faulty_rpc_client_recovery() -> None:
    fake = FaultyRpcClient([None])
    result = await fake.call("getAccountInfo", ["mint"])
    assert result["endpoint"] == 0
    assert fake.fired == 0


async def test_faulty_data_source_stale_returns_last_good() -> None:
    fake = FaultyDataSource(FaultMode.STALE, last_good={"tick": 1})
    value, freshness = await fake.fetch({"mint": "m"}, max_age_s=120.0)
    assert value == {"tick": 1}
    assert freshness.stale is True
    assert fake.fired == 1


async def test_faulty_data_source_without_cache_raises_product_stale() -> None:
    fake = FaultyDataSource(FaultMode.STALE)
    with pytest.raises(DataStale):
        await fake.fetch({"mint": "m"}, max_age_s=120.0)
    assert fake.fired == 1


async def test_faulty_price_source_stale_returns_last_good_or_none() -> None:
    cached = {"mint": "m", "s_lamports": 1}
    fake = FaultyPriceSource(FaultMode.STALE, last_good=cached)
    assert await fake.curve("m") is cached
    assert fake.fired == 1
    empty = FaultyPriceSource(FaultMode.STALE)
    assert await empty.curve("m") is None
    assert empty.fired == 1


async def test_faulty_execution_adapter_unknown_never_retries() -> None:
    fake = FaultyExecutionAdapter()
    with pytest.raises(InjectedUnknown):
        await fake.place({"ticket_id": "t"})
    with pytest.raises(InjectedUnknown):
        await fake.place({"ticket_id": "t"})
    assert len(fake.places) == 2
    assert fake.fired == 2


def test_faulty_ledger_store_unwritable_refuses_with_eacces(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        faulty = FaultyLedgerStore(store)
        with pytest.raises(PermissionError) as excinfo:
            faulty.append(
                ts_utc="2026-01-01T00:00:00.000Z",
                source="paper",
                correlation_id="desk",
                idempotency_key="k-0",
                type="JournalNote",
                payload={"source": "paper", "seat": "desk", "note_kind": "note", "text": "t", "refs": []},
            )
        assert excinfo.value.errno == errno.EACCES
        assert faulty.fired == 1
        assert faulty.verify() is True
        assert faulty.count() == 0
    finally:
        store.close()


def test_fixture_clock_jump_moves_without_host_reads() -> None:
    clock = FixtureClock(start=100.0)
    clock.jump(-30.0)
    assert clock.now() == 70.0
    clock.jump(10.0)
    assert clock.now() == 80.0
    clock.advance_to(90.0)
    assert clock.now() == 90.0


async def test_three_virtual_days_yield_three_rollovers(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        async def _ok(ctx: SeatContext) -> dict[str, Any]:
            return {"ok": True}

        supervisor = Supervisor(
            store=store, clock=clock, rng=make_rng(7), cycles=dict.fromkeys(ROSTER, _ok)
        )
        for day_offset in range(3):
            clock.advance_to(BASE + day_offset * 86400.0)
            outcomes = await supervisor.run_once()
            assert all(outcome == "ok" for outcome in outcomes.values())
        rows = [row for row in store.read(limit=None) if row["type"] == "DailyRollover"]
        assert len(rows) == 3
        assert [row["payload"]["day_utc"] for row in rows] == [
            "2026-01-01",
            "2026-01-02",
            "2026-01-03",
        ]
        for row in rows:
            day = str(row["payload"]["day_utc"])
            assert row["idempotency_key"] == rollover_key(day)
        assert store.verify() is True
    finally:
        store.close()


async def test_rollover_is_idempotent_within_a_day(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        async def _ok(ctx: SeatContext) -> dict[str, Any]:
            return {"ok": True}

        supervisor = Supervisor(
            store=store, clock=clock, rng=make_rng(7), cycles=dict.fromkeys(ROSTER, _ok)
        )
        await supervisor.run_once()
        await supervisor.run_once()
        rows = [row for row in store.read(limit=None) if row["type"] == "DailyRollover"]
        assert len(rows) == 1
    finally:
        store.close()
