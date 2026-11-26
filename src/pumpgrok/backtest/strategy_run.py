<<<<<<< HEAD
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
=======
"""Strategy-aware replay: one strategy, one fixture clock, intents through the router (BT-12).

The runner builds the strategy from the static registry and drives
:class:`StrategyRuntime` on a :class:`FixtureClock` over :class:`DatasetCurveSource`.
Every strategy Intent is handed to :class:`IntentRouter`. The paper adapter is the
offline replay sandbox, which selects :data:`PAPER_DEFAULT_FEE_MODEL` (fee model v2,
pinned ATA rent). This module never opens a socket and never imports an RPC or LLM client.

legacy_screening is the registry class: its hook calls the existing screening decision.
This module does not place orders itself. Exit-rule sells stay on the supervisor exit
pass, which is not a strategy Intent.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
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
        ledger = (
            Path(ledger_path)
            if ledger_path is not None
            else Path(tempfile.mkdtemp(prefix="pumpgrok-stratrun-")) / "ledger.sqlite"
        )
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
=======
import asyncio
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from pumpgrok.backtest.equity import equity_lamports
from pumpgrok.backtest.event_source import DatasetCurveSource
from pumpgrok.backtest.metrics import MetricsContext
from pumpgrok.backtest.metrics_v2 import MetricsV2, summarize_v2
from pumpgrok.backtest.roundtrip import RoundTrips, round_trips
from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.ids import CorrelationId, bind_calling_seat, bind_correlation
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.fees import PAPER_DEFAULT_FEE_MODEL
from pumpgrok.ledger.autonomy import autonomy_rows
from pumpgrok.ledger.deposit_reader import position_deposits_by_seq
from pumpgrok.ledger.reducer import reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.ticket_refs import load_refs
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.fixtures import event_epoch
from pumpgrok.replay.runner import ReplayTrade
from pumpgrok.risk.engine.constants import BUY_SEAT, SELL_SEAT
from pumpgrok.strategies.allocation import slice_lamports
from pumpgrok.strategies.attribution import desk_genesis, desk_net_lamports
from pumpgrok.strategies.base import Intent, Strategy
from pumpgrok.strategies.legacy import tick_snapshot
from pumpgrok.strategies.registry import STRATEGIES
from pumpgrok.strategies.runtime import StrategyRuntime
from pumpgrok.supervisor.intent_router import IntentRouter
from pumpgrok.supervisor.scheduler.orders import _replay_trading, _run_exit_rules
from pumpgrok.supervisor.scheduler.replay_runtime import (
    _await_order,
    _replay_trade,
    open_replay_runtime,
)

__all__ = ["StrategyRun", "run_strategy"]

#: The smoke parity seed. Two calls with the same seed and a fresh ledger match.
_PARITY_SEED = 20260101
#: One strategy's capital slice: 0.20 of paper equity, the registered weight.
_SLICE_BPS = 2_000
#: Replay slippage, the same bound the offline sandbox uses for a recorded fill.
_SLIPPAGE_BPS = 100
_PLACE_FIELDS = (
    "ticket_id",
    "mint",
    "side",
    "decision_id",
    "size_lamports",
    "token_units",
    "max_slippage_bps",
    "approval_id",
    "quote_id",
    "exit_reason",
)
_SECONDS_PER_DAY = Decimal(86400)
_ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


@dataclass(frozen=True)
class StrategyRun:
    """Fills, round trips and Metrics v2 for one offline strategy replay."""

    strategy_id: str
    fills: tuple[ReplayTrade, ...]
    round_trips: RoundTrips
    metrics_v2: MetricsV2
    net_lamports: int
    ledger_path: Path


def run_strategy(
    strategy_id: str,
    params: Mapping[str, Any],
    dataset_dir: str | Path,
    *,
    seed: int = _PARITY_SEED,
    ledger_path: str | Path | None = None,
) -> StrategyRun:
    """Replay one registered strategy over a fixture dataset.

    ``params`` is empty, or exactly the registered defaults. Overrides are refused:
    the baseline hooks read their class defaults, and this runner does not retune them.
    ``ledger_path`` defaults to a fresh file so a second call does not see the first.
    """
    target = Path(ledger_path) if ledger_path is not None else _fresh_ledger()
    return asyncio.run(
        _run(
            strategy_id,
            params,
            Path(dataset_dir),
            seed=seed,
            ledger_path=target,
        )
    )


def _fresh_ledger() -> Path:
    directory = Path(tempfile.mkdtemp(prefix="strategy-replay-"))
    return directory / "ledger.sqlite"


def _strategy_class(strategy_id: str) -> type[Strategy]:
    for cls in STRATEGIES:
        if cls.strategy_id == strategy_id:
            return cls
    known = ", ".join(cls.strategy_id for cls in STRATEGIES)
    raise ValueError(f"unknown strategy {strategy_id!r}; known: {known}")


def _require_defaults(cls: type[Strategy], params: Mapping[str, Any]) -> None:
    defaults = dict(getattr(cls, "DEFAULTS", {}))
    if not params:
        return
    unknown = sorted(set(params) - set(defaults))
    if unknown:
        raise ValueError(f"unknown parameters for {cls.strategy_id}: {unknown}")
    mismatched = [key for key in params if params[key] != defaults[key]]
    if mismatched:
        raise ValueError(
            f"parameter overrides are not applied for {cls.strategy_id}: {sorted(mismatched)}"
        )


def _place_body(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The place-tool fields. The router also sends a correlation the model forbids."""
    return {key: payload[key] for key in _PLACE_FIELDS if payload.get(key) is not None}


