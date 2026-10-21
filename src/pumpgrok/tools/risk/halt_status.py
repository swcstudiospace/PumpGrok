"""risk.halt_status: combined halt view (TOOL-005).

Folds the daily-loss/drawdown halt events, the kill-switch causes and the
effective execution mode into one read-only view. Breaker state is Phase 4
(RiskEngine owns it); ``breaker_open`` is False until then.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools._common import meta_now

__all__ = [
    "HALT_STATUS_SPEC",
    "HaltStatusIn",
    "HaltStatusOut",
    "build_halt_status_tool",
    "run_halt_status",
]


class HaltStatusIn(ToolInput):
    """No input: the view covers every halt cause."""


class HaltStatusOut(ToolOutput):
    """Halted iff any cause is active; ``reasons`` names the active causes."""

    halted: bool
    reasons: list[str] = []
    kill_switch_active: bool = False
    drawdown_halt: bool = False
    daily_loss_halt: bool = False
    breaker_open: bool = False
    effective_mode: Literal["paper", "live"] = "paper"


HALT_STATUS_SPEC = ToolSpec(
    name="risk.halt_status",
    description=(
        "Combined halt view: daily-loss and drawdown halts, kill switch, "
        "breaker states and effective execution mode. Read only."
    ),
    input_model=HaltStatusIn,
    output_model=HaltStatusOut,
    side_effect=SideEffect.READ,
    timeout_s=5.0,
    rate_limit_key="ledger",
    backend="pumpgrok.ledger.store.LedgerStore",
)


async def run_halt_status(
    inp: HaltStatusIn,
    store: LedgerStore,
    killswitch_path: Path | None,
    mode: Literal["paper", "live"] = "paper",
) -> dict:
    """Fold halt events and kill-switch causes into one view."""
    env_set = os.environ.get("PUMPGROK_KILLSWITCH", "").strip() == "1"
    file_set = killswitch_path is not None and killswitch_path.is_file()
    halt_active = False
    halt_reason: str | None = None
    kill_active = env_set or file_set
    for event in store.read(limit=1000):
        if event["type"] == "HaltSet":
            halt_active = True
            halt_reason = str(event["payload"].get("reason", "halted"))
        elif event["type"] == "HaltCleared":
            halt_active = False
            halt_reason = None
        elif event["type"] == "KillSwitchSet":
            kill_active = True
        elif event["type"] == "KillSwitchCleared":
            kill_active = env_set or file_set
    reasons: list[str] = []
    if kill_active:
        reasons.append("kill_switch")
    if halt_active and halt_reason:
        reasons.append(halt_reason)
    ambient = ambient_correlation()
    return HaltStatusOut.model_validate(
        {
            "halted": kill_active or halt_active,
            "reasons": reasons,
            "kill_switch_active": kill_active,
            "drawdown_halt": halt_reason == "drawdown",
            "daily_loss_halt": halt_reason == "daily_loss",
            "breaker_open": False,
            "effective_mode": mode,
            "meta": meta_now("ledger", inp.correlation_id or (str(ambient) if ambient else None)),
        }
    ).model_dump()


def build_halt_status_tool(
    store: LedgerStore,
    killswitch_path: Path | None,
    mode: Literal["paper", "live"] = "paper",
) -> Tool:
    """Bind ``risk.halt_status`` to one store, file path and mode."""

    @tool(HALT_STATUS_SPEC)
    async def _halt_status(payload: HaltStatusIn) -> dict:
        return await run_halt_status(payload, store, killswitch_path, mode)

    return _halt_status
