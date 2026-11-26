"""Intent router: the single path from strategy Intent to exec.place (RT-02, D-06).

A strategy emits a frozen :class:`~pumpgrok.strategies.base.Intent`; the only
consumer that may turn it into an order is this router. It validates the
intent against the four registered strategy ids, and below the
``autonomous-paper`` autonomy level it journals a refusal and approves
nothing — no ticket, no approval, no ``place`` call. At autonomy it
allocates the ticket, mints the approval, records the ticket attribution
ref, and places exactly one order through the injected ``place``.

The router imports no execution adapter and no network client: ``place`` is
injected, so tests pass a recording fake and the live-data paper root binds
the real paper adapter.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.ledger.autonomy import read_autonomy
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.strategy_state import record_attribution_ref
from pumpgrok.ledger.tickets import allocate_ticket
from pumpgrok.replay.clock import Clock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.strategies.base import Intent
from pumpgrok.strategies.registry import is_known_strategy

__all__ = ["IntentRouter", "Place", "RouteResult"]

#: Injected order placement: the only path from an Intent to exec.place.
Place = Callable[[OrderRequest], Awaitable[Any]]

_AUTONOMOUS = "autonomous-paper"


@dataclass(frozen=True)
class RouteResult:
    """Outcome of routing one Intent; refusals carry no ticket or approval."""

    status: str  # "placed" | "refused"
    strategy_id: str
    ticket_id: str | None = None
    approval_id: str | None = None
    reason: str = ""


class IntentRouter:
    """Route strategy Intents to ``place`` with ticket and approval allocation."""

    def __init__(
        self,
        *,
        store: LedgerStore,
        place: Place,
        clock: Clock,
        autonomy: str | Callable[[], str] | None = None,
        seat: str = "desk",
        source: str = "paper",
        correlation_id: str = "intent-router",
        max_slippage_bps: int = 100,
    ) -> None:
        self._store = store
        self._place = place
        self._clock = clock
        self._autonomy = autonomy
        self._seat = seat
        self._source = source
        self._correlation_id = correlation_id
        self._max_slippage_bps = max_slippage_bps
        self._ids = IdFactory(clock, make_rng())

    def _level(self) -> str:
        """The current autonomy level: injected, or read from the ledger."""
        if callable(self._autonomy):
            return str(self._autonomy())
        if isinstance(self._autonomy, str):
            return self._autonomy
        return read_autonomy(self._store)

    def _journal_refusal(self, intent: Intent, reason: str) -> None:
        """Record a below-autonomy refusal as a journal row, never silently."""
        ts_utc = format_ts_utc(self._clock.now())
        self._store.append(
            ts_utc=ts_utc,
            source=self._source,
            correlation_id=self._correlation_id,
            idempotency_key=(
                f"intent-refusal|{intent.strategy_id}|{intent.mint}|"
                f"{intent.side}|{intent.size_lamports}|{ts_utc}"
            ),
            type="JournalNote",
            payload={
                "source": self._source,
                "seat": self._seat,
                "note_kind": "note",
                "text": (
                    f"intent refused {intent.strategy_id} {intent.side} "
                    f"{intent.mint} {intent.size_lamports}: {reason}"
                ),
                "refs": [],
            },
        )

    async def route(self, intent: Intent) -> RouteResult:
        """Route one Intent: refused with a journal row below autonomy, else placed."""
        strategy_id = intent.strategy_id
        if not is_known_strategy(strategy_id):
            self._journal_refusal(intent, f"unknown strategy id {strategy_id!r}")
            return RouteResult(
                status="refused",
                strategy_id=strategy_id,
                reason=f"unknown strategy id {strategy_id!r}",
            )
        if intent.side not in ("buy", "sell"):
            self._journal_refusal(intent, f"bad side {intent.side!r}")
            return RouteResult(
                status="refused",
                strategy_id=strategy_id,
                reason=f"bad side {intent.side!r}",
            )
        level = self._level()
        if level != _AUTONOMOUS:
            reason = f"below autonomous-paper: {level}"
            self._journal_refusal(intent, reason)
            return RouteResult(status="refused", strategy_id=strategy_id, reason=reason)

        ts_utc = format_ts_utc(self._clock.now())
        ticket_id = allocate_ticket(
            self._store,
            ts_utc=ts_utc,
            source=self._source,
            correlation_id=self._correlation_id,
            seat=self._seat,
            title=f"intent {strategy_id} {intent.side} {intent.mint}",
        )
        approval_id = f"apr-{self._ids.ulid()}"
        record_attribution_ref(
            self._store,
            strategy_id=strategy_id,
            ticket_id=ticket_id,
            mint=intent.mint,
            ts_utc=ts_utc,
            source=self._source,
            correlation_id=self._correlation_id,
        )
        request = OrderRequest(
            ticket_id=ticket_id,
            mint=intent.mint,
            side=Side.BUY if intent.side == "buy" else Side.SELL,
            decision_id=self._ids.ulid(),
            size_lamports=intent.size_lamports,
            max_slippage_bps=self._max_slippage_bps,
            approval_id=approval_id,
            correlation_id=self._correlation_id,
        )
        await self._place(request)
        return RouteResult(
            status="placed",
            strategy_id=strategy_id,
            ticket_id=ticket_id,
            approval_id=approval_id,
        )