async def _run(
    strategy_id: str,
    params: Mapping[str, Any],
    dataset_dir: Path,
    *,
    seed: int,
    ledger_path: Path,
) -> StrategyRun:
    cls = _strategy_class(strategy_id)
    _require_defaults(cls, params)
    runtime = open_replay_runtime(dataset_dir, FilterSettings(), seed=seed, ledger_path=ledger_path)
    try:
        if runtime.adapter._fees is not PAPER_DEFAULT_FEE_MODEL:
            raise RuntimeError("strategy replay requires the pinned paper fee model")
        if not isinstance(runtime.clock, FixtureClock):
            raise RuntimeError("strategy replay runs on the fixture clock")
        clock = runtime.clock
        source = DatasetCurveSource(runtime.dataset.events, clock=clock)
        _enable_router(runtime.store, format_ts_utc(clock.now()))
        trading = _replay_trading(runtime)
        equity = RiskBudget().paper_equity_lamports
        router = IntentRouter(
            exec_place=_submit(trading, clock),
            risk=runtime.risk,
            store=runtime.store,
            clock=clock,
            ids=runtime.ids,
            slices=slice_lamports(equity, {strategy_id: _SLICE_BPS}),
            max_slippage_bps=_SLIPPAGE_BPS,
        )
        strategy = _build(cls, strategy_id, source, runtime.ids)
        driver = StrategyRuntime(
            clock=clock, strategies=(strategy,), sink=_sink(router, trading, runtime.ids)
        )

        async def before_stamp(_stamp: float) -> None:
            if trading.refresh_marks is not None:
                await trading.refresh_marks()
            runtime.risk.evaluate_halts(source="replay", correlation_id="desk")

        async def after_stamp(_stamp: float) -> None:
            await _run_exit_rules(trading)

        ticks = [tick_snapshot(dict(event)) for event in source.events]
        with bind_correlation(CorrelationId.new(runtime.ids)):
            await driver.run(ticks, before_stamp=before_stamp, after_stamp=after_stamp)
        if not runtime.store.verify():
            raise RuntimeError("strategy replay ledger failed verification")
        return _result(strategy_id, runtime.store, trading.attempts, source, ledger_path)
    finally:
        runtime.store.close()


def _enable_router(store: LedgerStore, ts_utc: str) -> None:
    """The router reads autonomy from the ledger. Offline replay has no operator row yet."""
    store.append_batch(
        autonomy_rows(
            "autonomous-paper",
            "human:replay",
            previous="manual-ticket",
            ts_utc=ts_utc,
            source="replay",
            correlation_id="desk",
        )
    )


def _build(cls: type, strategy_id: str, source: DatasetCurveSource, ids: Any) -> Any:
    if strategy_id == "legacy_screening":
        return cls(events=list(source.events), filter_cfg=FilterSettings(), ids=ids)
    return cls()


