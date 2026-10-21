"""desk.brief: start-of-turn brief (TOOL-007).

Halt status is real (folded from the ledger through the same code path as
``risk.halt_status``); memory recall is real (the seat bank). The ticket
list has no store in Phase 3, so ``tickets`` is empty — documented as the
accepted partial until the supervisor lands.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from pumpgrok.core.ids import Clock, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools._common import meta_now
from pumpgrok.tools.desk._memory import MemoryBank
from pumpgrok.tools.risk.halt_status import HaltStatusIn, run_halt_status

__all__ = [
    "BRIEF_SPEC",
    "BriefIn",
    "BriefOut",
    "build_brief_tool",
    "run_brief",
]


class BriefIn(ToolInput):
    """Brief for one turn; ``refresh`` is accepted and etag-visible."""

    task_id: str = Field(min_length=1, max_length=64)
    refresh: bool = False


class BriefOut(ToolOutput):
    """Tickets (empty until Phase 4), halt, recall and an etag."""

    tickets: list[dict] = Field(default_factory=list)
    halt: dict = Field(default_factory=dict)
    recall: list[dict] = Field(default_factory=list)
    etag: str = ""


BRIEF_SPEC = ToolSpec(
    name="desk.brief",
    description=(
        "Start-of-turn brief: the seat's open tickets, halt status, last "
        "receipts and memory recall. Read only."
    ),
    input_model=BriefIn,
    output_model=BriefOut,
    side_effect=SideEffect.READ,
    timeout_s=10.0,
    rate_limit_key="desk",
    backend="pumpgrok.tools.desk.brief",
)


async def run_brief(
    inp: BriefIn,
    store: LedgerStore,
    bank: MemoryBank,
    clock: Clock,
    killswitch_path: Path | None,
    mode: Literal["paper", "live"] = "paper",
) -> dict:
    """Fold halt + recall; etag covers (task_id, refresh, UTC minute)."""
    halt = await run_halt_status(HaltStatusIn(), store, killswitch_path, mode)
    halt.pop("meta", None)
    recall = bank.recall(inp.task_id, 5)
    minute = datetime.fromtimestamp(clock.now(), UTC).strftime("%Y-%m-%dT%H:%M")
    etag = hashlib.sha256(f"{inp.task_id}\n{inp.refresh}\n{minute}".encode()).hexdigest()[:16]
    ambient = ambient_correlation()
    return BriefOut.model_validate(
        {
            "tickets": [],
            "halt": halt,
            "recall": recall,
            "etag": etag,
            "meta": meta_now(
                "desk", inp.correlation_id or (str(ambient) if ambient else None)
            ),
        }
    ).model_dump()


def build_brief_tool(
    store: LedgerStore,
    bank: MemoryBank,
    clock: Clock,
    killswitch_path: Path | None = None,
    mode: Literal["paper", "live"] = "paper",
) -> Tool:
    """Bind ``desk.brief`` to one store, bank, clock, file path and mode."""

    @tool(BRIEF_SPEC)
    async def _brief(payload: BriefIn) -> dict:
        return await run_brief(payload, store, bank, clock, killswitch_path, mode)

    return _brief
