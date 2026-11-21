"""Single Grok gateway entry point (Phase 14, GRK-01..GRK-04, GRK-07, GRK-08).

Every Grok call passes through `GrokGateway.call`: deterministic prefilter
(skip before any budget spend), strict sanitizer plus JSON parse, canonical
cache key (ints/strings only), in-flight coalescing, layered persisted budget,
and a gateway ledger of hashes/counts only. Exit rules, risk, execution and
the watcher never import this package.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from pumpgrok.core.idempotency import canonical_json
from pumpgrok.grok.budget import BudgetExhausted, LayeredBudget
from pumpgrok.grok.cache import Cache, build_cache_key_payload, canonical_request_hash
from pumpgrok.grok.coalesce import Coalescer
from pumpgrok.grok.ledger import GatewayLedger
from pumpgrok.grok.prefilter import Prefilter
from pumpgrok.grok.sanitize import StrictParseError, parse_strict_json, sanitize_prompt
from pumpgrok.replay.clock import Clock

__all__ = [
    "BudgetExhausted",
    "Cache",
    "Coalescer",
    "GatewayLedger",
    "GatewayRequest",
    "GatewayResponse",
    "GrokGateway",
    "Prefilter",
    "ReplayBackend",
    "ReplayMiss",
    "StrictParseError",
    "Transport",
    "build_cache_key_payload",
    "canonical_request_hash",
    "parse_strict_json",
    "sanitize_prompt",
]


class Transport(Protocol):
    """The only network seam. Fakes are supplied by tests."""

    async def __call__(self, request: "GatewayRequest") -> str: ...


class ReplayMiss(RuntimeError):
    """Replay backend has no recorded response for this request hash."""


@dataclass(frozen=True)
class GatewayRequest:
    agent: str
    prompt: str
    consequence_id: str
    score: int = 0
    model: str = "fast"
    cost: int = 1

    def key_payload(self) -> dict[str, Any]:
        return build_cache_key_payload(
            agent=self.agent,
            model=self.model,
            prompt_hash=hashlib.sha256(self.prompt.encode()).hexdigest(),
            consequence_id=self.consequence_id,
        )

    @property
    def cache_key(self) -> str:
        return canonical_request_hash(self.key_payload())


@dataclass(frozen=True)
class GatewayResponse:
    parsed: dict[str, Any]
    text: str
    cached: bool = False
    fallback: bool = False


@dataclass(frozen=True)
class ReplayBackend:
    """Recorded responses keyed by canonical request hash. Never a network client."""

    recorded: Mapping[str, str] = field(default_factory=dict)

    async def __call__(self, request: GatewayRequest) -> str:
        key = request.cache_key
        try:
            return self.recorded[key]
        except KeyError:
            raise ReplayMiss(f"no recorded response for {key}") from None


class GrokGateway:
    """The one gateway every agent calls."""

    def __init__(
        self,
        *,
        clock: Clock,
        budget: LayeredBudget,
        transport: Callable[[GatewayRequest], Awaitable[str]],
        prefilter: Prefilter | None = None,
        cache: Cache | None = None,
        ledger: GatewayLedger | None = None,
        coalescer: Coalescer | None = None,
    ) -> None:
        self._clock = clock
        self._budget = budget
        self._transport = transport
        self._prefilter = prefilter if prefilter is not None else Prefilter(clock=clock)
        self._cache = cache if cache is not None else Cache(clock=clock)
        self._ledger = ledger if ledger is not None else GatewayLedger()
        self._coalescer = coalescer if coalescer is not None else Coalescer()

    @property
    def ledger(self) -> GatewayLedger:
        return self._ledger

    @property
    def transport_calls(self) -> int:
        return self._ledger.transport_calls

    async def call(self, request: GatewayRequest) -> GatewayResponse | None:
        """Run one request. Returns None when the prefilter skips it (no spend)."""
        if not request.consequence_id:
            raise ValueError("consequence_id is required on every gateway call")
        if not self._prefilter.admits(request.score):
            self._ledger.record(
                request_hash=request.cache_key,
                agent=request.agent,
                outcome="skipped",
                lamports=0,
            )
            return None
        if not self._budget.try_debit(request.agent, request.cost):
            raise BudgetExhausted(f"budget exhausted for {request.agent}")
        sanitized = sanitize_prompt(request.prompt)
        cached = self._cache.get(request.cache_key, request.agent)
        if cached is not None:
            self._ledger.record(
                request_hash=request.cache_key,
                agent=request.agent,
                outcome="cached",
                lamports=0,
            )
            return GatewayResponse(parsed=parse_strict_json(cached), text=cached, cached=True)

        async def _once() -> GatewayResponse:
            text = await self._transport(request)
            received = text
            # Fallback responses may be flagged by the transport convention
            # "[fallback]{...}"; the rest of the gateway treats them as
            # untrusted model output and sanitizes identically.
            if received.startswith("[fallback]"):
                received = received[len("[fallback]") :]
            parsed = parse_strict_json(sanitize_prompt(received))
            self._ledger.record(
                request_hash=request.cache_key,
                agent=request.agent,
                outcome="transport",
                lamports=request.cost,
            )
            return GatewayResponse(parsed=parsed, text=text, fallback=text.startswith("[fallback]"))

        response = await self._coalescer.run(request.cache_key, _once)
        if not response.fallback:
            self._cache.set(request.cache_key, response.text, request.agent)
        return response
