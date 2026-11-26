"""Fee model v2 branches pinned; v1 numbers unchanged (FEE-01)."""

from __future__ import annotations

from pumpgrok.execution.fees import FeeModel, FeeModelV2, fee_model_for

SIZE = 1_000_000_000


def test_v1_numbers_unchanged() -> None:
    v1 = FeeModel()
    assert v1.venue_fee(SIZE) == 10_000_000
    assert v1.network_cost() == 5_000 + 4_000


def test_v2_builder_fee_branches() -> None:
    v2 = FeeModelV2()
    assert v2.builder_fee(SIZE, use_builder=True) == 5_000_000
    assert v2.builder_fee(SIZE, use_builder=False) == 0


def test_v2_first_buy_ata_only() -> None:
    v2 = FeeModelV2()
    assert v2.first_buy_extra(is_first_buy=True) == 2_039_280
    assert v2.first_buy_extra(is_first_buy=False) == 0


def test_v2_priority_cap() -> None:
    v2 = FeeModelV2()
    assert v2.priority_fee() == 4_000  # under cap
    capped = FeeModelV2(micro_lamports_per_cu=1_000_000_000)
    assert capped.priority_fee() == 1_000_000  # capped


def test_v2_integer_flooring() -> None:
    v2 = FeeModelV2()
    assert v2.builder_fee(199, use_builder=True) == 0  # floors


def test_selector() -> None:
    assert isinstance(fee_model_for("v1"), FeeModel)
    assert not isinstance(fee_model_for("v1"), FeeModelV2)
    assert isinstance(fee_model_for("v2"), FeeModelV2)