def _submit(trading: Any, clock: FixtureClock) -> Any:
    """Turn the router's payload into the granted place tool, and settle virtual time."""
    buy_grant = trading.place
    sell_grant = trading.exit_place

    async def submit(payload: dict[str, Any]) -> dict[str, Any]:
        grant = buy_grant if payload.get("side") == "buy" else sell_grant
        try:
            model = grant.spec.input_model.model_validate(_place_body(payload))
        except ValidationError:
            return {
                "status": "rejected",
                "reason": "invalid_order",
                "ticket_id": str(payload.get("ticket_id", "")),
            }
        settled = await _await_order(clock, grant(model))
        if isinstance(settled, dict):
            return settled
        return cast(dict[str, Any], settled.model_dump(mode="json"))

    return submit


def _routable(intent: Intent, ids: Any, mapped: dict[str, str]) -> Intent:
    """The router requires a ULID decision id. Baseline hooks use a stable string.

    Mint one ULID per string so two runs with the same seed route the same id.
    """
    if _ULID.fullmatch(intent.decision_id):
        return intent
    decision_id = mapped.get(intent.decision_id)
    if decision_id is None:
        decision_id = ids.ulid()
        mapped[intent.decision_id] = decision_id
    return replace(intent, decision_id=decision_id)


def _sink(router: IntentRouter, trading: Any, ids: Any) -> Any:
    mapped: dict[str, str] = {}

    async def sink(intents: tuple[Intent, ...]) -> None:
        for intent in intents:
            if trading.refresh_marks is not None:
                await trading.refresh_marks()
            routable = _routable(intent, ids, mapped)
            seat = BUY_SEAT if routable.side == "buy" else SELL_SEAT
            with bind_calling_seat(seat):
                routed = await router.route(routable)
            place = routed.place
            if place is None:
                trading.attempts.append(
                    ReplayTrade(
                        side=routable.side,
                        mint=routable.mint,
                        outcome="rejected",
                        reason=routed.reason or "refused",
                    )
                )
                continue
            outcome = str(place.get("status", ""))
            raw_reason = place.get("reason")
            reason = str(raw_reason or ("ok" if outcome == "filled" else ""))
            trading.attempts.append(
                _replay_trade(
                    trading.store,
                    side=routable.side,
                    mint=routable.mint,
                    outcome=outcome,
                    reason=reason,
                    decision_id=routable.decision_id,
                )
            )

    return sink


def _result(
    strategy_id: str,
    store: LedgerStore,
    attempts: list[ReplayTrade],
    source: DatasetCurveSource,
    ledger_path: Path,
) -> StrategyRun:
    rows = store.read(limit=None)
    book = round_trips(rows, load_refs(store))
    curve = _equity_curve(store)
    elapsed = _elapsed_days(source.events)
    metrics = summarize_v2(
        book,
        MetricsContext(
            initial_equity_lamports=equity_lamports(_genesis(store)),
            equity_curve_lamports=curve,
            elapsed_days=elapsed,
        ),
    )
    return StrategyRun(
        strategy_id=strategy_id,
        fills=tuple(attempts),
        round_trips=book,
        metrics_v2=metrics,
        net_lamports=_net(store),
        ledger_path=ledger_path,
    )


def _genesis(store: LedgerStore) -> Any:
    return desk_genesis(store)


def _net(store: LedgerStore) -> int:
    return desk_net_lamports(store)


def _equity_curve(store: LedgerStore) -> tuple[int, ...]:
    deposits = position_deposits_by_seq(store)
    state = _genesis(store)
    points: list[int] = []
    for row in store.read(limit=None):
        state = reduce(state, row, deposits)
        if row.get("type") == "FillRecorded":
            points.append(equity_lamports(state))
    return tuple(points)


def _elapsed_days(events: Sequence[Mapping[str, Any]]) -> Decimal:
    if not events:
        return Decimal(0)
    start = Decimal(str(_event_stamp(events[0])))
    end = Decimal(str(_event_stamp(events[-1])))
    if end < start:
        return Decimal(0)
    return (end - start) / _SECONDS_PER_DAY


def _event_stamp(event: Mapping[str, Any]) -> float:
    raw = event.get("ts")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return event_epoch(dict(event))
    return float(raw)
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
