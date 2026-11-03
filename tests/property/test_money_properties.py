"""QLT-07: integer lamport money math with Decimal ratios only (CONTEXT D-01).

Money is an int count of lamports. Decimal appears only where a value is a SOL amount or a ratio,
and the conversion is exact or rounds with the one ROUND_HALF_UP rule in core/units.py.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from pumpgrok.core.units import (
    LAMPORTS_PER_SOL,
    lamports_to_sol,
    sol_to_lamports,
    split_lamports,
)
from pumpgrok.ledger.reducer import PositionView, position_value_lamports

LAMPORT_RANGE = st.integers(min_value=-(10**18), max_value=10**18)
SOL_AMOUNT = st.decimals(
    min_value=Decimal("-1000000000"),
    max_value=Decimal("1000000000"),
    allow_nan=False,
    allow_infinity=False,
    places=12,
)


@settings(max_examples=300, deadline=None)
@given(LAMPORT_RANGE)
def test_lamports_survive_a_round_trip_through_sol_exactly(lamports: int) -> None:
    sol = lamports_to_sol(Decimal(lamports))
    assert isinstance(sol, Decimal)
    assert sol_to_lamports(sol) == lamports


@settings(max_examples=300, deadline=None)
@given(SOL_AMOUNT)
def test_sol_to_lamports_is_round_half_up_integer_math(sol: Decimal) -> None:
    result = sol_to_lamports(sol)
    expected = int((sol * LAMPORTS_PER_SOL).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    assert type(result) is int
    assert result == expected


@settings(max_examples=300, deadline=None)
@given(LAMPORT_RANGE)
def test_split_lamports_partitions_the_absolute_amount(lamports: int) -> None:
    whole, remainder = split_lamports(lamports)
    assert type(whole) is int and type(remainder) is int
    assert 0 <= remainder < LAMPORTS_PER_SOL
    assert whole * LAMPORTS_PER_SOL + remainder == abs(lamports)


@settings(max_examples=300, deadline=None)
@given(
    cost=LAMPORT_RANGE,
    mark=LAMPORT_RANGE,
    priced=st.booleans(),
)
def test_position_value_is_the_last_mark_once_priced_else_cost_basis(
    cost: int, mark: int, priced: bool
) -> None:
    position = PositionView(
        mint="mint-under-test",
        cost_basis_lamports=cost,
        last_mtm_lamports=mark,
        last_mtm_ts_utc="2026-01-01T00:00:00.000000Z" if priced else "",
    )
    value = position_value_lamports(position)
    assert type(value) is int
    assert value == (mark if priced else cost)


@pytest.mark.parametrize("bad", [1.0, 1.5, "1"])
def test_money_fields_reject_float_and_string_amounts(bad: object) -> None:
    with pytest.raises(ValidationError):
        PositionView(mint="mint-under-test", cost_basis_lamports=bad)  # type: ignore[arg-type]
