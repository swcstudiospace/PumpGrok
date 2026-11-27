"""HOST-10: tokens shorter than 32 bytes or duplicated are refused."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "desk-gateway" / "src"))

from desk_gateway.config import validate_tokens

GOOD = "x" * 32
OTHER = "y" * 32


def test_good_tokens_pass() -> None:
    validate_tokens({"a": GOOD, "b": OTHER})


def test_short_token_refused() -> None:
    try:
        validate_tokens({"a": "short"})
    except ValueError:
        return
    raise AssertionError("short token must raise")


def test_equal_tokens_refused() -> None:
    try:
        validate_tokens({"a": GOOD, "b": GOOD})
    except ValueError:
        return
    raise AssertionError("equal tokens must raise")
