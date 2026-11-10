"""Paper prices require fresh, independently admitted live observations."""

import random
import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.datafeed.price import LivePriceSource
from pumpgrok.events.sources import STALE_AFTER_S, SourceSupervisor
from pumpgrok.execution.paper_adapter import CurveSnapshot, OrderRejectedError, PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.tools.onchain import curve_layout

MINT = "mint-1"
START = 1_767_225_600.0


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    clock = FixtureClock(START)
    health = SourceSupervisor(clock, random.Random(0), path=tmp_path / "cursor.db")
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    prices = LivePriceSource(clock=clock, health=health, max_age_s=10.0)
    yield prices, health, clock
    health.close()


def observation(clock: FixtureClock, *, source: str = "rpc", complete: bool = False):
    return CurveObservation(
        mint=MINT,
        ts_utc=clock.utc_iso(),
        s_lamports=42_000_000_000,
        t_units=766_428_571_428_571,
        complete=complete,
        source=source,
    )


async def test_verified_fresh_live_observation_prices_with_non_fixture_provenance(source):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock))
    snapshot = await prices.curve(MINT)
    assert snapshot is not None
    assert (snapshot.s_lamports, snapshot.t_units) == (42_000_000_000, 766_428_571_428_571)
    assert snapshot.mint == MINT
    assert snapshot.source == "rpc"
    assert snapshot.source != "fixture"
    assert snapshot.ts == clock.now()


async def test_never_framed_and_disconnected_fail_closed(source):
    prices, health, clock = source
    prices.observe(observation(clock))
    # SourceSupervisor alone reports a never-framed source as live.
    assert await prices.curve(MINT) is None
    health.note_frame()
    assert await prices.curve(MINT) is not None
    health.note_failure()
    assert await prices.curve(MINT) is None
    health.note_frame()
    assert await prices.curve(MINT) is None
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is not None


async def test_stale_observation_and_stale_connection_independently_fail_closed(source):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is not None
    clock.advance_to(START + 11)
    health.note_frame()
    assert await prices.curve(MINT) is None
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is not None
    clock.advance_to(clock.now() + STALE_AFTER_S + 1)
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is None


async def test_assumed_status_revokes_existing_live_observation_dynamically(source, monkeypatch):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is not None
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
    assert await prices.curve(MINT) is None
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    assert await prices.curve(MINT) is not None


@pytest.mark.parametrize("label", ["fixture", "unknown", "unverified"])
async def test_live_ingestion_cannot_forge_replay_or_admit_unknown_sources(source, label):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock, source=label))
    assert await prices.curve(MINT) is None


async def test_unknown_mint_and_future_observation_are_unavailable(source):
    prices, health, clock = source
    health.note_frame()
    prices.observe(replace(observation(clock), ts_utc="2099-01-01T00:00:00Z"))
    assert await prices.curve(MINT) is None
    assert await prices.curve("unknown") is None


async def test_future_observation_cannot_block_later_current_observations(source):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is not None
    future = replace(observation(clock), ts_utc="2099-01-01T00:00:00Z")
    try:
        prices.observe(future)
    except ValueError:
        pass
    clock.advance_to(START + 1)
    health.note_frame()
    prices.observe(replace(observation(clock), s_lamports=43_000_000_000))
    recovered = await prices.curve(MINT)
    assert recovered is not None
    assert recovered.s_lamports == 43_000_000_000
    assert recovered.ts == clock.now()


async def test_reconnect_requires_new_observation_for_each_mint(source):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is not None
    clock.advance_to(START + 1)
    health.note_failure()
    assert await prices.curve(MINT) is None
    clock.advance_to(START + 2)
    health.note_frame()
    prices.observe(replace(observation(clock), mint="another-mint"))
    assert await prices.curve(MINT) is None
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is not None


@pytest.mark.parametrize("max_age_s", [0, -1, float("inf"), float("nan")])
def test_freshness_budget_must_be_explicit_and_valid(source, max_age_s):
    _, health, clock = source
    with pytest.raises(ValueError):
        LivePriceSource(clock=clock, health=health, max_age_s=max_age_s)


async def test_assumed_live_rpc_denies_buy_but_allows_protective_sell(tmp_path: Path):
    """A real adapter must retain INV-R-16 without authorizing unreviewed entries."""
    assert curve_layout.LAYOUT_STATUS == "ASSUMED"
    mint = "So11111111111111111111111111111111111111112"
    clock = FixtureClock(START)
    health = SourceSupervisor(clock, random.Random(0), path=tmp_path / "cursor.db")
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", "10000000000")
    store.set_meta("source", "paper")
    budget = RiskBudget()
    sol_reserves = 42_000_000_000
    token_reserves = 766_428_571_428_571
    risk = RiskEngine(
        store=store,
        budget=budget,
        ids=IdFactory(clock, random.Random(7)),
        clock=clock,
        autonomy="autonomous-paper",
        get_reserves=lambda _mint: (sol_reserves, token_reserves),
    )
    prices = LivePriceSource(clock=clock, health=health, max_age_s=300.0)
    adapter = PaperAdapter(
        store=store, risk=risk, ids=IdFactory(clock, make_rng(7)),
        clock=clock, rng=make_rng(7), budget=budget, price_source=prices, p_drop=0.0,
    )

    def request(ticket: str, side: Side, units: int | None = None) -> OrderRequest:
        return OrderRequest(
            ticket_id=ticket, mint=mint, side=side, decision_id=adapter._ids.ulid(),
            size_lamports=200_000_000 if side is Side.BUY else None,
            token_units=units, max_slippage_bps=100,
            approval_id=f"apr-{adapter._ids.ulid()}", correlation_id="test",
        )

    async def place(order: OrderRequest, seat: str, exit_reason: str | None = None):
        task = asyncio.create_task(
            adapter.place(order, seat=seat, exit_reason=exit_reason, correlation_id="test")
        )
        for _ in range(400):
            if task.done():
                break
            clock.advance_to(clock.now() + 1.0)
            await asyncio.sleep(0)
        return await task

    class ReplayOpeningPrice:
        async def curve(self, requested_mint: str) -> CurveSnapshot | None:
            if requested_mint != mint:
                return None
            return CurveSnapshot(
                mint=mint, s_lamports=sol_reserves, t_units=token_reserves,
                source="fixture", ts=clock.now(),
            )

    def observe_rpc() -> None:
        health.note_frame()
        prices.observe(CurveObservation(
            mint=mint, ts_utc=clock.utc_iso(), s_lamports=sol_reserves,
            t_units=token_reserves, complete=False, source="rpc",
        ))

    try:
        # Open through trusted replay only; the protective exit uses the real live source.
        adapter._price = ReplayOpeningPrice()
        bought = await place(request("SOL-20260201-102", Side.BUY), "bot-04-sniper")
        assert bought.filled_units > 0
        adapter._price = prices
        observe_rpc()
        try:
            sold = await place(
                request("SOL-20260201-103", Side.SELL, bought.filled_units),
                "bot-06-exit",
                exit_reason="stop_loss",
            )
        except OrderRejectedError as exc:
            assert exc.reason != "no_reserves"
            raise
        assert sold.filled_units > 0
        fills_before = len(store.read(types=["FillRecorded"], limit=None))
        observe_rpc()
        with pytest.raises(OrderRejectedError) as rejected:
            await place(request("SOL-20260201-104", Side.BUY), "bot-04-sniper")
        assert rejected.value.reason == "data_unavailable"
        assert len(store.read(types=["FillRecorded"], limit=None)) == fills_before
    finally:
        health.close()
        store.close()
