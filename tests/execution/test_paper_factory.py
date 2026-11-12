"""Production composition refuses injected curve sources; the factory is the only entry.

The factory is the only construction site for a PaperAdapter. A BUY is admitted only
through a verify_replay token. The exact live source composes for paper exits and
marks and never admits entry: live RPC provenance is not admitted yet.
"""

from __future__ import annotations

import asyncio
import random
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Literal

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.datafeed.price import LivePriceSource
from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.execution import build_adapter, build_paper_adapter
from pumpgrok.execution.fees import FeeModel
from pumpgrok.execution.paper_adapter import (
    CurveSnapshot,
    OrderRejectedError,
    PaperAdapter,
    PriceSource,
)
from pumpgrok.execution.paper_factory import VerifiedReplay
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine

from .replay_support import replay_authority, tick

START = 1_769_900_000.0
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-101"
MINT = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
SIZE = 200_000_000


class ScriptedCurves:
    """Injected test source: pops one scripted snapshot per read, holds the last."""

    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


def _snap(source: str) -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0, source=source)


def _factory_adapter(
    tmp_path: Path, reads: list[CurveSnapshot]
) -> tuple[PaperAdapter, FixtureClock, LedgerStore]:
    clock = FixtureClock(START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    risk = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(7)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )
    adapter = build_adapter(
        object(),
        store=store,
        risk=risk,
        ids=IdFactory(clock, make_rng(7)),
        clock=clock,
        rng=make_rng(7),
        price_source=ScriptedCurves(reads),
        p_drop=0.0,
    )
    return adapter, clock, store


async def _place(adapter: PaperAdapter, clock: FixtureClock, request: OrderRequest) -> Fill:
    task = asyncio.create_task(adapter.place(request, seat="bot-04-sniper", correlation_id="test"))
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return await task


async def test_factory_injected_fixture_buy_is_not_filled(tmp_path: Path) -> None:
    """RED: a fixture source injected through the factory fills a BUY that must be refused."""
    adapter, clock, store = _factory_adapter(tmp_path, [_snap("fixture")] * 3)
    request = OrderRequest(
        ticket_id=TICKET,
        mint=MINT,
        side=Side.BUY,
        decision_id=adapter._ids.ulid(),
        size_lamports=SIZE,
        token_units=None,
        max_slippage_bps=100,
        approval_id=f"apr-{adapter._ids.ulid()}",
        correlation_id="test",
    )
    try:
        await _place(adapter, clock, request)
    except OrderRejectedError:
        pass
    kinds = [event["type"] for event in store.read(limit=None)]
    assert "FillRecorded" not in kinds


class _Wrapper:
    """Delegating wrapper around the live source: a different object, never admitted."""

    def __init__(self, inner: LivePriceSource) -> None:
        self._inner = inner

    async def curve(self, mint: str) -> CurveSnapshot | None:
        return await self._inner.curve(mint)


class _LiveSubclass(LivePriceSource):
    """Subclass of the live source: exact-type membership refuses it."""


@pytest.fixture
def live_env(
    tmp_path: Path,
) -> Iterator[tuple[FixtureClock, LedgerStore, SourceSupervisor, LivePriceSource]]:
    clock = FixtureClock(START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    health = SourceSupervisor(clock, random.Random(0), path=tmp_path / "cursor.db")
    live = LivePriceSource(clock=clock, health=health, max_age_s=10.0, max_observations=16)
    yield clock, store, health, live
    health.close()


def _live_adapter(
    clock: FixtureClock,
    store: LedgerStore,
    live: object,
    *,
    price_source: PriceSource | None = None,
    replay: VerifiedReplay | None = None,
    source: Literal["paper", "replay", "manual"] = "paper",
    fees: FeeModel | None = None,
    reserves_observer: Callable[[CurveSnapshot], None] | None = None,
) -> PaperAdapter:
    risk = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(7)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )
    return build_paper_adapter(
        object(),
        store=store,
        risk=risk,
        ids=IdFactory(clock, make_rng(7)),
        clock=clock,
        rng=make_rng(7),
        live_source=live,  # type: ignore[arg-type]
        price_source=price_source,
        replay=replay,
        source=source,
        fees=fees,
        reserves_observer=reserves_observer,
        p_drop=0.0,
    )


