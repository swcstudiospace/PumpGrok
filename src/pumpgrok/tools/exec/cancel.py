"""exec.cancel: cancel a pending paper order (TOOL-004).

Ledger-backed: the outcome reads the ledger plus the adapter's in-flight
set. ``not_found`` when no ``OrderPlaced`` names the order (or a terminal
``OrderRejected`` already exists), ``already_filled`` when a ``FillRecorded``
names it, ``cancelled`` when the adapter drops the in-flight attempt. The
presented ``approval_id`` must equal the ``OrderPlaced`` row's approval id;
anything else fails closed with ``approval_unknown`` and writes nothing.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import Field

from pumpgrok.core.adapter import ExecutionAdapter
from pumpgrok.core.errors import PermissionDenied
from pumpgrok.core.idempotency import exec_cancel_key
from pumpgrok.core.ids import ULID_RE, Clock, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools._common import meta_now

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
    """Ledger-backed cancel result: nothing is appended on any path."""

    cancelled: bool
    status_after: Literal["cancelled", "already_filled", "not_found"]
    idempotency_key: str = Field(min_length=32, max_length=32)


CANCEL_SPEC = ToolSpec(
    name="exec.cancel",
    description=(
        "Cancel a pending paper order owned by the calling seat. "
        "Reads the ledger for the placed, fill, and reject rows plus the "
        "adapter in-flight set; the presented approval_id must match the "
        "placed row exactly."
    ),
    input_model=CancelIn,
    output_model=CancelOut,
    side_effect=SideEffect.PAPER_WRITE,
    timeout_s=10.0,
    rate_limit_key="exec",
    requires_approval=False,
    idempotent=True,
    backend="pumpgrok.execution.paper_adapter.PaperAdapter.cancel",
)


def _placed_row(store: LedgerStore, order_id: str, ticket_id: str) -> dict[str, Any] | None:
    """Latest ``OrderPlaced`` row naming both the order and the ticket."""
    found: dict[str, Any] | None = None
    for event in store.read(limit=None):
        if event.get("type") != "OrderPlaced":
            continue
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        if (
            str(payload.get("order_id", "")) == order_id
            and str(payload.get("ticket_id", "")) == ticket_id
        ):
            found = event
    return found


def _has_row(store: LedgerStore, event_type: str, order_id: str) -> bool:
    """True when a row of ``event_type`` names ``order_id``."""
    for event in store.read(limit=None):
        if event.get("type") != event_type:
            continue
        payload = event.get("payload", {})
        if isinstance(payload, dict) and str(payload.get("order_id", "")) == order_id:
            return True
    return False


def _placed_approval_id(placed: dict[str, Any]) -> str:
    """Approval id the placer presented, stored in the placed row."""
    payload = placed.get("payload", {})
    if not isinstance(payload, dict):
        return ""
    try:
        approval = json.loads(str(payload.get("approval_json", "{}")))
    except ValueError:
        return ""
    if isinstance(approval, dict):
        return str(approval.get("approval_id", ""))
    return ""


def _out(inp: CancelIn, clock: Clock, correlation: str | None, **fields: Any) -> dict[str, Any]:
    """Validate one cancel payload envelope (single construction site)."""
    return CancelOut.model_validate(
        {
            "idempotency_key": exec_cancel_key(inp.order_id),
            "meta": meta_now("exec", correlation, clock),
            **fields,
        }
    ).model_dump()


async def run_cancel(
    inp: CancelIn,
    adapter: ExecutionAdapter,
    store: LedgerStore,
    clock: Clock,
) -> dict[str, Any]:
    """Resolve the cancel against ledger rows plus the adapter in-flight set.

    Reads only; no row is appended on any path. Unknown orders, orders with
    a recorded fill, and orders with a recorded reject all return without
    touching the adapter. A presented approval id that does not equal the
    placed row's id fails closed before the adapter is touched.
    """
    ambient = ambient_correlation()
    correlation = inp.correlation_id or (str(ambient) if ambient else None)
    placed = _placed_row(store, inp.order_id, inp.ticket_id)
    if placed is None:
        return _out(inp, clock, correlation, cancelled=False, status_after="not_found")
    if _placed_approval_id(placed) != inp.approval_id:
        raise PermissionDenied(
            f"approval {inp.approval_id} does not match order {inp.order_id}",
            tool="exec.cancel",
            bot="",
            reason="approval_unknown",
        )
    if _has_row(store, "FillRecorded", inp.order_id):
        return _out(inp, clock, correlation, cancelled=False, status_after="already_filled")
    if _has_row(store, "OrderRejected", inp.order_id):
        return _out(inp, clock, correlation, cancelled=False, status_after="not_found")
    payload = placed.get("payload", {})
    decision_id = str(payload.get("decision_id", "")) if isinstance(payload, dict) else ""
    cancelled = await adapter.cancel(inp.order_id, inp.ticket_id, decision_id)
    return _out(
        inp,
        clock,
        correlation,
        cancelled=cancelled,
        status_after="cancelled" if cancelled else "not_found",
    )


def build_cancel_tool(adapter: ExecutionAdapter, store: LedgerStore, clock: Clock) -> Tool:
    """Bind ``exec.cancel`` to one adapter, store and clock (no globals)."""

    @tool(CANCEL_SPEC)
    async def _cancel(payload: CancelIn) -> dict[str, Any]:
        return await run_cancel(payload, adapter, store, clock)

    return _cancel
