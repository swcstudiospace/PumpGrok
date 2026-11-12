"""Paper prices require fresh, independently admitted live observations."""

import asyncio
import random
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.datafeed.graduation import entry_allowed
from pumpgrok.datafeed.price import LivePriceSource, ReservesCache
from pumpgrok.events.sources import STALE_AFTER_S, SourceStatus, SourceSupervisor
from pumpgrok.execution import build_paper_adapter
from pumpgrok.execution.paper_adapter import OrderRejectedError
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.tools.onchain import curve_layout

from replay_support import replay_authority, tick

MINT = "mint-1"
START = 1_767_225_600.0


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    clock = FixtureClock(START)
    health = SourceSupervisor(clock, random.Random(0), path=tmp_path / "cursor.db")
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    prices = LivePriceSource(clock=clock, health=health, max_age_s=10.0, max_observations=16)
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


async def test_assumed_status_denies_entry_but_preserves_exit_observation(source, monkeypatch):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock))
    snap = await prices.curve(MINT)
    # Changed (strict gate, owner accept-degrade): a live rpc observation never admits entry.
    assert not entry_allowed(snap, now=clock.now(), max_age_s=10.0)
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
    snap = await prices.curve(MINT)
    assert snap is not None and snap.source == "rpc"
    assert not entry_allowed(snap, now=clock.now(), max_age_s=10.0)
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    # Changed (strict gate, owner accept-degrade): VERIFIED layout does not admit live entry.
    assert not entry_allowed(await prices.curve(MINT), now=clock.now(), max_age_s=10.0)


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
    prices.observe(future)
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


@pytest.mark.parametrize("interruption", ["failure", "resync"])
async def test_unobserved_reconnect_fences_each_mint_at_same_timestamp(source, interruption):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock))
    prices.observe(replace(observation(clock), mint="another-mint"))
    assert await prices.curve(MINT) is not None
    assert await prices.curve("another-mint") is not None
    if interruption == "failure":
        health.note_failure()
    else:
        health.resync([MINT, "another-mint"])
    health.note_frame()
    # No read or clock advance occurred while the connection was interrupted.
    assert await prices.curve(MINT) is None
    assert await prices.curve("another-mint") is None
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is not None
    assert await prices.curve("another-mint") is None


async def test_silent_stale_interval_fences_cached_mint_after_unrelated_frame(tmp_path: Path):
    clock = FixtureClock(START)
    health = SourceSupervisor(clock, random.Random(0), path=tmp_path / "cursor.db")
    prices = LivePriceSource(
        clock=clock, health=health, max_age_s=STALE_AFTER_S + 100.0, max_observations=16
    )
    try:
        health.note_frame()
        prices.observe(observation(clock))
        assert await prices.curve(MINT) is not None
        clock.advance_to(START + STALE_AFTER_S + 1)
        # No status read while stale: an unrelated frame must not revive MINT.
        health.note_frame()
        prices.observe(replace(observation(clock), mint="another-mint"))
        assert await prices.curve("another-mint") is not None
        assert await prices.curve(MINT) is None
        prices.observe(observation(clock))
        assert await prices.curve(MINT) is not None
    finally:
        health.close()


@pytest.mark.parametrize("max_age_s", [0, -1, float("inf"), float("nan")])
def test_freshness_budget_must_be_explicit_and_valid(source, max_age_s):
    _, health, clock = source
    with pytest.raises(ValueError):
        LivePriceSource(clock=clock, health=health, max_age_s=max_age_s, max_observations=16)


@pytest.mark.parametrize("bad_frame", [float("nan"), float("inf"), -float("inf"), START - 1])
def test_invalid_frame_cannot_end_resync_or_change_health(source, bad_frame):
    _, health, clock = source
    health.note_frame()
    health.resync([MINT])
    generation = health.connection_generation
    with pytest.raises(ValueError):
        health.note_frame(bad_frame)
    assert health.last_frame_at == START
    assert health.connection_generation == generation
    assert health.status_at(clock.now()) is SourceStatus.resyncing
    health.note_frame()
    assert health.status_at(clock.now()) is SourceStatus.live


@pytest.mark.parametrize("capacity", [0, -1, True, 1.5])
def test_observation_capacity_must_be_a_positive_integer(source, capacity):
    _, health, clock = source
    with pytest.raises(ValueError):
        LivePriceSource(clock=clock, health=health, max_age_s=10.0, max_observations=capacity)


async def test_capacity_rejects_new_mints_without_evicting_fresh_data(source):
    _, health, clock = source
    prices = LivePriceSource(clock=clock, health=health, max_age_s=10.0, max_observations=2)
    health.note_frame()
    prices.observe(observation(clock))
    prices.observe(replace(observation(clock), mint="another-mint"))
    with pytest.raises(OverflowError):
        prices.observe(replace(observation(clock), mint="third-mint"))
    assert await prices.curve(MINT) is not None
    assert await prices.curve("another-mint") is not None
    assert await prices.curve("third-mint") is None
    clock.advance_to(START + 11)
    health.note_frame()
    prices.observe(replace(observation(clock), mint="third-mint"))
    assert await prices.curve("third-mint") is not None
    assert await prices.curve(MINT) is None


