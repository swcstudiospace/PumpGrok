"""desk.memory_retain: retain a decision or verified command (TOOL-007).

Refused without ``receipt_path`` or ``source`` (fail-closed ValueError
before anything is stored). Idempotency is ``d(tool, bot, sha256(input))``
where the bot slot is ``task_id`` or ``"shared"`` when no task is named.
"""

from __future__ import annotations
import hashlib
from typing import Self

from pydantic import Field, model_validator

from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import meta_now
from pumpgrok.tools.desk._memory import MemoryBank

__all__ = [
    "MEMORY_RETAIN_SPEC",
    "MemoryRetainIn",
    "MemoryRetainOut",
    "build_memory_retain_tool",
    "memory_retain_key",
    "run_memory_retain",
]


class MemoryRetainIn(ToolInput):
    """One record; provenance (receipt or source) is mandatory."""

    content: str = Field(min_length=1, max_length=8000)
    receipt_path: str | None = None
    source: str | None = None
    task_id: str | None = None
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _provenance_required(self) -> Self:
        if not self.receipt_path and not self.source:
            raise ValueError("memory_retain refused: receipt_path or source is required")
        return self


class MemoryRetainOut(ToolOutput):
    """Stable id of the retained record (replayed on duplicate)."""

    id: str


MEMORY_RETAIN_SPEC = ToolSpec(
    name="desk.memory_retain",
    description=(
        "Retain a decision or verified command in the seat memory bank. "
        "Refused without receipt_path or source."
    ),
    input_model=MemoryRetainIn,
    output_model=MemoryRetainOut,
    side_effect=SideEffect.PAPER_WRITE,
    timeout_s=5.0,
    rate_limit_key="desk",
    idempotent=True,
    backend="pumpgrok.tools.desk._memory.MemoryBank",
)


def memory_retain_key(bot: str, content: str) -> str:
    """Derived key: d(tool, bot, sha256(content))."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return hashlib.sha256(f"desk.memory_retain\n{bot}\n{digest}".encode()).hexdigest()[:32]


async def run_memory_retain(inp: MemoryRetainIn, bank: MemoryBank) -> dict:
    """Store the record (or replay the id for a duplicate key)."""
    bot = inp.task_id or "shared"
    key = memory_retain_key(bot, inp.content)
    record_id = bank.retain(
        key=key,
        record={
            "content": inp.content,
            "receipt_path": inp.receipt_path,
            "source": inp.source,
            "task_id": inp.task_id,
            "tags": inp.tags,
        },
    )
    ambient = ambient_correlation()
    return MemoryRetainOut.model_validate(
        {
            "id": record_id,
            "meta": meta_now(
                "desk", inp.correlation_id or (str(ambient) if ambient else None)
            ),
        }
    ).model_dump()


def build_memory_retain_tool(bank: MemoryBank) -> Tool:
    """Bind ``desk.memory_retain`` to one bank (no globals)."""

    @tool(MEMORY_RETAIN_SPEC)
    async def _memory_retain(payload: MemoryRetainIn) -> dict:
        return await run_memory_retain(payload, bank)

    return _memory_retain
