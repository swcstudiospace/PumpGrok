"""exec.place: single paper order with the TOOL-004 input contract (B7).

Phase 3 scope: the input contract only (``decision_id`` required, key derived
from ``(ticket_id, side, decision_id)`` only, ``approval_id`` required, g6
flags). The atomic consume-and-order ledger transaction and
repeat-returns-first-fill are Phase 4 work and must NOT be implemented here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from pumpgrok.core.adapter import ExecutionAdapter, OrderRequest
from pumpgrok.core.idempotency import exec_place_key
from pumpgrok.core.ids import ULID_RE, Clock, ambient_correlation
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import MintStr, meta_now

__all__ = [
    "PLACE_SPEC",
    "PlaceIn",
    "PlaceOut",
    "build_place_tool",
    "run_place",
]


class PlaceIn(ToolInput):
    """One paper order. ``approval_id`` (g6) is required, never optional."""

    ticket_id: str = Field(pattern=r"^SOL-\d{8}-\d{3}$")
    mint: MintStr
    side: Literal["buy", "sell"]
    decision_id: str = Field(pattern=ULID_RE)
    size_lamports: int | None = Field(default=None, gt=0)
    token_units: int | None = Field(default=None, gt=0)
    max_slippage_bps: int = Field(ge=1, le=10_000)
    approval_id: str = Field(pattern=r"^apr-[0-9A-HJKMNP-TV-Z]{26}$")
    quote_id: str | None = None

    @model_validator(mode="after")
    def _size_matches_side(self) -> Self:
        if self.side == "buy" and self.size_lamports is None:
            raise ValueError("buy requires size_lamports")
        if self.side == "sell" and self.token_units is None:
            raise ValueError("sell requires token_units")
        return self


class PlaceOut(ToolOutput):
    """Rejected without touching the adapter, or the adapter's answer.

    In Phase 3 the adapter always raises ``not_yet_implemented``, so a
    ``filled`` status is unreachable; the model keeps the catalog statuses
    for the Phase 4 backend.
    """

    ticket_id: str = Field(pattern=r"^SOL-\d{8}-\d{3}$")
    side: Literal["buy", "sell"]
    decision_id: str = Field(pattern=ULID_RE)
    idempotency_key: str = Field(min_length=32, max_length=32)
    status: Literal["filled", "partial", "rejected", "unknown"]
    reason: str | None = None


PLACE_SPEC = ToolSpec(
    name="exec.place",
    description=(
        "Place exactly one paper order; fail-closed on approval, decision key, "
        "and exit-BUY. Phase 3 validates the input contract only."
    ),
    input_model=PlaceIn,
    output_model=PlaceOut,
    side_effect=SideEffect.PAPER_WRITE,
    timeout_s=20.0,
    rate_limit_key="exec",
    requires_approval=True,
    idempotent=True,
    backend="pumpgrok.execution.not_yet_implemented.NotYetImplementedAdapter.place",
)


def _request_of(inp: PlaceIn) -> OrderRequest:
    """Convert the tool input to the adapter contract (one conversion)."""
    ambient = ambient_correlation()
    return OrderRequest.model_validate(
        {
            **inp.model_dump(),
            "correlation_id": inp.correlation_id or (str(ambient) if ambient else "none"),
        }
    )


async def run_place(
    inp: PlaceIn,
    adapter: ExecutionAdapter,
    get_budget: Callable[[], RiskBudget],
    clock: Clock,
) -> dict[str, Any]:
    """Validate the B7 contract, then hand the order to the adapter.

    Refusals (exit cannot BUY via ``seat_may_trade``) return a ``rejected``
    payload before the adapter is touched. A valid shape reaches
    ``adapter.place``, which raises ``not_yet_implemented`` in Phase 3 (B5).
    """
    key = exec_place_key(inp.ticket_id, inp.side, inp.decision_id)
    ambient = ambient_correlation()
    correlation = inp.correlation_id or (str(ambient) if ambient else None)
    if inp.side == "buy" and not get_budget().may_open_exposure:
        return PlaceOut.model_validate(
            {
                "ticket_id": inp.ticket_id,
                "side": inp.side,
                "decision_id": inp.decision_id,
                "idempotency_key": key,
                "status": "rejected",
                "reason": "seat_may_trade",
                "meta": meta_now("exec", correlation, clock),
            }
        ).model_dump()
    request = _request_of(inp)
    # Phase 3: raises NotYetImplemented (code not_yet_implemented, no fake Fill).
    fill = await adapter.place(request)
    return PlaceOut.model_validate(
        {
            "ticket_id": inp.ticket_id,
            "side": inp.side,
            "decision_id": inp.decision_id,
            "idempotency_key": key,
            "status": fill.status.value,
            "reason": fill.reason,
            "meta": meta_now("exec", correlation, clock),
        }
    ).model_dump()


def build_place_tool(
    adapter: ExecutionAdapter, get_budget: Callable[[], RiskBudget], clock: Clock
) -> Tool:
    """Bind ``exec.place`` to one adapter, one budget provider and a clock."""

    @tool(PLACE_SPEC)
    async def _place(payload: PlaceIn) -> dict[str, Any]:
        return await run_place(payload, adapter, get_budget, clock)

    return _place
