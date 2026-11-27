"""Characterization: REST analyzer, parsing, and metrics (STRUCT-003).

Pins ``engine/analyzer.py`` against
``vendor/grokbot-pumpfun/tests/test_analyzer.py`` (vendor oracle, kept
byte-identical per R53).

Divergences from the oracle (deliberate):

- No ``Bearer`` header is sent: no settings field carries a pump.fun key,
  so there is nothing to attach.
- Every ``_get`` records a per-source health flag in ``Analyzer.health``;
  a failed provider raises ``DataStale`` plus ``False`` health, never a
  stand-in value (R47).
- ``_veto_reason`` returns ASCII codes (``creator_share_veto``,
  ``top5_share_veto``), not Russian sentences.
- Time is fixed: the token factory uses an explicit ``NOW`` instead of
  ``time.time()``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from pumpgrok.config.settings import DataSettings, FilterSettings
from pumpgrok.core.errors import DataStale
from pumpgrok.engine.analyzer import (
    Analyzer,
    _veto_reason,
    compute_metrics,
    enrich_token,
    parse_holder,
    parse_trade,
)
from pumpgrok.engine.models import Holder, Token, TokenMetrics, Trade

NOW = 1_700_000_000.0

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "http"


def _body(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["http"]


@pytest.fixture
def analyzer_parts() -> tuple[DataSettings, FilterSettings]:
    return DataSettings(), FilterSettings(max_risk_score=7.0)


def token(**overrides: Any) -> Token:
    base: dict[str, Any] = {
        "mint": "Mint1",
        "name": "Cat",
        "symbol": "CAT",
        "image_uri": "https://i",
        "creator": "Creator1",
        "created_timestamp": NOW - 600,
    }
    base.update(overrides)
    return Token(**base)


def client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))


# --- network -----------------------------------------------------------------


async def test_fetch_hits_three_endpoints(analyzer_parts: tuple) -> None:
    data, filter_cfg = analyzer_parts
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        assert "authorization" not in {k.lower() for k in request.headers}
        if request.url.path.endswith("/holders"):
            return httpx.Response(200, json=_body("pumpfun_holder.json"))
        if "/trades/all/" in request.url.path:
            return httpx.Response(200, json=[{"user": "w1", "txType": "buy", "solAmount": 0.5}])
        return httpx.Response(200, json={"description": "plain card"})

    analyzer = Analyzer(data, filter_cfg, client(handler))
    async with analyzer:
        info, holders, trades = await analyzer.fetch("Mint1")
    assert sorted(seen) == ["/coins/Mint1", "/coins/Mint1/holders", "/trades/all/Mint1"]
    assert info["description"] == "plain card"
    assert holders[0].is_creator
    assert holders[1].share == pytest.approx(0.18)
    assert trades[0].wallet == "w1"
    assert analyzer.source_health("/coins/Mint1") is True
    assert analyzer.source_health("/coins/Mint1/holders") is True


async def test_failed_request_raises_stale_not_empty(analyzer_parts: tuple) -> None:
    """The provider is down: that is stale data, never an empty card and empty lists."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "no"})

    data, filter_cfg = analyzer_parts
    analyzer = Analyzer(data, filter_cfg, client(handler))
    async with analyzer:
        with pytest.raises(DataStale):
            await analyzer.fetch("Mint1")
    assert analyzer.source_health("/coins/Mint1") is False


def _transport_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _html_body(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"<html>maintenance</html>", request=request)


