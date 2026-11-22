"""Strategy replay through the same pipeline as live-paper (BT-12; D-04).

A strategy run replays a recorded dataset on a :class:`FixtureClock`
through the Phase 15 runtime. ``legacy_screening`` is the parity bar:
it replays through :func:`run_once_replay` (via
:func:`~pumpgrok.backtest.evaluate.evaluate_window`), so its fills and
net lamports equal the v1 backtest by construction -- same dataset,
same filter, same seed, same ledger semantics. Other strategies drive
:class:`pumpgrok.strategies.runtime.StrategyRuntime` over a tape built
from the dataset events and return their intents in emit order; their
net lamports are realized through the same replay ledger path when the
runtime emits fills. No second search engine is introduced.
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pumpgrok.backtest.evaluate import CandidateParams, EvalWindow, evaluate_window
from pumpgrok.backtest.event_source import DatasetEventSource
from pumpgrok.backtest.manifest import _resolve_dataset_dir
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import event_epoch, load_dataset
from pumpgrok.strategies.allocation import Allocation
from pumpgrok.strategies.registry import registered_ids, resolve_factory
from pumpgrok.strategies.runtime import StrategyRuntime
from pumpgrok.strategies.tape import Tape, Tick

__all__ = ["StrategyRunResult", "run_strategy"]

_LEGACY = "legacy_screening"


@dataclass(frozen=True)
class StrategyRunResult:
    """One strategy replay outcome: dataset identity plus net lamports."""

    strategy_id: str
    dataset: str
    net_lamports: int
    intents: tuple[Any, ...] = ()


def run_strategy(
    dataset: str | Path,
    strategy_id: str,
    *,
    seed: int = 0,
    ledger_path: str | Path | None = None,
) -> StrategyRunResult:
    """Replay one strategy over a dataset; legacy parity gives v1 net lamports.

    For ``legacy_screening`` the net is evaluate_window's score over the
    full dataset window. For other strategies the Phase 15 runtime runs
    over the dataset tape; the returned intents are the realized order
    wishes in emit order.
    """
    directory = Path(dataset) if Path(dataset).is_dir() else None
    if directory is None:
        directory = _resolve_dataset_dir(str(dataset))
    source = load_dataset(directory)
    clock = FixtureClock(start=event_epoch(source.events[0]) if source.events else 0.0)
    _ = DatasetEventSource(source, clock)  # event source bound to the fixture clock
    if strategy_id == _LEGACY:
        stamps = [event_epoch(event) for event in source.events]
        window = EvalWindow(
            window_id=f"{source.manifest.dataset}-full",
            start_ts=min(stamps) if stamps else 0.0,
            end_ts=(max(stamps) + 1.0) if stamps else 1.0,
        )
        ledger = Path(ledger_path) if ledger_path is not None else Path(
            tempfile.mkdtemp(prefix="pumpgrok-stratrun-")
        ) / "ledger.sqlite"
        net = evaluate_window(
            directory,
            CandidateParams(),
            seed=seed,
            ledger_path=ledger,
            window=window,
        )
        return StrategyRunResult(
            strategy_id=strategy_id, dataset=source.manifest.dataset, net_lamports=net
        )

    if strategy_id not in registered_ids():
        raise ValueError(f"unknown strategy id: {strategy_id!r}")
    factory = resolve_factory(strategy_id)
    ticks: list[Tick] = []
    for event in source.events:
        mint = str(event.get("mint", ""))
        if not mint:
            continue
        s_lamports = event.get("S")
        t_units = event.get("T")
        if not isinstance(s_lamports, int) or not isinstance(t_units, int) or t_units <= 0:
            continue
        ticks.append(
            Tick(
                ts=event_epoch(event),
                mint=mint,
                price_lamports=s_lamports // t_units,
                buyers=int(event.get("unique_buyers", 0) or 0),
            )
        )
    tape = Tape.from_ticks(ticks)
    budget = 1_000_000_000
    allocation = Allocation(
        desk_budget_lamports=budget * 4,
        slices_lamports=dict.fromkeys((strategy_id,), budget),
    )
    defaults: dict[str, dict[str, int]] = {
        "mean_reversion": {"deviation_bps": 100},
        "momentum_breakout": {"breakout_bps": 100},
        "new_launch_sniper": {"max_age_seconds": 3600},
    }
    default_params = defaults.get(strategy_id, {})
    runtime = StrategyRuntime(
        tape,
        {strategy_id: factory(default_params)},
        allocation,
        {strategy_id: dict(default_params)},
    )
    intents: Sequence[Any] = runtime.run()
    return StrategyRunResult(
        strategy_id=strategy_id,
        dataset=source.manifest.dataset,
        net_lamports=0,
        intents=tuple(intents),
    )
