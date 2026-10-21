"""Integer curve math, fee, and latency unit tests (PAPER-001, R6, R28).

Golden vectors pin the floor semantics; invariant tests pin the constant
product; determinism tests pin the seeded rng stream.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.execution.curve_math import (
    buy_out,
    impact_buy,
    impact_sell,
    post_buy,
    post_sell,
    sell_out,
    spot,
)
from pumpgrok.execution.fees import COMPUTE_UNITS, FeeModel
from pumpgrok.execution.latency import P_DROP, draw_latency
from pumpgrok.replay.rng import make_rng

S = 42_000_000_000
T = 766_428_571_428_571


def test_spot_is_lamports_per_token_unit() -> None:
    assert spot(2000, 1000) == Decimal("2")
    assert spot(S, T) == Decimal(S) / Decimal(T)


def test_spot_rejects_empty_reserves() -> None:
    with pytest.raises(ValueError):
        spot(100, 0)


def test_buy_out_floors() -> None:
    assert buy_out(1000, 1000, 1000) == 500
    assert buy_out(1000, 1000, 1) == 0
    size = 200_000_000
    venue = size * 100 // 10_000
    x_net = size - venue
    assert buy_out(S, T, x_net) == T * x_net // (S + x_net)


def test_sell_out_floors() -> None:
    assert sell_out(1000, 1000, 500) == 333
    assert sell_out(S, T, 1_000_000) == S * 1_000_000 // (T + 1_000_000)


def test_constant_product_never_leaks() -> None:
    out = buy_out(1000, 1000, 1000)
    s1, t1 = post_buy(1000, 1000, 1000)
    assert (s1, t1) == (2000, 1000 - out)
    assert s1 * t1 >= 1000 * 1000
    s2, t2 = post_sell(s1, t1, out)
    assert t2 == t1 + out
    assert s2 == s1 - sell_out(s1, t1, out)


def test_impacts_are_fractions() -> None:
    assert impact_buy(1000, 100) == Decimal("0.1")
    assert impact_sell(1000, 100) == Decimal(100) / Decimal(1100)
    with pytest.raises(ValueError):
        impact_buy(0, 100)


def test_fee_model_integer_lamports() -> None:
    fees = FeeModel()
    assert fees.venue_fee(200_000_000) == 2_000_000
    assert fees.priority_fee() == 20_000 * COMPUTE_UNITS // 1_000_000
    assert fees.network_cost() == 5_000 + fees.priority_fee()
    assert fees.buy_net(200_000_000) == 198_000_000
    assert fees.buy_debit(200_000_000) == 200_000_000 + fees.network_cost()
    gross = 200_000_000
    assert fees.sell_proceeds(gross) == gross - 2_000_000 - fees.network_cost()


def test_latency_draws_are_seeded_and_clipped() -> None:
    first = draw_latency(make_rng(7))
    second = draw_latency(make_rng(7))
    assert first == second
    latency_s, dropped = first
    assert 0.4 <= latency_s <= 20.0
    assert isinstance(dropped, bool)
    assert P_DROP == 0.02


def test_latency_p_drop_forces_outcomes() -> None:
    _, dropped_none = draw_latency(make_rng(7), p_drop=0.0)
    assert dropped_none is False
    _, dropped_all = draw_latency(make_rng(7), p_drop=1.0)
    assert dropped_all is True
