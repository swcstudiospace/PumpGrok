"""Shared Grok call guards: rate limit, daily budget, concurrency.

Port of the vendor ``ops.py`` ``GrokOps`` minus the circuit breaker and the
metrics sink, both Phase 4 per R52. ``precheck`` therefore reports only the
daily budget; the fail-closed behavior on a blown budget is unchanged (the
agent falls back to its pessimistic result). Concurrency still flows through
one semaphore plus the token bucket, on the injected clock.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pumpgrok.core.budget import CallBudget
from pumpgrok.core.ratelimit import RateLimiter


class GrokOps:
    """Process-wide limiters and call counters shared by every agent."""

    def __init__(self, limiter: RateLimiter, budget: CallBudget, max_concurrency: int = 1) -> None:
        self.limiter = limiter
        self.budget = budget
        self.semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self.tokens_in = 0
        self.tokens_out = 0
        self.calls: dict[str, int] = {}
        self.throttled: dict[str, int] = {}
        self.blocked: dict[str, int] = {}
        self.failures: dict[str, int] = {}

    def precheck(self, agent: str) -> str | None:
        """Why not to call Grok right now, or None when calling is fine."""
        if not self.budget.try_spend():
            self.blocked[agent] = self.blocked.get(agent, 0) + 1
            return f"daily call budget exhausted ({self.budget.max_per_day})"
        return None

    @asynccontextmanager
    async def slot(self, agent: str) -> AsyncIterator[None]:
        """One guarded call position: concurrency plus call rate."""
        async with self.semaphore:
            waited = await self.limiter.acquire()
            if waited > 0:
                self.throttled[agent] = self.throttled.get(agent, 0) + 1
            self.calls[agent] = self.calls.get(agent, 0) + 1
            yield

    def record_success(self, agent: str, usage: dict[str, Any] | None = None) -> None:
        """Account a completed call, folding token usage when reported."""
        if usage:
            self.tokens_in += int(usage.get("prompt_tokens") or 0)
            self.tokens_out += int(usage.get("completion_tokens") or 0)

    def record_failure(self, agent: str) -> None:
        """Account a failed call (transport error, bad shape, 4xx/5xx)."""
        self.failures[agent] = self.failures.get(agent, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        """Operator-visible counters. Nothing secret is ever included."""
        return {
            "budget_spent": self.budget.spent,
            "budget_remaining": self.budget.remaining,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "calls": dict(self.calls),
            "throttled": dict(self.throttled),
            "blocked": dict(self.blocked),
            "failures": dict(self.failures),
        }
