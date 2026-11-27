"""Sidecar response cache and canonical key for Grok admission (GRK-02; Design A section 4).

The key is ``canonical_request_hash`` over an explicit payload. The payload
holds only ints and strings: a Decimal is stringified, and any other leaf is
refused. A field name that ``canonical_request_hash`` would silently drop is
refused too, so two different inputs can never share a key.

Successful responses keep the per-agent TTL. Transport errors are negative
entries for 30 s, so a failing upstream is not retried in a storm. Fallbacks
are never written here; the gateway enforces that.
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.replay.clock import Clock
from pumpgrok.replay.recorder import _VOLATILE_RE
from pumpgrok.replay.recorder import canonical_request_hash as _recorder_hash

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
            raise TypeError(
                f"cache key field {key!r} must be int or str, got {type(value).__name__}"
            )


def canonical_request_hash(payload: dict[str, Any]) -> str:
    """sha256 of the canonical payload. Float leaves raise TypeError.

    Float leaves are refused here; validated payloads hash exactly like the
    replay recorder's canonical request hash.
    """
    for value in payload.values():
        if isinstance(value, float):
            raise TypeError("cache key payload must be ints/strings only, float found")
    return _recorder_hash(payload)


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


TTL_S_BY_AGENT: Mapping[str, int] = {
    "narrative": 86400,
    "auditor": 300,
    "timing": 900,
    "checker": 60,
}
NEGATIVE_TTL_S = 30
MAX_ROWS = 5000

KEY_KIND = "event"

_BUSY_TIMEOUT_S = 5.0

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS grok_cache ("
    " key TEXT PRIMARY KEY,"
    " agent TEXT NOT NULL,"
    " status TEXT NOT NULL,"
    " response TEXT,"
    " expires_at REAL NOT NULL,"
    " seq INTEGER NOT NULL)"
)


class CacheUnavailable(PumpgrokError):
    """The sidecar cache could not be read or written."""

    code = "grok_cache_unavailable"


@dataclass(frozen=True)
class CachedResult:
    """A live cache row: ``status`` is ``ok`` (with response) or ``error`` (negative)."""

    status: str
    response: str | None


def scalar_fields(fields: Mapping[str, object]) -> dict[str, int | str]:
    """Reduce an input mapping to the reviewed scalar payload; refuse anything else."""
    payload: dict[str, int | str] = {}
    for name, value in fields.items():
        if not isinstance(name, str) or not name:
            raise TypeError("input field names must be non-empty strings")
        if _VOLATILE_RE.search(name):
            raise ValueError(f"input field {name!r} would be stripped from the key")
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError(f"input field {name!r} is a non-finite Decimal")
            payload[name] = str(value)
        elif isinstance(value, bool) or not isinstance(value, (int, str)):
            raise TypeError(
                f"input field {name!r} must be int, str or Decimal, got {type(value).__name__}"
            )
        else:
            payload[name] = value
    return payload


def cache_key(
    *,
    agent: str,
    model: str,
    prompt_sha: str,
    schema: str,
    sanitizer_version: str,
    fields: Mapping[str, object],
) -> str:
    """sha256 over the canonical admission payload (replay hash function)."""
    return canonical_request_hash(
        {
            "kind": KEY_KIND,
            "agent": agent,
            "model": model,
            "prompt_sha": prompt_sha,
            "schema": schema,
            "sanitizer_version": sanitizer_version,
            "input": scalar_fields(fields),
        }
    )


class ResponseCache:
    """Sidecar SQLite cache with TTL expiry and a least-recently-used row cap."""

    def __init__(self, path: str | Path, clock: Clock, *, max_rows: int = MAX_ROWS) -> None:
        self._path = Path(path)
        self._clock = clock
        self._max_rows = max_rows
        self._open().close()

    def _open(self) -> sqlite3.Connection:
        try:
            con = sqlite3.connect(self._path, timeout=_BUSY_TIMEOUT_S, isolation_level=None)
            con.execute(_SCHEMA)
        except sqlite3.Error as exc:
            raise CacheUnavailable(f"grok cache store unavailable: {exc}") from exc
        return con

    def get(self, key: str) -> CachedResult | None:
        """The live entry for ``key``, or None. Touching an entry makes it most recent."""
        now = self._clock.now()
        con = self._open()
        try:
            row = con.execute(
                "SELECT status, response, expires_at FROM grok_cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            if row[2] <= now:
                con.execute("DELETE FROM grok_cache WHERE key = ?", (key,))
                return None
            con.execute(
                "UPDATE grok_cache SET seq = (SELECT COALESCE(MAX(seq), 0) + 1 FROM grok_cache)"
                " WHERE key = ?",
                (key,),
            )
            return CachedResult(status=row[0], response=row[1])
        except sqlite3.Error as exc:
            raise CacheUnavailable(f"grok cache read failed: {exc}") from exc
        finally:
            con.close()

    def put_ok(self, key: str, *, agent: str, response: str) -> None:
        """Store a successful response for the agent's TTL."""
        self._put(key, agent=agent, status="ok", response=response, ttl_s=_ttl(agent))

    def put_error(self, key: str, *, agent: str) -> None:
        """Store a transport-error negative entry for ``NEGATIVE_TTL_S``."""
        self._put(key, agent=agent, status="error", response=None, ttl_s=NEGATIVE_TTL_S)

    def _put(self, key: str, *, agent: str, status: str, response: str | None, ttl_s: int) -> None:
        now = self._clock.now()
        con = self._open()
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM grok_cache WHERE expires_at <= ?", (now,))
            con.execute(
                "INSERT OR REPLACE INTO grok_cache (key, agent, status, response, expires_at, seq)"
                " VALUES (?, ?, ?, ?, ?,"
                " (SELECT COALESCE(MAX(seq), 0) + 1 FROM grok_cache))",
                (key, agent, status, response, now + ttl_s),
            )
            excess = _count(con) - self._max_rows
            if excess > 0:
                con.execute(
                    "DELETE FROM grok_cache WHERE key IN"
                    " (SELECT key FROM grok_cache ORDER BY seq ASC LIMIT ?)",
                    (excess,),
                )
            con.execute("COMMIT")
        except sqlite3.Error as exc:
            _rollback_quietly(con)
            raise CacheUnavailable(f"grok cache write failed: {exc}") from exc
        finally:
            con.close()

    def count(self) -> int:
        """Rows currently held, expired ones included until the next write."""
        con = self._open()
        try:
            return _count(con)
        except sqlite3.Error as exc:
            raise CacheUnavailable(f"grok cache read failed: {exc}") from exc
        finally:
            con.close()


def _ttl(agent: str) -> int:
    try:
        return TTL_S_BY_AGENT[agent]
    except KeyError as exc:
        raise ValueError(f"no cache TTL for agent {agent!r}") from exc


def _count(con: sqlite3.Connection) -> int:
    row = con.execute("SELECT COUNT(*) FROM grok_cache").fetchone()
    return int(row[0])


def _rollback_quietly(con: sqlite3.Connection) -> None:
    with contextlib.suppress(sqlite3.Error):
        con.execute("ROLLBACK")
