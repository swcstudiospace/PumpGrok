"""v4 settings sections. Each ships off, with an empty allowlist.

No sockets, URLs, keys, or network clients. Later plans wire behavior
only when a section is explicitly enabled.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


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


class RecorderSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    allowlist: tuple[str, ...] = ()


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
    model: Literal["v1"] = "v1"
