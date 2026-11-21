"""Bonding-curve account decode over Solana RPC (STRUCT-002, B9, T-03-02-01).

Token-first layout: an 8-byte discriminator, token reserves before SOL
reserves, five little-endian u64 counters, then a one-byte completion flag
(0/1). Both the 49-byte account (counters only) and the 166-byte account
(same counters plus token-mint and related pubkeys) decode. The layout is
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
from typing import Final

from pydantic import BaseModel, ConfigDict

from pumpgrok.core.units import lamports_to_sol, sol_to_lamports
from pumpgrok.tools._common import UNITS_PER_TOKEN
from pumpgrok.tools.onchain.pump_events import EVENT_DECODE_STATUS

#: Token-first 49-byte layout: disc, virt_token, virt_sol, real_token,
#: real_sol, total_supply, completion flag. Token fields precede SOL fields.
_CURVE_STRUCT = struct.Struct("<8sQQQQQB")
CURVE_ACCOUNT_SIZE = _CURVE_STRUCT.size
#: Token-first 166-byte layout: disc, token_mint, counters (token-first),
#: completion flag, creator, amm_pool, reserved trailer.
_CURVE_STRUCT_166 = struct.Struct("<8s32sQQQQQB32s32s21s")
CURVE_ACCOUNT_SIZE_166 = _CURVE_STRUCT_166.size
#: Accepted discriminator bytes: the ASSUMED fixture marker and the real
#: bonding-curve discriminator the probe checks (the curve layout probe record).
_DISCRIMINATOR = b"ASSUMED\x00"
_REAL_DISCRIMINATOR = bytes.fromhex("17b7f83760d8ac60")
_ACCEPTED_DISCRIMINATORS = frozenset({_DISCRIMINATOR, _REAL_DISCRIMINATOR})

#: Bonding-curve layout verification state (R65). ASSUMED until a live probe
#: against mainnet bonding-curve accounts decodes under this layout and a
#: human reviews the probe record in tests/fixtures/rpc/bonding_curve/.
#: While ASSUMED, no paper entry may consume an RPC-derived price: the
#: PaperAdapter refuses with data_unavailable (fail closed).
LAYOUT_STATUS: Final[str] = "ASSUMED"

#: Lamports of real SOL at which the curve is considered complete (catalog:
#: 85 SOL, the retired oracle ``src/monitor.py:30``). [ASSUMED] threshold.
COMPLETION_SOL_LAMPORTS = sol_to_lamports(Decimal(85))


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
    #: 32-byte token mint (hex) from the 166-byte account; empty for 49-byte.
    token_mint: str = ""


def decode_curve_account(data: bytes) -> CurveState:
    """Decode raw account bytes with the token-first ASSUMED layout.

    Both the 49-byte and 166-byte accounts decode; the 166-byte variant
    additionally yields its token mint. Raises :class:`CurveDecodeError`
    on wrong length, a bad discriminator, or a non-boolean completion flag.
    """
    if len(data) == CURVE_ACCOUNT_SIZE:
        try:
            (disc, vtok, vsol, rtok, rsol, supply, complete) = _CURVE_STRUCT.unpack(data)
        except struct.error as exc:
            raise CurveDecodeError(f"curve account unpack failed: {type(exc).__name__}") from exc
        mint = b""
    elif len(data) == CURVE_ACCOUNT_SIZE_166:
        try:
            vals = _CURVE_STRUCT_166.unpack(data)
            disc, mint, vtok, vsol, rtok, rsol, supply, complete = vals[:8]
        except struct.error as exc:
            raise CurveDecodeError(f"curve account unpack failed: {type(exc).__name__}") from exc
    else:
        raise CurveDecodeError(f"curve account size {len(data)} not in token-first sizes")
    if disc not in _ACCEPTED_DISCRIMINATORS:
        raise CurveDecodeError("curve discriminator mismatch")
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
        token_mint=mint.hex() if mint else "",
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
    size: int = CURVE_ACCOUNT_SIZE,
    token_mint: bytes = b"",
) -> bytes:
    """Build token-first [ASSUMED]-layout bytes for tests. Never in production."""
    flag = 1 if complete else 0
    if size == CURVE_ACCOUNT_SIZE_166:
        return _CURVE_STRUCT_166.pack(
            _DISCRIMINATOR,
            bytes(token_mint).ljust(32, b"\x00")[:32],
            virtual_token_reserves_units,
            virtual_sol_reserves_lamports,
            real_token_reserves_units,
            real_sol_reserves_lamports,
            total_supply_units,
            flag,
            b"\x00" * 32,
            b"\x00" * 32,
            b"\x00" * 21,
        )
    return _CURVE_STRUCT.pack(
        _DISCRIMINATOR,
        virtual_token_reserves_units,
        virtual_sol_reserves_lamports,
        real_token_reserves_units,
        real_sol_reserves_lamports,
        total_supply_units,
        flag,
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


def rpc_curve_price_allowed(*, curve_source: str) -> bool:
    """True when a price from ``curve_source`` may price a paper entry.

    RPC-derived reserves are untrusted bytes until the layout is VERIFIED
    (T-04-08): while either status is ASSUMED they fail closed with
    ``data_unavailable`` at the entry gate. Fixture, rest and pumpportal
    integer ticks never pass through this layout, so replay is unaffected.
    Replay and fixture sources are allowed; unknown sources are refused.
    """
    if curve_source in ("replay", "fixture", "rest", "pumpportal"):
        return True
    if curve_source != "rpc":
        return False
    if LAYOUT_STATUS != "VERIFIED":
        return False
    return EVENT_DECODE_STATUS == "VERIFIED"
