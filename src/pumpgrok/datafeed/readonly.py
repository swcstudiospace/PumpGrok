"""Read-only method allowlist gate (MKT-09 first half, T-13-06b).

Every outbound feed call passes through here; anything else is refused by
name before it is sent. No send path is reachable from the feed.

Also provides an injected-transport boundary guarded by fail-closed read-only
methods and endpoint policy.
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import count
from typing import Any, Protocol
from urllib.parse import unquote_plus, urlsplit

from pumpgrok.config.settings import KEY_BEARING_VALUE_RE

ALLOWED_RPC_METHODS = frozenset({"getAccountInfo", "logsSubscribe", "getTransaction"})
ALLOWED_PORTAL_METHODS = frozenset({"subscribeNewToken", "subscribeMigration"})
ALLOWED_METHODS = ALLOWED_RPC_METHODS | ALLOWED_PORTAL_METHODS


class ReadonlyError(ValueError):
    """An outbound method outside the allowlist was attempted."""


def check_method(method: str) -> None:
    """Raise ReadonlyError unless ``method`` is allowlisted."""
    if method not in ALLOWED_METHODS:
        raise ReadonlyError(f"refused non-allowlisted method: {method}")


def guarded_call(method: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Check the method first; only then touch the transport."""
    check_method(method)
    return fn(*args, **kwargs)


_RPC_METHODS = frozenset({"logsSubscribe", "getAccountInfo", "getTransaction"})
_PORTAL_METHODS = frozenset({"subscribeNewToken", "subscribeMigration"})


def _validate_endpoint(endpoint: str) -> None:
    """Apply the TLS and keyless endpoint policy without exposing rejected values."""
    if not isinstance(endpoint, str) or any(char.isspace() for char in endpoint):
        raise ValueError("read-only endpoint is invalid")
    try:
        parts = urlsplit(endpoint)
        valid = (
            parts.scheme.lower() in {"https", "wss"}
            and bool(parts.hostname)
            and parts.username is None
            and parts.password is None
            and parts.port != 0
        )
    except ValueError:
        raise ValueError("read-only endpoint is invalid") from None
    if not valid or bool(parts.query) or KEY_BEARING_VALUE_RE.search(unquote_plus(endpoint)):
        raise ValueError("read-only endpoint is invalid")


class ReadTransport(Protocol):
    async def send(self, url: str, frame: dict[str, object]) -> object: ...


class ReadOnlyBoundary:
    """Allow only the feed's named read methods before invoking an injected transport."""

    def __init__(self, *, endpoint: str, transport: ReadTransport) -> None:
        _validate_endpoint(endpoint)
        self.endpoint = endpoint
        self.transport = transport
        self._request_ids = count(1)

    async def _send(self, frame: dict[str, object]) -> object:
        _validate_endpoint(self.endpoint)
        try:
            return await self.transport.send(self.endpoint, frame)
        except Exception:
            raise RuntimeError("read-only transport failed") from None

    async def rpc(self, method: str, params: list[object]) -> object:
        if method not in _RPC_METHODS:
            raise ValueError("RPC method is not permitted")
        return await self._send(
            {"jsonrpc": "2.0", "id": next(self._request_ids), "method": method, "params": params}
        )

    async def portal(self, method: str) -> object:
        if method not in _PORTAL_METHODS:
            raise ValueError("Portal method is not permitted")
        return await self._send({"method": method})
