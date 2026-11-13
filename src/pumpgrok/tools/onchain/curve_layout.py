"""Bonding-curve account decode over Solana RPC (STRUCT-002, B9, T-03-02-01).

[VERIFIED] The Pump IDL describes an 8-byte discriminator, five token-first
little-endian u64 counters, and a one-byte completion flag. The 49-byte
token-first layout was approved by human review (``LAYOUT_REVIEWED_BY``).
The 166-byte extended layout has no reviewed source and is refused (fail closed).
Shared by ``market.price`` and ``onchain.lp_status``.

RPC only: this module performs no HTTP reads outside the injected RPC
client and references no quote endpoint (R44, R46, R47).
"""

from __future__ import annotations

import base64
import struct
from decimal import Decimal
from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict

from pumpgrok.core.units import lamports_to_sol, sol_to_lamports
from pumpgrok.tools._common import UNITS_PER_TOKEN

_CURVE_STRUCT = struct.Struct("<8sQQQQQB")
CURVE_ACCOUNT_SIZE = _CURVE_STRUCT.size
_EXTENDED_CURVE_ACCOUNT_SIZE = 166
_BONDING_CURVE_DISCRIMINATOR = bytes.fromhex("17b7f83760d8ac60")

#: Bonding-curve layout verification state (R65). VERIFIED for the 49-byte
#: token-first account only, set by the human reviewer named in
#: ``LAYOUT_REVIEWED_BY``. The 166-byte extended layout stays ASSUMED and is
#: refused by :func:`decode_curve_account`. Price admission does not read this
#: status; it is gated by :func:`rpc_curve_price_allowed` provenance.
LAYOUT_STATUS: Final[str] = "VERIFIED"
LAYOUT_REVIEWED_BY: Final[str] = "human:Ove"

#: Lamports of real SOL at which the curve is considered complete (catalog:
#: 85 SOL, the retired oracle ``src/monitor.py:30``). [ASSUMED] threshold.
COMPLETION_SOL_LAMPORTS = sol_to_lamports(Decimal(85))


class CurveDecodeError(ValueError):
    """The account bytes do not match the verified curve layout."""


class CurveState(BaseModel):
    """Decoded bonding-curve counters. Money is int; ratios stay Decimal."""

    model_config = ConfigDict(frozen=True)

    virtual_sol_reserves_lamports: int
    virtual_token_reserves_units: int
    real_sol_reserves_lamports: int
    real_token_reserves_units: int
    total_supply_units: int
    complete: bool


def decode_curve_account(data: bytes) -> CurveState:
    """Decode raw account bytes with the VERIFIED 49-byte token-first layout.

    Raises :class:`CurveDecodeError` for the 166-byte extended layout (ASSUMED,
    refused fail closed), an unsupported size, a discriminator, or a completion
    flag; callers map it to ``DataStale``.
    """
    if len(data) == _EXTENDED_CURVE_ACCOUNT_SIZE:
        raise CurveDecodeError(
            f"{_EXTENDED_CURVE_ACCOUNT_SIZE}-byte extended curve layout is ASSUMED; refused"
        )
    if len(data) != CURVE_ACCOUNT_SIZE:
        raise CurveDecodeError(f"unsupported curve account size {len(data)}")
    discriminator, vtok, vsol, rtok, rsol, supply, complete = _CURVE_STRUCT.unpack_from(data)
    if discriminator != _BONDING_CURVE_DISCRIMINATOR:
        raise CurveDecodeError("invalid bonding curve discriminator")
    if complete not in (0, 1):
        raise CurveDecodeError(f"curve completion flag not boolean: {complete!r}")
    for name, value in (
        ("virtual_sol", vsol),
        ("virtual_token", vtok),
        ("real_sol", rsol),
        ("real_token", rtok),
        ("supply", supply),
    ):
        if value == 0 and name in ("virtual_sol", "virtual_token", "supply"):
            raise CurveDecodeError(f"curve reserve {name} is zero; price undefined")
    return CurveState(
        virtual_sol_reserves_lamports=vsol,
        virtual_token_reserves_units=vtok,
        real_sol_reserves_lamports=rsol,
        real_token_reserves_units=rtok,
        total_supply_units=supply,
        complete=bool(complete),
    )


def decode_curve_account_base64(data: object) -> CurveState:
    """Decode the ``data`` field of a base64 ``getAccountInfo`` value.

    Accepts only the ``["<base64>", "base64"]`` pair form. The ``jsonParsed``
    object form carries no curve bytes and is rejected as malformed.
    """
    if not isinstance(data, list) or len(data) != 2 or data[1] != "base64":
        raise CurveDecodeError("curve account is not base64-encoded bytes")
    try:
        raw = base64.b64decode(data[0], validate=True)
    except (ValueError, TypeError) as exc:
        raise CurveDecodeError("curve account base64 is malformed") from exc
    return decode_curve_account(raw)


def encode_curve_fixture(
    *,
    virtual_sol_reserves_lamports: int,
    virtual_token_reserves_units: int,
    real_sol_reserves_lamports: int,
    real_token_reserves_units: int,
    total_supply_units: int,
    complete: bool,
) -> bytes:
    """Build [ASSUMED]-layout account bytes for tests. Never used in production."""
    return _CURVE_STRUCT.pack(
        _BONDING_CURVE_DISCRIMINATOR,
        virtual_token_reserves_units,
        virtual_sol_reserves_lamports,
        real_token_reserves_units,
        real_sol_reserves_lamports,
        total_supply_units,
        1 if complete else 0,
    )


def curve_price_sol_per_token(state: CurveState) -> Decimal:
    """SOL per token from virtual reserves (vendor ``price_from_reserves`` math).

    The ported float expression ``(vsol / 1e9) / (vtok / 1e6)`` is evaluated
    here in :class:`Decimal` at the wrapper boundary; the vendor module keeps
    its float form untouched (characterization pins).
    """
    return lamports_to_sol(
        Decimal(state.virtual_sol_reserves_lamports)
        / Decimal(state.virtual_token_reserves_units)
        * Decimal(UNITS_PER_TOKEN)
    )


def curve_progress(state: CurveState) -> Decimal:
    """Completion ratio 0..1 from real SOL against the 85 SOL bar."""
    ratio = Decimal(state.real_sol_reserves_lamports) / Decimal(COMPLETION_SOL_LAMPORTS)
    return min(Decimal(1), max(Decimal(0), ratio))


def curve_market_cap_lamports(state: CurveState) -> int:
    """Market cap in lamports: virtual SOL scaled by supply over virtual tokens."""
    return (
        state.virtual_sol_reserves_lamports * state.total_supply_units
    ) // state.virtual_token_reserves_units


class CurveProvenance(Enum):
    """Where a bonding-curve snapshot came from. Only replay provenance may admit entry."""

    VERIFIED_REPLAY = "verified_replay"
    UNVERIFIED_FIXTURE = "unverified_fixture"
    LIVE_RPC = "live_rpc"
    UNKNOWN = "unknown"


#: The curve source label a verified replay read carries (replay/sources.py).
VERIFIED_REPLAY_SOURCE: Final[str] = "fixture"


def rpc_curve_price_allowed(*, curve_source: str, provenance: CurveProvenance) -> bool:
    """Admit an entry price only from verified replay provenance (fail closed).

    Every provenance other than ``VERIFIED_REPLAY`` is refused, including a
    non-replay snapshot whose source label reads ``fixture``. ``LAYOUT_STATUS``
    does not widen admission: no live RPC provenance is admitted yet.
    """
    return provenance is CurveProvenance.VERIFIED_REPLAY and curve_source == VERIFIED_REPLAY_SOURCE
