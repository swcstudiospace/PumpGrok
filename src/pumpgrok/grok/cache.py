"""Canonical cache with per-agent TTLs (GRK-03, T-14-01-02).

The cache key payload is an explicit dict of ints/strings only; a float leaf
raises TypeError. Fallback results are never stored (callers pass the flag,
and `set` refuses them).
"""

from __future__ import annotations

import hashlib
from typing import Any

from pumpgrok.core.idempotency import canonical_json
from pumpgrok.replay.clock import Clock

AGENT_TTL_S: dict[str, float] = {
    "chief": 60.0,
    "scout": 30.0,
    "risk": 30.0,
    "whale": 30.0,
    "signal": 15.0,
}
DEFAULT_TTL_S = 30.0


def build_cache_key_payload(
    *, agent: str, model: str, prompt_hash: str, consequence_id: str
) -> dict[str, Any]:
    """The explicit key payload. Ints and strings only, by construction."""
    payload: dict[str, Any] = {
        "agent": agent,
        "model": model,
        "prompt_hash": prompt_hash,
        "consequence_id": consequence_id,
        "version": 1,
    }
    _assert_int_str(payload)
    return payload


def _assert_int_str(payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            raise TypeError(f"cache key field {key!r} must be int or str, got {type(value).__name__}")


def canonical_request_hash(payload: dict[str, Any]) -> str:
    """sha256 of the canonical payload. Float leaves raise TypeError."""
    for value in payload.values():
        if isinstance(value, float):
            raise TypeError("cache key payload must be ints/strings only, float found")
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


class Cache:
    def __init__(self, *, clock: Clock) -> None:
        self._clock = clock
        self._entries: dict[str, tuple[float, str]] = {}

    def get(self, key: str, agent: str) -> str | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock.now() >= expires_at:
            del self._entries[key]
            return None
        _ = agent
        return value

    def set(self, key: str, value: str, agent: str, *, is_fallback: bool = False) -> None:
        if is_fallback:
            return
        ttl = AGENT_TTL_S.get(agent, DEFAULT_TTL_S)
        self._entries[key] = (self._clock.now() + ttl, value)

    def __len__(self) -> int:
        return len(self._entries)
