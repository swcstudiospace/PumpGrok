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

# Small-order (torsion) encodings: the 8 points whose order divides 8. Their orders are asserted
# in test_torsion_vectors_have_the_stated_order from the curve equation and the group law.
# ZERO_Y and ZERO_Y_SIGNED have order 4 (they double to MINUS_ONE); MINUS_ONE has order 2.
ORDER_8_A = bytes.fromhex("c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a")
ORDER_8_A_SIGNED = bytes.fromhex("c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac03fa")
ORDER_8_B = bytes.fromhex("26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05")
ORDER_8_B_SIGNED = bytes.fromhex("26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc85")
TORSION_ENCODINGS = [
    (IDENTITY, 1),
    (MINUS_ONE, 2),
    (ZERO_Y, 4),
    (ZERO_Y_SIGNED, 4),
    (ORDER_8_A, 8),
    (ORDER_8_A_SIGNED, 8),
    (ORDER_8_B, 8),
    (ORDER_8_B_SIGNED, 8),
]
SQRT_M1 = pow(2, (P - 1) // 4, P)


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
            expect_ok = _euler_on_curve(y) and y not in (0, 1)
            if expect_ok:
                assert decode_public_point(raw) == raw, raw.hex()
                accepted += 1
            else:
                with pytest.raises(ValueError):
                    decode_public_point(raw)
                refused += 1
    assert accepted > 0
    assert refused > 0


def _affine_add(p: tuple[int, int], q: tuple[int, int]) -> tuple[int, int]:
    """Edwards addition for a = -1 (RFC 8032 section 5.1.4), test-side group law."""
    x1, y1 = p
    x2, y2 = q
    t = D * x1 * x2 * y1 * y2 % P
    x3 = (x1 * y2 + y1 * x2) * pow(1 + t, P - 2, P) % P
    y3 = (y1 * y2 + x1 * x2) * pow(1 - t, P - 2, P) % P
    return x3, y3


def _multiply(n: int, p: tuple[int, int]) -> tuple[int, int]:
    result = (0, 1)
    addend = p
    while n:
        if n & 1:
            result = _affine_add(result, addend)
        addend = _affine_add(addend, addend)
        n >>= 1
    return result


def _point_from_encoding(raw: bytes) -> tuple[int, int]:
    """Affine (x, y) of a canonical encoding, with the curve equation asserted."""
    value = int.from_bytes(raw, "little")
    y = value & ((1 << 255) - 1)
    x_sign = value >> 255
    x_squared = (y * y - 1) * pow(D * y * y + 1, P - 2, P) % P
    x = pow(x_squared, (P + 3) // 8, P)
    if x * x % P != x_squared:
        x = x * SQRT_M1 % P
    assert x * x % P == x_squared, "encoding is not on the curve"
    if (x & 1) != x_sign:
        x = (P - x) % P
    assert (y * y - x * x - 1 - D * x * x * y * y) % P == 0
    return x, y


@pytest.mark.parametrize(("raw", "order"), TORSION_ENCODINGS)
def test_torsion_vectors_have_the_stated_order(raw: bytes, order: int) -> None:
    point = _point_from_encoding(raw)
    assert _multiply(order, point) == (0, 1)
    if order > 1:
        assert _multiply(order // 2, point) != (0, 1)


def test_rfc8032_public_keys_are_not_small_order() -> None:
    for hex_key in RFC8032_PUBLIC_KEYS.values():
        assert _multiply(8, _point_from_encoding(bytes.fromhex(hex_key))) != (0, 1)


@pytest.mark.parametrize("raw", [raw for raw, _order in TORSION_ENCODINGS])
def test_small_order_points_are_refused(raw: bytes) -> None:
    with pytest.raises(ValueError) as excinfo:
        decode_public_point(raw)
    assert raw.hex() not in str(excinfo.value)
