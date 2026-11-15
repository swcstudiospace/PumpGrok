"""STR-04 / criterion 6: momentum_breakout flips exactly at each bound; strat-breakout fills.

Hand computation of tests/fixtures/replay/strat-breakout, lookback 300 s, breakout 20%,
stop 25%, max hold 900 s, entry size 10_000_000 lamports:

- BreakMintA: prices 1.0e6 at t=0, 10, 20 (window high 1.0e6, breakout threshold 1.2e6).
  t=30 price 1.2e6 equals the threshold -> BUY (entry 1.2e6).
  t=40 1.5e6 holds (peak). t=60 1.0e6 holds (above the stop 0.9e6).
  t=70 0.9e6 equals the stop 1.2e6 * 0.75 -> SELL (stop).
- BreakMintB: prices 2.0e6 at t=100, 110 (window high 2.0e6, threshold 2.4e6).
  t=120 2.4e6 equals the threshold -> BUY (entry 2.4e6).
  t=200 2.5e6 and t=500 2.0e6 hold (stop 1.8e6 not reached).
  t=1019 is 899 s after entry and holds; t=1020 is 900 s -> SELL (max hold).

Expected fills, (seconds after 2026-01-01T00:00:00Z, mint, side):
  (30, A, buy), (70, A, sell), (120, B, buy), (1020, B, sell).
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
from pumpgrok.strategies.momentum_breakout import MomentumBreakout
from pumpgrok.strategies.runtime import StrategyRuntime

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "replay"
START = parse_ts_utc("2026-01-01T00:00:00.000Z")
SIZE = 10_000_000
MINT_A = "BreakMintAAAA1111111111111111111111111111111"
MINT_B = "BreakMintBBBB2222222222222222222222222222222"
SYNTH = "SynthBreakoutMint"


def _snapshots(name: str) -> list[TickSnapshot]:
    data = load_dataset(FIXTURES / name)
    return sorted((tick_snapshot(event) for event in data.events), key=lambda tick: tick.ts)


def _t(ts: float, price: int, mint: str = SYNTH) -> TickSnapshot:
    return TickSnapshot(
        mint=mint, ts=ts, launch_ts=0.0, price_lamports=price, unique_buyers=10, curve_progress=0.0
    )


async def _fills(
    ticks: Sequence[TickSnapshot],
) -> list[tuple[float, str, str, int]]:
    clock = FixtureClock(start=0.0)
    out: list[tuple[float, str, str, int]] = []

    async def sink(intents: tuple[Intent, ...]) -> None:
        for intent in intents:
            out.append((clock.now(), intent.mint, intent.side, intent.size_lamports))

    runtime = StrategyRuntime(clock=clock, strategies=(MomentumBreakout(),), sink=sink)
    await runtime.run(ticks)
    return out


def test_strat_breakout_fixture_yields_the_asserted_fills() -> None:
    fills = asyncio.run(_fills(_snapshots("strat-breakout")))
    assert fills == [
        (START + 30, MINT_A, "buy", SIZE),
        (START + 70, MINT_A, "sell", SIZE),
        (START + 120, MINT_B, "buy", SIZE),
        (START + 1020, MINT_B, "sell", SIZE),
    ]


@pytest.mark.parametrize(("price", "bought"), [(1_199_999, False), (1_200_000, True)])
def test_entry_flips_exactly_at_the_breakout_bound(price: int, bought: bool) -> None:
    fills = asyncio.run(_fills([_t(0, 1_000_000), _t(10, price)]))
    assert [side for _, _, side, _ in fills] == (["buy"] if bought else [])


@pytest.mark.parametrize(("price", "sold"), [(900_001, False), (900_000, True)])
def test_stop_flips_exactly_at_the_stop_bound(price: int, sold: bool) -> None:
    fills = asyncio.run(_fills([_t(0, 1_000_000), _t(10, 1_200_000), _t(20, price)]))
    assert [side for _, _, side, _ in fills] == (["buy", "sell"] if sold else ["buy"])


@pytest.mark.parametrize(("hold_end", "sold"), [(909, False), (910, True)])
def test_max_hold_flips_exactly_at_the_hold_bound(hold_end: float, sold: bool) -> None:
    ticks = [_t(0, 1_000_000), _t(10, 1_200_000), _t(hold_end, 1_200_000)]
    fills = asyncio.run(_fills(ticks))
    assert [side for _, _, side, _ in fills] == (["buy", "sell"] if sold else ["buy"])


@pytest.mark.parametrize(("breakout_ts", "bought"), [(300, True), (301, False)])
def test_lookback_flips_exactly_at_the_window_edge(breakout_ts: float, bought: bool) -> None:
    fills = asyncio.run(_fills([_t(0, 1_000_000), _t(breakout_ts, 1_200_000)]))
    assert [side for _, _, side, _ in fills] == (["buy"] if bought else [])


def test_a_held_position_is_not_bought_again() -> None:
    ticks = [_t(0, 1_000_000), _t(10, 1_200_000), _t(20, 1_500_000), _t(30, 2_000_000)]
    fills = asyncio.run(_fills(ticks))
    assert [side for _, _, side, _ in fills] == ["buy"]
