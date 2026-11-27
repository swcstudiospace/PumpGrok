"""Core settings sections: run mode, data and RPC ingress, LLM and quote endpoints, wallet.

Split out of config/settings.py (11-04, CONTEXT D-11). Each section keeps its class name, field
set, validators and defaults, so its JSON schema and default-value digest stay as pinned in
tests/config/test_settings_surface_characterization.py. settings.py imports these classes and
declares one field per section.
"""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import parse_qsl, unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from pumpgrok.core.ed25519_point import decode_public_point
from pumpgrok.core.units import LAMPORTS_PER_SOL

Mode = Literal["paper", "live"]

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_INDEX = {char: index for index, char in enumerate(_BASE58_ALPHABET)}
_PUBLIC_KEY_BYTES = 32
# A 32-byte value encodes to at most 44 base58 characters, so longer input is
_PUBLIC_KEY_MAX_CHARS = 44


class ConfigError(RuntimeError):
    """Settings are not fit to start. The list of problems is the argument."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__(
            "settings are not fit to start:\n"
            + "\n".join(f"- {problem}" for problem in self.problems)
        )


# A value shaped like a URL or argument carrying a secret: api-key=, api_key=,
# apikey=, secret=, password=, token=, or a bare key= parameter. The bare key=
# alternative requires a non-identifier char before it so that innocent words
# containing "key" (e.g. monkey=) do not match.
KEY_BEARING_VALUE_RE = re.compile(
    r"(?i)(?:api[-_]?key=|secret=|password=|token=|(?<![A-Za-z_-])key=)"
)

# Query parameter or path-style names that carry a credential: api-key, apikey, token, secret,
# key, password and suffixed forms (x-api-key, access_token, client_secret). A separator must
# precede the name, so innocent words such as monkey or tokenizer do not match.
_CREDENTIAL_PARAM_RE = re.compile(
    r"(?i)(?:^|[-_])(?:api[-_]?key|apikey|token|secret|key|password|passwd|pwd|auth)$"
)
# A long opaque token: 24+ URL-safe characters holding both a letter and a digit. Provider keys
# ride in path segments or parameter values; plain words and short version segments do not match.
_OPAQUE_TOKEN_RE = re.compile(r"(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{24,}")


def _refuse_credential_url(url: str, setting: str) -> None:
    """Refuse a URL that carries a credential: userinfo, a key parameter or an opaque token.

    Raises ConfigError naming ``setting`` only. It is a ConfigError rather than ValueError so
    pydantic does not copy the rejected URL into its ValidationError text.
    """
    parts = urlsplit(url)
    params = parse_qsl(parts.query, keep_blank_values=True)
    tokens = [unquote(segment) for segment in parts.path.split("/")]
    tokens.extend(value for _, value in params)
    credential = (
        "@" in parts.netloc
        or KEY_BEARING_VALUE_RE.search(url) is not None
        or any(_CREDENTIAL_PARAM_RE.search(name) for name, _ in params)
        or any(_OPAQUE_TOKEN_RE.fullmatch(token) for token in tokens)
    )
    if credential:
        raise ConfigError([f"{setting}: URL carries a credential (userinfo, key or opaque token)"])


def _require_scheme(url: str, schemes: tuple[str, ...], setting: str) -> str:
    """Refuse a URL off the TLS schemes or carrying a credential (value never echoed)."""
    if urlsplit(url).scheme.lower() not in schemes:
        raise ValueError(f"URL must use {' or '.join(s + '://' for s in schemes)}")
    _refuse_credential_url(url, setting)
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
        return _require_scheme(v, ("https",), "data.rest_url")

    @field_validator("ws_url")
    @classmethod
    def _tls_ws_url(cls, v: str) -> str:
        return _require_scheme(v, ("https", "wss"), "data.ws_url")


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
            _require_scheme(endpoint, ("https", "wss"), "rpc.endpoints")
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
        return _require_scheme(v, ("https",), "grok.base_url")


class JupiterSettings(BaseModel):
    """Jupiter Swap V2 quote endpoint, informational only (R44, R38)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    quote_url: str = "https://api.jup.ag/swap/v2/order"

    @field_validator("quote_url")
    @classmethod
    def _tls_quote_url(cls, v: str) -> str:
        return _require_scheme(v, ("https", "wss"), "jupiter.quote_url")


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
    """True when text is base58, decodes to 32 bytes and is an Ed25519 point; never raises."""
    if len(text) > _PUBLIC_KEY_MAX_CHARS:
        return False
    try:
        raw = _base58_decode(text)
    except ValueError:
        return False
    if len(raw) != _PUBLIC_KEY_BYTES:
        return False
    try:
        decode_public_point(raw)
    except ValueError:
        return False
    return True


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

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    allowlist: tuple[str, ...] = ()

    @field_validator("allowlist")
    @classmethod
    def _validate_allowlist(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        """Every entry must be a base58 string that decodes to exactly 32 bytes."""
        for index, entry in enumerate(v):
            if not _is_public_key_text(entry):
                raise ValueError(
                    f"allowlist entry {index} is not a 32-byte base58 Ed25519 public key"
                )
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
