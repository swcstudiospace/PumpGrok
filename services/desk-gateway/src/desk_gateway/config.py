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

from pumpgrok.ledger.paths import PAPER_LEDGER_PATH

SEAT_CREDENTIAL_ENV_PREFIX = "DESK_GATEWAY_TOKEN_"


@dataclass(frozen=True)
class GatewayConfig:
    """Everything one gateway process binds with; ``tokens`` is never repr'd.

    ``ledger_path`` is the one paper ledger, the file ``pumpgrok report --daily`` reads.
    ``data_dir`` holds the kill latch (``KILLSWITCH``) and the journal, not the ledger.
    """

    host: str
    port: int
    contracts_dir: Path
    data_dir: Path
    repo_root: Path
    tokens: Mapping[str, str] = field(repr=False)
    ledger_path: Path = PAPER_LEDGER_PATH
    # Bot token for the alert channel (RISK-004). Empty means no Telegram kill source.
    telegram_token: str = field(default="", repr=False)


def token_env_name(short: str) -> str:
    """Environment variable holding the bearer token for one seat short."""
    return f"{SEAT_CREDENTIAL_ENV_PREFIX}{short.upper()}"


#: Minimum bearer token length in bytes (HOST-10).
MIN_TOKEN_BYTES = 32

#: Hosts considered loopback for the bind refusal (HOST-09).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def is_loopback_host(host: str) -> bool:
    """True iff the bind host is loopback."""
    return host.strip().lower() in LOOPBACK_HOSTS


def _flag_set(environ: Mapping[str, str], name: str) -> bool:
    return environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def validate_gateway_bind(host: str, environ: Mapping[str, str] | None = None) -> None:
    """HOST-09: refuse a non-loopback bind unless TLS or a reverse proxy is flagged."""
    env = os.environ if environ is None else environ
    if is_loopback_host(host):
        return
    if _flag_set(env, "DESK_GATEWAY_TLS") or _flag_set(env, "DESK_GATEWAY_REVERSE_PROXY"):
        return
    raise ValueError(
        f"refused gateway bind on non-loopback host {host!r} without DESK_GATEWAY_TLS or DESK_GATEWAY_REVERSE_PROXY"
    )


def validate_tokens(tokens: Mapping[str, str]) -> None:
    """HOST-10: refuse tokens shorter than 32 bytes and equal-token pairs."""
    seen: dict[str, str] = {}
    for short, token in tokens.items():
        if len(token.encode("utf-8")) < MIN_TOKEN_BYTES:
            raise ValueError(f"gateway token for seat {short!r} is shorter than 32 bytes")
        if token in seen:
            raise ValueError(f"gateway tokens for seats {seen[token]!r} and {short!r} are equal")
        seen[token] = short


def load_tokens(shorts: list[str], env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Read configured per-seat tokens; unconfigured seats are absent (503)."""
    source = env if env is not None else os.environ
    tokens: dict[str, str] = {}
    for short in shorts:
        value = source.get(token_env_name(short))
        if value:
            tokens[short] = value
    return tokens
