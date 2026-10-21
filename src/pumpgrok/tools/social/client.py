"""Pump.fun read-only enrichment client (TOOL-009 social clause, B14a).

Every read in this module uses ``httpx`` GET and nothing else: there is no
helper with a write-verb name, no alternate HTTP verb call site, and no key
material in URLs or logs (T-03-02-02). The SC4 shell check must print
nothing over this directory while it stays non-empty; the skeleton test
pins both halves. Registered catalog tools never route through here in
Phase 3: market and onchain readers stay RPC-only per B9.
"""

from __future__ import annotations

from decimal import Decimal

import httpx

from pumpgrok.core.errors import DataStale
from pumpgrok.core.tool import UpstreamModel, parse_upstream

VENUE_BASE_URL = "https://frontend-api.pump.fun"

_TRADE_LIMIT_MAX = 200
_HOLDER_LIMIT_MAX = 50


class CoinMeta(UpstreamModel):
    """Untrusted coin row; every field optional, unknown fields ignored."""

    mint: str | None = None
    name: str | None = None
    symbol: str | None = None
    uri: str | None = None
    twitter: str | None = None
    telegram: str | None = None
    website: str | None = None
    creator: str | None = None
    virtual_sol_reserves: Decimal | None = None
    virtual_token_reserves: Decimal | None = None
    complete: bool | None = None


class VenueTrade(UpstreamModel):
    """Untrusted trade row; amounts stay strings until a typed boundary."""

    wallet: str | None = None
    side: str | None = None
    sol_amount: str | None = None
    token_amount: str | None = None
    ts: int | None = None
    tx: str | None = None


class VenueHolder(UpstreamModel):
    """Untrusted holder row."""

    wallet: str | None = None
    share: Decimal | None = None
    amount: str | None = None


async def fetch_coin(
    client: httpx.AsyncClient,
    mint: str,
    *,
    base_url: str = VENUE_BASE_URL,
    timeout_seconds: float = 10.0,
) -> CoinMeta:
    """GET one coin row; typed error when the venue errs or garbles."""
    try:
        resp = await client.get(f"{base_url}/coins/{mint}", timeout=timeout_seconds)
        resp.raise_for_status()
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DataStale(f"social coin row failed mint={mint}") from exc
    return parse_upstream(CoinMeta, body, blind=True)


async def fetch_recent_trades(
    client: httpx.AsyncClient,
    mint: str,
    *,
    limit: int = 200,
    base_url: str = VENUE_BASE_URL,
    timeout_seconds: float = 10.0,
) -> list[VenueTrade]:
    """GET recent trade rows, newest first, bounded to ``limit`` entries."""
    bounded = max(1, min(limit, _TRADE_LIMIT_MAX))
    try:
        resp = await client.get(
            f"{base_url}/trades/all/{mint}", params={"limit": bounded}, timeout=timeout_seconds
        )
        resp.raise_for_status()
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DataStale(f"social trade rows failed mint={mint}") from exc
    rows = body if isinstance(body, list) else body.get("trades", [])
    if not isinstance(rows, list):
        raise DataStale(f"social trade rows malformed mint={mint}")
    return [parse_upstream(VenueTrade, row, blind=True) for row in rows[:bounded]]


async def fetch_top_holders(
    client: httpx.AsyncClient,
    mint: str,
    *,
    limit: int = 50,
    base_url: str = VENUE_BASE_URL,
    timeout_seconds: float = 10.0,
) -> list[VenueHolder]:
    """GET holder rows, largest first, bounded to ``limit`` entries."""
    bounded = max(1, min(limit, _HOLDER_LIMIT_MAX))
    try:
        resp = await client.get(
            f"{base_url}/coins/{mint}/holders",
            params={"limit": bounded},
            timeout=timeout_seconds,
        )
        resp.raise_for_status()
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DataStale(f"social holder rows failed mint={mint}") from exc
    rows = body if isinstance(body, list) else body.get("holders", [])
    if not isinstance(rows, list):
        raise DataStale(f"social holder rows malformed mint={mint}")
    return [parse_upstream(VenueHolder, row, blind=True) for row in rows[:bounded]]
