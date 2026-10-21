"""Gateway configuration: per-seat tokens from the environment only (TOOL-010).

Token source is ``DESK_GATEWAY_TOKEN_<SHORT>`` (upper short, e.g.
``DESK_GATEWAY_TOKEN_SNIPER``). No secret ever lives in code, and tokens
are never logged; only the seat short name and the status code are.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

SEAT_CREDENTIAL_ENV_PREFIX = "DESK_GATEWAY_TOKEN_"


@dataclass(frozen=True)
class GatewayConfig:
    """Everything one gateway process binds with; ``tokens`` is never repr'd."""

    host: str
    port: int
    contracts_dir: Path
    data_dir: Path
    repo_root: Path
    tokens: Mapping[str, str] = field(repr=False)


def token_env_name(short: str) -> str:
    """Environment variable holding the bearer token for one seat short."""
    return f"{SEAT_CREDENTIAL_ENV_PREFIX}{short.upper()}"


def load_tokens(shorts: list[str], env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Read configured per-seat tokens; unconfigured seats are absent (503)."""
    source = env if env is not None else os.environ
    tokens: dict[str, str] = {}
    for short in shorts:
        value = source.get(token_env_name(short))
        if value:
            tokens[short] = value
    return tokens
