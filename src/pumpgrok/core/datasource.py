"""Data source contracts: freshness, health, and the fetch protocol (interfaces.md 2.6)."""

from __future__ import annotations

import enum
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class Freshness(BaseModel):
    model_config = ConfigDict(frozen=True)

    fetched_at: datetime
    age_s: float = Field(ge=0.0)
    max_age_s: float = Field(gt=0.0)

    @property
    def stale(self) -> bool:
        return self.age_s > self.max_age_s


class HealthStatus(enum.StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class Health(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: HealthStatus
    checked_at: datetime
    consecutive_failures: int = Field(ge=0)
    breaker_open: bool = False
    cooldown_until: datetime | None = None
    detail: str | None = None


@runtime_checkable
class DataSource(Protocol):
    """A market, on-chain, or social feed (D8 sources only).

    `fetch` must never raise on upstream failure; it returns the cached value with
    `Freshness.stale == True` or raises DataStale when no cache exists.
    """

    name: str  # 'pumpfun_rest' | 'pumpportal_ws' | 'jupiter_lite' | 'solana_rpc' | 'xai_grok'
    rate_limit_key: str

    async def fetch(
        self, request: Mapping[str, Any], *, max_age_s: float
    ) -> tuple[Any, Freshness]: ...

    def freshness(self, key: str) -> Freshness | None: ...

    async def health(self) -> Health: ...

    async def aclose(self) -> None: ...
