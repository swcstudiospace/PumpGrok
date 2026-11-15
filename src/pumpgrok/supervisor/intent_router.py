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
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.ledger.autonomy import read_autonomy
from pumpgrok.ledger.store import LedgerStore
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


@dataclass(frozen=True)
class RouteResult:
    """What the router did with one Intent. ``place`` is exec.place's output when submitted."""

    status: RouteStatus
    ticket_id: str | None
    reason: str | None = None
    place: dict[str, Any] | None = None


def _link_key(intent: Intent) -> str:
    return f"route|{intent.strategy_id}|{intent.decision_id}"


class IntentRouter:
    """Route strategy Intents to exec.place. Every collaborator is injected."""

    def __init__(
        self,
        *,
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
