"""Analyzer SOL conversion goes through the shared ``core.units`` helper.

Provider SOL amounts must convert to lamports exactly as approvals and
budgets do, including the ROUND_HALF_UP half-lamport edges. Deterministic,
no network.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from pumpgrok.core import units
from pumpgrok.engine import analyzer
from pumpgrok.engine.analyzer import _to_lamports

# (provider value, expected lamports). Covers the half-lamport boundary,
# negatives, whole and fractional SOL, and float/int provider inputs.
CASES: list[tuple[Any, int]] = [
    ("0", 0),
    ("0.0000000004", 0),
    ("0.0000000005", 1),
    ("0.0000000014", 1),
    ("0.0000000015", 2),
    ("0.0000000016", 2),
    ("-0.0000000015", -2),
    ("1", 1_000_000_000),
    ("0.5", 500_000_000),
    ("85.0000000005", 85_000_000_001),
    ("123.456789012", 123_456_789_012),
    (0.1, 100_000_000),
    (1e-9, 1),
    (2, 2_000_000_000),
]


@pytest.mark.parametrize(("value", "expected"), CASES)
def test_analyzer_conversion_equals_shared_helper(value: Any, expected: int) -> None:
    shared = units.sol_to_lamports(Decimal(str(value)))
    assert _to_lamports(value) == shared == expected


def test_analyzer_conversion_calls_shared_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    """The analyzer must delegate to the shared helper, not re-implement it."""
    seen: list[Decimal] = []
    real = units.sol_to_lamports

    def spy(value: Decimal) -> int:
        seen.append(value)
        return real(value)

    monkeypatch.setattr(analyzer, "sol_to_lamports", spy)
    assert _to_lamports("0.0000000015") == 2
    assert seen == [Decimal("0.0000000015")]


@pytest.mark.parametrize("value", ["abc", "NaN", "sNaN", "Infinity", None])
def test_unparseable_amount_raises_value_error(value: Any) -> None:
    """ValueError is what ``_safe_parse`` catches to skip a poisoned row."""
    with pytest.raises(ValueError, match="bad amount"):
        _to_lamports(value)