def _null_card(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/coins/Mint1":
        return httpx.Response(200, content=b"null", request=request)
    return httpx.Response(200, json=[], request=request)


def _object_for_list(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/coins/Mint1":
        return httpx.Response(200, json={}, request=request)
    return httpx.Response(200, json={"error": "rate limited"}, request=request)


@pytest.mark.parametrize(
    "handler",
    [_transport_error, _html_body, _null_card, _object_for_list],
    ids=["transport_error", "non_json_body", "null_card", "object_for_list"],
)
async def test_failed_fetch_never_yields_a_clean_analysis(
    analyzer_parts: tuple, handler: Any
) -> None:
    data, filter_cfg = analyzer_parts
    analyzer = Analyzer(data, filter_cfg, client(handler))
    async with analyzer:
        with pytest.raises(DataStale):
            await analyzer.analyze(token())


async def test_healthy_empty_answer_is_not_stale(analyzer_parts: tuple) -> None:
    """A provider that answers with nothing is a healthy empty answer, not a failure."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={} if request.url.path == "/coins/Mint1" else [])

    data, filter_cfg = analyzer_parts
    analyzer = Analyzer(data, filter_cfg, client(handler))
    async with analyzer:
        metrics = await analyzer.analyze(token())
    assert metrics.trade_count == 0
    assert analyzer.passes(metrics) == (False, "no_trade_data")
    assert analyzer.source_health("/trades/all/Mint1") is True


async def test_successful_fetch_yields_unchanged_analysis(analyzer_parts: tuple) -> None:
    """Success path regression: these metrics are the values recorded before the fix."""
    data, filter_cfg = analyzer_parts
    card = {
        "description": "a cat coin",
        "twitter": "https://x.com/cat",
        "telegram": "https://t.me/cat",
    }
    holders = [{"owner": f"h{i}", "percentage": 3 + (i % 3)} for i in range(15)]
    trades = [
        {
            "user": f"w{i % 7}",
            "txType": "sell" if i % 4 == 0 else "buy",
            "solAmount": 0.1 + (i % 5) * 0.05,
            "timestamp": NOW - 600 + i * 10,
        }
        for i in range(40)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/holders"):
            return httpx.Response(200, json=holders)
        if "/trades/all/" in path:
            return httpx.Response(200, json=trades)
        return httpx.Response(200, json=card)

    tok = token()
    analyzer = Analyzer(data, filter_cfg, client(handler))
    async with analyzer:
        metrics = await analyzer.analyze(tok)
        verdict = analyzer.passes(metrics)

    assert metrics.model_dump() == {
        "buy_sell_ratio": 3.0,
        "creator_share": 0.0,
        "curve_health": 0.7815,
        "risk_score": 2.77,
        "sniper_count": 1,
        "social_signals": 0.7,
        "top5_share": 0.25,
        "trade_count": 40,
        "unique_wallets": 7,
        "wallet_diversity": 0.1925,
    }
    assert verdict == (True, "ok")
    assert (tok.description, tok.twitter, tok.telegram) == (
        "a cat coin",
        "https://x.com/cat",
        "https://t.me/cat",
    )


async def test_analyze_rejects_token_without_trades(analyzer_parts: tuple) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[] if request.url.path != "/coins/Mint1" else {})

    data, filter_cfg = analyzer_parts
    analyzer = Analyzer(data, filter_cfg, client(handler))
    async with analyzer:
        metrics = await analyzer.analyze(token())
    ok, reason = analyzer.passes(metrics)
    assert not ok and reason == "no_trade_data"


async def test_risky_token_rejected_by_score(analyzer_parts: tuple) -> None:
    data, filter_cfg = analyzer_parts
    analyzer = Analyzer(data, filter_cfg, client(lambda request: httpx.Response(200, json=[])))

    ok, _ = analyzer.passes(TokenMetrics(risk_score=6.9, trade_count=30))
    assert ok
    ok, reason = analyzer.passes(TokenMetrics(risk_score=7.1, trade_count=30))
    assert not ok and reason == "risk_score_too_high"


def test_client_outside_context_is_an_error(analyzer_parts: tuple) -> None:
    data, filter_cfg = analyzer_parts
    with pytest.raises(RuntimeError):
        _ = Analyzer(data, filter_cfg).client


# --- parsing -----------------------------------------------------------------


def test_parse_holder_variants() -> None:
    assert parse_holder({"address": "a", "amount": 5, "share": 0.2}).share == 0.2
    assert parse_holder({"wallet": "a", "percentage": 25}).share == 0.25
    assert parse_holder({"owner": "a", "balance": 3, "isCreator": True}).is_creator


def test_parse_holder_fixture_shapes() -> None:
    holders = [parse_holder(h) for h in _body("pumpfun_holder.json")]
    assert holders[0].is_creator and holders[0].share == pytest.approx(0.25)
    assert holders[1].share == pytest.approx(0.18)
    assert all(h.address for h in holders)


def test_parse_trade_normalizes_milliseconds() -> None:
    trade = parse_trade(
        {
            "user": "w",
            "txType": "sell",
            "solAmount": 1.5,
            "timestamp": (NOW - 10) * 1000,
        }
    )
    assert trade.timestamp == pytest.approx(NOW - 10)
    assert not trade.is_buy
    assert trade.sol_amount == 1_500_000_000


def test_enrich_fills_only_missing_fields() -> None:
    tok = token(description="already here")
    enrich_token(
        tok,
        {"description": "card", "twitter": "t", "virtual_sol_reserves": 30_000_000_000},
    )
    assert tok.description == "already here"
    assert tok.twitter == "t"
    assert tok.sol_in_curve == 30_000_000_000


# --- metrics -----------------------------------------------------------------


def healthy_trades(count: int = 30) -> list[Trade]:
    start = NOW - 600
    return [
        Trade(
            wallet=f"w{i % 20}",
            is_buy=True,
            sol_amount=500_000_000 + (i % 7) * 50_000_000,
            timestamp=start + i * 10.0,
        )
        for i in range(count)
    ]


def test_healthy_token_has_low_risk() -> None:
    holders = [Holder(address=f"h{i}", share=0.02) for i in range(20)]
    metrics = compute_metrics(
        token(twitter="t", telegram="tg", website="w", description="long enough here"),
        holders,
        healthy_trades(),
    )
    assert metrics.risk_score < 7.0
    assert metrics.quality > 0.3


def test_creator_holding_half_supply_is_disqualifying() -> None:
    holders = [Holder(address="Creator1", share=0.5, is_creator=True)]
    metrics = compute_metrics(token(), holders, healthy_trades())
    assert metrics.risk_score == 10.0


def test_concentrated_top5_is_vetoed() -> None:
    holders = [Holder(address=f"h{i}", share=0.18) for i in range(5)]
    metrics = compute_metrics(token(), holders, healthy_trades())
    assert metrics.risk_score == 10.0
    assert metrics.quality == 0.0


def test_veto_boundaries() -> None:
    just_over = compute_metrics(
        token(), [Holder(address="c", share=0.25, is_creator=True)], healthy_trades()
    )
    assert just_over.risk_score == 10.0
    below = compute_metrics(
        token(), [Holder(address="c", share=0.249, is_creator=True)], healthy_trades()
    )
    assert below.risk_score < 10.0


def test_veto_codes_are_ascii() -> None:
    assert _veto_reason(0.30, 0.0) == "creator_share_veto"
    assert _veto_reason(0.0, 0.85) == "top5_share_veto"
    assert _veto_reason(0.0, 0.0) is None


def test_veto_ignores_good_metrics() -> None:
    """A good curve and live socials do not buy out a quarter-held supply."""
    holders = [Holder(address="Creator1", share=0.25, is_creator=True)]
    metrics = compute_metrics(
        token(twitter="t", telegram="tg", website="w", description="long enough here"),
        holders,
        healthy_trades(),
    )
    assert metrics.risk_score == 10.0


def test_snipers_counted_in_first_seconds() -> None:
    created = NOW - 600
    buys = [
        Trade(wallet=f"s{i}", is_buy=True, sol_amount=1_000_000_000, timestamp=created + 5.0)
        for i in range(8)
    ]
    buys += [Trade(wallet="late", is_buy=True, sol_amount=1_000_000_000, timestamp=created + 500.0)]
    metrics = compute_metrics(token(created_timestamp=created), [], buys)
    assert metrics.sniper_count == 8


def test_single_wallet_kills_diversity() -> None:
    trades = [
        Trade(wallet="one", is_buy=True, sol_amount=1_000_000_000, timestamp=NOW - i)
        for i in range(5)
    ]
    metrics = compute_metrics(token(), [], trades)
    assert metrics.wallet_diversity == 0.0


def test_thin_data_penalized() -> None:
    few = compute_metrics(token(), [], healthy_trades(count=3))
    many = compute_metrics(token(), [], healthy_trades(count=30))
    assert few.risk_score > many.risk_score


def test_socials_lower_risk() -> None:
    bare = compute_metrics(token(), [], healthy_trades())
    social = compute_metrics(
        token(
            twitter="t",
            telegram="tg",
            website="w",
            description="a description longer than twenty chars",
        ),
        [],
        healthy_trades(),
    )
    assert social.risk_score < bare.risk_score
