"""notify.alert: human alert through the abstract Notifier (TOOL-006).

Sinks: stdout + file always on; Telegram and webhook only to allowlisted
destinations (R39). Escalation kinds include the supervisor-relay set
(``bot_restart_exhausted`` through ``ledger_inconsistent``, R40).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from pumpgrok.core.ids import Clock, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import meta_now
from pumpgrok.tools.notify.notifier import Notifier, alert_key

__all__ = [
    "ALERT_SPEC",
    "AlertIn",
    "AlertOut",
    "build_alert_tool",
    "run_alert",
]


class AlertIn(ToolInput):
    """One human alert; ``destinations`` defaults to the whole allowlist."""

    severity: Literal["info", "warning", "critical"]
    kind: Literal[
        "rug_flag",
        "halt",
        "breaker",
        "killswitch",
        "escalation",
        "report",
        "unknown_result",
        "bot_restart_exhausted",
        "heartbeat_stale",
        "persistence_down",
        "clock_skew",
        "ledger_inconsistent",
    ]
    text: str = Field(min_length=1, max_length=4000)
    ticket_id: str | None = Field(default=None, pattern=r"^SOL-\d{8}-\d{3}$")
    fields: dict[str, Any] = Field(default_factory=dict)
    destinations: list[str] | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class AlertOut(ToolOutput):
    """Per-sink delivery rows; ``suppressed`` on idempotent repeat."""

    delivered: list[dict[str, Any]] = Field(default_factory=list)
    suppressed: bool = False


ALERT_SPEC = ToolSpec(
    name="notify.alert",
    description=(
        "Human alert through the Notifier: stdout+file always, Telegram and "
        "webhook only to allowlisted destinations."
    ),
    input_model=AlertIn,
    output_model=AlertOut,
    side_effect=SideEffect.PAPER_WRITE,
    timeout_s=10.0,  # j8 applies per network sink inside the Notifier, not here
    rate_limit_key="notify",
    idempotent=True,
    backend="pumpgrok.tools.notify.notifier.Notifier.send",
)


async def run_alert(inp: AlertIn, notifier: Notifier, clock: Clock) -> dict[str, Any]:
    """Fan out through the notifier with a derived key when omitted."""
    ambient = ambient_correlation()
    key = inp.idempotency_key or alert_key(inp.kind, inp.ticket_id, inp.severity, clock)
    result = await notifier.send(
        severity=inp.severity,
        kind=inp.kind,
        text=inp.text,
        ticket_id=inp.ticket_id,
        fields=inp.fields,
        destinations=inp.destinations,
        idempotency_key=key,
    )
    return AlertOut.model_validate(
        {
            **result,
            "meta": meta_now("notify", inp.correlation_id or (str(ambient) if ambient else None)),
        }
    ).model_dump()


def build_alert_tool(notifier: Notifier, clock: Clock) -> Tool:
    """Bind ``notify.alert`` to one notifier and clock (no globals)."""

    @tool(ALERT_SPEC)
    async def _alert(payload: AlertIn) -> dict[str, Any]:
        return await run_alert(payload, notifier, clock)

    return _alert
