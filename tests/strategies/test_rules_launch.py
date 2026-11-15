"""STR-04 / criterion 6: new_launch_sniper flips exactly at each bound; strat-launch fills.

Hand computation of tests/fixtures/replay/strat-launch, max age 300 s, min unique buyers 5,
max curve progress 0.10, take profit 80%, entry size 10_000_000 lamports:

- LaunchMintL4 is 300 s old at t=0 with 5 buyers: age equals the bound and buyers equal the
  floor -> BUY at t=0.
- LaunchMintL2 is 120 s old at t=0 with progress just above 0.10 (S = 8_500_000_001): no buy.
  At t=30 it is 150 s old, 10 buyers, progress 0.094 -> BUY.
- LaunchMintL1 is 60 s old at t=0 with 4 buyers: no buy. At t=60 it has 5 buyers, progress
  exactly 0.10 -> BUY. At t=180, S = 15.3e9 is exactly 1.8 x the entry 8.5e9 -> SELL (take profit).
- LaunchMintL3 is 600 s old at t=0 with 50 buyers: too old, no buy.

Expected fills, (seconds after 2026-01-01T00:00:00Z, mint, side):
  (0, L4, buy), (30, L2, buy), (60, L1, buy), (180, L1, sell).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

import pytest

from pumpgrok.replay.clock import FixtureClock, parse_ts_utc
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.strategies import Intent, TickSnapshot
from pumpgrok.strategies.legacy import tick_snapshot
from pumpgrok.strategies.new_launch_sniper import NewLaunchSniper
from pumpgrok.strategies.runtime import StrategyRuntime

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "replay"
START = parse_ts_utc("2026-01-01T00:00:00.000Z")
SIZE = 10_000_000
MINT_L1 = "LaunchMintL1111111111111111111111111111111"
MINT_L2 = "LaunchMintL2222222222222222222222222222222"
MINT_L4 = "LaunchMintL4444444444444444444444444444444"
SYNTH = "SynthLaunchMint"


def _snapshots(name: str) -> list[TickSnapshot]:
    data = load_dataset(FIXTURES / name)
    return sorted((tick_snapshot(event) for event in data.events), key=lambda tick: tick.ts)


def _t(
    ts: float,
    price: int,
    *,
    launch: float = 0.0,
    buyers: int = 10,
    progress: float = 0.0,
    mint: str = SYNTH,
) -> TickSnapshot:
    return TickSnapshot(
        mint=mint,
        ts=ts,
        launch_ts=launch,
        price_lamports=price,
        unique_buyers=buyers,
        curve_progress=progress,
    )


async def _fills(ticks: Sequence[TickSnapshot]) -> list[tuple[float, str, str, int]]:
    clock = FixtureClock(start=0.0)
    out: list[tuple[float, str, str, int]] = []

    async def sink(intents: tuple[Intent, ...]) -> None:
        for intent in intents:
            out.append((clock.now(), intent.mint, intent.side, intent.size_lamports))

    runtime = StrategyRuntime(clock=clock, strategies=(NewLaunchSniper(),), sink=sink)
    await runtime.run(ticks)
    return out


def test_strat_launch_fixture_yields_the_asserted_fills() -> None:
    fills = asyncio.run(_fills(_snapshots("strat-launch")))
    assert fills == [
        (START + 0, MINT_L4, "buy", SIZE),
        (START + 30, MINT_L2, "buy", SIZE),
        (START + 60, MINT_L1, "buy", SIZE),
        (START + 180, MINT_L1, "sell", SIZE),
    ]


@pytest.mark.parametrize(("age", "bought"), [(300, True), (301, False)])
def test_age_flips_exactly_at_the_max_age_bound(age: float, bought: bool) -> None:
    fills = asyncio.run(_fills([_t(age, 1_000_000_000, launch=0.0, buyers=5)]))
    assert [side for _, _, side, _ in fills] == (["buy"] if bought else [])


@pytest.mark.parametrize(("buyers", "bought"), [(4, False), (5, True)])
def test_buyers_flip_exactly_at_the_floor(buyers: int, bought: bool) -> None:
    fills = asyncio.run(_fills([_t(60, 1_000_000_000, buyers=buyers)]))
    assert [side for _, _, side, _ in fills] == (["buy"] if bought else [])


@pytest.mark.parametrize(("progress", "bought"), [(0.1, True), (0.10000000001, False)])
def test_curve_progress_flips_exactly_at_the_ceiling(progress: float, bought: bool) -> None:
    fills = asyncio.run(_fills([_t(60, 8_500_000_000, buyers=5, progress=progress)]))
    assert [side for _, _, side, _ in fills] == (["buy"] if bought else [])


@pytest.mark.parametrize(("exit_price", "sold"), [(179, False), (180, True)])
def test_take_profit_flips_exactly_at_the_target(exit_price: int, sold: bool) -> None:
    ticks = [_t(0, 100, buyers=10), _t(10, exit_price, buyers=10)]
    fills = asyncio.run(_fills(ticks))
    assert [side for _, _, side, _ in fills] == (["buy", "sell"] if sold else ["buy"])


def test_a_mint_is_entered_once_even_after_it_has_been_sold() -> None:
    ticks = [_t(0, 100), _t(10, 180), _t(20, 100)]
    fills = asyncio.run(_fills(ticks))
    assert [side for _, _, side, _ in fills] == ["buy", "sell"]


def test_mints_are_tracked_separately() -> None:
    other = "SynthLaunchMintB"
    ticks = [_t(0, 100), _t(5, 100, mint=other), _t(10, 180)]
    fills = asyncio.run(_fills(ticks))
    assert [(mint, side) for _, mint, side, _ in fills] == [
        (SYNTH, "buy"),
        (other, "buy"),
        (SYNTH, "sell"),
    ]
