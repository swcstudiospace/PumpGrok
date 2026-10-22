"""Regression: ordinary swaps must classify as trades (review finding 21).

A swap moves tokens from the pool's token account to the buyer's account. The
mint's per-account changes therefore net to zero across all accounts; only the
trader's own change (by owner, or by the SOL-matching side) classifies it.
"""

from __future__ import annotations

from pumpgrok.tools.market.trades import parse_trade_tx

MINT = "M" * 44
TRADER = "T" * 44
POOL = "P" * 44
OTHER = "O" * 44


def _balance(index: int, amount: int, owner: str | None) -> dict:
    entry: dict = {"accountIndex": index, "mint": MINT, "uiTokenAmount": {"amount": str(amount)}}
    if owner is not None:
        entry["owner"] = owner
    return entry


def _tx(
    *,
    sol_pre: int,
    sol_post: int,
    pre_tokens: list[dict],
    post_tokens: list[dict],
    keys: list[str],
) -> dict:
    return {
        "blockTime": 1_000,
        "meta": {
            "err": None,
            "preBalances": [sol_pre, 0, 0],
            "postBalances": [sol_post, 0, 0],
            "preTokenBalances": pre_tokens,
            "postTokenBalances": post_tokens,
        },
        "transaction": {"message": {"accountKeys": [{"pubkey": k} for k in keys]}},
    }


def test_buy_with_owner_data_is_classified() -> None:
    # Trader pays SOL and its token account gains 1_000_000; the pool's account loses it.
    tx = _tx(
        sol_pre=100,
        sol_post=90,
        pre_tokens=[_balance(1, 0, TRADER), _balance(2, 9_000_000, POOL)],
        post_tokens=[_balance(1, 1_000_000, TRADER), _balance(2, 8_000_000, POOL)],
        keys=[TRADER, POOL, OTHER],
    )
    trade = parse_trade_tx(MINT, "sig-buy", 0, tx)
    assert trade is not None
    assert trade.side == "buy"
    assert trade.wallet == TRADER
    assert trade.token_units == 1_000_000
    assert trade.sol_lamports == 10


def test_sell_with_owner_data_is_classified() -> None:
    # Trader receives SOL and its token account loses 500_000 to the pool.
    tx = _tx(
        sol_pre=90,
        sol_post=95,
        pre_tokens=[_balance(1, 500_000, TRADER), _balance(2, 1_000_000, POOL)],
        post_tokens=[_balance(1, 0, TRADER), _balance(2, 1_500_000, POOL)],
        keys=[TRADER, POOL],
    )
    trade = parse_trade_tx(MINT, "sig-sell", 0, tx)
    assert trade is not None
    assert trade.side == "sell"
    assert trade.token_units == 500_000
    assert trade.sol_lamports == 5


def test_buy_without_owner_data_is_classified() -> None:
    # No owner field: the trader is the side whose change matches the SOL direction.
    tx = _tx(
        sol_pre=100,
        sol_post=90,
        pre_tokens=[_balance(2, 9_000_000, None)],
        post_tokens=[_balance(1, 1_000_000, None), _balance(2, 8_000_000, None)],
        keys=[TRADER, POOL],
    )
    trade = parse_trade_tx(MINT, "sig-buy-noowner", 0, tx)
    assert trade is not None
    assert trade.side == "buy"
    assert trade.token_units == 1_000_000


def test_pool_only_movement_without_trader_is_not_a_trade() -> None:
    # Tokens move between two other accounts; the fee payer's token balance is unchanged.
    tx = _tx(
        sol_pre=100,
        sol_post=90,
        pre_tokens=[_balance(1, 0, TRADER), _balance(2, 9_000_000, POOL)],
        post_tokens=[_balance(1, 0, TRADER), _balance(2, 8_000_000, POOL)],
        keys=[TRADER, POOL],
    )
    assert parse_trade_tx(MINT, "sig-none", 0, tx) is None
