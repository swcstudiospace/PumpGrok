"""STR-04 / criterion 6: mean_reversion flips exactly at each bound; strat-reversion fills.

Statistics are population statistics over the prior ticks of the same mint inside the window
(exclusive of the current tick), computed in exact rational arithmetic.

Hand computation of tests/fixtures/replay/strat-reversion, window 600 s, z 2.0, max hold
900 s, stop 15%, entry size 10_000_000 lamports:

- RevertMintR1: prices 90e6 (t=0), 110e6 (t=10): mean 100e6, variance 100e12, sd 10e6.
  t=20 price 80e6 equals mean - 2 sd -> BUY.
  t=30 price 95e6 is above the window mean of {90, 110, 80} = 93.33e6 -> SELL (at the mean).
  t=40 price 70e6: window {90, 110, 80, 95}, mean 93.75e6, variance 117.1875e12;
  (93.75 - 70)^2 = 564.06 >= 4 * 117.19 = 468.75 -> BUY.
  t=50 price 100e6 is above the window mean of {90, 110, 80, 95, 70} = 89e6 -> SELL (at the mean).
- RevertMintR2: 90e6 (t=5), 110e6 (t=15), 80e6 (t=25) -> BUY at t=25.
  t=35 price 68e6 equals the stop 80e6 * 0.85 -> SELL (stop).

Expected fills, (seconds after 2026-01-01T00:00:00Z, mint, side):
  (20, R1, buy), (25, R2, buy), (30, R1, sell), (35, R2, sell), (40, R1, buy), (50, R1, sell).
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
from pumpgrok.strategies.mean_reversion import MeanReversion
from pumpgrok.strategies.runtime import StrategyRuntime

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "replay"
START = parse_ts_utc("2026-01-01T00:00:00.000Z")
SIZE = 10_000_000
MINT_R1 = "RevertMintR1111111111111111111111111111111"
MINT_R2 = "RevertMintR2222222222222222222222222222222"
SYNTH = "SynthRevertMint"


def _snapshots(name: str) -> list[TickSnapshot]:
    data = load_dataset(FIXTURES / name)
    return sorted((tick_snapshot(event) for event in data.events), key=lambda tick: tick.ts)


def _t(ts: float, price: int, mint: str = SYNTH) -> TickSnapshot:
    return TickSnapshot(
        mint=mint, ts=ts, launch_ts=0.0, price_lamports=price, unique_buyers=10, curve_progress=0.0
    )


async def _fills(ticks: Sequence[TickSnapshot]) -> list[tuple[float, str, str, int]]:
    clock = FixtureClock(start=0.0)
    out: list[tuple[float, str, str, int]] = []

    async def sink(intents: tuple[Intent, ...]) -> None:
        for intent in intents:
            out.append((clock.now(), intent.mint, intent.side, intent.size_lamports))

    runtime = StrategyRuntime(clock=clock, strategies=(MeanReversion(),), sink=sink)
    await runtime.run(ticks)
    return out


def test_strat_reversion_fixture_yields_the_asserted_fills() -> None:
    fills = asyncio.run(_fills(_snapshots("strat-reversion")))
    assert fills == [
        (START + 20, MINT_R1, "buy", SIZE),
        (START + 25, MINT_R2, "buy", SIZE),
        (START + 30, MINT_R1, "sell", SIZE),
        (START + 35, MINT_R2, "sell", SIZE),
        (START + 40, MINT_R1, "buy", SIZE),
        (START + 50, MINT_R1, "sell", SIZE),
    ]


@pytest.mark.parametrize(("price", "bought"), [(19, True), (20, True), (21, False)])
def test_entry_flips_exactly_at_mean_minus_z_sigma(price: int, bought: bool) -> None:
    # Window {60, 140}: mean 100, population variance 1600, sd 40; z 2 gives a threshold of 20.
    fills = asyncio.run(_fills([_t(0, 60), _t(10, 140), _t(20, price)]))
    assert [side for _, _, side, _ in fills] == (["buy"] if bought else [])


def test_zero_variance_window_never_triggers_entry() -> None:
    fills = asyncio.run(_fills([_t(0, 100), _t(10, 100), _t(20, 0)]))
    assert fills == []


@pytest.mark.parametrize(("exit_price", "sold"), [(69, False), (70, True)])
def test_mean_exit_flips_exactly_at_the_mean(exit_price: int, sold: bool) -> None:
    # Entry at 20 (t=20). Window at t=40 is {60, 140, 20, 60}: mean exactly 70.
    ticks = [_t(0, 60), _t(10, 140), _t(20, 20), _t(30, 60), _t(40, exit_price)]
    fills = asyncio.run(_fills(ticks))
    assert [side for _, _, side, _ in fills] == (["buy", "sell"] if sold else ["buy"])


@pytest.mark.parametrize(("stop_price", "sold"), [(69, False), (68, True)])
def test_stop_flips_exactly_at_the_stop_bound(stop_price: int, sold: bool) -> None:
    # Entry at 80 (t=20); stop 80 * 0.85 = 68.
    ticks = [_t(0, 90), _t(10, 110), _t(20, 80), _t(30, stop_price)]
    fills = asyncio.run(_fills(ticks))
    assert [side for _, _, side, _ in fills] == (["buy", "sell"] if sold else ["buy"])


@pytest.mark.parametrize(("hold_end", "sold"), [(919, False), (920, True)])
def test_max_hold_flips_exactly_at_the_hold_bound(hold_end: float, sold: bool) -> None:
    # Entry at t=20; the window is empty by t=919, so only the stop and hold rules apply.
    ticks = [_t(0, 90), _t(10, 110), _t(20, 80), _t(30, 79), _t(hold_end, 79)]
    fills = asyncio.run(_fills(ticks))
    assert [side for _, _, side, _ in fills] == (["buy", "sell"] if sold else ["buy"])


def test_mints_are_tracked_separately() -> None:
    fills = asyncio.run(
        _fills([_t(0, 90, MINT_R1), _t(5, 90, MINT_R2), _t(10, 110, MINT_R1), _t(15, 110, MINT_R2)])
    )
    assert fills == []
