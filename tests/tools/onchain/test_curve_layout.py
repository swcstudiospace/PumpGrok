"""Offline behavioral checks for the BondingCurve account wire layout."""

from __future__ import annotations

import struct
from decimal import Decimal

import pytest

from pumpgrok.tools.onchain.curve_layout import (
    CurveDecodeError,
    curve_price_sol_per_token,
    decode_curve_account,
    encode_curve_fixture,
)

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
    assert state.extended_data == b""
    assert curve_price_sol_per_token(state) == Decimal("0.002")


def test_extended_token_first_reserves() -> None:
    extension = bytes(range(117))
    state = decode_curve_account(_token_first_account() + extension)

    assert state.virtual_token_reserves_units == 101
    assert state.virtual_sol_reserves_lamports == 202
    assert state.real_token_reserves_units == 303
    assert state.real_sol_reserves_lamports == 404
    assert state.total_supply_units == 505
    assert state.complete is True
    assert state.extended_data == extension


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
