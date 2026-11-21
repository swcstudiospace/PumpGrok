"""Shared datafeed event types. Frozen models, integer money only, extra forbid."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CurveTick(BaseModel):
    """One integer bonding-curve tick. No float money; ratios stay Decimal elsewhere."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mint: str = Field(min_length=1)
    ts_utc: str = Field(min_length=1)
    virtual_sol_reserves_lamports: int = Field(strict=True, ge=0)
    virtual_token_reserves_units: int = Field(strict=True, ge=0)
    real_sol_reserves_lamports: int = Field(strict=True, ge=0)
    real_token_reserves_units: int = Field(strict=True, ge=0)
    total_supply_units: int = Field(strict=True, ge=0)
    complete: bool
    curve_source: str = "replay"


class GapEvent(BaseModel):
    """A feed gap: no frames arrived for an interval. First-class bus event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mint: str | None = None
    ts_utc: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    from_ts_utc: str = Field(min_length=1)
    to_ts_utc: str = Field(min_length=1)
    curve_source: str = "replay"


class TokenCreated(BaseModel):
    """A new token was created on the curve (free PumpPortal frame)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mint: str = Field(min_length=1)
    ts_utc: str = Field(min_length=1)
    curve_source: str = "pumpportal"


class Migrated(BaseModel):
    """A token migrated off the curve."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mint: str = Field(min_length=1)
    ts_utc: str = Field(min_length=1)
    curve_source: str = "pumpportal"


class TradeSeen(BaseModel):
    """A trade was seen via logsSubscribe on a bonding-curve account."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mint: str = Field(min_length=1)
    ts_utc: str = Field(min_length=1)
    signature: str = Field(min_length=1)
    sol_amount_lamports: int = Field(strict=True, ge=0)
    token_amount_units: int = Field(strict=True, ge=0)
    curve_source: str = "pumpportal"


class MarkMade(BaseModel):
    """A mark was recorded for a held mint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mint: str = Field(min_length=1)
    ts_utc: str = Field(min_length=1)
    price_lamports: int = Field(strict=True, ge=0)
    curve_source: str = "replay"


DatafeedEvent = CurveTick | GapEvent | TokenCreated | Migrated | TradeSeen | MarkMade
