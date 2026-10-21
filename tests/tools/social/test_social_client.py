"""Social GET-only client over fixtures (Phase 3 plan 03-02, task 4).

Pins read-only venue enrichment: GET transport only, unknown fields
ignored, malformed rows typed. MockTransport only; no live network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import httpx

from pumpgrok.core.errors import DataStale
from pumpgrok.tools.social.client import (
    fetch_coin,
    fetch_recent_trades,
    fetch_top_holders,
)

MINT = "So11111111111111111111111111111111111111112"


def _client(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport)


async def test_fetch_coin_ignores_unknown_fields() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        assert request.url.path == f"/coins/{MINT}"
        return httpx.Response(
            200,
            json={
                "mint": MINT,
                "name": "Test",
                "symbol": "TST",
                "venue_noise": {"nested": [1, 2]},
                "complete": False,
            },
        )

    coin = await fetch_coin(_client(handler), MINT)
    assert seen["method"] == "GET"
    assert coin.name == "Test"
    assert coin.symbol == "TST"
    assert coin.creator is None


async def test_fetch_recent_trades_bounds_and_parses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "trades": [
                    {"wallet": "W1", "side": "buy", "sol_amount": "10", "extra": True},
                    {"wallet": "W2", "side": "sell", "sol_amount": "5"},
                ]
            },
        )

    trades = await fetch_recent_trades(_client(handler), MINT, limit=1)
    assert len(trades) == 1
    assert trades[0].wallet == "W1"


async def test_fetch_top_holders_bounds_and_parses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(
            200, json=[{"wallet": "W1", "share": "0.5"}, {"wallet": "W2", "share": "0.3"}]
        )

    holders = await fetch_top_holders(_client(handler), MINT, limit=10)
    assert [h.wallet for h in holders] == ["W1", "W2"]


async def test_venue_errors_become_typed() -> None:
    def http_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "bad"})

    with pytest.raises(DataStale):
        await fetch_coin(_client(http_error), MINT)

    def garbled(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\xff\xfe not json")

    with pytest.raises(DataStale):
        await fetch_recent_trades(_client(garbled), MINT)

    def shape_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"holders": {"not": "a list"}})

    with pytest.raises(DataStale):
        await fetch_top_holders(_client(shape_error), MINT)


def test_client_module_uses_get_only() -> None:
    import ast

    path = Path(__file__).resolve().parents[3] / "src" / "pumpgrok" / "tools" / "social" / "client.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("post", "put", "patch", "delete"):
            raise AssertionError(f"write-verb call site: {node.attr}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (
            "post",
            "put",
            "patch",
            "delete",
        ):
            raise AssertionError(f"write-verb helper: {node.name}")
    assert "client.get(" in path.read_text(encoding="utf-8")
