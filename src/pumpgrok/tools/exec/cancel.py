"""exec.cancel: cancel a pending paper order (TOOL-004).

Phase 3 scope: the input contract only (``order_id``, ``ticket_id``,
``approval_id`` required; g6; key over ``order_id``). The adapter reads
``decision_id`` from the order in Phase 4; with no order book to read, a
valid shape raises ``not_yet_implemented``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from pumpgrok.core.errors import NotYetImplemented
from pumpgrok.core.ids import ULID_RE, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.core.idempotency import exec_cancel_key

__all__ = [
    "CANCEL_SPEC",
    "CancelIn",
    "CancelOut",
    "build_cancel_tool",
    "run_cancel",
]


class CancelIn(ToolInput):
    """Cancel one pending order owned by the calling seat."""

    order_id: str = Field(pattern=ULID_RE)
    ticket_id: str = Field(pattern=r"^SOL-\d{8}-\d{3}$")
    approval_id: str = Field(pattern=r"^apr-[0-9A-HJKMNP-TV-Z]{26}$")


class CancelOut(ToolOutput):
    """Cancel result; unreachable in Phase 3 (kept for the Phase 4 backend)."""

    cancelled: bool
    status_after: Literal["cancelled", "already_filled", "not_found"]
    idempotency_key: str = Field(min_length=32, max_length=32)


CANCEL_SPEC = ToolSpec(
    name="exec.cancel",
    description=(
        "Cancel a pending paper order owned by the calling seat. Phase 3 "
        "validates the input only; cancellation is Phase 4 work."
    ),
    input_model=CancelIn,
    output_model=CancelOut,
    side_effect=SideEffect.PAPER_WRITE,
    timeout_s=10.0,
    rate_limit_key="exec",
    requires_approval=True,
    idempotent=True,
    backend="phase-4-paper-adapter-cancel",
)


async def run_cancel(inp: CancelIn) -> dict:
    """Validate the input, then refuse: no order book exists in Phase 3."""
    ambient = ambient_correlation()
    raise NotYetImplemented(
        "exec.cancel needs the Phase 4 PaperAdapter order book",
        tool="exec.cancel",
        order_id=inp.order_id,
        ticket_id=inp.ticket_id,
        idempotency_key=exec_cancel_key(inp.order_id),
        correlation_id=inp.correlation_id or (str(ambient) if ambient else "none"),
    )


def build_cancel_tool() -> Tool:
    """Bind ``exec.cancel`` (no backend in Phase 3, no globals)."""

    @tool(CANCEL_SPEC)
    async def _cancel(payload: CancelIn) -> dict:
        return await run_cancel(payload)

    return _cancel

