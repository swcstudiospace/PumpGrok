"""Ed25519 public-point decoder, stdlib only (RFC 8032 section 5.1.3).

Decode-only. It checks that a 32-octet compressed point is well formed and on
the curve: exact length, canonical y (y < p), curve membership (x recovered or
rejected), and the sign-bit rule (x = 0 with the sign bit set is rejected).
It does not sign, does not multiply scalars, does not generate keys and does
not check small order or subgroup membership; those are outside ONB-06.

INV-S-01 allows this module, and only this module, to refer to ``ed25519``.
"""

from __future__ import annotations

_P = 2**255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)
_POINT_BYTES = 32
_Y_MASK = (1 << 255) - 1


def _encode(x: int, y: int) -> bytes:
    """Canonical RFC 8032 section 5.1.2 encoding of an affine point."""
    return ((y & _Y_MASK) | ((x & 1) << 255)).to_bytes(_POINT_BYTES, "little")


def decode_public_point(raw: bytes) -> bytes:
    """Validate a 32-octet Ed25519 point and return its canonical encoding.

    Raises ValueError on any failure. The message never contains the input.
    For every accepted input the returned bytes equal ``raw``.
    """
    if not isinstance(raw, bytes) or len(raw) != _POINT_BYTES:
        raise ValueError("Ed25519 point must be exactly 32 bytes")
    value = int.from_bytes(raw, "little")
    x_sign = value >> 255
    y = value & _Y_MASK
    if y >= _P:
        raise ValueError("Ed25519 point y-coordinate is not canonical")

    y_sq = y * y % _P
    u = (y_sq - 1) % _P
    v = (_D * y_sq + 1) % _P
    # Candidate root x = (u/v)^((p+3)/8), computed as u v^3 (u v^7)^((p-5)/8).
    x = u * pow(v, 3, _P) % _P * pow(u * pow(v, 7, _P) % _P, (_P - 5) // 8, _P) % _P
    v_x_sq = v * x * x % _P
    if v_x_sq == u:
        pass
    elif v_x_sq == (-u) % _P:
        x = x * _SQRT_M1 % _P
    else:
        raise ValueError("Ed25519 point is not on the curve")

    if x == 0 and x_sign == 1:
        raise ValueError("Ed25519 point has sign bit set with x = 0")
    if (x & 1) != x_sign:
        x = (_P - x) % _P
    return _encode(x, y)
