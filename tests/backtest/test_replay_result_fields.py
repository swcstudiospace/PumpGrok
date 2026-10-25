"""BT-02: replay results expose per-fill fields, not only the outcome.

Each trade in the replay result carries price, venue fee, network cost,
latency, filled fraction and outcome. Money fields are integer base units;
price, latency and filled fraction are Decimals. Deterministic fixtures only;
no network, no wall clock.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pumpgrok.backtest.results import FillDetail
from pumpgrok.config.settings import FilterSettings
from pumpgrok.replay.runner import ReplayTrade
from pumpgrok.supervisor.scheduler import run_once_replay

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101

OUTCOMES = ("filled", "partial", "rejected", "unknown")


def test_trades_carry_per_fill_fields(tmp_path: Path) -> None:
    """Every replay trade names outcome plus the five per-fill numbers."""
    result = run_once_replay(SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "a.sqlite")
    assert result.trades, "the smoke replay must place at least one order"
    for trade in result.trades:
        assert trade.outcome in OUTCOMES
        assert isinstance(trade.venue_fee_lamports, int)
        assert not isinstance(trade.venue_fee_lamports, bool)
        assert isinstance(trade.network_cost_lamports, int)
        assert not isinstance(trade.network_cost_lamports, bool)
        assert isinstance(trade.price_avg, Decimal)
        assert isinstance(trade.latency_s, Decimal)
        assert isinstance(trade.filled_fraction, Decimal)


def test_filled_trades_carry_positive_numbers(tmp_path: Path) -> None:
    """Fills record a positive price and fraction; fees never go negative."""
    result = run_once_replay(SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "b.sqlite")
    filled = [trade for trade in result.trades if trade.outcome in ("filled", "partial")]
    assert filled, "the smoke replay must fill at least one order"
    for trade in filled:
        assert trade.price_avg > 0
        assert trade.filled_fraction > 0
        assert trade.venue_fee_lamports >= 0
        assert trade.network_cost_lamports >= 0
        assert trade.latency_s >= 0


def test_unfilled_trades_keep_zeroed_money(tmp_path: Path) -> None:
    """Rejected attempts keep zeroed money fields and still name their outcome."""
    trade = ReplayTrade(side="buy", mint="MINT", outcome="rejected", reason="no_reserves")
    assert trade.outcome == "rejected"
    assert trade.venue_fee_lamports == 0
    assert trade.network_cost_lamports == 0
    assert trade.price_avg == Decimal("0")
    assert trade.latency_s == Decimal("0")
    assert trade.filled_fraction == Decimal("0")


def test_fill_detail_matches_trade_types() -> None:
    """The shared FillDetail carries the same field names and value types."""
    trade = ReplayTrade(
        side="buy",
        mint="MINT",
        outcome="filled",
        reason="ok",
        price_avg=Decimal("7"),
        venue_fee_lamports=100,
        network_cost_lamports=9000,
        latency_s=Decimal("1.2"),
        filled_fraction=Decimal("1"),
    )
    detail = FillDetail(
        price_avg=trade.price_avg,
        venue_fee_lamports=trade.venue_fee_lamports,
        network_cost_lamports=trade.network_cost_lamports,
        latency_s=trade.latency_s,
        filled_fraction=trade.filled_fraction,
        outcome=trade.outcome,
    )
    assert detail.price_avg == Decimal("7")
    assert detail.venue_fee_lamports == 100
    assert detail.network_cost_lamports == 9000
    assert detail.latency_s == Decimal("1.2")
    assert detail.filled_fraction == Decimal("1")
    assert detail.outcome == "filled"
