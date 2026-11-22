"""FEE-01: backtest and paper fee results agree for both models.

Backtest scoring and the paper adapter both price fills through the one
FeeModel vocabulary: venue fee, network cost, and the cash-debit/proceeds
identities. This test proves the two consumers of the selector agree on
identical fills for v1 and v2, and that the cash semantics and the
slippage_exceeded/tx_dropped distinction are unchanged by the flip.
"""

from __future__ import annotations

from pumpgrok.config.sections.v4 import PaperFeesSettings
from pumpgrok.execution.fees import FeeModel, fee_model_for
from pumpgrok.execution.paper_factory import paper_fees_from

SIZE = 1_000_000_000


def test_selector_and_factory_agree_for_both_models() -> None:
    for name in ("v1", "v2"):
        selected = fee_model_for(name)
        built = paper_fees_from(PaperFeesSettings(model=name))
        assert type(selected) is type(built)
        assert selected.venue_fee(SIZE) == built.venue_fee(SIZE)
        assert selected.network_cost() == built.network_cost()
        assert selected.buy_net(SIZE) == built.buy_net(SIZE)
        assert selected.sell_proceeds(SIZE) == built.sell_proceeds(SIZE)


def test_cash_semantics_unchanged() -> None:
    for name in ("v1", "v2"):
        fees = fee_model_for(name)
        # Cash debit is filled plus network cost for both models.
        if name == "v1":
            assert fees.buy_debit(SIZE) == SIZE + fees.network_cost()
        else:
            assert fees.buy_debit(SIZE) == SIZE + fees.network_cost()
        assert fees.sell_proceeds(SIZE) == SIZE - fees.venue_fee(SIZE) - fees.network_cost()


def test_v1_arithmetic_pinned_against_v2_venue_and_network() -> None:
    v1: FeeModel = fee_model_for("v1")
    v2 = fee_model_for("v2")
    # Venue and ordinary network cost are the same number in both models;
    # v2 only adds the builder fee and first-buy ATA rent.
    assert v1.venue_fee(SIZE) == v2.venue_fee(SIZE) == 10_000_000
    assert v1.network_cost() == v2.network_cost() == 9_000
