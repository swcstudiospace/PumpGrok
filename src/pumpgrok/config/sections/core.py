"""Core settings sections: run mode, data and RPC ingress, LLM and quote endpoints, wallet.

Split out of config/settings.py (11-04, CONTEXT D-11). Each section keeps its class name, field
set, validators and defaults, so its JSON schema and default-value digest stay as pinned in
tests/config/test_settings_surface_characterization.py. settings.py imports these classes and
declares one field per section.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from pumpgrok.core.units import LAMPORTS_PER_SOL

Mode = Literal["paper", "live"]

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_INDEX = {char: index for index, char in enumerate(_BASE58_ALPHABET)}
_PUBLIC_KEY_BYTES = 32
# A 32-byte value encodes to at most 44 base58 characters, so longer input is
# refused before any big-integer arithmetic.
_PUBLIC_KEY_MAX_CHARS = 44


def _require_scheme(url: str, schemes: tuple[str, ...]) -> str:
    """Refuse a URL whose scheme is not one of ``schemes`` (TLS only; value never echoed)."""
    if urlsplit(url).scheme.lower() not in schemes:
        raise ValueError(f"URL must use {' or '.join(s + '://' for s in schemes)}")
    return url


class DataSettings(BaseModel):
    """Pump.fun REST plus PumpPortal websocket ingress (D8)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rest_url: str = "https://frontend-api.pump.fun"
    ws_url: str = "wss://pumpportal.fun/api/data"
    ws_max_queue: int = Field(default=16, ge=1)
    request_timeout: float = 10.0

    @field_validator("rest_url")
    @classmethod
    def _tls_rest_url(cls, v: str) -> str:
        return _require_scheme(v, ("https",))

    @field_validator("ws_url")
    @classmethod
    def _tls_ws_url(cls, v: str) -> str:
        return _require_scheme(v, ("https", "wss"))


class RpcSettings(BaseModel):
    """Solana JSON-RPC failover list. Endpoints are keyless URLs only.

    Paid-provider keys travel in ``api_key`` and are sent as a header;
    key-bearing endpoint values are refused at startup (T-02-01).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    endpoints: list[str] = Field(default_factory=lambda: ["https://api.mainnet-beta.solana.com"])
    api_key: SecretStr = SecretStr("")

    @field_validator("endpoints")
    @classmethod
    def _tls_endpoints(cls, v: list[str]) -> list[str]:
        for endpoint in v:
            _require_scheme(endpoint, ("https", "wss"))
        return v


class GrokSettings(BaseModel):
    """x.ai chat completions (R48). Secrets arrive via env only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str = "https://api.x.ai/v1"
    strong_model: str = "grok-4.3"
    strong_effort: str = "low"
    fast_model: str = "grok-4.20-0309-non-reasoning"
    api_key: SecretStr = SecretStr("")

    @field_validator("base_url")
    @classmethod
    def _tls_base_url(cls, v: str) -> str:
        return _require_scheme(v, ("https",))


class JupiterSettings(BaseModel):
    """Jupiter Swap V2 quote endpoint, informational only (R44, R38)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    quote_url: str = "https://api.jup.ag/swap/v2/order"

    @field_validator("quote_url")
    @classmethod
    def _tls_quote_url(cls, v: str) -> str:
        return _require_scheme(v, ("https", "wss"))


def _base58_decode(text: str) -> bytes:
    """Decode base58 with the stdlib; ValueError on any character outside the alphabet.

    Each leading '1' stands for one zero byte.
    """
    number = 0
    for char in text:
        digit = _BASE58_INDEX.get(char)
        if digit is None:
            raise ValueError("character outside the base58 alphabet")
        number = number * 58 + digit
    leading_zeros = len(text) - len(text.lstrip("1"))
    body = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return b"\x00" * leading_zeros + body


def _is_public_key_text(text: str) -> bool:
    """True when text is base58 and decodes to exactly 32 bytes; never raises."""
    if len(text) > _PUBLIC_KEY_MAX_CHARS:
        return False
    try:
        return len(_base58_decode(text)) == _PUBLIC_KEY_BYTES
    except ValueError:
        return False


class PlatformSettings(BaseModel):
    """Declares what the desk trades on. It selects no endpoint and changes no mode.

    Live stays refused by the live gate.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    chain: Literal["solana"] = "solana"
    venue: Literal["pumpfun-bonding-curve"] = "pumpfun-bonding-curve"
    execution: Literal["paper"] = "paper"
    quote_only: tuple[Literal["jupiter-swap-v2"], ...] = ("jupiter-swap-v2",)


class WalletSettings(BaseModel):
    """Wallet allowlist of PUBLIC KEYS only (base58, exactly 32 bytes each).

    Seeds, private keys and keypairs are never valid here. A failing entry is
    reported by its index alone; its value is never echoed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    allowlist: tuple[str, ...] = ()

    @field_validator("allowlist")
    @classmethod
    def _validate_allowlist(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        """Every entry must be a base58 string that decodes to exactly 32 bytes."""
        for index, entry in enumerate(v):
            if not _is_public_key_text(entry):
                raise ValueError(f"allowlist entry {index} is not a 32-byte base58 public key")
        return v


class ExecutionSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Mode = "paper"


class ReplaySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # INT-05: the composition-root default seed. Deliberately a literal, not an
    # import of the replay-module seed constant, which must stay inside replay code.
    seed: int = 20260101


class LiveSettings(BaseModel):
    """The live gate reads these caps; enabling live still requires every precondition.

    Money is integer lamports; 1 SOL is 1_000_000_000.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    notional_cap_lamports: int | None = LAMPORTS_PER_SOL

    @field_validator("notional_cap_lamports")
    @classmethod
    def _validate_notional_cap(cls, v: int | None) -> int | None:
        """A set cap must be positive and no more than the 1 SOL ceiling."""
        if v is not None and not 0 < v <= LAMPORTS_PER_SOL:
            raise ValueError("notional_cap_lamports must be in (0, 1 SOL]")
        return v
