<<<<<<< HEAD
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
=======
"""Intent router: the only path from a strategy Intent to exec.place (RT-02, criterion 11).

``route`` runs in this order:

1. A decision already routed (its link row exists) returns ``duplicate``. Nothing is placed.
   A decision is routed at most once, so a repeat never makes a second ticket or order.
2. Below autonomous-paper, read from the ledger by ``read_autonomy``, the router journals a
   refusal and returns ``refused``. It calls neither RiskEngine.check nor exec.place, and it
   approves nothing.
3. ``allocate_ticket`` takes the next ticket id. A failed allocation is journaled, not raised.
4. ``append_with_ticket_ref`` links the ticket to its strategy. The link row carries the
   decision's idempotency key, which is what makes step 1 work.
5. An intent over its strategy's slice, or from an unknown strategy, is refused.
6. ``RiskEngine.check`` mints the autonomous_paper approval. The router never builds one. A
   refusal, or an approval not bound to this ticket, mint and size, is journaled.
7. ``exec.place`` is called exactly once, with the ticket id and the approval id.

A refusal uses the existing JournalNote note kind. No event type, NoteKind or event field is
added, so the contracts surface is unchanged.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
=======
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.ledger.autonomy import read_autonomy
from pumpgrok.ledger.store import LedgerStore
<<<<<<< HEAD
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
=======
from pumpgrok.ledger.ticket_refs import append_with_ticket_ref
from pumpgrok.ledger.tickets import TicketAllocationFailed, allocate_ticket
from pumpgrok.replay.clock import Clock, format_ts_utc
from pumpgrok.strategies.base import Intent

if TYPE_CHECKING:
    from pumpgrok.risk.engine.model import RiskDecision

__all__ = ["ExecPlace", "IntentRouter", "RouteResult"]

#: exec.place as the router calls it: one place payload in, the tool's output out.
ExecPlace = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

SOURCE = "paper"
SEAT = "desk"
CORRELATION = "desk"

RouteStatus = Literal["submitted", "duplicate", "refused"]


class _RiskCheck(Protocol):
    def check(self, order: OrderRequest, *, source: str, correlation_id: str) -> RiskDecision: ...
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687


@dataclass(frozen=True)
class RouteResult:
<<<<<<< HEAD
    """Outcome of routing one Intent; refusals carry no ticket or approval."""

    status: str  # "placed" | "refused"
    strategy_id: str
    ticket_id: str | None = None
    approval_id: str | None = None
    reason: str = ""


class IntentRouter:
    """Route strategy Intents to ``place`` with ticket and approval allocation."""
=======
    """What the router did with one Intent. ``place`` is exec.place's output when submitted."""

    status: RouteStatus
    ticket_id: str | None
    reason: str | None = None
    place: dict[str, Any] | None = None


def _link_key(intent: Intent) -> str:
    return f"route|{intent.strategy_id}|{intent.decision_id}"


