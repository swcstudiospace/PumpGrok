"""v4 settings sections. Each ships off, with an empty allowlist.

No sockets, URLs, keys, or network clients. Later plans wire behavior
only when a section is explicitly enabled.
"""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict

#: Supervisor wake modes. `cadence` is the default and stays byte-identical; `event` wakes seats
#: from the event bus (EVT-10). Selected by `--wake-mode` or `events.wake_mode`.
WakeMode = Literal["cadence", "event"]
WAKE_MODES: tuple[str, ...] = get_args(WakeMode)


def resolve_wake_mode(cli_value: str | None, settings_value: str) -> str:
    """The explicit `--wake-mode` flag wins; with no flag the settings value applies."""
    return settings_value if cli_value is None else cli_value


class EventsSettings(BaseModel):
    """Event sidecar. Wake mode selects cadence or event; the path is a local file, not a socket."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    allowlist: tuple[str, ...] = ()
    wake_mode: WakeMode = "cadence"
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
