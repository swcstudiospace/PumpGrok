"""Input validators and choice records (ONB-05..ONB-10, T-14-08-02).

Wallet addresses must base58-decode to exactly 32 bytes and pass a
best-effort Ed25519 curve-point check. Refusals name the field and never
echo the value. Paper never reads the wallet field. RPC choices record the
host only.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from pumpgrok.core.idempotency import canonical_json

_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_INDEX = {char: idx for idx, char in enumerate(_BASE58)}
_FIELD = 2**255 - 19
_D = (-121665 * pow(121666, _FIELD - 2, _FIELD)) % _FIELD


def _base58_decode(text: str) -> bytes:
    number = 0
    for char in text:
        digit = _INDEX.get(char)
        if digit is None:
            raise ValueError("character outside the base58 alphabet")
        number = number * 58 + digit
    leading = len(text) - len(text.lstrip("1"))
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * leading + body


def _is_curve_point(raw: bytes) -> bool:
    """Ed25519 curve-point check: y coordinate is a quadratic residue."""
    if len(raw) != 32:
        return False
    y = int.from_bytes(raw, "little") & ((1 << 255) - 1)
    if y >= _FIELD:
        return False
    y2 = (y * y - 1) * pow((_D * y * y + 1) % _FIELD, _FIELD - 2, _FIELD) % _FIELD
    return y2 == 0 or pow(y2, (_FIELD - 1) // 2, _FIELD) == 1


def is_valid_wallet_address(text: str) -> bool:
    if not text or len(text) > 44:
        return False
    try:
        raw = _base58_decode(text)
    except ValueError:
        return False
    return len(raw) == 32 and _is_curve_point(raw)


def refuse_wallet(text: str) -> str:
    """Refusal line naming the field. The value never appears in the message."""
    if is_valid_wallet_address(text):
        return ""
    return "wallet_public_address refused: not a valid 32-byte curve point"


def host_only(endpoint: str) -> str:
    """Record scheme://host:port only. Never path, query, userinfo, or key."""
    parts = urlsplit(endpoint)
    port = f":{parts.port}" if parts.port is not None else ""
    return f"{parts.scheme}://{parts.hostname}{port}"


def record_choice_via_text(path_text: str, name: str, value: str) -> dict[str, str]:
    """One recorded operator choice (RPC host only)."""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"name": name, "value": host_only(value), "source": "operator-choice"}
    line = canonical_json(row)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return row
