"""Single admission path for event-driven Grok requests (GRK-01, GRK-03, GRK-06).

Order for every request:

1. deterministic prefilter, before any cost: a rejected candidate spends nothing;
2. sanitize the untrusted text;
3. cache lookup on the canonical key (a negative entry short-circuits);
4. in-flight coalescing: identical concurrent requests share one call;
5. circuit breaker: an open breaker refuses without spend;
6. persisted layered budget: one atomic charge for admitted transport work;
7. transport under the call deadline, with a bounded in-flight count.

Every refusal returns a ``GrokOutcome`` with a reason for the fallback ladder.
Fallbacks are never cached and never count as model success. The caller
chooses observe-only or pessimistic handling from the reason.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal, Protocol

from pumpgrok.grok.budget import BudgetUnavailable, LayeredBudget
from pumpgrok.grok.cache import (
    TTL_S_BY_AGENT,
    CacheUnavailable,
    ResponseCache,
    cache_key,
    scalar_fields,
)
from pumpgrok.replay.clock import Clock

# Design A prefilter values (14-DESIGN-A-DECISIONS.md, owner-approved 2026-11-13).
MIN_AGE_S = 120
MAX_AGE_S = 3600
MIN_UNIQUE_BUYERS = 5
MARKET_WINDOW_S = 3600
MINT_COOLDOWN_S = 300
MIN_PRERANK = Decimal("0.5")

# Bounded concurrency, breaker and deadline (Design A sections 5 and 8).
MAX_INFLIGHT = 4
BREAKER_FAILURES = 3
BREAKER_COOLDOWN_S = 60
TRANSPORT_DEADLINE_S = 20

# Ordinary callers keep the reserve share; the checker may spend it.
RESERVE_AGENTS = frozenset({"checker"})

SANITIZER_VERSION = "1"

Status = Literal["fresh", "cache_hit", "coalesced", "prefilter_skip", "rule_fallback"]

_SHA_RE = re.compile(r"[0-9a-f]{64}")


def sanitize(text: str) -> str:
    """NFKC-normalise, then drop control and format characters. Tab and newline survive."""
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(
        ch for ch in normalized if ch in "\t\n" or unicodedata.category(ch) not in {"Cc", "Cf"}
    )


@dataclass(frozen=True)
class Candidate:
    """Facts about one candidate, all supplied by the event that triggered the request."""

    mint: str
    created_at: float
    first_trade_at: float
    unique_buyers: int
    prerank: Decimal
    last_decision_at: float | None = None


@dataclass(frozen=True)
class PrefilterVerdict:
    admit: bool
    reason: str


def prefilter(candidate: Candidate, *, now: float) -> PrefilterVerdict:
    """Pure, ordered admission rules. The same inputs always give the same verdict."""
    if not 0 <= candidate.prerank <= 1:
        return PrefilterVerdict(False, "prerank_out_of_range")
    age = now - candidate.created_at
    if age < MIN_AGE_S:
        return PrefilterVerdict(False, "too_young")
    if age > MAX_AGE_S:
        return PrefilterVerdict(False, "too_old")
    if now - candidate.first_trade_at > MARKET_WINDOW_S:
        return PrefilterVerdict(False, "market_window_closed")
    last_decision = candidate.last_decision_at
    if last_decision is not None and now - last_decision < MINT_COOLDOWN_S:
        return PrefilterVerdict(False, "mint_cooldown")
    if candidate.unique_buyers < MIN_UNIQUE_BUYERS:
        return PrefilterVerdict(False, "too_few_buyers")
    if candidate.prerank < MIN_PRERANK:
        return PrefilterVerdict(False, "low_prerank")
    return PrefilterVerdict(True, "admitted")


@dataclass(frozen=True)
class GrokRequest:
    """One Grok call wanted for one event. ``event_id`` is the causation id and is required."""

    event_id: str
    agent: str
    model: str
    prompt_sha: str
    schema: str
    input: Mapping[str, int | str | Decimal]
    text: str
    candidate: Candidate

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id (causation) is required")
        if self.agent not in TTL_S_BY_AGENT:
            raise ValueError(f"unknown agent {self.agent!r}")
        if not _SHA_RE.fullmatch(self.prompt_sha):
            raise ValueError("prompt_sha must be 64 lowercase hex characters")
        if "text_sha" in self.input:
            raise ValueError("input field 'text_sha' is reserved for the sanitized text digest")
        scalar_fields(self.input)


@dataclass(frozen=True)
class GrokOutcome:
    """Result of admission. ``response`` is set only for fresh, cache_hit and coalesced."""

    status: Status
    event_id: str
    response: str | None
    reason: str | None


class GrokTransport(Protocol):
    """The real model call. Raises on any failure; returns the response text on success."""

    async def __call__(self, request: GrokRequest, text: str) -> str: ...


class CircuitBreaker:
    """Three consecutive failures open it; after the cooldown one half-open probe runs."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._probe = False

    @property
    def llm_available(self) -> bool:
        return self._opened_at is None

    def admits(self) -> bool:
        if self._opened_at is None:
            return True
        if self._probe:
            return False
        return self._clock.now() - self._opened_at >= BREAKER_COOLDOWN_S

    def start(self) -> None:
        """Mark a call as started. While half-open this is the single probe."""
        if self._opened_at is not None:
            self._probe = True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._probe = False

    def record_failure(self) -> None:
        now = self._clock.now()
        if self._opened_at is not None:
            self._opened_at = now
            self._probe = False
            return
        self._failures += 1
        if self._failures >= BREAKER_FAILURES:
            self._opened_at = now

    def abandon(self) -> None:
        """A started call was cancelled before any verdict; free the probe slot."""
        self._probe = False


