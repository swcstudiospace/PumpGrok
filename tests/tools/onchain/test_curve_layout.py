"""Token-first curve decode: 49 and 166 byte accounts (MKT-01)."""

from __future__ import annotations

import pytest

from pumpgrok.tools.onchain.curve_layout import (
    CURVE_ACCOUNT_SIZE,
    CURVE_ACCOUNT_SIZE_166,
    CurveDecodeError,
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
    assert state.token_mint == ""
    pass


def test_166_byte_round_trip_with_mint() -> None:
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
    state = decode_curve_account(raw)
    pass
    assert state.token_mint == mint.hex()
    assert state.complete is True


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
