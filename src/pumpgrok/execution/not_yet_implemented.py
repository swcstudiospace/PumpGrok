"""Phase 3 execution backend: every method refuses (TOOL-004, binding B7).

``NotYetImplementedAdapter`` implements :class:`ExecutionAdapter` without
faking anything: quotes, simulations, fills, cancels and positions all raise
:class:`NotYetImplemented` (code ``not_yet_implemented``). The atomic
consume-and-order ledger transaction and repeat-returns-first-fill are Phase 4
work; this module only proves the input contract fail-closed.
"""

from __future__ import annotations

from collections.abc import Sequence

from pumpgrok.core.adapter import (
    ExecutionAdapter,
    ExecutionMode,
    Fill,
    OrderRequest,
    Position,
    Quote,
    SimulationResult,
)
from pumpgrok.core.errors import NotYetImplemented

__all__ = ["NotYetImplementedAdapter"]


class NotYetImplementedAdapter(ExecutionAdapter):
    """Refusing execution backend for Phase 3 (binding B7 partial).

    Never returns a quote, fill, simulation or position: every method raises
    so a valid-shape call surfaces the ``not_yet_implemented`` envelope (B5)
    instead of a fake Fill.
    """

    mode = ExecutionMode.PAPER
    venue = "paper"

    async def quote(
        self, input_mint: str, output_mint: str, amount: int, slippage_bps: int
    ) -> Quote:
        raise NotYetImplemented(
            "exec.quote needs the Phase 4 PaperAdapter",
            tool="exec.quote",
        )

    async def simulate(self, request: OrderRequest) -> SimulationResult:
        raise NotYetImplemented(
            "exec.simulate needs the Phase 4 PaperAdapter",
            tool="exec.simulate",
            ticket_id=request.ticket_id,
        )

    async def place(self, request: OrderRequest) -> Fill:
        raise NotYetImplemented(
            "exec.place needs the Phase 4 consume-and-order transaction",
            tool="exec.place",
            ticket_id=request.ticket_id,
            decision_id=request.decision_id,
        )

    async def cancel(self, order_id: str, ticket_id: str, decision_id: str) -> bool:
        raise NotYetImplemented(
            "exec.cancel needs the Phase 4 PaperAdapter",
            tool="exec.cancel",
            order_id=order_id,
        )

    async def positions(self, mint: str | None = None) -> Sequence[Position]:
        raise NotYetImplemented(
            "exec.positions needs the Phase 4 ledger snapshot reader",
            tool="exec.positions",
        )
