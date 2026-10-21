"""Solana JSON-RPC client: one injected httpx client, ordered failover (STRUCT-002).

Tenacity ``AsyncRetrying`` drives retries with ``sleep=clock.sleep`` and a
seeded wait, so replays reproduce every delay from the fixture alone (R27).
Endpoints are keyless URLs only; a paid-provider key travels separately in
``api_key`` and is sent as an ``x-api-key`` header. The header name is
provisional pending provider confirmation (Open Q7); keyless public RPC is
all Phase 2 tests use.

Nothing raised or logged here carries an endpoint URL, a header value, or
``str(exc)`` from httpx: errors name the method and the endpoint count only
(T-02-01, T-02-02).
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any

import httpx
from pydantic import SecretStr
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
)

from pumpgrok.replay.clock import Clock
from pumpgrok.replay.rng import make_rng


class RpcError(RuntimeError):
    """Redacted RPC failure: method plus endpoint count, never URLs or keys."""


class _Failover(Exception):
    """Internal: an RPC-level error on this endpoint; try the next one."""


class _SeededWait:
    """Exponential backoff with seeded jitter (never global ``random``).

    Tenacity ``wait_random_exponential`` draws from the global ``random``
    module, which breaks replay determinism (R27). This wait draws from the
    injected ``random.Random`` instead. Tenacity calls it with one
    ``RetryCallState`` argument and uses the returned float as seconds.
    """

    def __init__(
        self, rng: random.Random, base: float = 0.1, factor: float = 2.0, cap: float = 5.0
    ) -> None:
        self._rng = rng
        self._base = base
        self._factor = factor
        self._cap = cap

    def __call__(self, retry_state: Any) -> float:
        attempt = max(int(getattr(retry_state, "attempt_number", 1)), 1)
        ceiling = min(self._base * (self._factor ** (attempt - 1)), self._cap)
        return ceiling + self._rng.uniform(0, ceiling)


class RpcClient:
    """Ordered-failover JSON-RPC over an injected httpx client."""

    def __init__(
        self,
        endpoints: Sequence[str],
        client: httpx.AsyncClient,
        clock: Clock,
        rng: random.Random | None = None,
        *,
        api_key: SecretStr | None = None,
        timeout_seconds: float = 15.0,
        max_attempts_per_endpoint: int = 3,
    ) -> None:
        if not endpoints:
            raise RpcError("rpc misconfigured: no endpoints")
        self._endpoints = list(endpoints)
        self._client = client
        self._clock = clock
        self._rng = rng if rng is not None else make_rng()
        self._api_key = api_key if api_key is not None else SecretStr("")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max(1, max_attempts_per_endpoint)

    @property
    def endpoint_count(self) -> int:
        return len(self._endpoints)

    def _headers(self) -> dict[str, str]:
        key = self._api_key.get_secret_value()
        if key:
            return {"x-api-key": key}
        return {}

    async def _post_once(self, endpoint: str, method: str, params: list[Any]) -> Any:
        resp = await self._client.post(
            endpoint,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            headers=self._headers(),
            timeout=self._timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "error" in data:
            raise RpcError(f"rpc error for method={method}")
        if isinstance(data, dict):
            return data.get("result")
        return data

    async def call(self, method: str, params: list[Any]) -> Any:
        """POST ``method`` to each endpoint in order; first success wins.

        Transport failures retry per endpoint (tenacity, injected clock);
        an RPC-level ``error`` fails over to the next endpoint immediately.
        Raises :class:`RpcError` with no URL, header, or exception text.
        """
        for endpoint in self._endpoints:
            try:
                async for attempt in AsyncRetrying(
                    sleep=self._clock.sleep,
                    wait=_SeededWait(self._rng),
                    stop=stop_after_attempt(self._max_attempts),
                    retry=retry_if_exception_type(httpx.HTTPError),
                    reraise=True,
                ):
                    with attempt:
                        try:
                            return await self._post_once(endpoint, method, params)
                        except RpcError as exc:
                            raise _Failover from exc
            except _Failover:
                continue
            except (httpx.HTTPError, RetryError):
                continue
        raise RpcError(f"rpc failed method={method} endpoints={len(self._endpoints)}") from None