class GrokGateway:
    """The one place a Grok call is admitted, cached, coalesced, charged and sent."""

    def __init__(
        self,
        *,
        clock: Clock,
        transport: GrokTransport,
        cache: ResponseCache,
        budget: LayeredBudget,
    ) -> None:
        self._clock = clock
        self._transport = transport
        self._cache = cache
        self._budget = budget
        self._breaker = CircuitBreaker(clock)
        self._slots = asyncio.Semaphore(MAX_INFLIGHT)
        self._inflight: dict[str, asyncio.Future[GrokOutcome]] = {}

    @property
    def llm_available(self) -> bool:
        return self._breaker.llm_available

    async def admit(self, request: GrokRequest) -> GrokOutcome:
        verdict = prefilter(request.candidate, now=self._clock.now())
        if not verdict.admit:
            return GrokOutcome("prefilter_skip", request.event_id, None, verdict.reason)

        text = sanitize(request.text)
        try:
            key = _request_key(request, text)
            cached = self._cache.get(key)
        except CacheUnavailable:
            return _fallback(request, "cache_unavailable")

        if cached is not None:
            if cached.status == "ok":
                return GrokOutcome("cache_hit", request.event_id, cached.response, None)
            return _fallback(request, "cached_transport_error")

        pending = self._inflight.get(key)
        if pending is not None:
            shared = await asyncio.shield(pending)
            if shared.response is not None:
                return replace(shared, event_id=request.event_id, status="coalesced")
            return replace(shared, event_id=request.event_id)

        return await self._own(request, text, key)

    async def _own(self, request: GrokRequest, text: str, key: str) -> GrokOutcome:
        future: asyncio.Future[GrokOutcome] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        outcome: GrokOutcome | None = None
        try:
            outcome = await self._call(request, text, key)
            return outcome
        finally:
            if outcome is None:  # the owner was cancelled before a verdict
                outcome = _fallback(request, "cancelled")
            self._inflight.pop(key, None)
            future.set_result(outcome)

    async def _call(self, request: GrokRequest, text: str, key: str) -> GrokOutcome:
        if not self._breaker.admits():
            return _fallback(request, "breaker_open")
        started = False
        try:
            # The deadline covers the wait for an in-flight slot: a queued call is
            # bounded like any other and cannot reach the transport after its deadline.
            async with self._clock.timeout(TRANSPORT_DEADLINE_S), self._slots:
                # Re-check after the wait: the breaker may have opened, and the budget
                # may have run out, while this call was queued.
                if not self._breaker.admits():
                    return _fallback(request, "breaker_open")
                try:
                    charged = self._budget.try_charge(
                        reserve_priority=request.agent in RESERVE_AGENTS
                    )
                except BudgetUnavailable:
                    return _fallback(request, "budget_unavailable")
                if not charged:
                    return _fallback(request, "budget_exhausted")
                self._breaker.start()
                started = True
                response = await self._transport(request, text)
        except TimeoutError:
            if not started:  # timed out in the slot queue; the transport never ran
                return _fallback(request, "timeout")
            return self._failed(request, key, "timeout")
        except Exception:
            return self._failed(request, key, "transport_error")
        except BaseException:
            if started:  # only the call that took the half-open probe may release it
                self._breaker.abandon()
            raise

        if not isinstance(response, str):
            return self._failed(request, key, "transport_error")
        self._breaker.record_success()
        try:
            self._cache.put_ok(key, agent=request.agent, response=response)
        except CacheUnavailable:
            pass  # the response is valid and already paid for; only the reuse is lost
        return GrokOutcome("fresh", request.event_id, response, None)

    def _failed(self, request: GrokRequest, key: str, reason: str) -> GrokOutcome:
        self._breaker.record_failure()
        try:
            self._cache.put_error(key, agent=request.agent)
        except CacheUnavailable:
            pass
        return _fallback(request, reason)


def _request_key(request: GrokRequest, text: str) -> str:
    text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return cache_key(
        agent=request.agent,
        model=request.model,
        prompt_sha=request.prompt_sha,
        schema=request.schema,
        sanitizer_version=SANITIZER_VERSION,
        fields={**request.input, "text_sha": text_sha},
    )


def _fallback(request: GrokRequest, reason: str) -> GrokOutcome:
    return GrokOutcome("rule_fallback", request.event_id, None, reason)
