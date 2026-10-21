"""Tool contracts: specs, envelopes, and the binding decorator (interfaces.md 2.5)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pumpgrok.core.side_effect import SideEffect

TOOL_NAME_RE = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"


class RetryPolicy(BaseModel):
    """tenacity policy (D5). `attempts=1` means no retry."""

    model_config = ConfigDict(frozen=True)

    attempts: int = Field(default=1, ge=1, le=10)
    base_s: float = Field(default=0.5, ge=0.0)  # seconds, not money
    max_s: float = Field(default=5.0, ge=0.0)
    jitter: bool = True
    retry_on: tuple[str, ...] = ("timeout", "5xx", "429")

    @classmethod
    def none(cls) -> RetryPolicy:
        return cls(attempts=1)


class ToolMeta(BaseModel):
    """Envelope every tool output carries."""

    source: str
    fetched_at: datetime
    freshness_s: float = Field(ge=0.0)
    correlation_id: str
    stale: bool = False
    reason: str | None = None


class ToolInput(BaseModel):
    """Base for every tool input model. `extra='forbid'` mirrors additionalProperties: false."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    correlation_id: str | None = None


class ToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: ToolMeta


class ToolSpec(BaseModel):
    """Static description of one tool. One instance per entry in the tool catalog."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str = Field(pattern=TOOL_NAME_RE)
    description: str = Field(min_length=10, max_length=1000)
    input_model: type[ToolInput]
    output_model: type[ToolOutput]
    side_effect: SideEffect
    timeout_s: float = Field(gt=0.0, le=300.0)
    retry: RetryPolicy = Field(default_factory=RetryPolicy.none)
    rate_limit_key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    requires_approval: bool = False  # roster gate g6: approval_id required in input
    idempotent: bool = False  # True for every write; input carries or derives a key
    backend: str = Field(min_length=1)  # endpoint or module path, for the audit log

    @property
    def capability(self) -> str:
        """Namespace prefix: 'market' for 'market.price'."""
        return self.name.split(".", 1)[0]

    @model_validator(mode="after")
    def _writes_are_idempotent(self) -> Self:
        if self.side_effect is not SideEffect.READ and not self.idempotent:
            raise ValueError(f"{self.name}: write tools must be idempotent")
        if self.side_effect is SideEffect.READ and self.requires_approval:
            raise ValueError(f"{self.name}: read tools cannot require approval")
        return self

    def input_json_schema(self) -> dict[str, Any]:
        schema = self.input_model.model_json_schema()
        schema["additionalProperties"] = False
        return schema


@runtime_checkable
class Tool(Protocol):
    """A callable with a spec. Implementations are plain async functions wrapped by `tool()`."""

    spec: ToolSpec

    async def __call__(self, payload: ToolInput, /) -> ToolOutput: ...


def tool(spec: ToolSpec) -> Callable[[Callable[[Any], Awaitable[Any]]], Tool]:
    """Attach a ToolSpec to an async function and validate I/O.

    The registry is the only caller of the returned object; it applies timeout,
    retry, rate limit, correlation stamping and the audit log around it.
    """

    def wrap(fn: Callable[[Any], Awaitable[Any]]) -> Tool:
        class _BoundTool:
            def __init__(self) -> None:
                self.spec = spec

            async def __call__(self, payload: ToolInput, /) -> ToolOutput:
                if not isinstance(payload, spec.input_model):
                    raise TypeError(f"{spec.name}: expected {spec.input_model.__name__}")
                result = await fn(payload)
                return spec.output_model.model_validate(result)

        return _BoundTool()

    return wrap
