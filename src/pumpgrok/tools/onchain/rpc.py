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
    retry_if_exception,
    stop_after_attempt,
)

from pumpgrok.core.errors import DataStale
from pumpgrok.core.tool import RetryPolicy
from pumpgrok.replay.clock import Clock
from pumpgrok.replay.rng import make_rng


class RpcError(RuntimeError):
    """Redacted RPC failure: method plus endpoint count, never URLs or keys."""


class _Failover(Exception):
    """Internal: an RPC-level error on this endpoint; try the next one."""


class _BadBody(Exception):
    """Internal: an endpoint returned malformed JSON; try the next one."""


def _retriable_rpc_error(exc: BaseException) -> bool:
    """Retry only timeouts, HTTP 5xx and 429 (catalog section 0).

    4xx (including unknown-method -32601 surfaced as HTTP) and connection
    errors fail over to the next endpoint immediately, without retry delay.
    """
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or 500 <= status <= 599
    return False


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
        retry: RetryPolicy | None = None,
    ) -> None:
        if not endpoints:
            raise RpcError("rpc misconfigured: no endpoints")
        self._endpoints = list(endpoints)
        self._client = client
        self._clock = clock
        self._rng = rng if rng is not None else make_rng()
        self._api_key = api_key if api_key is not None else SecretStr("")
        self._timeout_seconds = timeout_seconds
        if retry is None:
            retry = RetryPolicy(
                attempts=max(1, min(max_attempts_per_endpoint, 10)),
                base_s=0.1,
                max_s=5.0,
            )
        self._retry = retry

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
        try:
            data = resp.json()
        except ValueError as exc:
            raise _BadBody(f"rpc bad body method={method}") from exc
        if isinstance(data, dict) and "error" in data:
            raise RpcError(f"rpc error for method={method}")
        if isinstance(data, dict):
            return data.get("result")
        return data

    async def call(self, method: str, params: list[Any]) -> Any:
        """POST ``method`` to each endpoint in order; first success wins.

        Timeouts, HTTP 5xx and 429 retry per endpoint from the calling tool's
        RetryPolicy (j4/j5/j8); 4xx and connection errors fail over immediately.
        An RPC-level ``error`` fails over immediately; a malformed body fails
        over and becomes :class:`DataStale` when every endpoint is malformed.
        Failures raise :class:`RpcError` with no URL, header, or exception text.
        """
        bad_bodies = 0
        for endpoint in self._endpoints:
            try:
                async for attempt in AsyncRetrying(
                    sleep=self._clock.sleep,
                    wait=_SeededWait(self._rng, base=self._retry.base_s, cap=self._retry.max_s),
                    stop=stop_after_attempt(self._retry.attempts),
                    retry=retry_if_exception(_retriable_rpc_error),
                    reraise=True,
                ):
                    with attempt:
                        try:
                            return await self._post_once(endpoint, method, params)
                        except RpcError as exc:
                            raise _Failover from exc
            except _Failover:
                continue
            except _BadBody:
                bad_bodies += 1
                continue
            except (httpx.HTTPError, RetryError):
                continue
        if bad_bodies == len(self._endpoints):
            raise DataStale(f"rpc bad body method={method} endpoints={len(self._endpoints)}")
        raise RpcError(f"rpc failed method={method} endpoints={len(self._endpoints)}") from None
