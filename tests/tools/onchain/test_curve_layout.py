"""Offline behavioral checks for the BondingCurve account wire layout."""

from __future__ import annotations

import struct

import pytest

from pumpgrok.tools.onchain.curve_layout import CurveDecodeError, decode_curve_account

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


def test_extended_token_first_reserves() -> None:
    state = decode_curve_account(_token_first_account() + bytes(117))

    assert state.virtual_token_reserves_units == 101
    assert state.virtual_sol_reserves_lamports == 202
    assert state.real_token_reserves_units == 303
    assert state.real_sol_reserves_lamports == 404
    assert state.total_supply_units == 505
    assert state.complete is True


@pytest.mark.parametrize("extra", [b"", bytes(117)], ids=["49-byte", "166-byte"])
def test_wrong_discriminator_is_rejected(extra: bytes) -> None:
    account = bytes(8) + _token_first_account()[8:] + extra

    with pytest.raises(CurveDecodeError):
        decode_curve_account(account)
