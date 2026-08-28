"""Анализатор: три параллельных запроса, разбор ответов и метрики.

Транспорт замокан, в сеть тесты не ходят.
"""

import time

import httpx
import pytest

from src.analyzer import (
    Analyzer,
    compute_metrics,
    enrich_token,
    parse_holder,
    parse_trade,
)
from src.models import Config, Holder, Token, Trade


@pytest.fixture
def config() -> Config:
    cfg = Config()
    cfg.data.api_key = "data-key"
    cfg.filter.max_risk_score = 7.0
    return cfg


def token(**overrides) -> Token:
    base = {
        "mint": "Mint1",
        "name": "Cat",
        "symbol": "CAT",
        "image_uri": "https://i",
        "creator": "Creator1",
        "created_timestamp": time.time() - 600,
    }
    base.update(overrides)
    return Token(**base)


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))


# --- сеть -----------------------------------------------------------------


async def test_fetch_hits_three_endpoints(config):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/holders"):
            return httpx.Response(200, json=[{"address": "h1", "share": 0.1}])
        if "/trades/all/" in request.url.path:
            return httpx.Response(200, json=[{"user": "w1", "txType": "buy", "solAmount": 0.5}])
        return httpx.Response(200, json={"description": "кот"})

    analyzer = Analyzer(config, client(handler))
    info, holders, trades = await analyzer.fetch("Mint1")
    assert sorted(seen) == ["/coins/Mint1", "/coins/Mint1/holders", "/trades/all/Mint1"]
    assert info["description"] == "кот"
    assert holders[0].address == "h1"
    assert trades[0].wallet == "w1"


async def test_failed_request_degrades_to_empty(config):
    """Провайдер молчит — метрики считаются по тому, что есть, а не падение."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "нет"})

    analyzer = Analyzer(config, client(handler))
    info, holders, trades = await analyzer.fetch("Mint1")
    assert (info, holders, trades) == ({}, [], [])


async def test_analyze_rejects_token_without_trades(config):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[] if request.url.path != "/coins/Mint1" else {})

    analyzer = Analyzer(config, client(handler))
    metrics = await analyzer.analyze(token())
    ok, reason = analyzer.passes(metrics)
    assert not ok and reason == "no_trade_data"


def test_client_outside_context_is_an_error(config):
    with pytest.raises(RuntimeError):
        _ = Analyzer(config).client


# --- разбор ---------------------------------------------------------------


def test_parse_holder_variants():
    assert parse_holder({"address": "a", "amount": 5, "share": 0.2}).share == 0.2
    assert parse_holder({"wallet": "a", "percentage": 25}).share == 0.25
    assert parse_holder({"owner": "a", "balance": 3, "isCreator": True}).is_creator


def test_parse_trade_normalizes_milliseconds():
    trade = parse_trade({"user": "w", "txType": "sell", "solAmount": 1.5,
                         "timestamp": 1_800_000_000_000})
    assert trade.timestamp == 1_800_000_000
    assert not trade.is_buy
    assert trade.sol_amount == 1.5


def test_enrich_fills_only_missing_fields():
    tok = token(description="уже есть")
    enrich_token(tok, {"description": "из сети", "twitter": "https://x.com/c",
                       "virtual_sol_reserves": 30_000_000_000})
    assert tok.description == "уже есть"
    assert tok.twitter == "https://x.com/c"
    assert tok.sol_in_curve == 30.0


# --- метрики --------------------------------------------------------------


def healthy_trades(count: int = 30) -> list[Trade]:
    start = time.time() - 600
    return [
        Trade(wallet=f"w{i}", is_buy=True, sol_amount=0.3 + i * 0.02,
              timestamp=start + i * 20)
        for i in range(count)
    ]


def test_healthy_token_has_low_risk():
    holders = [Holder(address=f"h{i}", share=0.02) for i in range(20)]
    metrics = compute_metrics(token(twitter="t", telegram="tg", website="w",
                                    description="описание длиннее двадцати символов"),
                              holders, healthy_trades())
    assert metrics.risk_score < 7.0
    assert metrics.unique_wallets == 30
    assert metrics.quality > 0.3


def test_creator_holding_half_supply_is_disqualifying():
    holders = [Holder(address="Creator1", share=0.5, is_creator=True)]
    metrics = compute_metrics(token(), holders, healthy_trades())
    assert metrics.creator_share == 0.5
    assert metrics.risk_score == 10.0


def test_concentrated_top5_is_vetoed():
    holders = [Holder(address=f"h{i}", share=0.18) for i in range(5)]
    metrics = compute_metrics(token(), holders, healthy_trades())
    assert metrics.top5_share == pytest.approx(0.9)
    assert metrics.risk_score == 10.0
    assert metrics.quality == 0.0


def test_veto_boundaries():
    """Вето срабатывает ровно на пороге, а на волосок ниже — обычный счёт."""
    at_threshold = compute_metrics(
        token(), [Holder(address="Creator1", share=0.25, is_creator=True)], healthy_trades()
    )
    assert at_threshold.risk_score == 10.0

    below = compute_metrics(
        token(), [Holder(address="Creator1", share=0.24, is_creator=True)], healthy_trades()
    )
    assert below.risk_score < 10.0


def test_veto_ignores_good_metrics():
    """Хорошая кривая и живые соцсети не выкупают создателя на четверти."""
    holders = [Holder(address="Creator1", share=0.4, is_creator=True)]
    metrics = compute_metrics(
        token(twitter="t", telegram="tg", website="w",
              description="описание длиннее двадцати символов"),
        holders, healthy_trades(),
    )
    assert metrics.curve_health > 0.5
    assert metrics.risk_score == 10.0


def test_snipers_counted_in_first_seconds():
    created = time.time() - 600
    trades = [Trade(wallet=f"s{i}", is_buy=True, sol_amount=1.0, timestamp=created + 2)
              for i in range(8)]
    metrics = compute_metrics(token(created_timestamp=created), [], trades)
    assert metrics.sniper_count == 8


def test_single_wallet_kills_diversity():
    trades = [Trade(wallet="one", is_buy=True, sol_amount=1.0, timestamp=time.time())
              for _ in range(10)]
    metrics = compute_metrics(token(), [], trades)
    assert metrics.wallet_diversity == 0.0


def test_thin_data_penalized():
    few = compute_metrics(token(), [], healthy_trades(count=3))
    many = compute_metrics(token(), [], healthy_trades(count=30))
    assert few.risk_score > many.risk_score


def test_socials_lower_risk():
    bare = compute_metrics(token(), [], healthy_trades())
    social = compute_metrics(
        token(twitter="t", telegram="tg", website="w",
              description="описание длиннее двадцати символов"),
        [], healthy_trades(),
    )
    assert social.risk_score < bare.risk_score
