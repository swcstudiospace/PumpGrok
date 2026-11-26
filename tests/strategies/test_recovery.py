<<<<<<< HEAD
"""RT-04 (library half): restart restores tapes, peaks and probation."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.strategies.recovery import RecoveryStore
from pumpgrok.strategies.tape import Tape, Tick


def test_restart_restores_state_byte_identically(tmp_path: Path) -> None:
    tape = Tape.from_ticks(
        [
            Tick(ts=1.0, mint="MintA", price_lamports=1000, buyers=7, created_ts=0.0),
            Tick(ts=2.0, mint="MintA", price_lamports=1500, buyers=9, created_ts=0.0),
        ]
    )
    RecoveryStore(tmp_path / "recovery.json").save(
        "momentum_breakout",
        tape=tape,
        peaks={"MintA": 1500},
        probation={"MintA": True},
    )

    # Simulate a restart: a fresh store over the same file.
    restored = RecoveryStore(tmp_path / "recovery.json").load("momentum_breakout")
    assert restored.strategy_id == "momentum_breakout"
    assert restored.ticks == tape.ticks
    assert restored.peaks == {"MintA": 1500}
    assert restored.probation == {"MintA": True}


def test_unknown_strategy_restores_empty(tmp_path: Path) -> None:
    restored = RecoveryStore(tmp_path / "recovery.json").load("mean_reversion")
    assert restored.ticks == ()
    assert restored.peaks == {}
    assert restored.probation == {}
=======
"""RT-04 library half / criterion 8: restart recovery restores tapes, peaks and probation.

Each baseline strategy runs its fixture up to a split time with positions open, its book is
saved to strategy_state, a fresh strategy restores it, and the restored book must equal the
saved book by hash. Continuing the fresh strategy over the remaining ticks must produce the same
fills as one uninterrupted run.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, parse_ts_utc
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.strategies import Intent, Strategy, TickSnapshot
from pumpgrok.strategies.legacy import tick_snapshot
from pumpgrok.strategies.mean_reversion import MeanReversion
from pumpgrok.strategies.momentum_breakout import MomentumBreakout
from pumpgrok.strategies.new_launch_sniper import NewLaunchSniper
from pumpgrok.strategies.recovery import restore_state, save_state
from pumpgrok.strategies.runtime import StrategyRuntime

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "replay"
START = parse_ts_utc("2026-01-01T00:00:00.000Z")

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


CASES: list[tuple[Callable[[], Strategy], str, float]] = [
    # BreakMintA is open with its peak at 1.5e6 at t=40.
    (MomentumBreakout, "strat-breakout", 40.0),
    # LaunchMintL1 and LaunchMintL2 are open at t=60.
    (NewLaunchSniper, "strat-launch", 60.0),
    # RevertMintR1 and RevertMintR2 are open at t=25.
    (MeanReversion, "strat-reversion", 25.0),
]


@pytest.mark.parametrize(("factory", "dataset", "split"), CASES)
def test_restart_restores_tapes_peaks_and_probation(
    tmp_path: Path, factory: Callable[[], Strategy], dataset: str, split: float
) -> None:
    ticks = _snapshots(dataset)
    head = [tick for tick in ticks if tick.ts <= START + split]
    tail = [tick for tick in ticks if tick.ts > START + split]
    uninterrupted = asyncio.run(_fills(factory(), ticks))

    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        before = factory()
        head_fills = asyncio.run(_fills(before, head))
        assert before.book.positions, "the split must leave a position open"
        digest = save_state(store, before)

        after = factory()
        assert restore_state(store, after) is True
        assert after.book.to_dict() == before.book.to_dict()
        assert save_state(store, after) == digest
        tail_fills = asyncio.run(_fills(after, tail))
    finally:
        store.close()

    assert head_fills + tail_fills == uninterrupted


def test_restore_without_a_saved_state_leaves_the_book_fresh(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        strategy = MomentumBreakout()
        fresh = strategy.book.to_dict()
        assert restore_state(store, strategy) is False
        assert strategy.book.to_dict() == fresh
    finally:
        store.close()
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
