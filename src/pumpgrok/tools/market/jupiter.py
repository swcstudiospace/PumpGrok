"""Jupiter Swap V2 quote, informational only (STRUCT-002, R44, R38).

``GET`` ``https://api.jup.ag/swap/v2/order`` with no ``taker`` so all routers
compete. Never ``/execute``, ``/build`` or ``/submit``: this module cannot
place an order. The optional ``JUPITER_API_KEY`` is read once in the
composition root (``resolve_api_key``), carried as ``SecretStr`` and sent as
``x-api-key``; the keyless state is logged, never the key (Pitfall 3).

v1 unit trap (Pitfall 2): v1 ``priceImpactPct`` was a decimal ratio while v2
``priceImpact`` is percentage points. This module maps
``price_impact_ratio = priceImpact / 100`` and never reads ``priceImpactPct``.
``inAmount``/``outAmount`` handling follows the hand-authored fixture
(ASSUMED A2): both are mapped defensively with ``.get``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import SecretStr

logger = logging.getLogger(__name__)

QUOTE_URL = "https://api.jup.ag/swap/v2/order"


def resolve_api_key() -> SecretStr:
    """Read ``JUPITER_API_KEY`` once in the composition root (Open Q6).

    This is deliberately not a ``PUMPGROK_`` Settings field: TOML must never
    hold secrets. Empty means keyless.
    """
    return SecretStr(os.environ.get("JUPITER_API_KEY", ""))


async def get_quote(
    input_mint: str,
    output_mint: str,
    amount: int,
    slippage_bps: int,
    client: httpx.AsyncClient,
    *,
    quote_url: str = QUOTE_URL,
    api_key: SecretStr | None = None,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    """Fetch a quote-only order; ``{"ok": False}`` with no raise on failure."""
    key = api_key if api_key is not None else SecretStr("")
    keyless = not key.get_secret_value()
    logger.info("jupiter quote keyless=%s", keyless)
    headers: dict[str, str] = {}
    if not keyless:
        headers["x-api-key"] = key.get_secret_value()
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": str(slippage_bps),
    }
    try:
        resp = await client.get(quote_url, params=params, headers=headers, timeout=timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return {"ok": False, "error": "jupiter quote failed"}

    route = data.get("routePlan") or []
    price_impact = data.get("priceImpact")
    return {
        "ok": True,
        "inputMint": data.get("inputMint"),
        "outputMint": data.get("outputMint"),
        "inAmount": data.get("inAmount"),
        "outAmount": data.get("outAmount"),
        "otherAmountThreshold": data.get("otherAmountThreshold"),
        "slippageBps": data.get("slippageBps"),
        "priceImpactRatio": (float(price_impact) / 100) if price_impact is not None else None,
        "routePlan": [
            {
                "swapInfo": r.get("swapInfo", {}),
                "percent": r.get("percent"),
            }
            for r in route
        ],
        "router": data.get("router"),
        "requestId": data.get("requestId"),
        "raw": data,
    }
