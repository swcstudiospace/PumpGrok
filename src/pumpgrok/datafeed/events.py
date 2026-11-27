"""Shared datafeed event types. Frozen models, integer money only, extra forbid.

Also defines read-only curve observations consumed by the event bridge.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from pumpgrok.replay.clock import parse_ts_utc


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


@dataclass(frozen=True)
class CurveObservation:
    mint: str
    ts_utc: str
    s_lamports: int
    t_units: int
    complete: bool
    source: str

    def validate(self) -> float:
        """Validate without coercion and return the UTC observation time."""
        if not isinstance(self.mint, str) or not self.mint.strip():
            raise ValueError("mint must be a nonempty string")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a nonempty string")
        if not isinstance(self.ts_utc, str):
            raise ValueError("timestamp must be a UTC string")
        try:
            stamp = datetime.fromisoformat(self.ts_utc)
            if stamp.utcoffset() != timedelta(0):
                raise ValueError("timestamp must use UTC")
            epoch = parse_ts_utc(self.ts_utc)
        except (ValueError, OverflowError, OSError) as exc:
            raise ValueError("timestamp must be a valid UTC timestamp") from exc
        if type(self.s_lamports) is not int or self.s_lamports <= 0:
            raise ValueError("SOL reserves must be a positive integer")
        if type(self.t_units) is not int or self.t_units <= 0:
            raise ValueError("token reserves must be a positive integer")
        if type(self.complete) is not bool:
            raise ValueError("complete must be a boolean")
        return epoch

    def replay_tick(self) -> dict[str, str | int | bool]:
        """Map base-unit observation fields to the existing replay tick format."""
        return {
            "kind": "tick",
            "mint": self.mint,
            "ts_utc": self.ts_utc,
            "S": self.s_lamports,
            "T": self.t_units,
            "complete": self.complete,
            "source": self.source,
        }
