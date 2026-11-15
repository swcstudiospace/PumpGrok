"""FEE-01 parity: backtest and paper price fills from one default fee model."""

from __future__ import annotations

import os

import pytest

from pumpgrok.cli import backtest
from pumpgrok.config.settings import Settings
from pumpgrok.execution import paper_factory
from pumpgrok.execution.fees import PAPER_DEFAULT_FEE_MODEL

SIZE = 200_000_000


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_backtest_selects_fees_with_the_paper_selection_function(clean_env: None) -> None:
    assert backtest.paper_fee_model is paper_factory.paper_fee_model


def test_backtest_and_paper_agree_on_every_fee_term(clean_env: None) -> None:
    settings = Settings()
    backtest_fees = backtest.paper_fee_model(settings)
    paper_fees = paper_factory.paper_fee_model(settings)
    assert backtest_fees == paper_fees == PAPER_DEFAULT_FEE_MODEL
    for first_buy in (True, False):
        assert backtest_fees.buy_network_cost(first_buy=first_buy) == (
            paper_fees.buy_network_cost(first_buy=first_buy)
        )
    assert backtest_fees.venue_fee(SIZE) == paper_fees.venue_fee(SIZE)
    assert backtest_fees.sell_proceeds(SIZE) == paper_fees.sell_proceeds(SIZE)
