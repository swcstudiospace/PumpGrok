"""Live-data paper composition root (MKT-09, D-06).

Composes the Phase 13 datafeed into a paper desk: the fail-closed live price
source, the held-mint marks loop, the 15-03 strategy runtime under slice
allocation, and the Intent router as the only path to order placement.

The root refuses to build unless the execution mode is paper — a live mode
raises :class:`LivePaperError` before any component is constructed. Feed
access goes through the read-only allowlist only: :meth:`LivePaperDesk.feed_call`
checks the method name before touching the transport, so nothing outside the
five allowlisted read methods is reachable from this root.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pumpgrok.core.adapter import ExecutionMode
from pumpgrok.datafeed.marks import MarksLoop
from pumpgrok.datafeed.mintbook import MintBook
from pumpgrok.datafeed.price import LivePriceSource
from pumpgrok.datafeed.readonly import ALLOWED_METHODS, guarded_call
from pumpgrok.execution.entry_hook import EntryHook
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import Clock, FixtureClock, WallClock
from pumpgrok.risk.entry_checks import EntryChecks
from pumpgrok.strategies.allocation import Allocation
from pumpgrok.strategies.registry import is_known_strategy, resolve_factory
from pumpgrok.strategies.runtime import StrategyRuntime
from pumpgrok.strategies.tape import Tape
from pumpgrok.supervisor.intent_router import IntentRouter, Place

__all__ = ["LivePaperDesk", "LivePaperError", "build_live_paper", "strategy_factory"]


class LivePaperError(ValueError):
    """The live-data paper root refused to build."""


def strategy_factory(strategy_id: str) -> type[Any]:
    """Resolve one strategy class through the registry, guarding its fallback.

    The registry's ``resolve_factory`` falls back to returning the module
    object when the named class is absent; a module is not a strategy
    constructor, so the guard refuses it instead of calling it.
    """
    if not is_known_strategy(strategy_id):
        raise LivePaperError(f"unknown strategy id: {strategy_id!r}")
    factory = resolve_factory(strategy_id)
    if not isinstance(factory, type):
        raise LivePaperError(
            f"registry returned no strategy class for {strategy_id!r} "
            f"(got {type(factory).__name__})"
        )
    return factory


@dataclass(frozen=True)
class LivePaperDesk:
    """The composed live-data paper desk; feed access is allowlist-guarded."""

    mode: str
    store: LedgerStore
    clock: Clock
    prices: LivePriceSource
    book: MintBook
    marks: MarksLoop
    runtime: StrategyRuntime
    router: IntentRouter
    allocation: Allocation
    allowed_methods: frozenset[str] = ALLOWED_METHODS
    entry_checks: EntryChecks | None = None
    entry_hook: EntryHook = field(default_factory=EntryHook)

    def feed_call(self, method: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Call the transport only when ``method`` is on the read-only allowlist."""
        return guarded_call(method, fn, *args, **kwargs)


def build_live_paper(
    *,
    mode: ExecutionMode | str,
    store: LedgerStore,
    clock: Clock,
    place: Place,
    strategy_ids: tuple[str, ...] = ("momentum_breakout",),
    params: dict[str, dict[str, Any]] | None = None,
    desk_budget_lamports: int = 1_000_000_000,
    slices_lamports: dict[str, int] | None = None,
    tape: Tape | None = None,
    entry_checks: EntryChecks | None = None,
) -> LivePaperDesk:
    """Compose the paper desk; refuse unless the execution mode is paper."""
    if mode != ExecutionMode.PAPER:
        raise LivePaperError(f"live-data paper root needs paper mode, got {mode!r}")
    if not isinstance(clock, (FixtureClock, WallClock)):
        raise LivePaperError("live-data paper root needs a fixture or wall clock")

    params = params or {}
    strategies: dict[str, Any] = {}
    for strategy_id in strategy_ids:
        strategies[strategy_id] = strategy_factory(strategy_id)(params.get(strategy_id, {}))

    allocation = Allocation(
        desk_budget_lamports=desk_budget_lamports,
        slices_lamports=(
            dict(slices_lamports)
            if slices_lamports is not None
            else dict.fromkeys(strategies, desk_budget_lamports)
        ),
    )
    runtime = StrategyRuntime(
        tape=tape if tape is not None else Tape(),
        strategies=strategies,
        allocation=allocation,
        params=params,
    )
    prices = LivePriceSource()
    book = MintBook()
    marks = MarksLoop(
        book,
        clock,
        lambda mint: prices.price(mint, now_epoch=clock.now()),
        lambda mint, price: None,
    )
    router = IntentRouter(store=store, place=place, clock=clock)
    return LivePaperDesk(
        mode=str(mode),
        store=store,
        clock=clock,
        prices=prices,
        book=book,
        marks=marks,
        runtime=runtime,
        router=router,
        allocation=allocation,
        entry_checks=entry_checks,
        entry_hook=EntryHook(),
    )