def _live_observation(clock: FixtureClock) -> CurveObservation:
    return CurveObservation(
        mint=MINT, ts_utc=clock.utc_iso(), s_lamports=S0, t_units=T0, complete=False, source="rpc"
    )


def _buy_request(adapter: PaperAdapter) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=MINT,
        side=Side.BUY,
        decision_id=adapter._ids.ulid(),
        size_lamports=SIZE,
        token_units=None,
        max_slippage_bps=100,
        approval_id=f"apr-{adapter._ids.ulid()}",
        correlation_id="test",
    )


def test_live_composition_binds_the_exact_live_source(live_env) -> None:
    clock, store, _health, live = live_env
    adapter = _live_adapter(clock, store, live)
    assert adapter._price is live


def test_live_composition_refuses_wrapper_and_subclass(live_env) -> None:
    clock, store, health, live = live_env
    subclass = _LiveSubclass(clock=clock, health=health, max_age_s=10.0, max_observations=16)
    with pytest.raises(ValueError):
        _live_adapter(clock, store, _Wrapper(live))
    with pytest.raises(ValueError):
        _live_adapter(clock, store, subclass)


def test_live_composition_refuses_mixed_and_replay_sources(live_env, tmp_path: Path) -> None:
    clock, store, _health, live = live_env
    replay = replay_authority(tmp_path, clock, [tick(START, MINT, S0, T0)])
    with pytest.raises(ValueError):
        _live_adapter(clock, store, live, price_source=ScriptedCurves([_snap("rpc")]))
    with pytest.raises(ValueError):
        _live_adapter(clock, store, live, replay=replay)
    with pytest.raises(ValueError):
        _live_adapter(clock, store, live, source="replay")


async def test_live_buy_is_refused_even_on_a_fresh_live_observation(live_env) -> None:
    clock, store, health, live = live_env
    health.note_frame()
    live.observe(_live_observation(clock))
    adapter = _live_adapter(clock, store, live)
    with pytest.raises(OrderRejectedError):
        await _place(adapter, clock, _buy_request(adapter))
    assert "FillRecorded" not in [event["type"] for event in store.read(limit=None)]


async def test_live_source_still_serves_exit_reads(live_env) -> None:
    clock, store, health, live = live_env
    health.note_frame()
    live.observe(_live_observation(clock))
    adapter = _live_adapter(clock, store, live)
    snapshot = await adapter._read_curve(MINT)
    assert snapshot is not None
    assert snapshot.source == "rpc"


async def test_source_replaced_after_composition_fails_the_buy(live_env) -> None:
    clock, store, health, live = live_env
    health.note_frame()
    live.observe(_live_observation(clock))
    adapter = _live_adapter(clock, store, live)
    adapter._price = _Wrapper(live)
    with pytest.raises(OrderRejectedError):
        await _place(adapter, clock, _buy_request(adapter))
    assert "FillRecorded" not in [event["type"] for event in store.read(limit=None)]


def test_fee_model_defaults_to_v1_and_accepts_a_selected_model(live_env) -> None:
    clock, store, _health, live = live_env
    assert _live_adapter(clock, store, live)._fees == FeeModel()
    selected = FeeModel(venue_fee_bps=200)
    assert _live_adapter(clock, store, live, fees=selected)._fees is selected


def test_reserves_observer_requires_the_live_source(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    with pytest.raises(ValueError):
        _live_adapter(clock, store, None, reserves_observer=lambda _snapshot: None)


async def test_reserves_observer_receives_the_actual_returned_snapshot(live_env) -> None:
    clock, store, health, live = live_env
    health.note_frame()
    live.observe(_live_observation(clock))
    seen: list[CurveSnapshot] = []
    adapter = _live_adapter(clock, store, live, reserves_observer=seen.append)
    snapshot = await adapter._read_curve(MINT)
    assert snapshot is not None
    assert len(seen) == 1
    assert seen[0] is snapshot


async def test_reserves_observer_does_not_admit_a_buy(live_env) -> None:
    clock, store, health, live = live_env
    health.note_frame()
    live.observe(_live_observation(clock))
    seen: list[CurveSnapshot] = []
    adapter = _live_adapter(clock, store, live, reserves_observer=seen.append)
    with pytest.raises(OrderRejectedError):
        await _place(adapter, clock, _buy_request(adapter))
    assert "FillRecorded" not in [event["type"] for event in store.read(limit=None)]
