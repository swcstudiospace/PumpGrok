"""Token-first curve decode: 49 and 166 byte accounts (MKT-01).

Offline behavioral checks for the BondingCurve account wire layout.
"""

from __future__ import annotations

import struct
from decimal import Decimal

import pytest

from pumpgrok.tools.onchain import curve_layout
from pumpgrok.tools.onchain.curve_layout import (
    CURVE_ACCOUNT_SIZE,
    CURVE_ACCOUNT_SIZE_166,
    CurveDecodeError,
    curve_price_sol_per_token,
    decode_curve_account,
    encode_curve_fixture,
)

VSOL = 42_000_000_000
VTOK = 766_428_571_428_571
RSOL = 12_000_000_000
RTOK = 500_000_000_000_000
SUPPLY = 1_000_000_000_000_000


def test_sizes_pinned() -> None:
    assert CURVE_ACCOUNT_SIZE == 49
    assert CURVE_ACCOUNT_SIZE_166 == 166


def test_49_byte_round_trip_token_first() -> None:
    raw = encode_curve_fixture(
        virtual_sol_reserves_lamports=VSOL,
        virtual_token_reserves_units=VTOK,
        real_sol_reserves_lamports=RSOL,
        real_token_reserves_units=RTOK,
        total_supply_units=SUPPLY,
        complete=False,
    )
    assert len(raw) == 49
    # Token fields precede SOL fields in the wire order.
    state = decode_curve_account(raw)
    assert state.virtual_token_reserves_units == VTOK
    assert state.virtual_sol_reserves_lamports == VSOL
    assert state.real_token_reserves_units == RTOK
    assert state.real_sol_reserves_lamports == RSOL
    assert state.total_supply_units == SUPPLY


def test_166_byte_fixture_stays_assumed_fail_closed() -> None:
    # Even a structurally well-formed 166-byte account is refused: the
    # extended layout is ASSUMED (unreviewed) and decode fails closed.
    mint = bytes(range(32))
    raw = encode_curve_fixture(
        virtual_sol_reserves_lamports=VSOL,
        virtual_token_reserves_units=VTOK,
        real_sol_reserves_lamports=RSOL,
        real_token_reserves_units=RTOK,
        total_supply_units=SUPPLY,
        complete=True,
        size=CURVE_ACCOUNT_SIZE_166,
        token_mint=mint,
    )
    assert len(raw) == 166
    with pytest.raises(CurveDecodeError, match="166-byte extended curve layout is ASSUMED"):
        decode_curve_account(raw)


def test_bad_discriminator_rejected() -> None:
    raw = bytearray(
        encode_curve_fixture(
            virtual_sol_reserves_lamports=VSOL,
            virtual_token_reserves_units=VTOK,
            real_sol_reserves_lamports=RSOL,
            real_token_reserves_units=RTOK,
            total_supply_units=SUPPLY,
            complete=False,
        )
    )
    raw[0:8] = b"BADDISC\x00"
    with pytest.raises(CurveDecodeError):
        decode_curve_account(bytes(raw))


def test_wrong_length_rejected() -> None:
    with pytest.raises(CurveDecodeError):
        decode_curve_account(b"\x00" * 50)


# BondingCurve discriminator from the Pump IDL cited in 13-RESEARCH.md.
BONDING_CURVE_DISCRIMINATOR = bytes([23, 183, 248, 55, 96, 216, 172, 96])


def _token_first_account() -> bytes:
    # Pack independently of the production fixture encoder, in IDL field order.
    return struct.pack(
        "<8sQQQQQB",
        BONDING_CURVE_DISCRIMINATOR,
        101,  # virtual token reserves
        202,  # virtual SOL reserves
        303,  # real token reserves
        404,  # real SOL reserves
        505,  # total token supply
        1,  # complete
    )


def test_token_first_reserves() -> None:
    state = decode_curve_account(_token_first_account())

    assert state.virtual_token_reserves_units == 101
    assert state.virtual_sol_reserves_lamports == 202
    assert state.real_token_reserves_units == 303
    assert state.real_sol_reserves_lamports == 404
    assert state.total_supply_units == 505
    assert state.complete is True
    assert curve_price_sol_per_token(state) == Decimal("0.002")


def test_extended_166_layout_is_refused_fail_closed() -> None:
    account = _token_first_account() + bytes(range(116)) + b"\xff"
    assert len(account) == 166

    with pytest.raises(CurveDecodeError, match="166-byte extended curve layout is ASSUMED"):
        decode_curve_account(account)


@pytest.mark.parametrize("extra", [b"", bytes(117)], ids=["49-byte", "166-byte"])
def test_wrong_discriminator_is_rejected(extra: bytes) -> None:
    account = bytes(8) + _token_first_account()[8:] + extra

    with pytest.raises(CurveDecodeError):
        decode_curve_account(account)


@pytest.mark.parametrize("length", [0, 8, 48, 50, 165, 167])
def test_unsupported_lengths_are_rejected(length: int) -> None:
    account = (_token_first_account() + bytes(118))[:length]

    with pytest.raises(CurveDecodeError):
        decode_curve_account(account)


@pytest.mark.parametrize("extra", [b"", bytes(117)], ids=["49-byte", "166-byte"])
def test_invalid_completion_flag_is_rejected(extra: bytes) -> None:
    account = _token_first_account()[:-1] + b"\x02" + extra

    with pytest.raises(CurveDecodeError):
        decode_curve_account(account)


def test_fixture_encoder_preserves_legacy_economic_values() -> None:
    account = encode_curve_fixture(
        virtual_sol_reserves_lamports=202,
        virtual_token_reserves_units=101,
        real_sol_reserves_lamports=404,
        real_token_reserves_units=303,
        total_supply_units=505,
        complete=True,
    )

    assert account == _token_first_account()
    state = decode_curve_account(account)
    assert state.virtual_sol_reserves_lamports == 202
    assert state.virtual_token_reserves_units == 101
    assert state.real_sol_reserves_lamports == 404
    assert state.real_token_reserves_units == 303


def test_token_first_49_layout_status_is_verified_by_human_review() -> None:
    assert curve_layout.LAYOUT_STATUS == "VERIFIED"
    assert curve_layout.LAYOUT_REVIEWED_BY == "human:Ove"
