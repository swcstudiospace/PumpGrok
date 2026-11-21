"""v4 settings sections. Each ships off, with an empty allowlist.

No sockets, URLs, keys, or network clients. Later plans wire behavior
only when a section is explicitly enabled.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EventsSettings(BaseModel):
    """Event sidecar. Cadence wake only; the path is a local file, not a socket."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    allowlist: tuple[str, ...] = ()
    wake_mode: Literal["cadence"] = "cadence"
    sidecar_path: str = "var/desk/events.sqlite"


class GrokGatewaySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    allowlist: tuple[str, ...] = ()


class DatafeedSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    allowlist: tuple[str, ...] = ()
    watch_cap: int = Field(default=32, ge=1, le=1000)
    rate_limit_per_10s: int = Field(default=30, ge=1, le=1000)
    feed_state_dir: str = "var/desk/datafeed"


class RecorderSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    allowlist: tuple[str, ...] = ()
    dataset_root: str = "var/desk/datasets"


class StrategiesSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    allowlist: tuple[str, ...] = ()


class BacktestV2Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    allowlist: tuple[str, ...] = ()


class RiskStrategySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    allowlist: tuple[str, ...] = ()


class PromotionSettings(BaseModel):
    """Promotion gate config. No interval field; the clock stays in the caller."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    allowlist: tuple[str, ...] = ()


class SignerSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    allowlist: tuple[str, ...] = ()


class PaperFeesSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    allowlist: tuple[str, ...] = ()
    model: Literal["v1", "v2"] = "v1"
