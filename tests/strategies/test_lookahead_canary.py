"""STR-04 / criterion 6: no baseline decision reads a tick that has not happened yet.

For every baseline strategy and every fixture dataset, each decision at or before a cut time T
must be identical whether or not the ticks after T are present. A synthetic spike after T
proves the canary bites: the spike produces a decision, but only after T.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.strategies import Intent, Strategy, TickSnapshot
from pumpgrok.strategies.legacy import tick_snapshot
from pumpgrok.strategies.mean_reversion import MeanReversion
from pumpgrok.strategies.momentum_breakout import MomentumBreakout
from pumpgrok.strategies.new_launch_sniper import NewLaunchSniper
from pumpgrok.strategies.runtime import StrategyRuntime

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "replay"

Fill = tuple[float, str, str, int]


def _snapshots(name: str) -> list[TickSnapshot]:
    data = load_dataset(FIXTURES / name)
    return sorted((tick_snapshot(event) for event in data.events), key=lambda tick: tick.ts)


async def _fills(strategy: Strategy, ticks: Sequence[TickSnapshot]) -> list[Fill]:
    clock = FixtureClock(start=0.0)
    out: list[Fill] = []

    async def sink(intents: tuple[Intent, ...]) -> None:
        for intent in intents:
            out.append((clock.now(), intent.mint, intent.side, intent.size_lamports))

    await StrategyRuntime(clock=clock, strategies=(strategy,), sink=sink).run(ticks)
    return out


CASES: list[tuple[Callable[[], Strategy], str]] = [
    (MomentumBreakout, "strat-breakout"),
    (NewLaunchSniper, "strat-launch"),
    (MeanReversion, "strat-reversion"),
]


@pytest.mark.parametrize(("factory", "dataset"), CASES)
def test_decisions_up_to_each_cut_ignore_later_ticks(
    factory: Callable[[], Strategy], dataset: str
) -> None:
    ticks = _snapshots(dataset)
    full = asyncio.run(_fills(factory(), ticks))
    assert full, "the canary needs a dataset that produces decisions"
    for cut in ticks:
        prefix = [tick for tick in ticks if tick.ts <= cut.ts]
        through_cut = asyncio.run(_fills(factory(), prefix))
        assert through_cut == [fill for fill in full if fill[0] <= cut.ts], cut.ts


def test_a_spike_after_t_changes_only_decisions_after_t() -> None:
    flat = [
        TickSnapshot("SpikeMint", float(ts), 0.0, 1_000_000, 10, 0.0) for ts in range(0, 101, 10)
    ]
    spike = TickSnapshot("SpikeMint", 101.0, 0.0, 5_000_000, 10, 0.0)
    full = asyncio.run(_fills(MomentumBreakout(), [*flat, spike]))
    before = asyncio.run(_fills(MomentumBreakout(), flat))
    assert before == []
    assert full == [(101.0, "SpikeMint", "buy", 10_000_000)]
