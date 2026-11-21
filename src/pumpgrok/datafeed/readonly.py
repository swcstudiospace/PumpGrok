"""Read-only method allowlist gate (MKT-09 first half, T-13-06b).

Every outbound feed call passes through here; anything else is refused by
name before it is sent. No send path is reachable from the feed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
