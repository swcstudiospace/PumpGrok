"""Bonding-curve account decode over Solana RPC (STRUCT-002, B9, T-03-02-01).

[ASSUMED] Anchor-style layout: an 8-byte discriminator, five little-endian
u64 reserve counters, then a one-byte completion flag (0/1). The layout is
NOT verified against a mainnet account: every test fixture built with
:func:`encode_curve_fixture` is marked ASSUMED, and user confirmation of
the layout is pending. Shared by ``market.price`` and ``onchain.lp_status``.

RPC only: this module performs no HTTP reads outside the injected RPC
client and references no quote endpoint (R44, R46, R47).
"""
from __future__ import annotations

import base64
import struct
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from pumpgrok.tools._common import (
    LAMPORTS_PER_SOL,
    UNITS_PER_TOKEN,
)

_CURVE_STRUCT = struct.Struct("<8sQQQQQB")
CURVE_ACCOUNT_SIZE = _CURVE_STRUCT.size

#: Lamports of real SOL at which the curve is considered complete (catalog:
#: 85 SOL, ``vendor/grokbot-pumpfun/src/monitor.py:30``). [ASSUMED] threshold.
COMPLETION_SOL_LAMPORTS = 85 * LAMPORTS_PER_SOL


class CurveDecodeError(ValueError):
    """The account bytes do not match the ASSUMED curve layout."""


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
    """Decode raw account bytes with the ASSUMED layout.

    Raises :class:`CurveDecodeError` on any shape mismatch (wrong length,
    completion flag outside ``{0, 1}``); callers map it to ``DataStale``.
    """
    if len(data) != CURVE_ACCOUNT_SIZE:
        raise CurveDecodeError(
            f"curve account size {len(data)} != ASSUMED {CURVE_ACCOUNT_SIZE}"
        )
    try:
        (_, vsol, vtok, rsol, rtok, supply, complete) = _CURVE_STRUCT.unpack(data)
    except struct.error as exc:
        raise CurveDecodeError(f"curve account unpack failed: {type(exc).__name__}") from exc
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
        b"ASSUMED\x00",
        virtual_sol_reserves_lamports,
        virtual_token_reserves_units,
        real_sol_reserves_lamports,
        real_token_reserves_units,
        total_supply_units,
        1 if complete else 0,
    )


def curve_price_sol_per_token(state: CurveState) -> Decimal:
    """SOL per token from virtual reserves (vendor ``price_from_reserves`` math).

    The ported float expression ``(vsol / 1e9) / (vtok / 1e6)`` is evaluated
    here in :class:`Decimal` at the wrapper boundary; the vendor module keeps
    its float form untouched (characterization pins).
    """
    return (
        Decimal(state.virtual_sol_reserves_lamports)
        / Decimal(state.virtual_token_reserves_units)
        * Decimal(UNITS_PER_TOKEN)
        / Decimal(LAMPORTS_PER_SOL)
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
