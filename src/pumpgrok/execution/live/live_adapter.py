"""Refusing live adapter stub (interfaces.md 2.7, INV-C-03, R21).

Every adapter method appends one `LiveWriteAttempted` row to the ledger and then raises
`LiveGateError`. No transaction is built or submitted, and this module holds no key
material and imports no venue client. Precondition 8 (`adapter_registered`) stays unmet
because no implementation ships in this release.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar, NoReturn

from pumpgrok.core.adapter import (
    ExecutionMode,
    Fill,
    OrderRequest,
    Position,
    Quote,
    Side,
    SimulationResult,
)
from pumpgrok.core.errors import LiveGateError
from pumpgrok.core.idempotency import canonical_json, derive_idempotency_key
from pumpgrok.core.ids import CorrelationId, IdFactory, ambient_correlation
from pumpgrok.execution.live.live_gate import LiveGate
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.logging.json import current_seat
from pumpgrok.replay.clock import Clock

ADAPTER_NAME = "LiveAdapterStub"
# Seat recorded when a refused write has no bound seat (the desk itself).
FALLBACK_SEAT = "desk"


class LiveAdapterStub:
    """Refuses every live write. Constructing it runs nothing that reaches a venue."""

    mode: ClassVar[ExecutionMode] = ExecutionMode.LIVE
    venue: ClassVar[str] = "disabled"

    def __init__(
        self, *, gate: LiveGate, ledger: LedgerStore, clock: Clock, ids: IdFactory
    ) -> None:
        self._gate = gate
        self._ledger = ledger
        self._clock = clock
        self._ids = ids

    def _refuse(self, method: str) -> NoReturn:
        unmet = self._gate.check()
        attempt = self._ids.ulid()
        seat = current_seat() or FALLBACK_SEAT
        correlation = ambient_correlation() or CorrelationId(attempt)
        self._ledger.append(
            ts_utc=self._clock.utc_iso(),
            source="manual",
            correlation_id=str(correlation),
            idempotency_key=derive_idempotency_key(
                "live_adapter", seat, {"method": method, "unmet": unmet}, scope=attempt
            ),
            type="LiveWriteAttempted",
            payload={
                "source": "manual",
                "adapter": ADAPTER_NAME,
                "method": method,
                "caller_seat": seat,
                "gate_result_json": canonical_json({"unmet": unmet}),
                "stack_hash": "",
            },
        )
        raise LiveGateError(
            f"live {method} refused: no live adapter is available in this release",
            unmet=unmet,
            method=method,
        )

    async def quote(
        self, input_mint: str, output_mint: str, amount: int, slippage_bps: int
    ) -> Quote:
        self._refuse("quote")

    async def simulate(
        self,
        *,
        mint: str,
        side: Side,
        size_lamports: int | None,
        token_units: int | None,
    ) -> SimulationResult:
        self._refuse("simulate")

    async def place(self, request: OrderRequest) -> Fill:
        self._refuse("place")

    async def cancel(self, order_id: str, ticket_id: str, decision_id: str) -> bool:
        self._refuse("cancel")

    async def positions(self, mint: str | None = None) -> Sequence[Position]:
        self._refuse("positions")

    def cash_lamports(self) -> int:
        self._refuse("cash")

    def equity_lamports(self) -> int:
        self._refuse("equity")