class IntentRouter:
    """Route strategy Intents to exec.place. Every collaborator is injected."""
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687

    def __init__(
        self,
        *,
<<<<<<< HEAD
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
=======
        exec_place: ExecPlace,
        risk: _RiskCheck,
        store: LedgerStore,
        clock: Clock,
        ids: IdFactory,
        slices: Mapping[str, int],
        max_slippage_bps: int,
    ) -> None:
        self._exec_place = exec_place
        self._risk = risk
        self._store = store
        self._clock = clock
        self._ids = ids
        self._slices = dict(slices)
        self._max_slippage_bps = max_slippage_bps

    async def route(self, intent: Intent) -> RouteResult:
        """Route one Intent; see the module docstring for the order of checks."""
        prior = self._store.by_key(_link_key(intent))
        if prior is not None:
            return RouteResult("duplicate", str(prior["payload"]["refs"][0]))
        if read_autonomy(self._store) != "autonomous-paper":
            return self._refuse(intent, "autonomy_manual_ticket", None)
        ts = format_ts_utc(self._clock.now())
        try:
            ticket_id = allocate_ticket(
                self._store,
                ts_utc=ts,
                source=SOURCE,
                correlation_id=CORRELATION,
                seat=SEAT,
                title=f"strategy {intent.strategy_id} {intent.side}",
            )
        except TicketAllocationFailed:
            return self._refuse(intent, "ticket_allocation_failed", None)
        append_with_ticket_ref(
            self._store,
            self._link_row(intent, ticket_id, ts),
            ticket_id=ticket_id,
            strategy_id=intent.strategy_id,
        )
        return await self._check_and_place(intent, ticket_id)

    async def _check_and_place(self, intent: Intent, ticket_id: str) -> RouteResult:
        """Steps 5 to 7: size and risk checks, then the one exec.place call."""
        slice_lamports = self._slices.get(intent.strategy_id)
        if slice_lamports is None:
            return self._refuse(intent, "unknown_strategy", ticket_id)
        if intent.size_lamports > slice_lamports:
            return self._refuse(intent, "slice_exceeded", ticket_id)
        order = OrderRequest(
            ticket_id=ticket_id,
            mint=intent.mint,
            side=Side(intent.side),
            decision_id=intent.decision_id,
            size_lamports=intent.size_lamports,
            max_slippage_bps=self._max_slippage_bps,
            approval_id=f"apr-{self._ids.ulid()}",
            correlation_id=CORRELATION,
        )
        decision = self._risk.check(order, source=SOURCE, correlation_id=CORRELATION)
        if not decision.passed:
            return self._refuse(intent, decision.reason, ticket_id)
        approval = decision.approval
        if (
            approval is None
            or decision.approval_id != approval.id
            or approval.kind != "autonomous_paper"
            or approval.ticket_id != ticket_id
            or approval.mint != intent.mint
            or approval.size_lamports != intent.size_lamports
        ):
            return self._refuse(intent, "approval_mismatch", ticket_id)
        place = await self._exec_place(
            {
                "ticket_id": ticket_id,
                "mint": intent.mint,
                "side": intent.side,
                "decision_id": intent.decision_id,
                "size_lamports": intent.size_lamports,
                "max_slippage_bps": self._max_slippage_bps,
                "approval_id": approval.id,
                "correlation_id": CORRELATION,
            }
        )
        return RouteResult("submitted", ticket_id, None, place)

    def _link_row(self, intent: Intent, ticket_id: str, ts: str) -> dict[str, Any]:
        return {
            "ts_utc": ts,
            "source": SOURCE,
            "correlation_id": CORRELATION,
            "idempotency_key": _link_key(intent),
            "type": "JournalNote",
            "payload": {
                "source": SOURCE,
                "seat": SEAT,
                "note_kind": "note",
                "text": (
                    f"routed {intent.strategy_id} {intent.side} {intent.mint}"
                    f" to {ticket_id} decision {intent.decision_id}"
                ),
                "refs": [ticket_id],
            },
        }

    def _refuse(self, intent: Intent, reason: str, ticket_id: str | None) -> RouteResult:
        """Journal the refusal once per (strategy, decision, reason). Approves nothing."""
        key = f"route-refusal|{intent.strategy_id}|{intent.decision_id}|{reason}"
        if self._store.by_key(key) is None:
            self._store.append(
                ts_utc=format_ts_utc(self._clock.now()),
                source=SOURCE,
                correlation_id=CORRELATION,
                idempotency_key=key,
                type="JournalNote",
                payload={
                    "source": SOURCE,
                    "seat": SEAT,
                    "note_kind": "note",
                    "text": (
                        f"refused {intent.strategy_id} {intent.side} {intent.mint}"
                        f" decision {intent.decision_id}: {reason}"
                    ),
                    "refs": [ticket_id] if ticket_id else [],
                },
            )
        return RouteResult("refused", ticket_id, reason)
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
