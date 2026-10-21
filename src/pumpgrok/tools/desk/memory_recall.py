"""desk.memory_recall: recall from own and shared banks (TOOL-007)."""

from __future__ import annotations

from pydantic import Field

from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import meta_now
from pumpgrok.tools.desk._memory import MemoryBank

__all__ = [
    "MEMORY_RECALL_SPEC",
    "MemoryRecallIn",
    "MemoryRecallOut",
    "build_memory_recall_tool",
    "run_memory_recall",
]


class MemoryRecallIn(ToolInput):
    """Substring query over retained content."""

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    include_shared: bool = True


class MemoryRecallOut(ToolOutput):
    """Newest-first matching records (bank holds one shared file)."""

    items: list[dict] = Field(default_factory=list)


MEMORY_RECALL_SPEC = ToolSpec(
    name="desk.memory_recall",
    description=("Recall retained decisions from the own and shared banks. Read only."),
    input_model=MemoryRecallIn,
    output_model=MemoryRecallOut,
    side_effect=SideEffect.READ,
    timeout_s=5.0,
    rate_limit_key="desk",
    backend="pumpgrok.tools.desk._memory.MemoryBank",
)


async def run_memory_recall(inp: MemoryRecallIn, bank: MemoryBank) -> dict:
    """Search the bank; the shared file is the only bank in Phase 3."""
    _ = inp.include_shared  # Own/shared split is gateway routing (Phase 4).
    items = bank.recall(inp.query, inp.limit)
    ambient = ambient_correlation()
    return MemoryRecallOut.model_validate(
        {
            "items": items,
            "meta": meta_now("desk", inp.correlation_id or (str(ambient) if ambient else None)),
        }
    ).model_dump()


def build_memory_recall_tool(bank: MemoryBank) -> Tool:
    """Bind ``desk.memory_recall`` to one bank (no globals)."""

    @tool(MEMORY_RECALL_SPEC)
    async def _memory_recall(payload: MemoryRecallIn) -> dict:
        return await run_memory_recall(payload, bank)

    return _memory_recall
