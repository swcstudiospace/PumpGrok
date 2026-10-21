"""Regression: the analyzer reads ``data.request_timeout`` on its fetch path.

``Analyzer.__aenter__`` builds the httpx client from
``DataSettings.request_timeout``. That field was missing from
``DataSettings``, so any analyzer that owned its client raised
``AttributeError`` before the first request. No prior test built the
client without injecting one, so the defect went unseen.

The vendor oracle (``vendor/grokbot-pumpfun/src/models.py``, ``DataConfig``)
defines ``request_timeout: float = 10.0``. These tests pin that default and
check that the configured value reaches the transport layer on the fetch
path. ``tests/conftest.py`` blocks outbound transport methods for every test,
so the fake transport here replaces ``AsyncHTTPTransport.handle_async_request``
and records the timeout httpx attaches to each request.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pumpgrok.config.settings import DataSettings, FilterSettings
from pumpgrok.engine.analyzer import Analyzer

VENDOR_DEFAULT_REQUEST_TIMEOUT = 10.0
MINT = "Mint1"
CARD_PATH = f"/coins/{MINT}"


class _RecordingTransport:
    """Stands in for the network: records each request's timeout and answers 200."""

    def __init__(self) -> None:
        self.timeouts: list[dict[str, Any]] = []
        self.paths: list[str] = []

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.timeouts.append(dict(request.extensions["timeout"]))
        self.paths.append(request.url.path)
        body: Any = {} if request.url.path == CARD_PATH else []
        return httpx.Response(200, json=body, request=request)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _RecordingTransport:
    rec = _RecordingTransport()

    async def _fake(_self: Any, request: httpx.Request) -> httpx.Response:
        return rec.respond(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _fake)
    return rec


async def test_default_request_timeout_matches_vendor_and_is_applied(
    recorder: _RecordingTransport,
) -> None:
    settings = DataSettings()
    assert settings.request_timeout == VENDOR_DEFAULT_REQUEST_TIMEOUT

    async with Analyzer(settings, FilterSettings()) as analyzer:
        assert analyzer.client.timeout == httpx.Timeout(VENDOR_DEFAULT_REQUEST_TIMEOUT)
        info = await analyzer._get(CARD_PATH)

    assert info == {}
    assert analyzer.source_health(CARD_PATH) is True
    assert recorder.timeouts == [
        {
            "connect": VENDOR_DEFAULT_REQUEST_TIMEOUT,
            "read": VENDOR_DEFAULT_REQUEST_TIMEOUT,
            "write": VENDOR_DEFAULT_REQUEST_TIMEOUT,
            "pool": VENDOR_DEFAULT_REQUEST_TIMEOUT,
        }
    ]


async def test_configured_request_timeout_is_applied_to_fetch_path(
    recorder: _RecordingTransport,
) -> None:
    settings = DataSettings(request_timeout=7.5)

    async with Analyzer(settings, FilterSettings()) as analyzer:
        assert analyzer.client.timeout == httpx.Timeout(7.5)
        info, holders, trades = await analyzer.fetch(MINT)

    assert info == {}
    assert holders == []
    assert trades == []
    assert len(recorder.timeouts) == 3
    assert all(t["connect"] == 7.5 and t["read"] == 7.5 for t in recorder.timeouts)
    assert sorted(recorder.paths) == sorted(
        [CARD_PATH, f"/coins/{MINT}/holders", f"/trades/all/{MINT}"]
    )
