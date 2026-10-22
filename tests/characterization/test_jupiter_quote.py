"""Characterization: Jupiter Swap V2 quote (STRUCT-002, R44).

Pins ``tools/market/jupiter.py`` against the retired ``jupiter_quote``
root oracle (kept byte-identical per R53).

Divergences from the oracle (deliberate, per R54 and 02-RESEARCH.md Pitfall 1):
the port targets ``https://api.jup.ag/swap/v2/order`` (the oracle pins the
retired ``lite-api.jup.ag/swap/v1/quote``), sends no ``taker`` (all routers
compete), maps ``price_impact_ratio = priceImpact / 100`` and never reads the
v1 ``priceImpactPct`` decimal ratio, and takes an injected ``httpx`` client
instead of monkeypatched ``requests.get``. The quote is informational only
(R38): this module cannot execute, build or submit.

Ports 3 root unittest cases (R55): ``test_quote_url_is_current_lite_swap_api``,
``test_get_quote_calls_configured_url`` and ``test_main_exits_nonzero_when_quote_fails``
(root-oracle classes retired in 05-08). The
ported module exposes no ``main()`` (CLI verbs land in a later plan), so the
non-zero-exit contract is pinned via its exact predicate: an ``ok: False``
result.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

from pumpgrok.tools.market.jupiter import QUOTE_URL, get_quote, resolve_api_key

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "http"


def _body(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["http"]


@pytest.mark.characterization
def test_quote_url_is_swap_v2_order() -> None:
    assert QUOTE_URL == "https://api.jup.ag/swap/v2/order"
    assert "lite-api" not in QUOTE_URL
    for banned in ("/execute", "/build", "/submit"):
        assert banned not in QUOTE_URL


@pytest.mark.characterization
async def test_get_quote_calls_configured_url_without_taker() -> None:
    seen: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["params"] = dict(request.url.params)
        assert request.headers.get("x-api-key") is None
        return httpx.Response(200, json=_body("jupiter_order.json"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await get_quote("A", "B", 1, 50, client)
    assert result["ok"] is True
    assert seen["url"].split("?")[0] == "https://api.jup.ag/swap/v2/order"
    assert "taker" not in seen["params"]
    assert result["outAmount"] == "500000000"
    assert result["inAmount"] == "1000000000"
    # v2 priceImpact (percentage points) mapped to a ratio; v1 field never read.
    assert result["priceImpactRatio"] == pytest.approx(0.005)
    assert "priceImpactPct" not in result


@pytest.mark.characterization
async def test_quote_failure_is_ok_false(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Root case port: ok False is the exact predicate main() exits non-zero on."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "dns"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with caplog.at_level(logging.INFO, logger="pumpgrok.tools.market.jupiter"):
        result = await get_quote("A", "B", 1, 50, client)
    assert result["ok"] is False
    assert any("keyless=True" in record.message for record in caplog.records)


@pytest.mark.characterization
async def test_quote_sends_key_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JUPITER_API_KEY", "test-key")
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers.get("x-api-key")
        return httpx.Response(200, json=_body("jupiter_order.json"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await get_quote("A", "B", 1, 50, client, api_key=resolve_api_key())
    assert result["ok"] is True
    assert seen["key"] == "test-key"
