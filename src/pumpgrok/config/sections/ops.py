"""Ops settings sections: process state paths, human alert destinations and the health bind.

Split out of config/settings.py (11-04, CONTEXT D-11). Each section keeps its class name, field
set, validators and defaults, so its JSON schema and default-value digest stay as pinned in
tests/config/test_settings_surface_characterization.py.
"""

from __future__ import annotations

import ipaddress
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEALTH_HOST_LABEL_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
_HEALTH_HOST_NUMERIC_RE = re.compile(r"[0-9.]+")


class OpsSettings(BaseModel):
    """Process-lifetime state paths (vendor OpsConfig subset, Phase 2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reputation_path: str = "var/reputation.json"


class NotifySettings(BaseModel):
    """Human alert destinations (TOOL-006, R39).

    ``allowlist`` holds Telegram chat ids and webhook URLs; empty means
    stdout and file only. The Telegram token travels via env
    ``PUMPGROK_TELEGRAM_TOKEN`` only, never TOML and never this model.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    allowlist: list[str] = Field(default_factory=list)


class HealthSettings(BaseModel):
    """Health server bind host and port (INV-C-11).

    Port default 0 (disabled: never bind a socket under test or --once/--replay).
    The container sets PUMPGROK_HEALTH__PORT=8080 and PUMPGROK_HEALTH__HOST=0.0.0.0
    via compose (plan 07); --once/--replay forces 0 through health_port()
    regardless of this value. Host defaults to loopback: direct host runs never
    expose /healthz and /metrics to the LAN unless the operator opts into
    0.0.0.0 explicitly.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=0, ge=0, le=65535)

    @field_validator("host")
    @classmethod
    def _validate_host(cls, v: str) -> str:
        """Accept an IP literal or an RFC 1123 hostname; fail fast otherwise.

        Without this, a typo such as ``256.300.1.1`` survives load_settings()
        and only fails later as an unhandled socket.gaierror from
        asyncio.start_server. Dotted-numeric values must parse as IPv4 so a
        mistyped address is not mistaken for a hostname.
        """
        try:
            ipaddress.ip_address(v)
        except ValueError:
            pass
        else:
            return v
        if ":" in v or _HEALTH_HOST_NUMERIC_RE.fullmatch(v):
            raise ValueError(f"invalid health host: {v!r}")
        name = v[:-1] if v.endswith(".") else v
        if not name or len(name) > 253:
            raise ValueError(f"invalid health host: {v!r}")
        if not all(_HEALTH_HOST_LABEL_RE.match(label) for label in name.split(".")):
            raise ValueError(f"invalid health host: {v!r}")
        return v
