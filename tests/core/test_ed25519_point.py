"""Ed25519 point decoder: RFC 8032 section 7.1 vectors and malformed-point refusals."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.ed25519_point import decode_public_point

P = 2**255 - 19
D = 37095705934669439343138083508754565189542113879843219016388785533085940283555

# Public keys from RFC 8032 section 7.1 (TEST 1, TEST 2, TEST 3, TEST 1024, TEST SHA(abc)).
RFC8032_PUBLIC_KEYS = {
    "TEST 1": "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
    "TEST 2": "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
    "TEST 3": "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
    "TEST 1024": "278117fc144c72340f67d0f2316e8386ceffbf2b2428c9c51fef7c597f1d426e",
    "TEST SHA(abc)": "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
}

IDENTITY = bytes.fromhex("01" + "00" * 31)  # (0, 1), x = 0, sign bit 0
IDENTITY_SIGNED = bytes.fromhex("01" + "00" * 30 + "80")  # x = 0, sign bit 1
MINUS_ONE = bytes.fromhex("ec" + "ff" * 30 + "7f")  # (0, -1), x = 0, sign bit 0
MINUS_ONE_SIGNED = bytes.fromhex("ec" + "ff" * 30 + "ff")  # (0, -1), x = 0, sign bit 1
ZERO_Y = bytes(32)  # y = 0, x = sqrt(-1): exercises RFC 5.1.3 step 3.2
ZERO_Y_SIGNED = bytes.fromhex("00" * 31 + "80")

P_ENCODED = bytes.fromhex("ed" + "ff" * 30 + "7f")  # y = p, non-canonical
P_ENCODED_SIGNED = bytes.fromhex("ed" + "ff" * 30 + "ff")  # y = p, sign bit set
P_PLUS_ONE = bytes.fromhex("ee" + "ff" * 30 + "7f")  # y = p + 1, non-canonical
ALL_ONES_Y = bytes.fromhex("ff" * 31 + "7f")  # y = 2^255 - 1, non-canonical

OFF_CURVE_Y2 = bytes.fromhex("02" + "00" * 31)  # y = 2: u/v is a non-square
OFF_CURVE_Y2_SIGNED = bytes.fromhex("02" + "00" * 30 + "80")
OFF_CURVE_Y7 = bytes.fromhex("07" + "00" * 31)  # y = 7: u/v is a non-square


def _euler_on_curve(y: int) -> bool:
    """Independent curve-membership test: u/v is a square (or zero) mod p."""
    y_sq = y * y % P
    u = (y_sq - 1) % P
    v = (D * y_sq + 1) % P
    if u == 0:
        return True
    return pow(u * pow(v, P - 2, P) % P, (P - 1) // 2, P) == 1


def test_rfc_constant_d_matches_curve_definition() -> None:
    assert (-121665 * pow(121666, P - 2, P)) % P == D


@pytest.mark.parametrize("name", sorted(RFC8032_PUBLIC_KEYS))
def test_rfc8032_public_keys_are_accepted_unchanged(name: str) -> None:
    raw = bytes.fromhex(RFC8032_PUBLIC_KEYS[name])
    assert decode_public_point(raw) == raw


def test_sign_flip_of_valid_point_is_accepted() -> None:
    raw = bytes.fromhex(RFC8032_PUBLIC_KEYS["TEST 1"])
    flipped = raw[:31] + bytes([raw[31] ^ 0x80])
    assert decode_public_point(flipped) == flipped


def test_small_order_points_are_accepted_because_only_curve_membership_is_checked() -> None:
    assert decode_public_point(IDENTITY) == IDENTITY
    assert decode_public_point(MINUS_ONE) == MINUS_ONE


def test_y_zero_uses_sqrt_minus_one_branch_for_both_signs() -> None:
    assert decode_public_point(ZERO_Y) == ZERO_Y
    assert decode_public_point(ZERO_Y_SIGNED) == ZERO_Y_SIGNED


@pytest.mark.parametrize("raw", [IDENTITY_SIGNED, MINUS_ONE_SIGNED])
def test_x_zero_with_sign_bit_set_is_refused(raw: bytes) -> None:
    with pytest.raises(ValueError):
        decode_public_point(raw)


@pytest.mark.parametrize("raw", [P_ENCODED, P_ENCODED_SIGNED, P_PLUS_ONE, ALL_ONES_Y])
def test_non_canonical_y_at_or_above_p_is_refused(raw: bytes) -> None:
    with pytest.raises(ValueError):
        decode_public_point(raw)


@pytest.mark.parametrize("raw", [OFF_CURVE_Y2, OFF_CURVE_Y2_SIGNED, OFF_CURVE_Y7])
def test_off_curve_point_is_refused(raw: bytes) -> None:
    with pytest.raises(ValueError):
        decode_public_point(raw)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        bytes.fromhex(RFC8032_PUBLIC_KEYS["TEST 1"])[:31],
        bytes.fromhex(RFC8032_PUBLIC_KEYS["TEST 1"]) + b"\x00",
        bytes(33),
    ],
)
def test_wrong_length_is_refused(raw: bytes) -> None:
    with pytest.raises(ValueError):
        decode_public_point(raw)


def test_non_bytes_input_is_refused() -> None:
    with pytest.raises(ValueError):
        decode_public_point(RFC8032_PUBLIC_KEYS["TEST 1"])  # type: ignore[arg-type]


def test_refusal_messages_never_echo_input() -> None:
    wrong_length = bytes.fromhex("5ec7e7" + "ab" * 30)
    with pytest.raises(ValueError) as length_error:
        decode_public_point(wrong_length)
    assert "5ec7e7" not in str(length_error.value)
    assert wrong_length.hex() not in str(length_error.value)

    above_p = bytes.fromhex("ff" * 32)
    with pytest.raises(ValueError) as range_error:
        decode_public_point(above_p)
    assert "ffffffff" not in str(range_error.value)


def test_small_y_grid_matches_independent_curve_test() -> None:
    accepted = 0
    refused = 0
    for y in range(256):
        for sign in (0, 1):
            raw = (y | (sign << 255)).to_bytes(32, "little")
            expect_ok = _euler_on_curve(y) and not (y == 1 and sign == 1)
            if expect_ok:
                assert decode_public_point(raw) == raw, raw.hex()
                accepted += 1
            else:
                with pytest.raises(ValueError):
                    decode_public_point(raw)
                refused += 1
    assert accepted > 0
    assert refused > 0