async def test_assumed_live_rpc_denies_buy_but_allows_protective_sell(tmp_path: Path):
    """A real adapter must retain INV-R-16 without authorizing unreviewed entries."""
    assert curve_layout.LAYOUT_STATUS == "VERIFIED"
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
    prices = LivePriceSource(clock=clock, health=health, max_age_s=300.0, max_observations=16)
    replay = replay_authority(
        tmp_path,
        clock,
        [tick(START + second, mint, sol_reserves, token_reserves) for second in range(601)],
    )
    adapter = build_paper_adapter(
        SimpleNamespace(risk=budget),
        store=store,
        risk=risk,
        ids=IdFactory(clock, make_rng(7)),
        clock=clock,
        rng=make_rng(7),
        replay=replay,
        source="replay",
        p_drop=0.0,
    )

    def request(ticket: str, side: Side, units: int | None = None) -> OrderRequest:
        return OrderRequest(
            ticket_id=ticket,
            mint=mint,
            side=side,
            decision_id=adapter._ids.ulid(),
            size_lamports=200_000_000 if side is Side.BUY else None,
            token_units=units,
            max_slippage_bps=100,
            approval_id=f"apr-{adapter._ids.ulid()}",
            correlation_id="test",
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

    def observe_rpc() -> None:
        health.note_frame()
        prices.observe(
            CurveObservation(
                mint=mint,
                ts_utc=clock.utc_iso(),
                s_lamports=sol_reserves,
                t_units=token_reserves,
                complete=False,
                source="rpc",
            )
        )

    try:
        # Open through trusted replay only; the protective exit uses the real live source.
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


async def test_snapshot_label_is_the_explicit_live_rpc_stamp(source):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock))
    snapshot = await prices.curve(MINT)
    assert snapshot is not None
    assert snapshot.source == "rpc"


async def test_observer_receives_the_exact_snapshot_that_is_returned(source):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock))
    seen = []
    prices.set_observer(seen.append)
    snapshot = await prices.curve(MINT)
    assert snapshot is not None
    assert len(seen) == 1 and seen[0] is snapshot


async def test_observer_failure_never_changes_admission(source):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock))

    def failing(_snapshot):
        raise RuntimeError("risk cache offline")

    prices.set_observer(failing)
    snapshot = await prices.curve(MINT)
    assert snapshot is not None
    assert snapshot.source == "rpc"
    assert prices.observer_failures == 1


async def test_observer_is_not_called_when_admission_refuses(source):
    prices, health, clock = source
    seen = []
    prices.set_observer(seen.append)
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is None
    assert seen == []


async def test_fixture_labelled_observation_never_reaches_the_observer(source):
    prices, health, clock = source
    health.note_frame()
    seen = []
    prices.set_observer(seen.append)
    prices.observe(observation(clock, source="fixture"))
    assert await prices.curve(MINT) is None
    assert seen == []


def test_observer_must_be_callable_or_none(source):
    prices, _, _ = source
    with pytest.raises(TypeError):
        prices.set_observer("not callable")
    prices.set_observer(None)


def _snapshot(mint: str, s: int, t: int) -> CurveSnapshot:
    return CurveSnapshot(mint=mint, s_lamports=s, t_units=t, complete=False, source="rpc", ts=1.0)


def test_reserves_cache_keeps_the_latest_exact_reserves_per_mint():
    cache = ReservesCache(capacity=4)
    cache.observe(_snapshot("A", 10, 20))
    cache.observe(_snapshot("A", 11, 21))
    assert cache.get("A") == (11, 21)
    assert cache.get("B") is None
    assert len(cache) == 1


def test_reserves_cache_is_bounded_and_evicts_the_least_recently_stored():
    cache = ReservesCache(capacity=2)
    cache.observe(_snapshot("A", 1, 1))
    cache.observe(_snapshot("B", 2, 2))
    cache.store("A", 3, 3)
    cache.observe(_snapshot("C", 4, 4))
    assert cache.get("B") is None
    assert cache.get("A") == (3, 3)
    assert cache.get("C") == (4, 4)
    assert len(cache) == 2


@pytest.mark.parametrize("capacity", [0, -1, True, 1.5])
def test_reserves_cache_capacity_must_be_a_positive_integer(capacity):
    with pytest.raises(ValueError):
        ReservesCache(capacity=capacity)


@pytest.mark.parametrize(("s", "t"), [(0, 1), (1, 0), (True, 1), (1.5, 1)])
def test_reserves_cache_refuses_non_positive_or_non_integer_reserves(s, t):
    cache = ReservesCache(capacity=2)
    with pytest.raises(ValueError):
        cache.store("A", s, t)
    assert cache.get("A") is None
